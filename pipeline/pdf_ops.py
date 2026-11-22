"""PDF 取页与渲染：不判断结构式，只负责「哪几页有图 / 把页渲染成图」。"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

# 图注行：Fig. 1 / Figure 3 / Scheme 2 / Chart IV ...
CAPTION_RE = re.compile(
    r"^\s*(?:fig(?:ure)?|scheme|chart)\.?\s*[0-9]+[A-Za-z]?\b",
    re.IGNORECASE | re.MULTILINE,
)


def page_count(pdf_path: str | Path) -> int:
    with pymupdf.open(str(pdf_path)) as doc:
        return doc.page_count


def page_text(pdf_path: str | Path, page_no: int) -> str:
    """page_no 从 1 起。"""
    with pymupdf.open(str(pdf_path)) as doc:
        return doc[page_no - 1].get_text("text")


def pages_text(pdf_path: str | Path, pages: list[int]) -> str:
    return "\n\n".join(page_text(pdf_path, p) for p in pages)


def has_text_layer(pdf_path: str | Path, page_no: int = 1) -> bool:
    return len(page_text(pdf_path, page_no).strip()) >= 100


def find_caption_pages(pdf_path: str | Path) -> list[int]:
    """按文本层找带图注的页。

    扫描件每页本身就是一张图，不能拿「有没有图像对象」当判据，所以这里看
    「有没有 Fig./Scheme/Chart 图注」。文本层缺失时返回空列表，由调用方决定整篇转。
    """
    hits: list[int] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text and CAPTION_RE.search(text):
                hits.append(index)
    return hits


def render_page(pdf_path: str | Path, page_no: int, out_path: str | Path, dpi: int = 200) -> Path:
    """把整页按 dpi 渲染成 PNG。page_no 从 1 起。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(str(pdf_path)) as doc:
        pixmap = doc[page_no - 1].get_pixmap(dpi=dpi)
        pixmap.save(str(out_path))
    return out_path


def render_pages(
    pdf_path: str | Path,
    pages: list[int],
    out_dir: str | Path,
    dpi: int = 200,
) -> dict[int, Path]:
    out_dir = Path(out_dir)
    rendered: dict[int, Path] = {}
    for page_no in pages:
        rendered[page_no] = render_page(
            pdf_path, page_no, out_dir / f"p{page_no:03d}.png", dpi=dpi
        )
    return rendered


def select_pages(pdf_path: str | Path, title_pages: int = 2) -> tuple[list[int], str]:
    """返回要送 Mineru 的页码与选择方式。

    - 文本层能定位图注：只送首页（核标题）+ 有图注的页。
    - 定位不到：无法预筛，整篇都送。
    """
    total = page_count(pdf_path)
    caption_pages = find_caption_pages(pdf_path)
    if caption_pages:
        pages = sorted(set(range(1, min(title_pages, total) + 1)) | set(caption_pages))
        return pages, "captions"
    return list(range(1, total + 1)), "all_pages"
