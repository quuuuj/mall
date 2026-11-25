"""knowledge_rag — 电商政策知识库问答（新混合检索版）。

流程：FAQ 前置短路 → 混合召回(向量+BM25) → RRF 融合 → 精排 → 阈值判定 → 生成。
判定逻辑与检索测试台共用 HybridRetriever，保证测试与线上行为一致。

空召回或精排分低于阈值时拒答，引导四类工单，不调用生成模型。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from agent.streaming import stream_text
from retrieval.hybrid import HybridRetriever
from tracing.otel_config import trace_agent_call

logger = logging.getLogger(__name__)

# 引导建单的四类工单；阈值拦下的空召回与模型判定「文档不足」共用同一份话术
TICKET_GUIDANCE = """- 退款退货
- 物流异常
- 发票
- 投诉建议"""

RAG_SYSTEM_PROMPT = f"""你是电商平台的在线客服，负责依据平台政策文档回答用户问题。

回答规则：
1. 只依据给出的参考文档作答，不补充文档之外的政策、时效、价格或承诺
2. 文档没有覆盖的部分，明确说明「这一点我这边没有查到依据」，不要推测
3. 文档不足以回答时，在说明之后列出下面四类工单供用户选择（原文照抄，不增删）：
{TICKET_GUIDANCE}
4. 简洁直接，先给结论再给依据，控制在 3-5 句
5. 涉及具体订单的问题，请用户提供订单号，由客服查询
6. 末尾用一行标注引用的文档标题

回答格式：
结论 → 必要说明 → 「来源：<文档标题>」
"""

# 空召回 / 低分拒答共用话术
EMPTY_RECALL_REPLY = (
    "这个问题我在平台政策里没有找到明确依据，不好凭印象回答你。\n\n"
    "可以帮你转成人工工单跟进，选一类更接近的：\n"
    f"{TICKET_GUIDANCE}\n\n"
    "回复类别，或直接描述你的诉求，我来建单。"
)


class KnowledgeRagAgent:
    """知识检索节点 — FAQ 前置 + 混合检索 + 精排判定。"""

    def __init__(
        self,
        llm: ChatOpenAI,
        retriever: HybridRetriever,
        mcp_client: Any | None = None,
    ):
        self.llm = llm
        self.retriever = retriever
        self.mcp_client = mcp_client

    @trace_agent_call("knowledge_rag_hybrid")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """完整流程：FAQ 前置 → 混合检索 → 判定 → 回答/拒答。"""
        messages = state.get("messages", [])
        if not messages:
            return {}

        query = messages[-1].content
        if not isinstance(query, str) or not query.strip():
            return {"messages": [AIMessage(content=EMPTY_RECALL_REPLY)]}

        try:
            result = await self.retriever.retrieve(query)
        except Exception:
            logger.exception("混合检索失败，降级为拒答")
            return {"messages": [AIMessage(content=EMPTY_RECALL_REPLY)]}

        path = result.get("path")

        if path == "faq":
            # FAQ 标准答案：直接返回，累加命中计数（失败不影响回答）
            answer = result.get("answer") or EMPTY_RECALL_REPLY
            await self._count_faq_hit(result.get("faq_id"))
            return {"messages": [AIMessage(content=answer)]}

        if path == "reject":
            # 空召回或精排分不足：拒答，不调用生成模型
            return {"messages": [AIMessage(content=EMPTY_RECALL_REPLY)]}

        # path == "rag_answer"：用精排片段生成回答
        docs = result.get("rag_candidates") or []
        answer = await self._generate(query, docs)
        return {"messages": [AIMessage(content=answer)]}

    async def _generate(self, query: str, candidates: list[dict]) -> str:
        """基于精排片段生成回答。"""
        context = "\n\n---\n\n".join(
            f"文档: {c['payload'].get('title') or c['payload'].get('source') or '未知'}\n"
            f"内容: {c['payload'].get('content', '')}"
            for c in candidates
        )
        messages = [
            SystemMessage(content=RAG_SYSTEM_PROMPT),
            HumanMessage(content=f"用户问题: {query}\n\n参考文档:\n{context}"),
        ]
        return await stream_text(self.llm, messages)

    async def _count_faq_hit(self, faq_id: Any) -> None:
        if not faq_id or self.mcp_client is None:
            return
        try:
            await self.mcp_client.increment_faq_hit(int(faq_id))
        except Exception as e:
            logger.warning("FAQ 命中计数失败: %s", e)
