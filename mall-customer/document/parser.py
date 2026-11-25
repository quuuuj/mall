"""文档解析 — 按文件类型分派，输出纯文本。

支持：PDF（文本层直取 / 扫描件走 OCR）、DOCX、MD、TXT、HTML、图片。
扫描件判断：PDF 提取文本过少时逐页渲染走 PaddleOCR。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 每页文本少于该字符数视为无文本层，走 OCR
MIN_TEXT_PER_PAGE = 20


def parse_document(file_path: str | Path, file_type: str) -> str:
    """按类型解析文档，返回完整文本。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    parsers = {
        "md": _parse_plain,
        "txt": _parse_plain,
        "html": _parse_html,
        "htm": _parse_html,
        "docx": _parse_docx,
        "pdf": _parse_pdf,
        "image": _parse_image,
    }
    parser = parsers.get(file_type.lower())
    if parser is None:
        raise ValueError(f"不支持的文件类型: {file_type}")
    return parser(path)


def _parse_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_html(path: Path) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def _parse_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _parse_pdf(path: Path) -> str:
    """先试文本层，太少则逐页渲染走 OCR。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) >= MIN_TEXT_PER_PAGE * len(reader.pages):
        return text

    logger.info("PDF 无有效文本层（%d 页），转 OCR: %s", len(reader.pages), path.name)
    return _ocr_pdf(path)


def _parse_image(path: Path) -> str:
    return _ocr_images([path])


def _ocr_pdf(path: Path) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    images = [page.render(scale=2).to_pil() for page in pdf]
    return _ocr_images(images)


def _ocr_images(images: list) -> str:
    """PaddleOCR 懒加载（模型大，只有扫描件才初始化）。

    3.x 与 2.x API 不同，这里按实际能力分派：
    - 3.x：PaddleOCR(lang=...) + predict()，结果在 result.json["res"]["rec_texts"]；
      部分 CPU 上 oneDNN 推理会崩，用 PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=false 关闭。
    - 2.x：PaddleOCR(use_angle_cls=True, show_log=False) + ocr(cls=True)，
      结果为 [[(box, (text, score)), ...], ...]。
    模型缓存路径用 PADDLE_HOME 指定，避免重建镜像重复下载。
    """
    import inspect
    import numpy as np

    # oneDNN（mkldnn）推理在部分 CPU 上会抛 ArrayAttribute 不支持的异常，
    # 默认关掉。paddlex 在模块加载时读这个 flag，必须在 import paddleocr 前设置。
    import os
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "false")

    from paddleocr import PaddleOCR

    params = inspect.signature(PaddleOCR.__init__).parameters
    is_v3 = "predict" in dir(PaddleOCR) and "lang" in params and "use_angle_cls" not in params

    if is_v3:
        ocr = PaddleOCR(lang=os.getenv("OCR_LANG", "ch"))
    else:
        ocr = PaddleOCR(lang=os.getenv("OCR_LANG", "ch"),
                        use_angle_cls=True, show_log=False)

    texts: list[str] = []
    for image in images:
        # PaddleOCR 只接受 numpy 数组或路径，不接受 PIL 对象
        payload = np.asarray(image) if hasattr(image, "size") else image
        if is_v3:
            lines: list[str] = []
            for result in ocr.predict(payload) or []:
                data = getattr(result, "json", {}) or {}
                res = data.get("res") or data
                lines.extend(str(t) for t in (res.get("rec_texts") or []))
        else:
            lines = []
            for page in ocr.ocr(payload, cls=True) or []:
                for item in page or []:
                    if len(item) >= 2 and item[1]:
                        lines.append(str(item[1][0]))
        texts.append("\n".join(lines))
    return "\n\n".join(texts)
