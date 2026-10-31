"""
SSE 协议编码 — 单通道，每条 data 为带 type 字段的 JSON

事件类型：
- token          增量文本
- ticket         工单卡片（工单号、类型、状态、创建时间）
- login_required 需要登录（订单、历史、工单类诉求）
- error          对用户固定文案的错误
- done           流结束标记，必在流尾且只出现一次
"""

from __future__ import annotations

import json
from typing import Iterator

TOKEN = "token"
TICKET = "ticket"
LOGIN_REQUIRED = "login_required"
ERROR = "error"
DONE = "done"

EVENT_TYPES = frozenset({TOKEN, TICKET, LOGIN_REQUIRED, ERROR, DONE})

# 对用户固定文案，不透传异常原文
FALLBACK_ERROR_MESSAGE = "服务暂时不可用，请稍后重试"


def encode_event(event_type: str, **fields: object) -> str:
    """把一个事件编码为 SSE 帧（data 为 JSON）。"""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"未知的 SSE 事件类型: {event_type}")
    payload = {"type": event_type, **fields}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def encode_token(content: str) -> str:
    return encode_event(TOKEN, content=content)


def encode_done() -> str:
    return encode_event(DONE)


def encode_error(message: str = FALLBACK_ERROR_MESSAGE) -> str:
    return encode_event(ERROR, message=message)


def token_frames(text: str, chunk_size: int = 4) -> Iterator[str]:
    """把完整回复切成 token 事件序列（真流式落地前的中转形态）。"""
    for i in range(0, len(text), chunk_size):
        yield encode_token(text[i:i + chunk_size])
