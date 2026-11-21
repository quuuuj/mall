"""知识库管理服务 — 把解析/清洗/分块/向量化串成完整流水线。

被 /api/admin/* 调用。处理状态经 MCP 回写 mall-server（Python 不直连 MySQL）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from document.cleaner import clean_text
from document.chunker import split_chunks
from document.parser import parse_document
from retrieval.hybrid import HybridRetriever
from storage.embeddings import embed_documents, embed_query
from storage.qdrant_store import QdrantStore
from tools.mcp_client import McpBackendClient
from retrieval.rerank import RerankClient

logger = logging.getLogger(__name__)


class KnowledgeAdminService:
    """知识库后台处理服务。"""

    def __init__(
        self,
        store: QdrantStore | None = None,
        mcp: McpBackendClient | None = None,
        retriever: HybridRetriever | None = None,
    ):
        self.store = store or QdrantStore()
        self.mcp = mcp or McpBackendClient()
        self.hybrid = retriever or HybridRetriever(self.store, RerankClient(), embed_query)

    # ─── 单文档处理 ───

    async def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """解析 → 清洗 → 分块 → 向量化 → 入库，完成后回写状态。

        payload: {docId, filePath, title, chunkSize, chunkOverlap, cleanRules}
        """
        doc_id = int(payload["docId"])
        file_path = str(payload["filePath"])
        file_type = Path(file_path).suffix.lstrip(".").lower()
        if file_type in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
            file_type = "image"

        try:
            # OCR / 解析是 CPU 密集同步操作，放线程池避免阻塞事件循环
            text = await asyncio.to_thread(parse_document, file_path, file_type)
            rules = payload.get("cleanRules") or {}
            if isinstance(rules, str):
                rules = json.loads(rules or "{}")
            text = await asyncio.to_thread(clean_text, text, rules)

            chunks = await asyncio.to_thread(
                split_chunks, text,
                int(payload.get("chunkSize") or 800),
                int(payload.get("chunkOverlap") or 100),
            )
            if not chunks:
                raise ValueError("文档解析后无有效内容")

            meta = {
                "title": payload.get("title", ""),
                "category": payload.get("category", ""),
                "tags": payload.get("tags", ""),
                "enabled": True,
            }
            for chunk in chunks:
                chunk.update(meta)

            count = await asyncio.to_thread(
                self.store.upsert_doc_chunks, doc_id, chunks, embed_documents
            )
            await self._report_status(doc_id, "READY", chunk_count=count)
            logger.info("文档 %d 处理完成，入库 %d 个分块", doc_id, count)
            return {"docId": doc_id, "status": "READY", "chunkCount": count}

        except Exception as e:
            logger.exception("文档 %d 处理失败", doc_id)
            await self._report_status(doc_id, "FAILED", error_message=str(e)[:500])
            return {"docId": doc_id, "status": "FAILED", "error": str(e)[:500]}

    async def _report_status(self, doc_id: int, status: str, **kwargs) -> None:
        try:
            await self.mcp.update_ingest_status(doc_id, status, **kwargs)
        except Exception as e:
            # 回写失败不能吞：DB 会一直停在 PROCESSING，页面永远转圈
            logger.error("文档 %d 状态回写失败: %s", doc_id, e)

    # ─── 全量重建 ───

    async def rebuild(self) -> dict[str, Any]:
        """清空向量集合，从 DB 拉启用的文档和 FAQ 全量重建。"""
        docs = await self.mcp.list_enabled_docs()
        faqs = await self.mcp.list_enabled_faqs()
        logger.info("全量重建：%d 篇文档，%d 条 FAQ", len(docs), len(faqs))

        self.store.clear_all()
        doc_count = 0
        for doc in docs:
            result = await self.ingest({
                "docId": doc["docId"],
                "filePath": self._resolve_upload_path(doc["fileName"]),
                "title": doc.get("title", ""),
                "category": doc.get("category", ""),
                "tags": doc.get("tags", ""),
                "chunkSize": doc.get("chunkSize", 800),
                "chunkOverlap": doc.get("chunkOverlap", 100),
                "cleanRules": doc.get("cleanRules", "{}"),
            })
            if result.get("status") == "READY":
                doc_count += 1

        for faq in faqs:
            self.store.upsert_faq(faq, lambda texts: [embed_query(t) for t in texts])

        return {"docs": doc_count, "faqs": len(faqs)}

    def _resolve_upload_path(self, file_name: str) -> str:
        """把 Java 侧存的相对文件名还原成绝对路径。

        本地两边工作目录不同，用配置的统一上传根目录。
        """
        root = os.getenv("KNOWLEDGE_UPLOAD_DIR", "../mall-server/upload/knowledge/")
        return str(Path(root) / file_name)

    # ─── 单块编辑 ───

    def list_chunks(self, doc_id: int, limit: int = 1000) -> dict[str, Any]:
        chunks = self.store.list_doc_chunks(doc_id, limit)
        return {"docId": doc_id, "chunks": chunks}

    async def update_chunk_content(self, doc_id: int, chunk_index: int,
                                   content: str) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("切片内容不能为空")
        # embedding 是网络调用，放线程池避免阻塞对话事件循环
        found = await asyncio.to_thread(
            self.store.update_chunk_content,
            doc_id, chunk_index, content, embed_documents,
        )
        return {"docId": doc_id, "chunkIndex": chunk_index, "updated": found}

    def set_chunk_enabled(self, doc_id: int, chunk_index: int,
                          enabled: bool) -> dict[str, Any]:
        self.store.set_chunk_enabled(doc_id, chunk_index, enabled)
        return {"docId": doc_id, "chunkIndex": chunk_index, "enabled": enabled}

    def delete_chunk(self, doc_id: int, chunk_index: int) -> dict[str, Any]:
        self.store.delete_chunk(doc_id, chunk_index)
        return {"docId": doc_id, "chunkIndex": chunk_index, "deleted": True}

    # ─── 检索 ───

    async def retrieve(self, query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """检索测试：走与线上完全一致的混合检索流程。"""
        return await self.hybrid.retrieve(query, params)
