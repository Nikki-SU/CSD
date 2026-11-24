"""页级判断：这一页有没有图，不调用 MinerU。

文本层能读到图注（Fig./Scheme/Chart）就直接判有图；
读不到文本的扫描页，按 150 dpi 渲染后用连通域估计字高，
存在高度超过字高 2.5 倍的连通块，就判这页有图。

用途：只把「有图页」送 MinerU，避免整篇消耗解析额度。
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import cv2
import numpy as np
import pymupdf

# 只认行首的图注；正文里的「as shown in Fig. 2」不算这一页有图
CAPTION_RE = re.compile(r"(?im)^\s*(fig\.?|figure|scheme|chart)\b")


def page_profile(page: "pymupdf.Page", dpi: int = 150) -> dict:
    """返回单页的图/文特征与判定。"""
    started = time.time()
    text = page.get_text() or ""
    pix = page.get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else arr
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, 8)

    heights = stats[1:, cv2.CC_STAT_HEIGHT]
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = areas > 15
    median_h = float(np.median(heights[keep])) if keep.any() else 0.0
    big_blocks = int(((heights > 2.5 * median_h) & (areas > 800)).sum()) if median_h else 0

    # 老扫描件结构式夹在正文里、无图注、键线是断的：原始连通域抓不到。
    # 闭运算把断线连成块后，结构式表现为「中等块」：宽<栏宽一半、高约 3~10 行字高。
    # 判据来自实图量测（1937 JACS 第1页 3 个结构式均命中），非拍脑袋。
    k = max(5, int(gray.shape[1] * 0.007))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    _, _, cstats, _ = cv2.connectedComponentsWithStats(closed, 8)
    cw = cstats[1:, cv2.CC_STAT_WIDTH]
    ch = cstats[1:, cv2.CC_STAT_HEIGHT]
    ca = cstats[1:, cv2.CC_STAT_AREA]
    mid_bands = (ch > 4 * median_h) & (ch < 20 * median_h) if median_h else np.zeros(len(ca), bool)
    mid_blocks = int((mid_bands & (cw < gray.shape[1] * 0.5) & (cw > gray.shape[1] * 0.06)
                      & (ca > 1500)).sum())

    has_text = bool(text.strip())
    caption_hit = bool(CAPTION_RE.search(text))
    return {
        "page": int(page.number) + 1,
        "chars": len(text),
        "images": len(page.get_images(full=True)),
        "drawings": len(page.get_drawings()),
        "median_line_h": round(median_h, 1),
        "big_blocks": big_blocks,
        "mid_blocks": mid_blocks,
        "caption_hit": caption_hit,
        "has_figure": bool(big_blocks or mid_blocks or caption_hit),
        "ms": round((time.time() - started) * 1000),
    }


def scan_pdf(pdf: str | Path, dpi: int = 150) -> list[dict]:
    doc = pymupdf.open(pdf)
    try:
        rows = [page_profile(page, dpi=dpi) for page in doc]
    finally:
        doc.close()
    for row in rows:
        row["pdf"] = str(pdf)
    return rows


def mineru_figure_pages(content_list: list[dict]) -> set[int]:
    """MinerU 全量结果里的有图页（基准），页码从 1 起。"""
    return {int(item.get("page_idx", 0)) + 1 for item in content_list if item.get("type") == "image"}


def compare(scan_rows: list[dict], baseline_pages: set[int]) -> dict:
    """把页级判定与 MinerU 全量基准对照。"""
    predicted = {row["page"] for row in scan_rows if row["has_figure"]}
    truth = set(baseline_pages)
    tp = len(predicted & truth)
    fp = len(predicted - truth)
    fn = len(truth - predicted)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "pages": len(scan_rows),
        "baseline_pages": len(truth),
        "predicted_pages": len(predicted),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "missed_pages": sorted(truth - predicted),
        "saved_pages": len(scan_rows) - len(predicted),
    }
