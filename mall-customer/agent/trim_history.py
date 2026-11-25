"""trim_history 节点 — 滑动窗口裁剪会话历史。

Agent State 中最多保留最近 MESSAGE_WINDOW_SIZE 条消息（约 10 轮对话），
超出部分用 RemoveMessage 移除，防止状态无限增长。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph.message import RemoveMessage

from agent.limits import MAX_TURNS, TURN_LIMIT_REPLY

# 短期记忆滑动窗口大小
MESSAGE_WINDOW_SIZE = 20


def trim_history(state: dict[str, Any]) -> dict[str, Any]:
    """作为图的入口节点，在本轮输入合并之后执行。

    通过 RemoveMessage 走 add_messages reducer 裁剪，而不是直接覆盖列表。
    同时把 ticket / login_required 清零：这两项是「本轮」的产出标记，
    状态随 checkpointer 跨轮保留，不清零上一轮的工单卡片会跟着发一遍。

    轮次计数也在这里自增：消息历史被裁到固定窗口后无法反推总轮次，
    只能单独计数。超过 MAX_TURNS 时本轮不再进入 supervisor，
    直接给出固定话术（见 graph 的入口条件边）。
    """
    updates: dict[str, Any] = {"ticket": None, "login_required": False}

    messages = state.get("messages", [])
    turn_count = int(state.get("turn_count") or 0) + 1
    updates["turn_count"] = turn_count

    overflow = len(messages) - MESSAGE_WINDOW_SIZE
    if overflow > 0:
        updates["messages"] = [RemoveMessage(id=m.id) for m in messages[:overflow] if m.id]

    return updates


def turn_limit_reached(state: dict[str, Any]) -> bool:
    """本轮是否已超出会话轮次上限。"""
    return int(state.get("turn_count") or 0) > MAX_TURNS


def turn_limit_node(state: dict[str, Any]) -> dict[str, Any]:
    """撞上轮次上限时的终点：只发固定话术，不再调用模型。"""
    return {"messages": [AIMessage(content=TURN_LIMIT_REPLY)]}

