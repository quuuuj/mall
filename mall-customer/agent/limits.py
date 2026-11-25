"""limits — 单次回复长度与会话轮次的上限保护。

两个限制都放在 Python 侧：成本发生在调用模型的那一刻，拦截点要紧贴消费点。
Java 侧只做 SSE 中继，对这两个限制无感知。

token 计量用 tiktoken 的 cl100k_base。模型并不是 OpenAI 系列，这个计数只是
数量级上的近似（中文约 1 字 1~2 token），用于「别让一次回答无限长」的护栏足够，
不能当作计费依据。
"""

from __future__ import annotations

import os
from functools import lru_cache

import tiktoken

# 单次回复最多输出的 token 数，超过即截断并补一句说明
MAX_REPLY_TOKENS = int(os.getenv("MAX_REPLY_TOKENS", "1024"))
# 单个会话最多处理多少轮，超过后不再调用模型
MAX_TURNS = int(os.getenv("MAX_TURNS", "30"))

REPLY_TRUNCATED_NOTICE = (
    f"\n\n（这条回复较长，以上是前 {MAX_REPLY_TOKENS} token 的内容。"
    "需要更多细节可以继续追问，或转人工客服。）"
)

# 撞上轮次上限时的固定话术：不报错、不静默截断，给用户一条明确的出路。
# 不承诺「我来建单」—— 建单本身需要模型参与，撞上限后不再调用模型。
TURN_LIMIT_REPLY = (
    "这个会话已经聊了比较久，为了避免上下文太长影响回答质量，"
    "建议新开一个会话继续提问。\n\n"
    "如果需要人工处理，请联系人工客服说明诉求，也可以在新会话里提交工单。"
)


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """编码器只初始化一次（首次初始化需要几百毫秒）。"""
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoding().encode(text))


class ReplyTokenLimiter:
    """逐块喂入模型产出，超过上限后丢弃后续内容并标记 truncated。

    计数针对「已放行的全部文本」而不是单块：模型分块方式不影响最终截断位置，
    同一段回答无论切成几块，截断出来的内容都一致。
    """

    def __init__(self, max_tokens: int | None = None):
        self._max = MAX_REPLY_TOKENS if max_tokens is None else max_tokens
        self._released = ""
        self._truncated = False

    @property
    def truncated(self) -> bool:
        return self._truncated

    def feed(self, piece: str) -> str:
        """返回可以继续发给用户的增量文本（截断后恒为空串）。"""
        if self._truncated or not piece:
            return ""

        candidate = self._released + piece
        token_ids = _encoding().encode(candidate)
        if len(token_ids) <= self._max:
            self._released = candidate
            return piece

        kept = _encoding().decode(token_ids[: self._max])
        extra = kept[len(self._released):] if kept.startswith(self._released) else ""
        self._released = kept
        self._truncated = True
        return extra

    def finish(self) -> str:
        """流结束时调用：截断过就返回补发说明，否则返回空串。"""
        return REPLY_TRUNCATED_NOTICE if self._truncated else ""
