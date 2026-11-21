"""Rerank 客户端 — 走阿里云百炼 dashscope 原生 text-rerank 接口。

注意：百炼的兼容 OpenAI 网关（/compatible-mode/v1）**没有** /rerank 路由（实测 404），
rerank 必须走 dashscope 原生端点：
    POST https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
    {"model": "...", "input": {"query": "...", "documents": [...]},
     "parameters": {"top_n": 5, "return_documents": false}}
    返回 {"output": {"results": [{"index": 0, "relevance_score": 0.9}, ...]}}

配置项：
    RERANK_URL   完整端点 URL（优先）；未设置时由 RERANK_BASE_URL 推导
    RERANK_BASE_URL  服务根地址，默认 https://dashscope.aliyuncs.com
    RERANK_API_KEY / RERANK_MODEL / RERANK_ENABLED

这是外网调用，走系统代理（trust_env 默认 True）；内网 Qdrant 客户端才需要关代理。
失败时由调用方降级为向量相似度判定，这里不吞错。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_RERANK_PATH = "/api/v1/services/rerank/text-rerank/text-rerank"


class RerankClient:
    """文本重排客户端。"""

    def __init__(
        self,
        url: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        enabled: bool | None = None,
    ):
        explicit_url = url or os.getenv("RERANK_URL", "")
        root = (base_url or os.getenv("RERANK_BASE_URL", "https://dashscope.aliyuncs.com")).rstrip("/")
        self.url = explicit_url or (root + DEFAULT_RERANK_PATH)
        self.api_key = api_key if api_key is not None else os.getenv("RERANK_API_KEY", "")
        self.model = model or os.getenv("RERANK_MODEL", "qwen3.7-text-rerank")
        env_enabled = os.getenv("RERANK_ENABLED", "true").lower() != "false"
        self.enabled = env_enabled if enabled is None else enabled

    async def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[dict[str, Any]]:
        """返回 [{"index": 原下标, "score": 相关性分数}, ...]，按分数降序。"""
        if not documents:
            return []
        if not self.enabled or not self.api_key:
            # 未配置时返回降级标记，由上层用向量相似度兜底判定
            return [{"index": i, "score": 0.0, "degraded": True} for i in range(len(documents))]

        parameters: dict[str, Any] = {"return_documents": False}
        if top_n is not None:
            parameters["top_n"] = top_n
        body = {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": parameters,
        }

        # 外网服务：走系统代理（默认 trust_env=True）
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()

        results = (payload.get("output") or {}).get("results") or payload.get("results") or []
        ranked = [
            {"index": int(r["index"]), "score": float(r.get("relevance_score") or r.get("score") or 0.0)}
            for r in results if "index" in r
        ]
        return sorted(ranked, key=lambda x: x["score"], reverse=True)
