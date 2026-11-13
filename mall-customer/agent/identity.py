"""identity — 会话身份校验。

工单与订单节点都要确认 state 里带的是有效用户标识：
游客态拿不到用户 ID 时不该假装办成，而应引导登录。这段逻辑原先在 ticket_handler 里，
订单查询复用同一套判断后单独拆出来，避免一个节点去 import 另一个节点的私有函数。
"""

from __future__ import annotations

from typing import Any

from tools.mcp_client import McpToolError

# 游客态（无有效 user_id / session_id）时的回复；前端据 login_required 帧给登录入口
LOGIN_REQUIRED_REPLY = "这类诉求需要登录后才能办理，登录后我可以直接帮你建单。"


class LoginRequiredError(McpToolError):
    """游客态无法办理：缺有效的 user_id / session_id。"""


def to_positive_int(value: Any) -> int:
    """把 state 里的 user_id / session_id 规范成正整数，转不了就抛 LoginRequiredError。

    游客会话没有用户 ID、会话也还没在 MySQL 建行，此时不应假装办成功，
    也不该让用户「稍后重试」——诉求本身需要登录，交给前端弹登录入口。
    """
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise LoginRequiredError(f"缺少有效的用户或会话标识: {value!r}") from None
    if number <= 0:
        raise LoginRequiredError(f"缺少有效的用户或会话标识: {value!r}")
    return number
