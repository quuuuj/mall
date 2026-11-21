"""工作流状态 — 各节点共享的 AgentState 定义。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """整条链路的共享状态。

    messages 由 add_messages 合并（追加与 RemoveMessage 删除），其余字段后写覆盖。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str
    compliance_passed: bool
    # 本轮建单成功时的卡片数据，API 层据此发 ticket 帧。
    # 每轮开头由初始状态重置为 None，避免上一轮的卡片串到这一轮。
    ticket: dict[str, Any] | None
    # 本轮诉求需要登录才能办理（游客态），API 层据此发 login_required 帧
    login_required: bool
    # 会话累计轮次。消息历史会被 trim_history 裁剪到固定窗口，无法从中反推总轮次，
    # 因此单独计数；每轮由 trim_history 自增，超过上限即停止继续调用模型。
    turn_count: int
