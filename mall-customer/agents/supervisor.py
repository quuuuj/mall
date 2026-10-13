"""
Supervisor编排Agent — 中央协调者
负责接收用户请求，根据意图路由到对应子Agent，汇总结果返回。
采用LangGraph StateGraph实现，支持并行调度和Human-in-the-Loop断点。
"""

from __future__ import annotations

import operator
import os
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import RemoveMessage, add_messages

from agents.intent_router import IntentRouterAgent
from agents.knowledge_rag import KnowledgeRAGAgent
from agents.ticket_handler import TicketHandlerAgent
from agents.compliance_checker import ComplianceCheckerAgent
from agents.chitchat import ChitchatAgent
from memory.working_memory import WorkingMemory
from memory.long_term_memory import LongTermMemory
from tracing.otel_config import trace_agent_call


# ─── 状态定义 ───

# 短期记忆滑动窗口：Agent State 中最多保留最近 20 条消息（约 10 轮对话），
# 超出部分由 trim_history 节点用 RemoveMessage 移除，防止状态无限增长
MESSAGE_WINDOW_SIZE = 20


class AgentState(TypedDict):
    """Supervisor编排的全局状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str
    compliance_passed: bool
    current_agent: str
    retry_count: int


# ─── 记忆窗口 ───

def trim_history(state: AgentState) -> dict[str, Any]:
    """滑动窗口：把 Agent State 的消息裁剪到最近 MESSAGE_WINDOW_SIZE 条

    作为图的入口节点执行，紧接着本轮的输入合并之后——保证后续所有节点的
    LLM 只看得到窗口内的消息，checkpointer 持久化的也是有界状态。
    通过 RemoveMessage 走 add_messages reducer 裁剪，而不是直接覆盖列表。
    """
    messages = state.get("messages", [])
    overflow = len(messages) - MESSAGE_WINDOW_SIZE
    if overflow <= 0:
        return {}

    removals = [RemoveMessage(id=m.id) for m in messages[:overflow] if m.id]
    return {"messages": removals}


# ─── Supervisor节点 ───

SUPERVISOR_SYSTEM_PROMPT = """你是一个智能客服系统的Supervisor（主管编排Agent）。
你的职责是：
1. 分析用户意图，决定分发给哪个子Agent处理
2. 汇总子Agent的处理结果，生成最终回复
3. 确保所有回复都经过合规审查

可用的子Agent：
- knowledge_rag: 知识库检索和回答（商品、订单、退换货、平台规则等业务咨询）
- ticket_handler: 工单创建和查询（退款、理赔、投诉等需要办理的业务）
- chitchat: 闲聊寒暄（打招呼、问候、感谢、告别、与业务无关的闲聊）
- compliance_checker: 合规审查（敏感内容识别，仅在涉及资金安全、欺诈举报等场景直达）

路由规则：
- 业务咨询/查询类 → knowledge_rag
- 需要办理的业务、投诉 → ticket_handler
- 闲聊寒暄、与业务无关的消息 → chitchat（不要为此检索知识库）
- 拿不准时 → knowledge_rag（宁可多查，不可漏答）
"""


class SupervisorNode:
    """Supervisor决策节点"""

    def __init__(self, llm: ChatOpenAI, working_memory: WorkingMemory):
        self.llm = llm
        self.working_memory = working_memory

    @trace_agent_call("supervisor")
    async def route_decision(self, state: AgentState) -> AgentState:
        """分析用户意图，决定路由"""
        messages = state["messages"]
        session_id = state.get("session_id", "default")

        context = self.working_memory.get_context(session_id)

        routing_prompt = [
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
            SystemMessage(content=f"当前工作记忆上下文: {context}"),
            *messages,
            HumanMessage(content=(
                "请分析用户的最新消息，返回应该路由到的Agent名称。"
                "只返回以下之一: knowledge_rag, ticket_handler, chitchat, compliance_checker"
            )),
        ]

        response = await self.llm.ainvoke(routing_prompt)
        intent = response.content.strip().lower()

        valid_intents = {"knowledge_rag", "ticket_handler", "chitchat", "compliance_checker"}
        if intent not in valid_intents:
            intent = "knowledge_rag"

        self.working_memory.update(session_id, {"last_intent": intent})

        return {
            **state,
            "intent": intent,
            "current_agent": "supervisor",
        }

    @trace_agent_call("supervisor_synthesize")
    async def synthesize_response(self, state: AgentState) -> AgentState:
        """合规门控 — 子Agent的回答已由其本人写入 messages

        - 合规不通过：撤回本轮草稿消息（避免违规内容进入会话历史），追加转人工话术
        - 合规通过：末尾 AIMessage 即最终回复，不再追加（否则历史中出现重复消息）
        - 本轮无子Agent回答（如直达合规审查）：追加兜底话术
        """
        messages = state.get("messages", [])
        last = messages[-1] if messages else None

        if not state.get("compliance_passed", True):
            final_response = (
                "抱歉，您的请求涉及敏感内容，已转交人工客服处理。"
                "工单编号已自动生成，请留意后续通知。"
            )
            updates: list[BaseMessage] = []
            if isinstance(last, AIMessage) and last.id:
                updates.append(RemoveMessage(id=last.id))
            updates.append(AIMessage(content=final_response))
            return {**state, "messages": updates}

        if isinstance(last, AIMessage) and bool(last.content):
            return state

        final_response = "抱歉，暂时无法处理您的请求，请稍后重试。"
        return {**state, "messages": [AIMessage(content=final_response)]}


# ─── 路由函数 ───

def route_to_agent(state: AgentState) -> str:
    """根据意图路由到对应Agent节点"""
    intent = state.get("intent", "knowledge_rag")
    route_map = {
        "knowledge_rag": "knowledge_rag",
        "ticket_handler": "ticket_handler",
        "chitchat": "chitchat",
        "compliance_checker": "compliance_check",
    }
    return route_map.get(intent, "knowledge_rag")


def should_check_compliance(state: AgentState) -> str:
    """所有回复都需经过合规审查"""
    return "compliance_check"


# ─── 构建Graph ───

def create_supervisor_graph(
        llm: ChatOpenAI | None = None,
        working_memory: WorkingMemory | None = None,
        long_term_memory: LongTermMemory | None = None,
        checkpointer: Any | None = None,
        enable_checkpointing: bool = True,
) -> StateGraph:
    """
    构建Supervisor编排的多Agent StateGraph。

    这是整个系统的核心入口，将各子Agent通过有向图连接起来，
    由Supervisor节点负责路由决策和结果汇总。

    Args:
        llm: 语言模型实例
        working_memory: 工作记忆
        long_term_memory: 长期记忆
        checkpointer: LangGraph checkpointer（如 AsyncRedisSaver），对话状态由其持久化；
            为 None 且 enable_checkpointing=True 时回退到进程内 MemorySaver
        enable_checkpointing: 是否启用检查点（支持断点恢复）
    """
    if llm is None:
        # 若没有指定模型，就使用配置的默认模型
        llm = ChatOpenAI(model=os.getenv("MODEL_NAME"),
                         api_key=os.getenv("OPENAI_API_KEY"),
                         base_url=os.getenv("OPENAI_BASE_URL"),
                         temperature=0)
    if working_memory is None:
        working_memory = WorkingMemory()

    supervisor = SupervisorNode(llm, working_memory)

    intent_router = IntentRouterAgent(llm)  # 暂未接入路由，保留待意图识别Agent启用
    knowledge_agent = KnowledgeRAGAgent(llm, long_term_memory)
    ticket_agent = TicketHandlerAgent(llm)
    compliance_agent = ComplianceCheckerAgent(llm)
    chitchat_agent = ChitchatAgent(llm)

    graph = StateGraph(AgentState)

    graph.add_node("trim_history", trim_history)   # 滑动窗口：裁剪超窗口的历史消息
    graph.add_node("supervisor_route", supervisor.route_decision)
    graph.add_node("knowledge_rag", knowledge_agent.process)
    graph.add_node("ticket_handler", ticket_agent.process)
    graph.add_node("chitchat", chitchat_agent.process)
    graph.add_node("compliance_check", compliance_agent.process)
    graph.add_node("synthesize", supervisor.synthesize_response)

    graph.set_entry_point("trim_history")
    graph.add_edge("trim_history", "supervisor_route")

    graph.add_conditional_edges(
        "supervisor_route",
        route_to_agent,
        {
            "knowledge_rag": "knowledge_rag",
            "ticket_handler": "ticket_handler",
            "chitchat": "chitchat",
            "compliance_check": "compliance_check",
        },
    )

    graph.add_edge("knowledge_rag", "compliance_check")
    graph.add_edge("ticket_handler", "compliance_check")
    graph.add_edge("chitchat", "compliance_check")
    graph.add_edge("compliance_check", "synthesize")
    graph.add_edge("synthesize", END)

    if checkpointer is None and enable_checkpointing:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    return compiled
