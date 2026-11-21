"""compliance_checker — 出口合规审查节点。

审查子节点本轮写入的草稿回答：
- 规则层先查禁词与 PII（毫秒级，不依赖模型）
- 通过后再交给模型做深度审查
- 不通过时撤回草稿并换成固定话术，不让违规内容留在会话历史里
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.message import RemoveMessage

from tracing.otel_config import trace_agent_call

# 合规不通过时对用户的固定话术；只如实说明，不声称已建单
BLOCKED_REPLY = "抱歉，你的请求暂时无法在线处理，请联系人工客服进一步沟通。"
# 本轮没有子节点产出时的兜底话术
FALLBACK_REPLY = "抱歉，暂时无法处理您的请求，请稍后重试。"


@dataclass
class ComplianceResult:
    """合规审查结果"""

    passed: bool
    risk_level: str  # low, medium, high, critical
    violations: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    sanitized_content: str = ""


SENSITIVE_PATTERNS = {
    "phone": r"1[3-9]\d{9}",
    "id_card": r"\d{17}[\dXx]",
    "bank_card": r"\d{16,19}",
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
}

# 订单号是 22 位（yyyyMMddHHmmss + 雪花后 8 位），长于任何 PII 类型。
# 不先剔除的话，一段订单号会同时命中 phone / id_card / bank_card 三条正则，
# 订单查询的回答会在出口被判成 PII 泄露。二十位以上的纯数字不可能是 PII，
# 按这个长度阈值剥离比按订单号格式匹配更稳。
BUSINESS_ID_PATTERN = re.compile(r"\d{20,}")

FORBIDDEN_TERMS = [
    # 绝对化用语（广告法）
    "全网最低", "史上最低", "绝对正品", "百分百正品", "假一赔万",
    "永久保修", "终身免费", "永不涨价", "保证最便宜",
    # 未经授权的赔付承诺
    "保证退款", "一定赔偿", "全额补偿",
    # 引导站外交易
    "私下转账", "加我微信", "线下交易", "绕过平台",
]

RISK_PRIORITY = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class StreamingRuleGuard:
    """流式输出的规则守门：禁词可能在分块边界被切开，逐块检查会漏。

    做法是只扣住「恰好是某个禁词前缀」的尾部（如刚吐出「保」，可能是「保证收益」的开头），
    其余文本立刻放行，因此不会牺牲首字延迟。命中禁词时标记违规并丢弃已扣住的片段，
    调用方看到 violated 后应停止向用户发文本。
    流末尾必须 flush()，放出被扣住的尾部。
    """

    def __init__(self, forbidden_terms: list[str] | None = None):
        self._terms = forbidden_terms if forbidden_terms is not None else FORBIDDEN_TERMS
        self._pending = ""
        self.violated = False

    def _prefix_hold(self) -> int:
        """最长的、同时是某禁词真前缀的 pending 后缀长度。"""
        longest = min(len(self._pending), max(map(len, self._terms), default=1) - 1)
        for size in range(longest, 0, -1):
            suffix = self._pending[-size:]
            if any(len(term) > size and term.startswith(suffix) for term in self._terms):
                return size
        return 0

    def feed(self, chunk: str) -> str:
        """喂入一块增量文本，返回可以安全发出的部分（可能为空串）。"""
        if self.violated or not chunk:
            return ""
        self._pending += chunk
        if any(term in self._pending for term in self._terms):
            self.violated = True
            self._pending = ""
            return ""
        hold = self._prefix_hold()
        cut = len(self._pending) - hold
        if cut <= 0:
            return ""
        released, self._pending = self._pending[:cut], self._pending[cut:]
        return released

    def flush(self) -> str:
        """流结束：放出滞留的尾部（违规时已经清空，返回空串）。"""
        released, self._pending = self._pending, ""
        return released


COMPLIANCE_SYSTEM_PROMPT = """你是一个电商客服回复的合规审查Agent，负责判断客服草稿能否直接发给用户。

审查维度：
1. 绝对化用语与虚假承诺（如"全网最低价"、"绝对正品"、"永久保修"）
2. 未经授权的赔付承诺（擅自承诺退款金额、赔偿标准、补偿方案）
3. 引导站外交易（私下转账、加私人微信、绕过平台下单）
4. 泄露用户 PII 或他人订单信息（手机号、身份证号、银行卡号、他人收货地址）
5. 与平台规则不符的臆造（编造不存在的政策、时效、运费规则）
6. 歧视性、侮辱性内容

注意：平台订单号是 20 位以上的纯数字串，属于用户自己的订单信息，不是 PII，不因出现订单号判定泄露。

请只返回 JSON，不要输出任何其他内容：
{
    "passed": true/false,
    "risk_level": "low|medium|high|critical",
    "violations": ["违规项描述"],
    "suggestions": ["修改建议"]
}
"""


class ComplianceCheckerAgent:
    """合规审查节点"""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def _rule_based_check(self, content: str) -> list[str]:
        """基于规则的快速检查（不依赖LLM，低延迟）"""
        violations = []

        for term in FORBIDDEN_TERMS:
            if term in content:
                violations.append(f"包含禁用表述: '{term}'")

        # 先剔除订单号这类业务标识，避免长数字串被误判成手机号/身份证/银行卡
        content = BUSINESS_ID_PATTERN.sub("", content)
        for pii_type, pattern in SENSITIVE_PATTERNS.items():
            if re.search(pattern, content):
                label = {
                    "phone": "手机号", "id_card": "身份证号",
                    "bank_card": "银行卡号", "email": "邮箱地址",
                }.get(pii_type, pii_type)
                violations.append(f"检测到PII信息泄露: {label}")

        return violations

    def _mask_pii(self, content: str) -> str:
        """对PII信息进行脱敏处理，业务标识（订单号）原样保留。

        先把业务标识换成占位符，脱敏完再还原：订单号是用户自己要看的信息，
        既不该被判成 PII，也不该被打码。
        """
        kept: list[str] = []

        def _stash(match: re.Match[str]) -> str:
            kept.append(match.group())
            return f"\x00BIZ{len(kept) - 1}\x00"

        masked = BUSINESS_ID_PATTERN.sub(_stash, content)
        for pii_type, pattern in SENSITIVE_PATTERNS.items():
            def _mask_match(match):
                text = match.group()
                if len(text) <= 4:
                    return "****"
                return text[:3] + "*" * (len(text) - 6) + text[-3:]
            masked = re.sub(pattern, _mask_match, masked)
        for index, value in enumerate(kept):
            masked = masked.replace(f"\x00BIZ{index}\x00", value)
        return masked

    @trace_agent_call("compliance_rule_check")
    async def rule_check(self, content: str) -> ComplianceResult:
        """规则引擎快速检查"""
        violations = self._rule_based_check(content)
        sanitized = self._mask_pii(content)

        if not violations:
            return ComplianceResult(passed=True, risk_level="low", sanitized_content=sanitized)

        has_pii = any("PII" in v for v in violations)
        has_forbidden = any("禁用表述" in v for v in violations)
        if has_pii and has_forbidden:
            risk_level = "critical"
        elif has_pii or has_forbidden:
            risk_level = "high"
        else:
            risk_level = "medium"

        return ComplianceResult(
            passed=False,
            risk_level=risk_level,
            violations=violations,
            sanitized_content=sanitized,
        )

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """模型偶尔会把 JSON 包在 ```json 代码块里，剥掉围栏再解析。"""
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if len(lines) < 2:
            return stripped
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @trace_agent_call("compliance_llm_check")
    async def llm_check(self, content: str) -> ComplianceResult:
        """LLM深度合规审查（处理规则引擎无法覆盖的场景）

        解析失败一律按不通过处理（fail-closed）：模型输出不可信时不应放行草稿。
        """
        messages = [
            SystemMessage(content=COMPLIANCE_SYSTEM_PROMPT),
            HumanMessage(content=f"请审查以下客服回复内容的合规性：\n\n{content}"),
        ]

        response = await self.llm.ainvoke(messages)
        try:
            parsed = json.loads(self._strip_code_fence(str(response.content)))
            if not isinstance(parsed, dict):
                raise ValueError("审查结果不是 JSON 对象")
        except (json.JSONDecodeError, ValueError):
            return ComplianceResult(
                passed=False,
                risk_level="high",
                violations=["合规审查结果无法解析，按不通过处理"],
                sanitized_content=self._mask_pii(content),
            )

        return ComplianceResult(
            passed=parsed.get("passed") is True,
            risk_level=parsed.get("risk_level", "low"),
            violations=parsed.get("violations", []),
            suggestions=parsed.get("suggestions", []),
            sanitized_content=self._mask_pii(content),
        )

    @trace_agent_call("compliance_full_check")
    async def full_check(self, content: str) -> ComplianceResult:
        """两阶段合规审查：规则引擎快速检查 → 通过后再做 LLM 深度审查"""
        rule_result = await self.rule_check(content)
        if not rule_result.passed and rule_result.risk_level in ("high", "critical"):
            return rule_result

        llm_result = await self.llm_check(content)

        return ComplianceResult(
            passed=rule_result.passed and llm_result.passed,
            risk_level=max(
                rule_result.risk_level, llm_result.risk_level,
                key=lambda r: RISK_PRIORITY.get(r, 0),
            ),
            violations=rule_result.violations + llm_result.violations,
            suggestions=llm_result.suggestions,
            sanitized_content=rule_result.sanitized_content,
        )

    @trace_agent_call("compliance_checker")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为Graph节点处理状态：审查并（必要时）替换本轮草稿"""
        messages = state.get("messages", [])
        last = messages[-1] if messages else None

        # 本轮没有子节点产出（如直达合规审查）：补一条兜底话术
        if not isinstance(last, AIMessage) or not last.content:
            return {"messages": [AIMessage(content=FALLBACK_REPLY)], "compliance_passed": True}

        result = await self.full_check(last.content)
        if result.passed:
            return {"compliance_passed": True}

        # 撤回草稿，避免违规内容留在会话历史里
        updates: list[Any] = []
        if last.id:
            updates.append(RemoveMessage(id=last.id))
        updates.append(AIMessage(content=BLOCKED_REPLY))
        return {"messages": updates, "compliance_passed": False}
