"""order_query — 订单只读查询节点。

只做两件事：按订单号查单、查最近的订单。数据全部来自 mall-server 的 MCP 只读工具
（`get_order_by_sn` / `list_recent_orders`），归属由后端按 userId 过滤 ——
Agent 传错号只会查不到，不会查到别人的单。

回答文本由代码按工具返回值拼装，不让模型复述：订单金额、状态、时间这类事实
一旦经过模型转述就有被改写或编造的空间，而这里没有任何需要「润色」的内容。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.identity import LOGIN_REQUIRED_REPLY, LoginRequiredError, to_positive_int
from tools.mcp_client import McpBackendClient, McpToolError
from tracing.otel_config import trace_agent_call

# 订单号形如 202605010001 或 PO202605010001，取连续 8 位以上数字串
ORDER_SN_RE = re.compile(r"\b[A-Za-z]{0,3}\d{8,}\b")

RECENT_ORDERS_LIMIT = 5

ORDER_QUERY_PROMPT = """判断用户这条消息要查什么，只返回 JSON：
{
  "intent": "by_sn|recent",
  "order_sn": "intent 为 by_sn 时填写用户给出的订单号，否则省略"
}

规则：
- 用户给出订单号（8 位以上数字，可能带前缀）→ intent=by_sn
- 用户问「我最近买了什么」「我有哪些订单」「查下我的订单」这类没给号码的 → intent=recent
- 只输出 JSON，不要解释
"""


@dataclass
class OrderQueryOutcome:
    reply: str
    login_required: bool = False


class OrderQueryAgent:
    """订单查询节点：抽订单号 → 调 MCP 只读工具 → 代码拼装回答"""

    def __init__(self, llm: ChatOpenAI, mcp_client: McpBackendClient):
        self.llm = llm
        self.mcp_client = mcp_client

    @trace_agent_call("order_query_analyze")
    async def analyze(self, user_message: str) -> dict[str, Any]:
        """判断是按单号查还是查最近订单；解析失败退回正则判断"""
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=ORDER_QUERY_PROMPT),
                HumanMessage(content=f"用户消息: {user_message}"),
            ])
            content = (response.content or "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
            parsed = json.loads(content)
            if isinstance(parsed, dict) and parsed.get("intent") in ("by_sn", "recent"):
                return parsed
        except Exception:
            pass

        match = ORDER_SN_RE.search(user_message)
        if match:
            return {"intent": "by_sn", "order_sn": match.group(0)}
        return {"intent": "recent"}

    @trace_agent_call("order_query")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为 Graph 节点处理状态"""
        messages = state.get("messages", [])
        if not messages:
            return {}

        try:
            user_id = to_positive_int(state.get("user_id"))
        except LoginRequiredError:
            return {
                "messages": [AIMessage(content=LOGIN_REQUIRED_REPLY)],
                "ticket": None,
                "login_required": True,
            }

        user_message = messages[-1].content
        plan = await self.analyze(user_message)
        outcome = await self._query(plan, user_id)

        return {
            "messages": [AIMessage(content=outcome.reply)],
            "ticket": None,
            "login_required": outcome.login_required,
        }

    async def _query(self, plan: dict[str, Any], user_id: int) -> OrderQueryOutcome:
        try:
            if plan.get("intent") == "by_sn" and plan.get("order_sn"):
                order = await self.mcp_client.get_order_by_sn(user_id, str(plan["order_sn"]).strip())
                return OrderQueryOutcome(reply=self._format_order(order))
            data = await self.mcp_client.list_recent_orders(user_id, RECENT_ORDERS_LIMIT)
            return OrderQueryOutcome(reply=self._format_recent(data))
        except McpToolError as e:
            # 「查不到」与「服务不可用」对用户是两回事，分开说
            if "不存在" in str(e) or "not exist" in str(e).lower():
                return OrderQueryOutcome(reply=self._not_found_reply())
            return OrderQueryOutcome(
                reply="抱歉，订单查询暂时不可用，我没有拿到你的订单信息。\n\n"
                      "你可以稍后再试，或在门户「我的订单」里查看。"
            )
        except Exception:
            return OrderQueryOutcome(reply="抱歉，订单查询暂时不可用，请稍后再试。")

    def _not_found_reply(self) -> str:
        return (
            "没有查到这个订单号对应的订单。\n\n"
            "可能的原因：订单号记错了、这笔订单不属于当前账号。你可以核对后重新发给我，"
            "或在门户「我的订单」里查看。"
        )

    def _format_order(self, order: dict[str, Any]) -> str:
        lines = [
            f"订单 {order.get('orderSn', '')} 当前状态：{order.get('status') or '未知'}。",
            "",
            f"下单时间：{self._or_dash(order.get('createTime'))}",
        ]
        if order.get("paymentTime"):
            lines.append(f"支付时间：{order['paymentTime']}")
        if order.get("deliveryTime"):
            lines.append(f"发货时间：{order['deliveryTime']}")
        if order.get("receiptTime"):
            lines.append(f"签收时间：{order['receiptTime']}")
        items = order.get("items") or []
        if items:
            lines.append("")
            lines.append("商品：")
            lines.extend(
                f"- {item.get('productName')} × {item.get('amount')}（¥{self._money(item.get('price'))}）"
                for item in items
            )
        lines.append("")
        lines.append(f"订单金额：¥{self._money(order.get('totalAmount'))}")
        # 库里没有运单号，只能说到发货这一步，不能编造物流轨迹
        if order.get("status") == "已发货":
            lines.append("")
            lines.append("包裹已发出，具体物流轨迹请以快递员或快递公司查询结果为准。")
        return "\n".join(lines)

    def _format_recent(self, data: dict[str, Any]) -> str:
        orders = data.get("orders") or []
        if not orders:
            return "你名下还没有订单记录。"

        lines = [f"你最近有 {len(orders)} 笔订单：", ""]
        for index, order in enumerate(orders, start=1):
            names = "、".join(
                f"{item.get('productName')} × {item.get('amount')}"
                for item in (order.get("items") or [])
            ) or "商品信息缺失"
            lines.append(
                f"{index}. {order.get('orderSn', '')}｜{order.get('status') or '未知'}｜"
                f"¥{self._money(order.get('totalAmount'))}｜{self._or_dash(order.get('createTime'))}"
            )
            lines.append(f"   {names}")
        lines.append("")
        lines.append("想看某一笔的详情，把订单号发我。")
        return "\n".join(lines)

    @staticmethod
    def _money(value: Any) -> str:
        """金额统一两位小数：工具返回的是 JSON 数字，89.0 直接拼进文本会丢精度位。"""
        if value is None:
            return "—"
        try:
            return f"{Decimal(str(value)):.2f}"
        except (InvalidOperation, ValueError):
            return str(value)

    @staticmethod
    def _or_dash(value: Any) -> str:
        return value if value else "—"
