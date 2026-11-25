"""agent 包 — 工作流节点与编排。

每个文件对应图中的一个节点，节点名与模块名保持一致；
与业务无关的通用能力放 memory/ 与 tracing/，后端访问放 tools/。
"""

from __future__ import annotations

from agent.graph import build_graph

__all__ = ["build_graph"]
