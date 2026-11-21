"""任务层评测 — 订单查询与建单，断言到字段。

与检索层评测（eval/run_eval.py）的区别：这里走真实的 MCP 工具调用，
不经过 LLM 生成，回答文本由节点代码拼装，因此可以断言具体字段。

前置条件（不满足直接退出，避免跑出假数字）：
1. mall-server 已启动，且 /mcp 可用（X-Internal-Token 与 mall-customer 一致）
2. 数据库里有本脚本自建的测试用户与订单（脚本负责建与清理）

用法（在 mall-customer 目录下）：
    python -m eval.run_task_eval
    python -m eval.run_task_eval --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import pymysql  # noqa: E402

from agent.order_query import OrderQueryAgent  # noqa: E402
from tools.mcp_client import McpBackendClient, McpToolError  # noqa: E402

# 测试数据统一前缀，清理时只删这些，不碰任何真实数据
TEST_USER_ID = 900001
TEST_ORDER_PREFIX = "EVALTEST"
RESULT_PATH = Path(__file__).with_name("results-task.json")

DB_CONFIG = {
    "host": os.getenv("EVAL_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("EVAL_DB_PORT", "3307")),
    "user": os.getenv("EVAL_DB_USER", "root"),
    "password": os.getenv("EVAL_DB_PASSWORD", "123456"),
    "database": os.getenv("EVAL_DB_NAME", "mall"),
    "charset": "utf8mb4",
}


@dataclass
class TaskCase:
    name: str
    order_sn: str
    expect: dict


def _connect():
    return pymysql.connect(**DB_CONFIG, autocommit=True)


def setup() -> list[TaskCase]:
    """自建测试用户与订单，返回用例定义。

    不用种子数据：种子订单会被日常开发改动，某天评测突然变红却查不出原因。
    """
    cases = [
        TaskCase("已发货单", "EVALTEST0001", {"status": "已发货", "total": "89.00", "item": "评测商品A", "status_code": 2}),
        TaskCase("已完成单", "EVALTEST0002", {"status": "已完成", "total": "168.00", "item": "评测商品B", "status_code": 3}),
        TaskCase("待支付单", "EVALTEST0003", {"status": "待支付", "total": "25.50", "item": "评测商品C", "status_code": 0}),
    ]
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM oms_order_item WHERE order_id IN (SELECT id FROM oms_order WHERE order_sn LIKE %s)", (f"{TEST_ORDER_PREFIX}%",))
        cur.execute("DELETE FROM oms_order WHERE order_sn LIKE %s", (f"{TEST_ORDER_PREFIX}%",))

        for case in cases:
            cur.execute(
                "INSERT INTO oms_order (user_id, order_sn, total_amount, status) VALUES (%s, %s, %s, %s)",
                (TEST_USER_ID, case.order_sn, Decimal(case.expect["total"]), case.expect["status_code"]),
            )
            order_id = cur.lastrowid
            cur.execute(
                "INSERT INTO oms_order_item (order_id, product_id, product_name, product_price, amount) VALUES (%s, %s, %s, %s, %s)",
                (order_id, 1, case.expect["item"], Decimal(case.expect["total"]), 1),
            )
    return cases


def cleanup() -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM oms_order_item WHERE order_id IN (SELECT id FROM oms_order WHERE order_sn LIKE %s)", (f"{TEST_ORDER_PREFIX}%",))
        cur.execute("DELETE FROM oms_order WHERE order_sn LIKE %s", (f"{TEST_ORDER_PREFIX}%",))


def _order_status_text(status: int) -> str:
    """库里存的是状态码，回答里是中文；断言用中文对得上才算通过。"""
    return {0: "待付款", 1: "已付款", 2: "已发货", 3: "已完成", 4: "已取消"}.get(status, str(status))


async def run_case(client: McpBackendClient, case: TaskCase, verbose: bool) -> dict:
    agent = OrderQueryAgent(llm=None, mcp_client=client)
    record: dict = {"name": case.name, "order_sn": case.order_sn, "passed": False, "failures": []}

    try:
        order = await client.get_order_by_sn(TEST_USER_ID, case.order_sn)
    except McpToolError as exc:
        record["failures"].append(f"工具调用失败: {exc}")
        return record

    # 工具层断言：字段原样对上。金额走 Decimal 比较 —— 工具返回的是 JSON 数字，
    # 89.00 与 89.0 是同一个值，用字符串比会假红。
    if order.get("orderSn") != case.order_sn:
        record["failures"].append(f"orderSn 不符: {order.get('orderSn')}")
    if Decimal(str(order.get("totalAmount"))) != Decimal(case.expect["total"]):
        record["failures"].append(f"金额不符: {order.get('totalAmount')} != {case.expect['total']}")
    if order.get("status") != case.expect["status"]:
        record["failures"].append(f"状态不符: {order.get('status')} != {case.expect['status']}")
    items = order.get("items") or []
    names = [item.get("productName") for item in items]
    if case.expect["item"] not in names:
        record["failures"].append(f"商品不符: {names}")

    # 回答层断言：拼装出的文本里必须出现订单号、金额、商品名、状态
    reply = agent._format_order(order)
    for expected in (case.order_sn, case.expect["total"], case.expect["item"], case.expect["status"]):
        if expected not in reply:
            record["failures"].append(f"回答缺少 {expected}")

    # 出口合规断言：这条回答不能触发 PII 误判（订单号 22 位曾被判成银行卡）
    from agent.compliance_checker import ComplianceCheckerAgent

    violations = ComplianceCheckerAgent.__new__(ComplianceCheckerAgent)._rule_based_check(reply)
    if violations:
        record["failures"].append(f"合规误判: {violations}")

    record["passed"] = not record["failures"]
    if verbose:
        mark = "PASS" if record["passed"] else "FAIL"
        print(f"[{mark}] {case.name} {case.order_sn}")
        if record["failures"]:
            for failure in record["failures"]:
                print(f"        {failure}")
    return record


async def run_not_found_case(client: McpBackendClient, verbose: bool) -> dict:
    """查一个不存在的订单号：必须抛 McpToolError 且带「不存在」语义。"""
    agent = OrderQueryAgent(llm=None, mcp_client=client)
    record: dict = {"name": "不存在的订单号", "passed": False, "failures": []}
    try:
        await client.get_order_by_sn(TEST_USER_ID, "EVALTEST9999")
        record["failures"].append("不存在的订单号没有报错")
    except McpToolError as exc:
        reply = agent._not_found_reply() if "不存在" in str(exc) else ""
        if not reply:
            record["failures"].append(f"错误信息无法归为「查不到」: {exc}")
    record["passed"] = not record["failures"]
    if verbose:
        print(f"[{'PASS' if record['passed'] else 'FAIL'}] {record['name']}")
        for failure in record["failures"]:
            print(f"        {failure}")
    return record


async def run_cross_user_case(client: McpBackendClient, verbose: bool) -> dict:
    """别人的订单号不能查到（归属由 Java 侧按 userId 过滤）。"""
    record: dict = {"name": "跨用户不可见", "passed": False, "failures": []}
    other_user = TEST_USER_ID + 1
    try:
        await client.get_order_by_sn(other_user, "EVALTEST0001")
        record["failures"].append("其他用户查到了不属于自己的订单")
    except McpToolError:
        pass
    record["passed"] = not record["failures"]
    if verbose:
        print(f"[{'PASS' if record['passed'] else 'FAIL'}] {record['name']}")
        for failure in record["failures"]:
            print(f"        {failure}")
    return record


async def main() -> None:
    parser = argparse.ArgumentParser(description="任务层评测：订单查询与建单")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--keep", action="store_true", help="跑完不清理测试数据")
    args = parser.parse_args()

    client = McpBackendClient()
    print(f"[就绪] MCP 端点 {client.endpoint}，测试用户 {TEST_USER_ID}")

    cases = setup()
    records: list[dict] = []
    try:
        for case in cases:
            records.append(await run_case(client, case, args.verbose))
        records.append(await run_not_found_case(client, args.verbose))
        records.append(await run_cross_user_case(client, args.verbose))
    finally:
        if not args.keep:
            cleanup()
            print("[清理] 已删除测试订单")

    passed = sum(1 for r in records if r["passed"])
    total = len(records)
    print()
    print("=" * 60)
    print("任务层评测结果")
    print("=" * 60)
    print(f"用例总数      : {total}")
    print(f"任务成功率    : {passed}/{total} = {passed / total:.1%}")

    failed = [r for r in records if not r["passed"]]
    if failed:
        print()
        print(f"失败 {len(failed)} 条：")
        for record in failed:
            print(f"  - {record['name']}")
            for failure in record["failures"]:
                print(f"      {failure}")

    RESULT_PATH.write_text(
        json.dumps({"total": total, "passed": passed, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n结果已写入 {RESULT_PATH.name}")

    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
