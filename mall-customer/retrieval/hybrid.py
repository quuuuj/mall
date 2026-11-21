"""混合检索流程 — FAQ 前置短路 + RAG 混合召回/RRF/精排/阈值判定。

供在线对话（knowledge_rag 节点）与检索测试台（/api/admin/retrieve）共用，
保证测试台看到的行为和线上完全一致。
"""

from __future__ import annotations

import os
from typing import Any

from storage.qdrant_store import FAQ_COLLECTION, KNOWLEDGE_COLLECTION, QdrantStore
from retrieval.rerank import RerankClient

FAQ_CONFIDENCE_THRESHOLD = float(os.getenv("FAQ_CONFIDENCE_THRESHOLD", "0.7"))
ANSWER_THRESHOLD = float(os.getenv("ANSWER_THRESHOLD", "0.6"))
FAQ_RECALL_TOP_N = int(os.getenv("FAQ_RECALL_TOP_N", "5"))
RECALL_TOP_N = int(os.getenv("RECALL_TOP_N", "10"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))
RRF_K = int(os.getenv("RRF_K", "60"))
HNSW_EF = int(os.getenv("HNSW_EF", "64"))
SCORE_THRESHOLD = float(os.getenv("RAG_MIN_SCORE", "0.5"))


class HybridRetriever:
    """混合检索编排。"""

    def __init__(self, store: QdrantStore, reranker: RerankClient, embedder):
        self.store = store
        self.reranker = reranker
        self.embedder = embedder  # Callable[[str], list[float]] 单条向量

    async def retrieve(self, query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """执行完整流程，返回判定结果 + 各阶段明细。

        返回结构：
        {
          "path": "faq" | "rag_answer" | "reject",
          "answer": str,                  # path=faq 时的标准答案
          "confidence": float,            # 决策所用分数
          "threshold": float,
          "faq_candidates": [...],
          "rag_candidates": [...],        # 含 dense/bm25/rrf/rerank 分数
          "degraded": bool,
        }
        """
        p = {**self._defaults(), **(params or {})}

        # ── FAQ 前置 ──
        faq_vector = self.embedder(query)
        faq_hits = self.store.hybrid_search(
            FAQ_COLLECTION, faq_vector, query,
            top_n=p["faq_recall_top_n"], hnsw_ef=p["hnsw_ef"],
        )
        top_faq = faq_hits[0] if faq_hits else None
        if top_faq and top_faq["rrf_score"] >= p["faq_confidence_threshold"]:
            faq_payload = top_faq["payload"]
            return {
                "path": "faq",
                "answer": faq_payload.get("answer", ""),
                "faq_id": faq_payload.get("faq_id"),
                "confidence": top_faq["rrf_score"],
                "threshold": p["faq_confidence_threshold"],
                "faq_candidates": faq_hits,
                "rag_candidates": [],
                "degraded": False,
            }

        # ── RAG 粗排 ──
        doc_vector = faq_vector  # 同一个 embedding 模型
        candidates = self.store.hybrid_search(
            KNOWLEDGE_COLLECTION, doc_vector, query,
            top_n=p["recall_top_n"], score_threshold=p["score_threshold"],
            hnsw_ef=p["hnsw_ef"],
        )
        if not candidates:
            return {
                "path": "reject",
                "answer": "",
                "confidence": 0.0,
                "threshold": p["answer_threshold"],
                "faq_candidates": faq_hits,
                "rag_candidates": [],
                "degraded": False,
                "reason": "no_recall",
            }

        # ── 精排 ──
        documents = [c["payload"].get("content", "") for c in candidates]
        ranked = await self.reranker.rerank(query, documents, top_n=p["rerank_top_n"])
        degraded = bool(ranked and ranked[0].get("degraded"))

        for item in ranked:
            idx = item["index"]
            if 0 <= idx < len(candidates):
                candidates[idx]["rerank_score"] = item["score"]

        ordered = [c for c in candidates if "rerank_score" in c]
        ordered.sort(key=lambda c: c["rerank_score"], reverse=True)
        ordered = ordered[:p["rerank_top_n"]]
        top_score = ordered[0]["rerank_score"] if ordered else 0.0

        if degraded:
            # rerank 不可用：用向量相似度兜底判定。
            # 不能用 RRF 分兜底——RRF 是名次倒数（量级 1/(k+rank)≈0.016），
            # 和 0~1 的 answer_threshold 不是一个尺度，会导致降级时全部拒答。
            # dense_score 与精排分同量级，且有实际语义，适合做降级判定。
            top_score = max(
                (c.get("dense_score") or 0.0 for c in ordered),
                default=0.0,
            )

        if top_score < p["answer_threshold"]:
            return {
                "path": "reject",
                "answer": "",
                "confidence": top_score,
                "threshold": p["answer_threshold"],
                "faq_candidates": faq_hits,
                "rag_candidates": ordered,
                "degraded": degraded,
                "reason": "low_score",
            }

        return {
            "path": "rag_answer",
            "answer": "",  # 由调用方用 ordered 片段生成回答
            "confidence": top_score,
            "threshold": p["answer_threshold"],
            "faq_candidates": faq_hits,
            "rag_candidates": ordered,
            "degraded": degraded,
        }

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "faq_recall_top_n": FAQ_RECALL_TOP_N,
            "faq_confidence_threshold": FAQ_CONFIDENCE_THRESHOLD,
            "recall_top_n": RECALL_TOP_N,
            "score_threshold": SCORE_THRESHOLD,
            "hnsw_ef": HNSW_EF,
            "rerank_top_n": RERANK_TOP_N,
            "answer_threshold": ANSWER_THRESHOLD,
            "rrf_k": RRF_K,
        }
