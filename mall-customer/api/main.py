"""
FastAPI入口 — 提供REST API + SSE流式响应
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agents.supervisor import create_supervisor_graph
from api import sse
from api.sse import encode_done, encode_error
from memory.working_memory import WorkingMemory
from memory.short_term_memory import ShortTermMemory
from memory.long_term_memory import LongTermMemory
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
KNOWLEDGE_BASE_DIR = os.getenv("KNOWLEDGE_BASE_DIR", "./knowledge_base")
long_term_memory = LongTermMemory(
    index_path=os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index"),
    min_score=float(os.getenv("RAG_MIN_SCORE", "0.5")),
)
graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global graph

    init_tracer(
        service_name=os.getenv("OTEL_SERVICE_NAME", "smart-cs-multi-agent"),
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )

    # 短期记忆：Redis 持久化 Agent State，Redis 不可用时自动降级内存
    await short_term_memory.setup()

    # 知识库：索引已落盘则直接加载，否则从 knowledge_base/ 导入并写盘
    if long_term_memory.document_count == 0:
        loaded = long_term_memory.load_knowledge_base(KNOWLEDGE_BASE_DIR)
        logger.info("知识库已导入 %d 篇文档（目录 %s）", loaded, KNOWLEDGE_BASE_DIR)

    graph = create_supervisor_graph(
        working_memory=working_memory,
        long_term_memory=long_term_memory,
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


@app.post("/api/chat", dependencies=[Depends(require_internal_token)])
async def chat(request: ChatRequest):
    """主聊天接口 — SSE流式输出（每条 data 为带 type 字段的 JSON）"""
    if graph is None:
        raise HTTPException(status_code=503, detail="系统初始化中")

    session_id = request.session_id or str(uuid.uuid4())

    async def event_generator():
        from langchain_core.messages import AIMessage, HumanMessage

        initial_state = {
            "messages": [HumanMessage(content=request.message)],
            "user_id": request.user_id,
            "session_id": session_id,
            "intent": "",
            "compliance_passed": True,
            "current_agent": "",
            "retry_count": 0,
        }

        config = {"configurable": {"thread_id": session_id}}

        try:
            result = await graph.ainvoke(initial_state, config=config)
            # 最终回复即 Agent State 中末尾的 AIMessage（子Agent草稿或合成节点兜底话术）
            messages = result.get("messages") or []
            last = messages[-1] if messages else None
            final_response = (
                last.content
                if isinstance(last, AIMessage) and last.content
                else "系统处理异常，请稍后重试"
            )
        except Exception:
            logger.exception("对话处理失败 session_id=%s", session_id)
            yield encode_error()
            yield encode_done()
            return

        # 模拟打字机流式切块输出（真流式见 SSE 协议工单）
        for frame in sse.token_frames(final_response):
            yield frame
            await asyncio.sleep(0.03)

        yield encode_done()

    return StreamingResponse(
        event_generator(),
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
