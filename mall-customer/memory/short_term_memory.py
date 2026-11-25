"""
短期记忆 — 基于 LangGraph checkpointer 的会话状态持久化

Redis 可用时使用官方 AsyncRedisSaver（滑动窗口 TTL，读写均刷新过期时间），
Redis 不可用时降级为进程内 MemorySaver，保证服务可用。
对话状态（Agent State）由 checkpointer 以 thread_id=session_id 为键自动持久化，
业务代码无需手动写入消息。
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any

# Agent State 检查点：滑动窗口 TTL 30 分钟（读取/写入均刷新过期时间）
CHECKPOINT_TTL = {"default_ttl": 30, "refresh_on_read": True}


class ShortTermMemory:
    """基于 LangGraph checkpointer 的短期记忆（Redis 持久化，内存降级）"""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://:123456@localhost:6379/0")
        self._stack: AsyncExitStack | None = None
        self._checkpointer: Any | None = None

    async def setup(self) -> None:
        """初始化 checkpointer：优先 Redis，失败降级进程内 MemorySaver"""
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver

        stack = AsyncExitStack()
        try:
            checkpointer = await stack.enter_async_context(
                AsyncRedisSaver.from_conn_string(self._redis_url, ttl=CHECKPOINT_TTL)
            )
            await checkpointer.asetup()
            self._stack, self._checkpointer = stack, checkpointer
        except Exception as e:
            print(f"[ShortTermMemory] Redis checkpointer 初始化失败，降级为内存 MemorySaver: {e}")
            await stack.aclose()
            self._stack, self._checkpointer = None, MemorySaver()

    @property
    def checkpointer(self) -> Any | None:
        """传给 create_supervisor_graph 的 checkpointer（需先 setup）"""
        return self._checkpointer

    async def get_history(self, graph: Any, session_id: str, last_n: int = 20) -> list[dict]:
        """读取会话对话历史 — 从 LangGraph Agent State（checkpointer）获取

        Args:
            graph: 编译后的 StateGraph（持有 checkpointer）
            session_id: 会话 ID（即 thread_id）
            last_n: 返回最近 N 条消息
        """
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        try:
            snapshot = await graph.aget_state({"configurable": {"thread_id": session_id}})
        except Exception:
            snapshot = None

        messages = (snapshot.values or {}).get("messages", []) if snapshot else []
        role_map = {HumanMessage: "user", AIMessage: "assistant", SystemMessage: "system"}
        history = [
            {"role": role_map.get(type(msg), "system"), "content": msg.text}
            for msg in messages
        ]
        return history[-last_n:]

    async def aclose(self) -> None:
        """释放 Redis 连接（MemorySaver 降级时无操作）"""
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    async def __aenter__(self) -> ShortTermMemory:
        await self.setup()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()
