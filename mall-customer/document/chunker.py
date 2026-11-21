"""文本分块 — 段落优先，超长段落滑动切分。

输出每块带 index / content，供向量化入库使用。
"""

from __future__ import annotations

import re


def split_chunks(text: str, chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    """按段落优先切分；超长段落按字符滑窗切分，窗口间保留 overlap。

    chunk_size / overlap 单位为字符，overlap 会被约束到 [0, chunk_size//2]。
    """
    if chunk_size < 100:
        raise ValueError("chunk_size 不能小于 100")
    overlap = max(0, min(overlap, chunk_size // 2))

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[dict] = []

    def emit(content: str) -> None:
        if content.strip():
            chunks.append({"index": len(chunks), "content": content.strip()})

    buffer = ""
    for para in paragraphs:
        if len(para) <= chunk_size:
            candidate = f"{buffer}\n\n{para}".strip() if buffer else para
            if len(candidate) <= chunk_size:
                buffer = candidate
                continue
            if buffer:
                emit(buffer)
                buffer = para
                continue

        # 超长段落：先冲掉缓冲，再滑窗
        if buffer:
            emit(buffer)
            buffer = ""
        step = chunk_size - overlap
        for start in range(0, len(para), step):
            piece = para[start:start + chunk_size]
            if start + chunk_size >= len(para):
                emit(piece)
                break
            emit(piece)

    if buffer:
        emit(buffer)
    return chunks
