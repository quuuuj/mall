"""
FastAPI入口 — 提供REST API + SSE流式响应
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agents.supervisor import create_supervisor_graph
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
    if credentials.credentials != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="鉴权凭据无效")


working_memory = WorkingMemory()
short_term_memory = ShortTermMemory()
long_term_memory = LongTermMemory(
    index_path=os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
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

    graph = create_supervisor_graph(
        working_memory=working_memory,
        long_term_memory=long_term_memory,
        checkpointer=short_term_memory.checkpointer,
    )

    long_term_memory.add_document(
        content="我们的理财产品A年化收益率为3.5%-5.2%，投资期限为6个月至3年，最低投资金额10000元。注意：理财非存款，产品有风险，投资须谨慎。",
        source="product_faq.md",
    )
    long_term_memory.add_document(
        content="退款政策：用户在购买后7天内可申请无理由退款，超过7天需提供合理原因。退款将在3-5个工作日内原路退回。",
        source="refund_policy.md",
    )
    long_term_memory.add_document(
        content="开户流程：1.准备身份证原件 2.填写开户申请表 3.进行视频认证 4.设置交易密码 5.完成风险评估问卷。整个流程约需15-30分钟。",
        source="account_guide.md",
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
    """主聊天接口 — SSE流式输出"""
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
            final_response = "服务暂时不可用，请稍后重试"

        # 模拟打字机流式切块输出
        chunk_size = 4
        for i in range(0, len(final_response), chunk_size):
            chunk = final_response[i:i + chunk_size]
            payload = json.dumps({"content": chunk}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.03)

        yield "data: [DONE]\n\n"

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
