"""
闲聊Agent — 寒暄与无关消息处理
负责处理打招呼、感谢、问候等与业务无关的闲聊消息，
直接生成友好回复，不触发知识库检索，避免无意义的向量查询。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from tracing.otel_config import trace_agent_call


CHITCHAT_SYSTEM_PROMPT = """你是一个友好的电商客服，负责处理用户的寒暄与闲聊。

职责范围：
1. 回应打招呼、问候、感谢、告别等寒暄
2. 处理与业务无关的轻松闲聊（天气、心情、节日祝福等）
3. 适当引导用户回到业务话题（如查订单、退换货、商品咨询）

回答规则：
1. 简短友好，符合客服场景，不超过3句话
2. 不检索、不编造任何业务信息（商品价格、订单状态等一律不回答）
3. 不做任何业务承诺（退款、赔付、优惠等）
4. 用户若提及具体业务问题，礼貌引导其重新描述，由知识库回答
"""


class ChitchatAgent:
    """闲聊Agent - 处理寒暄，跳过知识库检索"""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    @trace_agent_call("chitchat_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为Graph节点处理状态：基于对话历史直接生成闲聊回复"""
        messages = state.get("messages", [])
        if not messages:
            return state

        response = await self.llm.ainvoke(
            [SystemMessage(content=CHITCHAT_SYSTEM_PROMPT), *messages]
        )

        return {
            **state,
            "messages": [AIMessage(content=response.content)],
        }
