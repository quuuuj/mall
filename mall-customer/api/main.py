"""
FastAPI入口 — 提供REST API + SSE流式响应
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agent.graph import build_graph
from agent.limits import ReplyTokenLimiter
from agent.streaming import ANSWER_STREAM_TAG
from agent.compliance_checker import StreamingRuleGuard
from api import sse
from api.sse import encode_done, encode_error
from api.knowledge_admin import KnowledgeAdminService
from retrieval.hybrid import HybridRetriever
from retrieval.rerank import RerankClient
from storage.embeddings import embed_query
from storage.qdrant_store import QdrantStore
from memory.working_memory import WorkingMemory
from memory.short_term_memory import ShortTermMemory
from tools.mcp_client import McpBackendClient
from tracing.otel_config import init_tracer

load_dotenv()

logger = logging.getLogger(__name__)

INTERNAL_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
_bearer = HTTPBearer(auto_error=False)


def require_internal_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """服务间调用鉴权 — 只在内部服务之间使用，不对公网。"""
    if not INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail="服务间鉴权未配置")
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少鉴权凭据")
    if not secrets.compare_digest(credentials.credentials, INTERNAL_TOKEN):
        raise HTTPException(status_code=403, detail="鉴权凭据无效")


working_memory = WorkingMemory()
short_term_memory = ShortTermMemory()
graph = None
knowledge_admin: KnowledgeAdminService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global graph, knowledge_admin

    init_tracer(
        service_name=os.getenv("OTEL_SERVICE_NAME", "smart-cs-multi-agent"),
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )

    # 对话状态持久化（Redis Checkpointer），Redis 不可用时降级为进程内 MemorySaver
    await short_term_memory.setup()

    # 知识库检索器：Qdrant 混合检索（FAQ 前置 + RAG 三段判定）
    retriever = HybridRetriever(QdrantStore(), RerankClient(), embed_query)
    # 知识库后台服务与在线检索共用同一套组件
    knowledge_admin = KnowledgeAdminService(retriever=retriever)

    graph = build_graph(
        working_memory=working_memory,
        retriever=retriever,
        mcp_client=McpBackendClient(),
        checkpointer=short_term_memory.checkpointer,
    )

    yield

    await short_term_memory.aclose()


app = FastAPI(
    title="智能客服多Agent系统",
    description="基于LangGraph的Supervisor编排多Agent智能客服系统",
    version="1.0.0",
    lifespan=lifespan,
)

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3001,http://localhost:3002").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    session_id: str | None = None


def _final_reply(output: Any) -> str:
    """从图输出里取末尾 AIMessage 的文本；取不到返回空串。"""
    from langchain_core.messages import AIMessage

    if not isinstance(output, dict):
        return ""
    messages = output.get("messages") or []
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and isinstance(last.content, str):
        return last.content
    return ""


def _compliance_failed(output: Any) -> bool:
    return isinstance(output, dict) and output.get("compliance_passed") is False


async def stream_reply(graph_chain: Any, initial_state: dict, config: dict) -> AsyncIterator[str]:
    """把图执行过程转成 SSE 帧：模型产出即帧发出，末尾补 done。

    - 只有带 answer_stream 标签的 on_chat_model_stream 才转 token，
      意图判断、查询改写、合规审查等内部调用的中间产出不会漏给用户
    - 模板话术（工单回复、空召回引导）没有模型流，流结束后整段按块补发
    - 规则层在每块发出前守门，禁词被分块切开也能拦住
    - 出口合规判不通过时，草稿已在流中发出无法收回，补发收尾节点的固定话术，
      让用户知道自己拿到的不是最终答复
    - 工单卡片（ticket）与登录引导（login_required）在文本之后发，避免用户先看到卡片后看到说明
    - 单次回复超过 MAX_REPLY_TOKENS 时边发边计数，超限后停止输出并补一句说明，
      不发 error 帧：用户已经拿到的部分内容是有效回答，截断不等于失败
    """
    guard = StreamingRuleGuard()
    limiter = ReplyTokenLimiter()
    streamed = False
    card: dict[str, Any] | None = None
    login_required = False

    def release(piece: str) -> list[str]:
        safe = guard.feed(piece)
        if not safe:
            return []
        allowed = limiter.feed(safe)
        return [sse.encode_token(allowed)] if allowed else []

    try:
        async for event in graph_chain.astream_events(initial_state, config=config, version="v2"):
            if guard.violated or limiter.truncated:
                break
            kind = event.get("event")
            if kind == "on_chat_model_stream" and ANSWER_STREAM_TAG in (event.get("tags") or []):
                chunk = (event.get("data") or {}).get("chunk")
                text = getattr(chunk, "text", None)
                if text:
                    streamed = True
                    for frame in release(text):
                        yield frame
            elif kind == "on_chain_end" and not event.get("parent_ids"):
                output = (event.get("data") or {}).get("output")
                if _compliance_failed(output):
                    # 草稿已被收尾节点换成固定话术，此时不给卡片，免得卡片和「无法处理」并存
                    card, login_required = None, False
                elif isinstance(output, dict):
                    card = output.get("ticket") or None
                    login_required = bool(output.get("login_required"))
                final_text = _final_reply(output)
                if not final_text or guard.violated or limiter.truncated:
                    continue
                if _compliance_failed(output) or not streamed:
                    # 无模型流的模板话术，或合规不通过时的固定话术
                    for piece in sse.chunk_text(final_text):
                        for frame in release(piece):
                            yield frame
                    streamed = True
    except Exception:
        logger.exception("对话处理失败")
        yield encode_error()
        yield encode_done()
        return

    if guard.violated:
        logger.warning("流式回复命中合规禁词，已中止输出")
        yield encode_error()
        yield encode_done()
        return

    tail = guard.flush()
    if tail:
        allowed = limiter.feed(tail)
        if allowed:
            yield sse.encode_token(allowed)

    notice = limiter.finish()
    if notice:
        yield sse.encode_token(notice)

    if card:
        yield sse.encode_event(sse.TICKET, ticket=card)
    if login_required:
        yield sse.encode_event(sse.LOGIN_REQUIRED)

    yield encode_done()


@app.post("/api/chat", dependencies=[Depends(require_internal_token)])
async def chat(request: ChatRequest):
    """主聊天接口 — SSE流式输出（每条 data 为带 type 字段的 JSON）"""
    if graph is None:
        raise HTTPException(status_code=503, detail="系统初始化中")

    session_id = request.session_id or str(uuid.uuid4())

    from langchain_core.messages import HumanMessage

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "user_id": request.user_id,
        "session_id": session_id,
        "intent": "",
        "compliance_passed": True,
        # 本轮产出标记，由 trim_history 统一清零后由 ticket_handler 按需写入
        "ticket": None,
        "login_required": False,
        # 会话累计轮次，由 trim_history 自增；初值 0 让首轮记为 1
        "turn_count": 0,
    }
    config = {"configurable": {"thread_id": session_id}}

    return StreamingResponse(
        stream_reply(graph, initial_state, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/history/{session_id}", dependencies=[Depends(require_internal_token)])
async def get_history(session_id: str, last_n: int = 20):
    """获取对话历史 — 读取 LangGraph Agent State（checkpointer）"""
    if graph is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    history = await short_term_memory.get_history(graph, session_id, last_n=last_n)
    return {"session_id": session_id, "messages": history}


# ─── 知识库管理接口（供 mall-server 调用，Bearer 鉴权） ───

class IngestRequest(BaseModel):
    docId: int
    filePath: str
    title: str = ""
    category: str = ""
    tags: str = ""
    chunkSize: int = 800
    chunkOverlap: int = 100
    cleanRules: dict | str | None = None


class FaqSyncRequest(BaseModel):
    faqs: list[dict]


class EnabledRequest(BaseModel):
    enabled: bool


class RetrieveRequest(BaseModel):
    query: str
    params: dict | None = None


class UpdateChunkRequest(BaseModel):
    content: str


@app.post("/api/admin/ingest", dependencies=[Depends(require_internal_token)])
async def admin_ingest(request: IngestRequest):
    """单文档处理：解析→清洗→分块→向量化。OCR 可能耗时，Java 侧异步触发。"""
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    return await knowledge_admin.ingest(request.model_dump())


@app.post("/api/admin/rebuild", dependencies=[Depends(require_internal_token)])
async def admin_rebuild():
    """全量重建向量（从 mall-server 拉启用文档与 FAQ）。"""
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    return await knowledge_admin.rebuild()


@app.post("/api/admin/retrieve", dependencies=[Depends(require_internal_token)])
async def admin_retrieve(request: RetrieveRequest):
    """检索测试：混合召回 + RRF + 精排 + 阈值判定，返回各阶段分数。"""
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    return await knowledge_admin.retrieve(request.query, request.params)


@app.post("/api/admin/faq/sync", dependencies=[Depends(require_internal_token)])
async def admin_faq_sync(request: FaqSyncRequest):
    """全量同步 FAQ 向量。"""
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    from storage.embeddings import embed_query

    for faq in request.faqs:
        knowledge_admin.store.upsert_faq(faq, lambda texts: [embed_query(t) for t in texts])
    return {"synced": len(request.faqs)}


@app.delete("/api/admin/doc/{doc_id}", dependencies=[Depends(require_internal_token)])
async def admin_delete_doc(doc_id: int):
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    knowledge_admin.store.delete_doc(doc_id)
    return {"deleted": doc_id}


@app.put("/api/admin/doc/{doc_id}/enabled", dependencies=[Depends(require_internal_token)])
async def admin_doc_enabled(doc_id: int, request: EnabledRequest):
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    knowledge_admin.store.set_doc_enabled(doc_id, request.enabled)
    return {"docId": doc_id, "enabled": request.enabled}


@app.delete("/api/admin/faq/{faq_id}", dependencies=[Depends(require_internal_token)])
async def admin_delete_faq(faq_id: int):
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    knowledge_admin.store.delete_faq(faq_id)
    return {"deleted": faq_id}


@app.put("/api/admin/faq/{faq_id}/enabled", dependencies=[Depends(require_internal_token)])
async def admin_faq_enabled(faq_id: int, request: EnabledRequest):
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    knowledge_admin.store.set_faq_enabled(faq_id, request.enabled)
    return {"faqId": faq_id, "enabled": request.enabled}


@app.get("/api/admin/doc/{doc_id}/chunks", dependencies=[Depends(require_internal_token)])
async def admin_list_chunks(doc_id: int, limit: int = 1000):
    """列出文档分块（只取 payload）。"""
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    return knowledge_admin.list_chunks(doc_id, limit)


@app.put("/api/admin/doc/{doc_id}/chunks/{chunk_index}", dependencies=[Depends(require_internal_token)])
async def admin_update_chunk(doc_id: int, chunk_index: int, request: UpdateChunkRequest):
    """编辑单块正文：立即重算向量。"""
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="切片内容不能为空")
    return knowledge_admin.update_chunk_content(doc_id, chunk_index, request.content)


@app.put("/api/admin/doc/{doc_id}/chunks/{chunk_index}/enabled", dependencies=[Depends(require_internal_token)])
async def admin_chunk_enabled(doc_id: int, chunk_index: int, request: EnabledRequest):
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    return knowledge_admin.set_chunk_enabled(doc_id, chunk_index, request.enabled)


@app.delete("/api/admin/doc/{doc_id}/chunks/{chunk_index}", dependencies=[Depends(require_internal_token)])
async def admin_delete_chunk(doc_id: int, chunk_index: int):
    if knowledge_admin is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    return knowledge_admin.delete_chunk(doc_id, chunk_index)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
