"""
长期记忆 — 基于 FAISS 的向量检索，承载知识库文档

设计要点：
- 嵌入由外部模型提供（默认 OpenAI 兼容 embedding 接口，模型名从 EMBEDDING_MODEL 读取），
  不再使用哈希伪向量，保证近义表述能召回同一篇文档
- 索引与文档元数据落盘，重启后直接加载；嵌入模型或维度变化时自动重建
- 检索带最低分阈值，低分视为「没查到」，交由上层给出四类工单引导，避免编造回答
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover - 缺少 faiss 时退化为余弦检索
    faiss = None

logger = logging.getLogger(__name__)

# 低于该相似度的召回视为空召回
DEFAULT_MIN_SCORE = 0.5
# 注入式嵌入器（测试用）在元数据里统一记为该标识
INJECTED_EMBEDDER_TAG = "injected"

Embedder = Callable[[str], list[float]]


class LongTermMemory:
    """长期记忆：FAISS 向量检索 + 落盘复用。

    Args:
        index_path: 索引文件路径（元数据写到同名 .meta.json）
        embedding_dim: 向量维度；为 None 时按首次嵌入结果推断
        embedder: 可注入的嵌入函数（测试用）；为 None 时按环境变量构建
        min_score: 检索最低相似度，低于该值不计入结果
    """

    def __init__(
        self,
        index_path: str = "./vector_store/faiss_index",
        embedding_dim: int | None = None,
        embedder: Embedder | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
    ):
        self.index_path = Path(index_path)
        self.metadata_path = self.index_path.with_suffix(".meta.json")
        self.min_score = min_score
        self._embedder = embedder
        # 索引落盘时记录模型标识，模型一换即视为旧索引失效。
        # 注入的嵌入器（测试用）统一记为 injected，不参与模型一致性判断。
        self._embedding_model = (
            INJECTED_EMBEDDER_TAG
            if embedder is not None
            else os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
        )
        self._dim = embedding_dim
        self._documents: list[dict[str, Any]] = []
        self._vectors: np.ndarray | None = None
        self._index = None
        self._load_from_disk()

    # ─── 嵌入 ───

    def _embed(self, text: str) -> np.ndarray:
        if self._embedder is None:
            self._embedder = self._build_default_embedder()
        vec = np.asarray(self._embedder(text), dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            raise ValueError("嵌入向量为零向量")
        vec = vec / norm
        if self._dim is None:
            self._dim = int(vec.shape[0])
        elif vec.shape[0] != self._dim:
            raise ValueError(f"嵌入维度不一致: 期望 {self._dim}, 实际 {vec.shape[0]}")
        return vec

    def _build_default_embedder(self) -> Embedder:
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY，无法构建嵌入模型")
        embeddings = OpenAIEmbeddings(
            model=self._embedding_model,
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL"),
            # 兼容 OpenAI 协议的第三方端点不支持 tiktoken 本地分词的 token 校验
            check_embedding_ctx_length=False,
        )
        return lambda text: embeddings.embed_query(text)

    # ─── 写入 ───

    def add_document(self, content: str, source: str = "", metadata: dict | None = None) -> str:
        """添加一篇文档（单条向量）。"""
        doc_id = hashlib.md5(f"{source}:{content}".encode()).hexdigest()[:12]
        vec = self._embed(content)
        self._documents.append(
            {"id": doc_id, "content": content, "source": source, "metadata": metadata or {}}
        )
        self._append_vector(vec, doc_id)
        return doc_id

    def add_documents_batch(self, documents: list[dict]) -> list[str]:
        return [
            self.add_document(
                content=doc.get("content", ""),
                source=doc.get("source", ""),
                metadata=doc.get("metadata", {}),
            )
            for doc in documents
        ]

    def _append_vector(self, vec: np.ndarray, doc_id: str) -> None:
        """把向量加入内存索引；FAISS 不可用时退化为 numpy 余弦检索。"""
        if faiss is not None:
            if self._index is None:
                self._index = faiss.IndexFlatIP(self._dim)
            self._index.add(vec.reshape(1, -1))
            return
        row = vec.reshape(1, -1)
        self._vectors = row if self._vectors is None else np.vstack([self._vectors, row])

    # ─── 检索 ───

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义检索；低于 min_score 的结果丢弃，全部丢弃即空召回。"""
        if not self._documents:
            return []

        query_vec = self._embed(query).reshape(1, -1)
        limit = min(top_k, len(self._documents))

        if self._index is not None and faiss is not None:
            scores, indices = self._index.search(query_vec, limit)
            pairs = list(zip(scores[0], indices[0]))
        elif self._vectors is not None:
            sims = self._vectors @ query_vec[0]
            order = np.argsort(-sims)[:limit]
            pairs = [(float(sims[i]), int(i)) for i in order]
        else:
            return []

        results: list[dict] = []
        for score, idx in pairs:
            if idx < 0 or idx >= len(self._documents):
                continue
            if float(score) < self.min_score:
                continue
            doc = dict(self._documents[idx])
            doc["score"] = float(score)
            results.append(doc)
        return results

    # ─── 落盘 ───

    def save(self) -> None:
        """把索引与文档元数据写到磁盘。"""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if self._index is not None and faiss is not None:
            faiss.write_index(self._index, str(self.index_path))
        elif self._vectors is not None:
            np.save(str(self.index_path) + ".npy", self._vectors)

        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "model": self._embedding_model,
                    "dim": self._dim,
                    "documents": self._documents,
                },
                f,
                ensure_ascii=False,
            )

    def _load_from_disk(self) -> bool:
        """尝试直接加载已有索引；模型或维度不匹配时视为无效，等待重建。"""
        if not self.metadata_path.exists():
            return False
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("知识库元数据损坏，将重建索引")
            return False

        if meta.get("model") != self._embedding_model:
            logger.info(
                "嵌入模型已变更（%s → %s），将重建知识库索引",
                meta.get("model"),
                self._embedding_model,
            )
            return False
        if self._dim is not None and meta.get("dim") != self._dim:
            logger.info("嵌入维度已变更，将重建知识库索引")
            return False

        documents = meta.get("documents") or []
        if self._dim is None:
            self._dim = meta.get("dim")

        try:
            if faiss is not None and self.index_path.exists():
                self._index = faiss.read_index(str(self.index_path))
            elif Path(str(self.index_path) + ".npy").exists():
                self._vectors = np.load(str(self.index_path) + ".npy")
            else:
                return False
        except Exception:
            logger.warning("知识库索引文件读取失败，将重建", exc_info=True)
            self._index = None
            self._vectors = None
            return False

        if self._index is not None and self._index.ntotal != len(documents):
            logger.warning("索引与文档数量不一致，将重建知识库索引")
            self._index = None
            return False

        self._documents = documents
        logger.info("知识库索引已从磁盘加载，文档数 %d", len(documents))
        return True

    # ─── 知识库导入 ───

    def load_knowledge_base(self, kb_dir: str, extensions: tuple[str, ...] = (".md", ".txt")) -> int:
        """从目录批量导入知识库文档（一篇文件一条向量），导入后立即落盘。

        文件首个 `# 标题` 作为文档标题写入 metadata，便于回答时标注来源。
        """
        kb_path = Path(kb_dir)
        if not kb_path.exists():
            logger.warning("知识库目录不存在: %s", kb_path)
            return 0

        count = 0
        for file_path in sorted(kb_path.rglob("*")):
            if file_path.suffix.lower() not in extensions:
                continue
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            title = _first_heading(content) or file_path.stem
            self.add_document(
                content=content,
                source=file_path.name,
                metadata={"file": str(file_path), "title": title},
            )
            count += 1

        if count:
            self.save()
        return count

    @property
    def document_count(self) -> int:
        return len(self._documents)


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
        if stripped:
            return None
    return None
