"""graph — 编译 LangGraph 工作流。

节点名与 agent/ 下的模块名一致，便于按节点名找到对应实现：

    trim_history → supervisor ─┬→ knowledge_rag ─┐
                               ├→ order_query ───┤
                               ├→ ticket_handler ─┤
                               └→ chitchat ───────┴→ compliance_checker → END

    trim_history 之后还有一道轮次上限判断：超过 MAX_TURNS 直接走 turn_limit → END。
"""

from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from retrieval.hybrid import HybridRetriever
from storage.embeddings import embed_query
from storage.qdrant_store import QdrantStore
from retrieval.rerank import RerankClient
from agent.chitchat import ChitchatAgent
from agent.compliance_checker import ComplianceCheckerAgent
from agent.knowledge_rag import KnowledgeRagAgent
from agent.order_query import OrderQueryAgent
from agent.state import AgentState
from agent.supervisor import ROUTE_TARGETS, SupervisorAgent
from agent.ticket_handler import TicketHandlerAgent
from agent.trim_history import trim_history, turn_limit_node, turn_limit_reached
from memory.working_memory import WorkingMemory
from tools.mcp_client import McpBackendClient


def _route(state: AgentState) -> str:
    """按 supervisor 给出的意图走；白名单外的取值已在节点内回落"""
    intent = state.get("intent", "knowledge_rag")
    return intent if intent in ROUTE_TARGETS else "knowledge_rag"


def build_graph(
    llm: ChatOpenAI | None = None,
    working_memory: WorkingMemory | None = None,
    retriever: HybridRetriever | None = None,
    mcp_client: McpBackendClient | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """构建并编译工作流。

    Args:
        llm: 语言模型，默认按环境变量创建
        working_memory: 工作记忆
        retriever: 混合检索器（FAQ 前置 + RAG 三段判定）
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
    if retriever is None:
        retriever = HybridRetriever(QdrantStore(), RerankClient(), embed_query)

    graph = StateGraph(AgentState)
    graph.add_node("trim_history", trim_history)
    graph.add_node("turn_limit", turn_limit_node)
    graph.add_node("supervisor", SupervisorAgent(llm, working_memory).route)
    graph.add_node("knowledge_rag", KnowledgeRagAgent(llm, retriever, mcp_client).process)
    graph.add_node("order_query", OrderQueryAgent(llm, mcp_client).process)
    graph.add_node("ticket_handler", TicketHandlerAgent(llm, mcp_client).process)
    graph.add_node("chitchat", ChitchatAgent(llm).process)
    graph.add_node("compliance_checker", ComplianceCheckerAgent(llm).process)

    graph.set_entry_point("trim_history")
    # 轮次上限在入口就拦下：撞上限的那一轮不再进 supervisor，避免继续调用模型
    graph.add_conditional_edges(
        "trim_history",
        lambda state: "turn_limit" if turn_limit_reached(state) else "supervisor",
        {"turn_limit": "turn_limit", "supervisor": "supervisor"},
    )
    graph.add_edge("turn_limit", END)
    graph.add_conditional_edges(
        "supervisor",
        _route,
        {
            "knowledge_rag": "knowledge_rag",
            "order_query": "order_query",
            "ticket_handler": "ticket_handler",
            "chitchat": "chitchat",
        },
    )
    for node in ("knowledge_rag", "order_query", "ticket_handler", "chitchat"):
        graph.add_edge(node, "compliance_checker")
    graph.add_edge("compliance_checker", END)

    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)
