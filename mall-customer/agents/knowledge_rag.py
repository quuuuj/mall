"""
知识检索Agent — 电商政策知识库问答（RAG）

流程：Query 改写 → 向量检索 → 重排 → 生成回答。
检索为空时不给编造内容，而是引导用户从四类工单中选择一项提交。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from memory.long_term_memory import LongTermMemory
from tracing.otel_config import trace_agent_call


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

QUERY_REWRITE_PROMPT = """把用户的口语化问题改写成适合向量检索的查询语句。
保留核心语义，补全被省略的主体（如「几天到」→「物流配送时效」）。
只输出改写后的查询，不要额外说明。

用户问题: {query}
"""

# 空召回时的引导话术：给出四类工单作为明确下一步
EMPTY_RECALL_REPLY = (
    "这个问题我在平台政策里没有找到明确依据，不好凭印象回答你。\n\n"
    "可以帮你转成人工工单跟进，选一类更接近的：\n"
    f"{TICKET_GUIDANCE}\n\n"
    "回复类别，或直接描述你的诉求，我来建单。"
)


class KnowledgeRAGAgent:
    """知识检索Agent — 实现完整 RAG 流程"""

    def __init__(self, llm: ChatOpenAI, long_term_memory: LongTermMemory | None = None):
        self.llm = llm
        self.long_term_memory = long_term_memory or LongTermMemory()

    @trace_agent_call("rag_query_rewrite")
    async def rewrite_query(self, original_query: str) -> str:
        """Query 改写：口语化问题 → 检索友好查询；失败时退回原问题"""
        try:
            response = await self.llm.ainvoke(
                [HumanMessage(content=QUERY_REWRITE_PROMPT.format(query=original_query))]
            )
            rewritten = (response.content or "").strip()
            return rewritten or original_query
        except Exception:
            return original_query

    @trace_agent_call("rag_retrieve")
    async def retrieve_documents(self, query: str, top_k: int = 5) -> list[dict]:
        """向量检索；低于相似度阈值的召回已被 LongTermMemory 过滤"""
        return self.long_term_memory.search(query, top_k=top_k)

    @trace_agent_call("rag_rerank")
    async def rerank_documents(
        self, query: str, documents: list[dict], top_k: int = 3
    ) -> list[dict]:
        """按相关性重排，提升首条文档的命中率；解析失败退回按分数排序"""
        if len(documents) <= 1:
            return documents[:top_k]

        doc_summaries = "\n".join(
            f"[{i}] {(doc.get('metadata') or {}).get('title') or doc.get('source', '')}: "
            f"{doc.get('content', '')[:200]}"
            for i, doc in enumerate(documents)
        )

        messages = [
            SystemMessage(content="你是文档相关性排序助手，只输出索引号。"),
            HumanMessage(content=(
                f"用户问题: {query}\n\n"
                f"候选文档:\n{doc_summaries}\n\n"
                f"按相关性从高到低返回最相关的 {top_k} 个文档索引，逗号分隔，如: 0,2,4"
            )),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            indices = [int(i.strip()) for i in response.content.split(",") if i.strip()]
            reranked = [documents[i] for i in indices if 0 <= i < len(documents)]
            return reranked[:top_k] or documents[:top_k]
        except Exception:
            return documents[:top_k]

    @trace_agent_call("rag_generate")
    async def generate_answer(self, query: str, context_docs: list[dict]) -> str:
        """基于检索文档生成回答；空召回走工单引导话术"""
        if not context_docs:
            return EMPTY_RECALL_REPLY

        context = "\n\n---\n\n".join(
            f"文档: {(doc.get('metadata') or {}).get('title') or doc.get('source', '未知')}\n"
            f"内容: {doc.get('content', '')}"
            for doc in context_docs
        )

        messages = [
            SystemMessage(content=RAG_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"用户问题: {query}\n\n"
                f"参考文档:\n{context}"
            )),
        ]

        response = await self.llm.ainvoke(messages)
        return response.content

    @trace_agent_call("knowledge_rag_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """完整 RAG 流程（作为 Graph 节点）"""
        messages = state.get("messages", [])
        if not messages:
            return state

        original_query = messages[-1].content
        rewritten_query = await self.rewrite_query(original_query)
        raw_docs = await self.retrieve_documents(rewritten_query, top_k=5)

        if not raw_docs:
            # 空召回不调生成模型，直接用引导话术，避免编造
            return {**state, "messages": [AIMessage(content=EMPTY_RECALL_REPLY)]}

        reranked_docs = await self.rerank_documents(rewritten_query, raw_docs, top_k=3)
        answer = await self.generate_answer(original_query, reranked_docs)

        return {**state, "messages": [AIMessage(content=answer)]}
