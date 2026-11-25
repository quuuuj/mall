"""文本清洗 — 按可配置开关去除解析噪声。

clean_rules 为 JSON，可选键（缺省 true）：
- strip_header_footer: 删除 3 页以上重复出现的首尾短行
- normalize_space: 折叠连续空白与换行
- strip_control: 去控制字符
- dedupe_paragraphs: 去重复段落
- strip_page_numbers: 去纯数字行
"""

from __future__ import annotations

import re
from collections import Counter

DEFAULT_RULES = {
    "strip_header_footer": True,
    "normalize_space": True,
    "strip_control": True,
    "dedupe_paragraphs": True,
    "strip_page_numbers": True,
}


def clean_text(text: str, rules: dict | None = None) -> str:
    config = {**DEFAULT_RULES, **(rules or {})}

    if config.get("strip_control"):
        text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)

    if config.get("strip_page_numbers"):
        text = "\n".join(line for line in text.splitlines() if not re.fullmatch(r"\s*\d{1,4}\s*", line))

    if config.get("strip_header_footer"):
        text = _strip_repeated_edges(text)

    if config.get("dedupe_paragraphs"):
        paragraphs = text.split("\n\n")
        deduped: list[str] = []
        for p in paragraphs:
            if not deduped or p.strip() != deduped[-1].strip():
                deduped.append(p)
        text = "\n\n".join(deduped)

    if config.get("normalize_space"):
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _strip_repeated_edges(text: str) -> str:
    """删除在多个段落首尾重复出现的短行（页眉页脚）。"""
    lines = text.splitlines()
    if len(lines) < 6:
        return text

    head = [l.strip() for l in lines[:5] if 0 < len(l.strip()) <= 60]
    tail = [l.strip() for l in lines[-5:] if 0 < len(l.strip()) <= 60]
    counts = Counter(head + tail)
    repeated = {line for line, n in counts.items() if n >= 2}
    return "\n".join(line for line in lines if line.strip() not in repeated)
