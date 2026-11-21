"""MCP 客户端封装 — 面向 mall-server 的轻量 MCP 访问。

Agent 统一通过 MCP 协议访问后端业务操作（如建单），不直连业务接口或持有仓储实现。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

logger = logging.getLogger(__name__)


class McpToolError(Exception):
    """MCP 工具调用失败异常。"""


@dataclass
class TicketResult:
    """建单成功后的工单信息。"""

    ticket_no: str
    category: str
    status: str
    create_time: str


class McpBackendClient:
    """基于 Streamable HTTP 的 MCP 后端客户端。

    Args:
        server_url: mall-server 的根地址或 /mcp 地址，默认读取 MALL_SERVER_URL
        token: 共享密钥，通过 X-Internal-Token 请求头传入
    """

    def __init__(self, server_url: str | None = None, token: str | None = None):
        base = (server_url or os.getenv("MALL_SERVER_URL", "http://localhost:8800")).rstrip("/")
        self.endpoint = base if base.endswith("/mcp") else f"{base}/mcp"
        self.token = token if token is not None else os.getenv("INTERNAL_API_TOKEN", "")

    def _build_http_client(self) -> httpx.AsyncClient:
        headers = {}
        if self.token:
            headers["X-Internal-Token"] = self.token
        # trust_env=False：内网服务调用不该走系统代理，否则本机设置了 http_proxy 时会转发失败
        return httpx.AsyncClient(headers=headers, timeout=15.0, trust_env=False)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """通过 MCP 调用后端工具。

        工具返回 isError 时不在 async with 内部抛异常：那会让上下文管理器退出阶段
        抛 ExceptionGroup，把真实错误（如「订单不存在」）盖成「服务不可用」。
        这里先记下错误，等连接关干净后再抛。
        """
        http_client = self._build_http_client()
        tool_error: str | None = None
        payload: dict[str, Any] = {}
        try:
            async with streamable_http_client(self.endpoint, http_client=http_client) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    if getattr(result, "is_error", False):
                        tool_error = self._extract_text(result) or f"工具 {name} 执行失败"
                    else:
                        payload = self._parse_result_data(result)
        except MCPError as e:
            logger.warning("MCP RPC 错误: %s", e)
            raise McpToolError(f"MCP 错误: {e.message}") from e
        except McpToolError:
            raise
        except Exception as e:
            logger.warning("MCP 请求异常: %s", e)
            raise McpToolError(f"服务暂时不可用: {e}") from e
        finally:
            await http_client.aclose()

        if tool_error is not None:
            raise McpToolError(tool_error)
        return payload

    async def create_ticket(
        self,
        user_id: int,
        session_id: int,
        category: int,
        summary: str,
        detail: dict[str, Any] | None = None,
        needs_info: bool = False,
        priority: int | None = None,
    ) -> TicketResult:
        """调用 create_ticket MCP 工具创建工单。"""
        args: dict[str, Any] = {
            "userId": user_id,
            "sessionId": session_id,
            "category": category,
            "summary": summary,
            "detail": json.dumps(detail or {}, ensure_ascii=False),
            "needsInfo": 1 if needs_info else 0,
        }
        if priority is not None:
            args["priority"] = priority

        data = await self.call_tool("create_ticket", args)
        ticket_no = data.get("ticketNo")
        if not ticket_no:
            raise McpToolError("工单创建返回缺少工单号")
        return TicketResult(
            ticket_no=ticket_no,
            category=data.get("category", ""),
            status=data.get("status", ""),
            create_time=data.get("createTime", ""),
        )

    async def get_order_by_sn(self, user_id: int, order_sn: str) -> dict[str, Any]:
        """按订单号查自己的订单（只读）。查不到或不属于该用户时抛 McpToolError。"""
        return await self.call_tool("get_order_by_sn", {
            "userId": user_id,
            "orderSn": order_sn,
        })

    async def list_recent_orders(self, user_id: int, limit: int = 5) -> dict[str, Any]:
        """查自己最近的订单（只读）。"""
        return await self.call_tool("list_recent_orders", {
            "userId": user_id,
            "limit": limit,
        })

    async def update_ingest_status(self, doc_id: int, status: str,
                                   chunk_count: int | None = None,
                                   error_message: str | None = None) -> dict[str, Any]:
        """回写文档处理状态（READY/FAILED）。"""
        args: dict[str, Any] = {"docId": doc_id, "status": status}
        if chunk_count is not None:
            args["chunkCount"] = chunk_count
        if error_message is not None:
            args["errorMessage"] = error_message
        return await self.call_tool("update_ingest_status", args)

    async def increment_faq_hit(self, faq_id: int) -> dict[str, Any]:
        """FAQ 命中计数 +1。"""
        return await self.call_tool("increment_faq_hit", {"faqId": faq_id})

    async def list_enabled_faqs(self) -> list[dict[str, Any]]:
        """拉启用的 FAQ（全量重建用）。"""
        data = await self.call_tool("list_enabled_faqs", {})
        return data.get("faqs", [])

    async def list_enabled_docs(self) -> list[dict[str, Any]]:
        """拉启用的文档元数据（全量重建用）。"""
        data = await self.call_tool("list_enabled_docs", {})
        return data.get("docs", [])

    def _extract_text(self, result: Any) -> str:
        content = getattr(result, "content", []) or []
        for item in content:
            text = getattr(item, "text", None)
            if text:
                return text
        return ""

    def _parse_result_data(self, result: Any) -> dict[str, Any]:
        text = self._extract_text(result)
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"raw": text}
