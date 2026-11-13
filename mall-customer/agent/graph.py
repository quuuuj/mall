"""graph — 编译 LangGraph 工作流。

节点名与 agent/ 下的模块名一致，便于按节点名找到对应实现：

    trim_history → supervisor ─┬→ knowledge_rag ─┐
                               ├→ order_query ───┤
                               ├→ ticket_handler ─┤
                               ├→ chitchat ───────┼→ compliance_checker → END
                               └→ compliance_checker
"""

from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agent.chitchat import ChitchatAgent
from agent.compliance_checker import ComplianceCheckerAgent
from agent.knowledge_rag import KnowledgeRagAgent
from agent.order_query import OrderQueryAgent
from agent.state import AgentState
from agent.supervisor import ROUTE_TARGETS, SupervisorAgent
from agent.ticket_handler import TicketHandlerAgent
from agent.trim_history import trim_history
from memory.long_term_memory import LongTermMemory
from memory.working_memory import WorkingMemory
from tools.mcp_client import McpBackendClient


def _route(state: AgentState) -> str:
    """按 supervisor 给出的意图走；白名单外的取值已在节点内回落"""
    intent = state.get("intent", "knowledge_rag")
    return intent if intent in ROUTE_TARGETS else "knowledge_rag"


def build_graph(
    llm: ChatOpenAI | None = None,
    working_memory: WorkingMemory | None = None,
    long_term_memory: LongTermMemory | None = None,
    mcp_client: McpBackendClient | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """构建并编译工作流。

    Args:
        llm: 语言模型，默认按环境变量创建
        working_memory: 工作记忆
        long_term_memory: 长期记忆（知识库向量库）
        mcp_client: 访问 mall-server 的 MCP 客户端
        checkpointer: 对话状态持久化；为 None 时用进程内 MemorySaver
    """
    if llm is None:
        llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=0,
        )
    working_memory = working_memory or WorkingMemory()
    mcp_client = mcp_client or McpBackendClient()

    graph = StateGraph(AgentState)
    graph.add_node("trim_history", trim_history)
    graph.add_node("supervisor", SupervisorAgent(llm, working_memory).route)
    graph.add_node("knowledge_rag", KnowledgeRagAgent(llm, long_term_memory).process)
    graph.add_node("order_query", OrderQueryAgent(llm, mcp_client).process)
    graph.add_node("ticket_handler", TicketHandlerAgent(llm, mcp_client).process)
    graph.add_node("chitchat", ChitchatAgent(llm).process)
    graph.add_node("compliance_checker", ComplianceCheckerAgent(llm).process)

    graph.set_entry_point("trim_history")
    graph.add_edge("trim_history", "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route,
        {
            "knowledge_rag": "knowledge_rag",
            "order_query": "order_query",
            "ticket_handler": "ticket_handler",
            "chitchat": "chitchat",
            "compliance_checker": "compliance_checker",
        },
    )
    for node in ("knowledge_rag", "order_query", "ticket_handler", "chitchat"):
        graph.add_edge(node, "compliance_checker")
    graph.add_edge("compliance_checker", END)

    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)
