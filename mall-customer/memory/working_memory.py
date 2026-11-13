"""工作记忆 — 会话内的临时上下文。

按 session_id 保存在进程内存里，供 supervisor 做路由决策时参考；
随进程重启清空，不需要持久化（对话历史由 checkpointer 承担）。
"""

from __future__ import annotations

import threading
from typing import Any


class WorkingMemory:
    """按会话保存最近写入的上下文键值，超量时丢弃最早的会话。"""

    def __init__(self, max_sessions: int = 1000):
        self._context: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max_sessions = max_sessions

    def update(self, session_id: str, data: dict[str, Any]) -> None:
        """合并写入单个会话的上下文。"""
        with self._lock:
            self._context.setdefault(session_id, {}).update(data)
            while len(self._context) > self._max_sessions:
                self._context.pop(next(iter(self._context)))

    def get_context(self, session_id: str) -> dict[str, Any]:
        """读取单个会话的上下文快照。"""
        with self._lock:
            return dict(self._context.get(session_id, {}))
