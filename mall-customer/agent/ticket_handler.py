"""ticket_handler — 工单处理节点。

机器人只做两件事：回答、建单。工单落在 MySQL（经 MCP 调用 mall-server），
Python 进程内不保存任何工单数据，服务重启后工单仍在。

用户指代一张已有工单时（「那个工单」「给它加急」），机器人从对话历史里
取出工单号并如实说明自己能做什么、不能做什么，不编造后台处理进度。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.identity import LOGIN_REQUIRED_REPLY, LoginRequiredError, to_positive_int
from tools.mcp_client import McpBackendClient, McpToolError, TicketResult
from tracing.otel_config import trace_agent_call

# 从对话历史中提取已有工单号（TK-YYYYMMDD-XXXXXX）
TICKET_RE = re.compile(r"TK-\d{8}-[A-Fa-f0-9]{6}")

# 四类工单，与 Java 侧 TicketCategoryEnum 的码值一致
CATEGORY_BY_NAME = {
    "退款退货": 1,
    "物流异常": 2,
    "发票": 3,
    "投诉建议": 4,
}

CATEGORY_LABELS = {code: name for name, code in CATEGORY_BY_NAME.items()}

# 各类工单的必填槽位，与 Java 侧 TicketServiceImpl.REQUIRED_FIELDS 保持一致。
# 缺任一字段时不硬建单，改为 needs_info=1 落库（标记待补充）并在回复里追问。
REQUIRED_SLOTS = {
    "退款退货": [("orderNo", "订单号"), ("reason", "退款/退货原因"), ("received", "是否已收到货")],
    "物流异常": [("orderNo", "订单号"), ("phenomenon", "具体异常现象")],
    "发票": [("orderNo", "订单号"), ("title", "发票抬头"), ("taxNo", "税号")],
    "投诉建议": [("description", "投诉的具体内容")],
}


@dataclass
class TicketOutcome:
    """一次工单节点的结果：给用户的回复文本 + 可供前端渲染的工单卡片。"""

    reply: str
    ticket: dict[str, Any] | None = None
    login_required: bool = False
    missing_slots: list[str] | None = None


TICKET_SYSTEM_PROMPT = """你是电商平台的客服工单助手，负责把用户的诉求整理成一张工单。

工单类型（只能选这四类之一）：
- 退款退货
- 物流异常
- 发票
- 投诉建议

请以 JSON 格式返回：
{
    "action": "create|query",
    "ticket_id": "仅 action 为 query 时填写：从对话历史中提取的已有工单号（TK- 开头）",
    "category": "退款退货|物流异常|发票|投诉建议",
    "summary": "一句话摘要，不超过 40 字",
    "slots": {
        "orderNo": "订单号，用户没给就省略",
        "reason": "退款/退货原因",
        "received": "是否已收货（true/false）",
        "phenomenon": "物流异常现象",
        "title": "发票抬头",
        "taxNo": "税号",
        "description": "投诉内容"
    }
}

规则：
- 用户提出**全新**的办理/投诉请求 → action=create
- 用户指代或追问**已有**工单（「那个工单」「它」「刚才的单子」「查一下进度」「给它加急」）→ action=query，并从对话历史中提取工单号
- slots 只填用户明确说过的字段，没提到的一律省略，不要猜测、不要补默认值
"""


class TicketHandlerAgent:
    """工单处理节点：分析诉求 → 调 MCP create_ticket 建单 → 如实回复"""

    def __init__(self, llm: ChatOpenAI, mcp_client: McpBackendClient):
        self.llm = llm
        self.mcp_client = mcp_client

    @trace_agent_call("ticket_analyze")
    async def analyze_request(self, user_message: str, history: str = "") -> dict:
        """分析用户需求，提取工单信息（history 供指代已有工单时取号）"""
        if history:
            user_content = f"对话历史:\n{history}\n\n当前用户消息: {user_message}"
        else:
            user_content = f"用户消息: {user_message}"
        response = await self.llm.ainvoke([
            SystemMessage(content=TICKET_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])

        content = (response.content or "").strip()
        # LLM 可能用 ```json 代码块包裹，剥壳后再解析
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            # 解析失败按「用户诉求原样建单」处理，由 MCP 侧字段校验兜底
            return {
                "action": "create",
                "summary": user_message[:100],
                "slots": {"description": user_message},
            }

    @trace_agent_call("ticket_create")
    async def create_ticket(self, ticket_info: dict, user_id: Any, session_id: Any) -> TicketOutcome:
        """建单并返回给用户的回复；失败时如实说明，不编造工单号"""
        category_name = (ticket_info.get("category") or "").strip()
        slots = {k: v for k, v in (ticket_info.get("slots") or {}).items() if v not in (None, "")}
        missing = self._missing_slots(category_name, slots)
        try:
            result = await self.mcp_client.create_ticket(
                user_id=to_positive_int(user_id),
                session_id=to_positive_int(session_id),
                category=self._resolve_category(ticket_info),
                summary=(ticket_info.get("summary") or "").strip()[:200] or "用户诉求",
                detail=slots,
                # 缺字段时仍落库，但标记 needsInfo，Java 侧据此跳过必填校验
                needs_info=bool(missing),
            )
        except LoginRequiredError:
            # 游客态：不是「建单失败」，而是压根办不了，引导登录而不是让用户重试
            return TicketOutcome(reply=LOGIN_REQUIRED_REPLY, login_required=True)
        except McpToolError:
            return TicketOutcome(
                reply=(
                    "抱歉，这张工单没有建成，我没有拿到工单号。\n\n"
                    "你可以稍后再发一次，或直接联系人工客服处理。"
                )
            )
        except Exception:
            return TicketOutcome(reply="抱歉，这张工单没有建成，我没有拿到工单号，请稍后再试。")

        reply = self._format_created(result, missing)
        return TicketOutcome(reply=reply, ticket=self._to_card(result), missing_slots=missing)

    def _missing_slots(self, category_name: str, slots: dict[str, Any]) -> list[str]:
        """按品类列出用户还没提供的必填字段（面向用户的中文名）。"""
        required = REQUIRED_SLOTS.get(category_name)
        if not required:
            return []
        return [label for key, label in required if not slots.get(key)]

    @staticmethod
    def _to_card(created: TicketResult) -> dict[str, Any]:
        """SSE ticket 帧的载荷（与 api/sse.py 的协议注释一致）。"""
        return {
            "ticketNo": created.ticket_no,
            "category": created.category,
            "status": created.status,
            "createTime": created.create_time,
        }

    def _resolve_category(self, ticket_info: dict) -> int:
        """模型给的类型名映射到码值；给不出来按「投诉建议」兜底，保证诉求有出口"""
        name = (ticket_info.get("category") or "").strip()
        return CATEGORY_BY_NAME.get(name, CATEGORY_BY_NAME["投诉建议"])

    def _format_created(self, created: TicketResult, missing: list[str] | None = None) -> str:
        category = created.category or "工单"
        status = created.status or "待处理"
        create_time = created.create_time or ""
        text = (
            f"工单已提交，工单号 {created.ticket_no}。\n\n"
            f"类型：{category}\n"
            f"状态：{status}\n"
            + (f"创建时间：{create_time}\n" if create_time else "")
        )
        if missing:
            text += (
                "\n这张单还缺以下信息，补给我之后人工客服能更快处理：\n"
                + "\n".join(f"- {label}" for label in missing)
            )
        else:
            text += (
                "\n人工客服会在 24 小时内响应、72 小时内给出处理方案，"
                "状态有变化我会在这里通知你。"
            )
        return text

    def _format_existing(self, ticket_no: str) -> str:
        """指代已有工单：只复述工单号与能力边界，不编造后台进度"""
        return (
            f"你提到的工单是 {ticket_no}。\n\n"
            "我这边只能提交工单，看不到后台的处理进度，也不能改优先级；"
            "进展由人工客服跟进，状态有变化会在会话里通知你。"
        )

    def _format_history(self, messages: list[Any]) -> str:
        """把对话历史（最近 10 条）格式化为文本，注入分析 prompt。"""
        lines: list[str] = []
        for m in messages[-10:]:
            role = "用户" if isinstance(m, HumanMessage) else "客服"
            content = m.content if isinstance(m.content, str) else str(m.content)
            lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines)

    def _extract_ticket_id(self, messages: list[Any]) -> str | None:
        """从对话历史（由新到旧）中提取最近出现的已有工单号。"""
        for m in reversed(messages):
            content = m.content if isinstance(m.content, str) else str(m.content)
            match = TICKET_RE.search(content)
            if match:
                return match.group(0)
        return None

    @trace_agent_call("ticket_handler")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为Graph节点处理状态"""
        messages = state.get("messages", [])
        if not messages:
            return {}

        last_message = messages[-1].content
        # 对话历史一并交给分析 LLM，否则它只看得到最新一条，无法得知用户指代的工单
        history_text = self._format_history(messages[:-1])
        ticket_info = await self.analyze_request(last_message, history_text)

        action = ticket_info.get("action", "create")
        # 双保险：LLM 没带 ticket_id 时，直接从对话历史里提取
        ticket_id = ticket_info.get("ticket_id") or self._extract_ticket_id(messages)

        if action == "query" and ticket_id:
            outcome = TicketOutcome(reply=self._format_existing(ticket_id))
        else:
            outcome = await self.create_ticket(
                ticket_info,
                user_id=state.get("user_id"),
                session_id=state.get("session_id"),
            )

        # 卡片与登录标记随 state 交给 API 层发帧；本轮没建单时显式置空，不继承上一轮
        return {
            "messages": [AIMessage(content=outcome.reply)],
            "ticket": outcome.ticket,
            "login_required": outcome.login_required,
        }
