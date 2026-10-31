"""
流式输出约定

节点里凡是「把模型产出直接给用户看」的调用，都用 ``stream_text`` 而非 ainvoke：
它给这次调用打上 ANSWER_STREAM_TAG，API 层只把带该标签的 on_chat_model_stream
事件转成 token 帧，其余内部调用（意图判断、查询改写、重排、合规审查）的中间产出
不会漏进用户的对话流。

节点返回值仍是完整文本，Agent State 里的消息与落库内容不受影响。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

# 标记「这次模型产出可以直接给用户看」；API 层据此挑选 token 事件
ANSWER_STREAM_TAG = "answer_stream"


async def stream_text(llm: Any, messages: list[BaseMessage], **kwargs: Any) -> str:
    """流式调用模型并返回拼接后的完整文本。

    模型不支持流式（或测试替身只实现了 ainvoke）时退回一次性调用，
    调用方拿到的都是完整字符串，无需分支。
    """
    astream = getattr(llm, "astream", None)
    if astream is None:
        response = await llm.ainvoke(messages, **kwargs)
        return response.content or ""

    parts: list[str] = []
    async for chunk in astream(messages, **{**kwargs, "config": {"tags": [ANSWER_STREAM_TAG]}}):
        text = getattr(chunk, "text", None)
        if text is None:
            text = chunk.content if isinstance(chunk.content, str) else ""
        if text:
            parts.append(text)
    return "".join(parts)
