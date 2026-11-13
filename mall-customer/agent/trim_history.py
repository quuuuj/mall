"""trim_history 节点 — 滑动窗口裁剪会话历史。

Agent State 中最多保留最近 MESSAGE_WINDOW_SIZE 条消息（约 10 轮对话），
超出部分用 RemoveMessage 移除，防止状态无限增长。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph.message import RemoveMessage

# 短期记忆滑动窗口大小
MESSAGE_WINDOW_SIZE = 20


def trim_history(state: dict[str, Any]) -> dict[str, Any]:
    """作为图的入口节点，在本轮输入合并之后执行。

    通过 RemoveMessage 走 add_messages reducer 裁剪，而不是直接覆盖列表。
    同时把 ticket / login_required 清零：这两项是「本轮」的产出标记，
    状态随 checkpointer 跨轮保留，不清零上一轮的工单卡片会跟着发一遍。
    """
    updates: dict[str, Any] = {"ticket": None, "login_required": False}

    messages = state.get("messages", [])
    overflow = len(messages) - MESSAGE_WINDOW_SIZE
    if overflow <= 0:
        return updates

    updates["messages"] = [RemoveMessage(id=m.id) for m in messages[:overflow] if m.id]
    return updates
