"""把单篇处理结果组装成契约要求的 doc.json / result.json / result.csv / 缩略图。

输入是 pipeline.article.process_article 的 ArticleResult 和原 PDF；
输出写到 job 的 outbox 目录，路径规则见 API_CONTRACT.md §四~§六。
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pymupdf
from PIL import Image

from .config import ArticleResult

THUMB_MAX = 512


def doi_from_filename(path: str | Path) -> str:
    """从 `10_1371_journal_pone_0000217.pdf` 这类文件名反推 DOI。

    文件名是 DOI 压平来的，`/` 和 `.` 都变成了 `_`，无法完全还原；
    前缀按 `10.xxxx` 还原，后缀统一按 `.` 还原。
    """
    stem = Path(path).stem
    match = re.match(r"^(10_\d{4,5})_(.+)$", stem)
    if not match:
        return ""
    return match.group(1).replace("_", ".") + "/" + match.group(2).replace("_", ".")


def _page_sizes(pdf_path: str | Path, dpi: int) -> dict[int, list[int]]:
    sizes: dict[int, list[int]] = {}
    doc = pymupdf.open(pdf_path)
    try:
        for index, page in enumerate(doc):
            sizes[index + 1] = [round(page.rect.width * dpi / 72), round(page.rect.height * dpi / 72)]
    finally:
        doc.close()
    return sizes


def _thumb(src: Path, dest: Path) -> bool:
    try:
        with Image.open(src) as image:
            image = image.convert("RGB")
            image.thumbnail((THUMB_MAX, THUMB_MAX))
            dest.parent.mkdir(parents=True, exist_ok=True)
            image.save(dest, "JPEG", quality=82)
        return True
    except (OSError, ValueError):
        return False


def _figure_entry(record: dict, out_dir: Path, sizes: dict[int, list[int]]) -> dict:
    page = int(record.get("page") or 1)
    page_wh = sizes.get(page) or [0, 0]
    bbox = record.get("bbox") or []
    if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        bbox = [0, 0, page_wh[0], page_wh[1]]

    saved = record.get("saved_path") or ""
    crop_path = Path(saved).resolve() if saved else None
    thumb_path = out_dir / "thumbs" / f"{record['figure_id']}.jpg"
    has_thumb = bool(crop_path and crop_path.exists() and _thumb(crop_path, thumb_path))

    return {
        "figure_id": record["figure_id"],
        "page": page,
        "bbox": [int(v) for v in bbox],
        "page_wh": page_wh,
        "thumb_path": f"thumbs/{record['figure_id']}.jpg" if has_thumb else "",
        "crop_path": str(crop_path) if crop_path else "",
        "compare_path": "",
        "legible": has_thumb,
        "has_structure": record.get("has_structure"),
        "caption": record.get("caption", ""),
        "query_features": None,
        "candidates": [],
    }


def build_doc(job: dict, result: ArticleResult) -> dict:
    return {
        "job_id": job["job_id"],
        "schema": 2,
        "verify_status": result.verify_status,
        "doi": result.doi or None,
        "title_claim": result.title_claim,
        "title_pdf": result.title_pdf,
        "title_sim": result.title_sim,
        "pages": len(result.pages_with_figures) if result.pages_with_figures else 0,
        "source": "local",
        "checked_at": result.__dict__.get("checked_at") or "",
        "outcome": result.outcome,
        "reject_reason": result.reject_reason,
    }


def build_result(job: dict, result: ArticleResult, pdf_path: str | Path, out_dir: Path) -> dict:
    sizes = _page_sizes(pdf_path, dpi=200)
    figures = [_figure_entry(record, out_dir, sizes) for record in result.figures]
    figures.sort(key=lambda f: (f["page"], f["bbox"][1], f["bbox"][0]))
    return {
        "job_id": job["job_id"],
        "schema": 2,
        "status": "partial",
        "doc": {
            "verify_status": result.verify_status,
            "doi": result.doi or None,
            "source": "local",
        },
        "counts": {
            "figures": len(figures),
            "legible": sum(1 for f in figures if f["legible"]),
            "has_structure": sum(1 for f in figures if f["has_structure"] is True),
        },
        "figures": figures,
    }


CSV_FIELDS = [
    "job_id", "figure_id", "page", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "page_w", "page_h",
    "legible", "has_structure", "rank", "candidate_id", "phash", "ssim", "topo_match",
    "rings", "ring_sizes", "labels", "crop_path", "render_path", "compare_path", "doc_verify",
    "query_rings", "query_ring_sizes", "query_labels", "thumb_path",
]


def write_outputs(job: dict, result: ArticleResult, pdf_path: str | Path, out_dir: Path) -> dict:
    """写 doc.json / result.json / result.csv，返回写出后的 result 字典。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = build_doc(job, result)
    payload = build_result(job, result, pdf_path, out_dir)
    (out_dir / "doc.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with (out_dir / "result.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for figure in payload["figures"]:
            bbox = figure["bbox"]
            writer.writerow({
                "job_id": job["job_id"],
                "figure_id": figure["figure_id"],
                "page": figure["page"],
                "bbox_x1": bbox[0], "bbox_y1": bbox[1], "bbox_x2": bbox[2], "bbox_y2": bbox[3],
                "page_w": figure["page_wh"][0], "page_h": figure["page_wh"][1],
                "legible": str(figure["legible"]).lower(),
                "has_structure": "" if figure["has_structure"] is None else str(figure["has_structure"]).lower(),
                "crop_path": figure["crop_path"],
                "thumb_path": figure["thumb_path"],
                "doc_verify": result.verify_status,
            })
    return payload
