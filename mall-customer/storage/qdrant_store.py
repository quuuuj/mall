"""Qdrant 向量存储封装 — 知识库文档的 dense + sparse 双向量检索。

两个集合：
- mall_knowledge：文档分块
- mall_faq：FAQ 问题

每个 point 同时存 dense（语义）与 sparse（BM25 关键词）向量，检索时两路并行召回，
上层用 RRF 融合。中文 sparse 由 jieba 分词后按词频生成，Qdrant 侧配 IDF modifier。
"""

from __future__ import annotations

import os
import re
from typing import Any

import jieba
from qdrant_client import QdrantClient, models

KNOWLEDGE_COLLECTION = "mall_knowledge"
FAQ_COLLECTION = "mall_faq"

# 与 embedding 模型匹配的维度；text-embedding-v4 默认 1024，可用环境变量覆盖
DEFAULT_VECTOR_SIZE = int(os.getenv("EMBEDDING_DIM", "1024"))

# 中文分词停用词（标点、纯符号、常见虚词）
_STOPWORDS = set("的了和在是我有不这那个就都而及与或对一个为以于其之")

_WORD_RE = re.compile(r"[一-龥a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """中文分词：jieba 精确模式，过滤停用词与单字符（除非是英文/数字）。"""
    tokens: list[str] = []
    for word in jieba.cut(text):
        word = word.strip().lower()
        if not word or word in _STOPWORDS:
            continue
        if len(word) == 1 and not _WORD_RE.fullmatch(word):
            continue
        if not _WORD_RE.search(word):
            continue
        tokens.append(word)
    return tokens


def sparse_vector(text: str) -> models.SparseVector:
    """按词频生成 sparse 向量，索引为词的稳定哈希。

    Qdrant 的 sparse vector 要求 indices 为 uint32。用 Python hash 不稳定（随进程变），
    所以用 md5 前 8 字节取模，保证同一词跨进程映射到同一维度。
    """
    counts: dict[int, float] = {}
    for token in tokenize(text):
        idx = int.from_bytes(__import__("hashlib").md5(token.encode()).digest()[:4], "big")
        counts[idx] = counts.get(idx, 0.0) + 1.0
    if not counts:
        # Qdrant 不接受空 sparse vector；放一个占位维度，保证不影响召回
        counts[0] = 0.0001
    indices = list(counts)
    return models.SparseVector(indices=indices, values=[counts[i] for i in indices])


class QdrantStore:
    """知识库向量存储。"""

    def _build_client(self, url: str, api_key: str | None):
        """内网调用不走系统代理：本机设了 http_proxy 时 qdrant httpx 客户端会误走代理。

        trust_env=False 经 QdrantClient **kwargs 透传给底层 httpx.Client。
        """
        if url == ":memory:":
            return QdrantClient(location=":memory:", check_compatibility=False)
        return QdrantClient(
            url=url, api_key=api_key, timeout=30.0,
            trust_env=False, check_compatibility=False,
        )

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ):
        url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = api_key if api_key is not None else os.getenv("QDRANT_API_KEY") or None
        self.client = self._build_client(url, api_key)
        self.vector_size = vector_size
        self._collections_ready = False

    def _ensure_collections(self) -> None:
        """懒建集合：构造时不连 Qdrant，首次读写时才连接。

        这样服务启动不依赖 Qdrant 就绪（对话链路里闲聊/订单请求根本不用向量库），
        也避免单测 build_graph 时因本地没起 Qdrant 而整体失败。
        """
        if self._collections_ready:
            return
        for name in (KNOWLEDGE_COLLECTION, FAQ_COLLECTION):
            if self.client.collection_exists(name):
                continue
            self.client.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE),
                },
                sparse_vectors_config={
                    "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF),
                },
            )
        self._collections_ready = True

    # ─── 写入 ───

    def upsert_doc_chunks(self, doc_id: int, chunks: list[dict[str, Any]],
                          embedder) -> int:
        """覆盖某文档的全部分块（先删后写，重传幂等）。

        chunks: [{"index": int, "content": str, "title":..., "category":..., "tags":..., "enabled": bool}]
        embedder: Callable[[list[str]], list[list[float]]] 批量嵌入
        """
        self._ensure_collections()
        self.delete_doc(doc_id)
        if not chunks:
            return 0

        texts = [c["content"] for c in chunks]
        vectors = embedder(texts)
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = self._point_id(doc_id, chunk["index"])
            points.append(models.PointStruct(
                id=point_id,
                vector={
                    "dense": vector,
                    "bm25": sparse_vector(chunk["content"]),
                },
                payload={
                    "doc_id": doc_id,
                    "chunk_index": chunk["index"],
                    "content": chunk["content"],
                    "title": chunk.get("title", ""),
                    "category": chunk.get("category", ""),
                    "tags": chunk.get("tags", ""),
                    "enabled": chunk.get("enabled", True),
                    "source_type": "doc",
                },
            ))
        self.client.upsert(KNOWLEDGE_COLLECTION, points=points, wait=True)
        return len(points)

    def upsert_faq(self, faq: dict[str, Any], embedder) -> None:
        """新增或更新一条 FAQ 向量。"""
        self._ensure_collections()
        vector = embedder([faq["question"]])[0]
        point_id = int(faq["faq_id"])
        self.client.upsert(FAQ_COLLECTION, points=[models.PointStruct(
            id=point_id,
            vector={"dense": vector, "bm25": sparse_vector(faq["question"] + " " + faq["answer"])},
            payload={
                "faq_id": faq["faq_id"],
                "question": faq["question"],
                "answer": faq["answer"],
                "category": faq.get("category", ""),
                "tags": faq.get("tags", ""),
                "enabled": faq.get("enabled", True),
                "source_type": "faq",
            },
        )], wait=True)

    def set_faq_enabled(self, faq_id: int, enabled: bool) -> None:
        self._ensure_collections()
        self.client.set_payload(
            FAQ_COLLECTION, payload={"enabled": enabled},
            points=[faq_id], wait=True,
        )

    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None:
        self._ensure_collections()
        ids = self._doc_point_ids(doc_id)
        if ids:
            self.client.set_payload(
                KNOWLEDGE_COLLECTION, payload={"enabled": enabled},
                points=ids, wait=True,
            )

    def delete_doc(self, doc_id: int) -> None:
        self._ensure_collections()
        ids = self._doc_point_ids(doc_id)
        if ids:
            self.client.delete(KNOWLEDGE_COLLECTION, points_selector=models.PointIdsList(points=ids), wait=True)

    def delete_faq(self, faq_id: int) -> None:
        self._ensure_collections()
        self.client.delete(FAQ_COLLECTION, points_selector=models.PointIdsList(points=[faq_id]), wait=True)

    def clear_all(self) -> None:
        """全量重建前清空两个集合。"""
        self._ensure_collections()
        for name in (KNOWLEDGE_COLLECTION, FAQ_COLLECTION):
            self.client.delete(name, points_selector=models.MatchAll(), wait=True)

    def count(self, collection: str) -> int:
        self._ensure_collections()
        return self.client.count(collection, exact=True).count

    # ─── 单块编辑（改动只落 Qdrant，整篇重建会覆盖） ───

    def list_doc_chunks(self, doc_id: int, limit: int = 1000) -> list[dict[str, Any]]:
        """列出某文档全部分块，按 chunk_index 升序；只取 payload，不取向量。"""
        self._ensure_collections()
        result, _ = self.client.scroll(
            KNOWLEDGE_COLLECTION,
            scroll_filter=models.Filter(must=[
                models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))
            ]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        chunks = [
            {
                "docId": doc_id,
                "chunkIndex": int((p.payload or {}).get("chunk_index", 0)),
                "content": (p.payload or {}).get("content", ""),
                "enabled": bool((p.payload or {}).get("enabled", True)),
            }
            for p in result
        ]
        return sorted(chunks, key=lambda c: c["chunkIndex"])

    def update_chunk_content(self, doc_id: int, chunk_index: int, content: str,
                             embedder) -> bool:
        """改单块正文：重算 dense + bm25，保留该点的其余 payload。返回块是否存在。"""
        self._ensure_collections()
        point_id = self._point_id(doc_id, chunk_index)
        found = self.client.retrieve(
            KNOWLEDGE_COLLECTION, ids=[point_id],
            with_payload=True, with_vectors=False,
        )
        if not found:
            return False
        payload = dict(found[0].payload or {})
        payload["content"] = content
        self.client.upsert(KNOWLEDGE_COLLECTION, points=[models.PointStruct(
            id=point_id,
            vector={
                "dense": embedder([content])[0],
                "bm25": sparse_vector(content),
            },
            payload=payload,
        )], wait=True)
        return True

    def set_chunk_enabled(self, doc_id: int, chunk_index: int, enabled: bool) -> None:
        """只改单块 enabled，不动向量。"""
        self._ensure_collections()
        self.client.set_payload(
            KNOWLEDGE_COLLECTION, payload={"enabled": enabled},
            points=[self._point_id(doc_id, chunk_index)], wait=True,
        )

    def delete_chunk(self, doc_id: int, chunk_index: int) -> None:
        """只删单块，chunk_index 留空洞，其余块不动。"""
        self._ensure_collections()
        self.client.delete(
            KNOWLEDGE_COLLECTION,
            points_selector=models.PointIdsList(points=[self._point_id(doc_id, chunk_index)]),
            wait=True,
        )

    # ─── 检索 ───

    def hybrid_search(
        self,
        collection: str,
        dense_vector: list[float],
        query_text: str,
        top_n: int,
        score_threshold: float = 0.0,
        hnsw_ef: int = 64,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        """两路并行召回，返回按 RRF 融合排序的候选。

        每条返回：payload、dense_score、bm25_score、rrf_score。
        """
        self._ensure_collections()
        query_filter = None
        if enabled_only:
            query_filter = models.Filter(must=[
                models.FieldCondition(key="enabled", match=models.MatchValue(value=True))
            ])

        dense_hits = self.client.query_points(
            collection_name=collection,
            query=dense_vector,
            using="dense",
            limit=top_n,
            score_threshold=score_threshold if score_threshold > 0 else None,
            query_filter=query_filter,
            search_params=models.SearchParams(hnsw_ef=hnsw_ef),
        ).points

        sparse_hits = self.client.query_points(
            collection_name=collection,
            query=sparse_vector(query_text),
            using="bm25",
            limit=top_n,
            query_filter=query_filter,
        ).points

        return rrf_fuse(dense_hits, sparse_hits)

    # ─── 内部 ───

    @staticmethod
    def _point_id(doc_id: int, chunk_index: int) -> int:
        # doc_id 占高 32 位，chunk_index 占低 32 位；两者都不超过 uint32
        return (doc_id << 32) | chunk_index

    def _doc_point_ids(self, doc_id: int) -> list[int]:
        self._ensure_collections()
        result, _ = self.client.scroll(
            KNOWLEDGE_COLLECTION,
            scroll_filter=models.Filter(must=[
                models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))
            ]),
            limit=1000,
            with_payload=False,
            with_vectors=False,
        )
        return [p.id for p in result]


def rrf_fuse(dense_hits: list, sparse_hits: list, k: int = 60) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion：按名次融合两路结果，不需要归一化不同量纲的分数。"""
    fused: dict[Any, dict[str, Any]] = {}

    def add(hits, key: str) -> None:
        for rank, hit in enumerate(hits, start=1):
            entry = fused.setdefault(hit.id, {
                "id": hit.id,
                "payload": hit.payload or {},
                "dense_score": None,
                "bm25_score": None,
                "rrf_score": 0.0,
            })
            entry[key] = float(hit.score) if hit.score is not None else None
            entry["rrf_score"] += 1.0 / (k + rank)

    add(dense_hits, "dense_score")
    add(sparse_hits, "bm25_score")
    return sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)
