"""文章级筛查：先便宜判断，必要时才整篇过一次 Mineru。

对应 DATASET_WORKFLOW v0.6 第二节：
取 PDF → 核身份 → 有没有图 → 图注判定。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import pdf_ops
from .config import Config
from .figures import load_content_list
from .llm import SemanticJudge
from .verify import crossref_metadata, verify_title

STRUCTURE_RE = re.compile(
    r"\b(scheme|reaction|synthesis|synthetic|compound|derivative|preparation|"
    r"conversion|equation|structure)\b",
    re.IGNORECASE,
)
NON_STRUCTURE_RE = re.compile(
    r"\b(plot|graph|curve|spectrum|spectra|nmr|infrared|uv|mass|chromatogram|"
    r"photograph|apparatus|cell|column|yield|kinetics|temperature dependence)\b",
    re.IGNORECASE,
)


def classify_caption(text: str) -> str:
    """structure / non_structure / ambiguous。"""
    if STRUCTURE_RE.search(text):
        return "structure"
    if NON_STRUCTURE_RE.search(text):
        return "non_structure"
    return "ambiguous"


def _mineru_captions(pdf_path: Path, out_dir: Path, config: Config) -> tuple[list[dict], str]:
    """整篇只过一次 Mineru，返回图注与 full.md；失败返回空。"""
    try:
        from .mineru import MineruClient

        client = MineruClient(config)
        parsed = client.parse_files([pdf_path], data_ids=["doc"], out_dir=out_dir / "mineru")
        root = parsed.get("doc")
        if not root:
            return [], ""
        content = load_content_list(root)
        captions = []
        for item in content:
            if item.get("type") != "image":
                continue
            caption = " ".join(item.get("image_caption") or []).strip()
            captions.append({"page": int(item.get("page_idx", 0)) + 1, "text": caption})
        md_path = root / "full.md"
        md = md_path.read_text(encoding="utf-8", errors="ignore") if md_path.exists() else ""
        return captions, md
    except Exception:
        return [], ""


def screen_article(
    pdf_path: str | Path,
    doi: str,
    out_dir: str | Path,
    config: Config | None = None,
    allow_mineru: bool = True,
) -> dict:
    config = config or Config.from_env()
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    meta = crossref_metadata(doi, mailto=config.crossref_mailto, timeout=config.timeout)
    judge = SemanticJudge(config)

    total = pdf_ops.page_count(pdf_path)
    text = pdf_ops.pages_text(pdf_path, list(range(1, min(2, total) + 1)))
    verdict = verify_title(meta["title"], text, judge)

    captions = pdf_ops.caption_lines(pdf_path)
    figures = bool(captions) or pdf_ops.has_figure_blocks(pdf_path)
    scanned = pdf_ops.is_scanned(pdf_path)

    # 没有文本层，或扫描件无法用便宜方式判断有没有图 → 整篇过一次 Mineru
    needs_mineru = (verdict["status"] == "unreadable") or (scanned and not figures)
    mineru_used = False
    if needs_mineru and allow_mineru and config.mineru_api_key:
        captions, md = _mineru_captions(pdf_path, out_dir, config)
        if md:
            mineru_used = True
            if verdict["status"] == "unreadable":
                verdict = verify_title(meta["title"], md, judge)
        figures = bool(captions)

    if verdict["status"] != "verified":
        structure, captionless, status = None, False, "doc_" + verdict["status"]
    elif not figures:
        structure, captionless, status = False, False, "no_figures"
    else:
        non_empty = [c for c in captions if c["text"].strip()]
        if non_empty:
            kinds = [classify_caption(c["text"]) for c in non_empty]
            if "structure" in kinds:
                structure, captionless, status = True, False, "structure"
            else:
                # 图注没能证明是结构式，就不算结构式；不设「不确定」
                structure, captionless, status = False, False, "non_structure"
        else:
            structure, captionless, status = None, True, "captionless"

    return {
        "doi": doi,
        "verify_status": verdict["status"],
        "title_sim": verdict["similarity"],
        "has_figures": bool(figures),
        "captionless": bool(captionless),
        "structure": structure,
        "status": status,
        "mineru_used": mineru_used,
        "needs_mineru": bool(needs_mineru and not mineru_used),
        "figure_pages": sorted({c["page"] for c in captions}),
    }
