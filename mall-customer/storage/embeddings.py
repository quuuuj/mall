"""Embedding 封装 — 统一走 OpenAI 兼容接口，供入库与检索共用。

向量化发生在两个地方：文档入库（批量）与在线检索（单条），必须用同一个模型，
否则向量空间不一致。这里把构建逻辑收在一处。
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from langchain_openai import OpenAIEmbeddings


@lru_cache(maxsize=1)
def _embeddings() -> OpenAIEmbeddings:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY，无法构建 embedding 模型")
    return OpenAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
        check_embedding_ctx_length=False,
    )


def embed_query(text: str) -> list[float]:
    """单条查询向量（L2 归一化，与入库一致）。"""
    return _normalize(_embeddings().embed_query(text))


def embed_documents(texts: list[str]) -> list[list[float]]:
    """批量文档向量。"""
    return [_normalize(v) for v in _embeddings().embed_documents(texts)]


def _normalize(vector: list[float]) -> list[float]:
    vec = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm == 0:
        raise ValueError("嵌入向量为零向量")
    return (vec / norm).tolist()
