"""supervisor — 路由决策节点。

分析用户最新消息，判断交给哪个节点处理；可用节点与图里的节点名一致：
knowledge_rag / order_query / ticket_handler / chitchat。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from memory.working_memory import WorkingMemory
from tracing.otel_config import trace_agent_call

ROUTE_TARGETS = ("knowledge_rag", "order_query", "ticket_handler", "chitchat")

SUPERVISOR_SYSTEM_PROMPT = """你是一个智能客服系统的 Supervisor（主管编排Agent）。
你的职责是分析用户意图，决定交给哪个节点处理。

可用节点：
- knowledge_rag: 知识库检索和回答（平台规则、退换货政策、运费、发票、时效等业务咨询）
- order_query: 查询用户自己的订单（「我那单到哪了」「我最近买了什么」「查一下订单 XXX」）
- ticket_handler: 工单创建和查询（退款、理赔、投诉等需要人工办理的业务）
- chitchat: 闲聊寒暄（打招呼、问候、感谢、告别、与业务无关的闲聊）

路由规则：
- 问具体订单的状态、金额、买了什么，或给出订单号 → order_query
- 问通用规则（运费怎么算、能退吗、开发票要什么）→ knowledge_rag
- 需要办理的业务、投诉 → ticket_handler
- 闲聊寒暄、与业务无关的消息 → chitchat（不要为此检索知识库）
- 拿不准时 → knowledge_rag（宁可多查，不可漏答）
"""


class SupervisorAgent:
    """路由节点：只输出意图名，白名单外的取值一律回落 knowledge_rag"""

    def __init__(self, llm: ChatOpenAI, working_memory: WorkingMemory):
        self.llm = llm
        self.working_memory = working_memory

    @trace_agent_call("supervisor")
    async def route(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为 Graph 节点：决定本轮走向"""
        messages = state.get("messages", [])
        if not messages:
            return {}

        session_id = state.get("session_id", "default")
        context = self.working_memory.get_context(session_id)

        response = await self.llm.ainvoke([
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
            SystemMessage(content=f"当前工作记忆上下文: {context}"),
            *messages,
            HumanMessage(content=(
                "请分析用户的最新消息，返回应该路由到的节点名称。"
                f"只返回以下之一: {', '.join(ROUTE_TARGETS)}"
            )),
        ])

        intent = (response.content or "").strip().lower()
        if intent not in ROUTE_TARGETS:
            intent = "knowledge_rag"

        self.working_memory.update(session_id, {"last_intent": intent})
        return {"intent": intent}
