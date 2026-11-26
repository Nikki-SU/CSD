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


DEFAULT_PARAMS = {
    "kernel_ratio": 0.007,   # 闭运算核 / 页宽
    "h_low": 4.0,            # 中块高度下限（× 字高）
    "h_high": 20.0,          # 中块高度上限（× 字高）
    "w_hi_ratio": 0.5,       # 中块宽度上限 / 页宽（排除整栏文字）
    "w_lo_ratio": 0.06,      # 中块宽度下限 / 页宽
    "area_min": 1500,        # 中块最小面积（像素）
}


def page_profile(page: "pymupdf.Page", dpi: int = 150, params: dict | None = None) -> dict:
    """返回单页的图/文特征与判定。params 可覆盖判据参数（供自动调参）。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
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
    # 闭运算把断线连成块后，结构式表现为「中等块」（参数可自动调，见 calibrate.py）。
    k = max(5, int(gray.shape[1] * p["kernel_ratio"]))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    _, _, cstats, _ = cv2.connectedComponentsWithStats(closed, 8)
    cw = cstats[1:, cv2.CC_STAT_WIDTH]
    ch = cstats[1:, cv2.CC_STAT_HEIGHT]
    ca = cstats[1:, cv2.CC_STAT_AREA]
    mid_bands = ((ch > p["h_low"] * median_h) & (ch < p["h_high"] * median_h)) if median_h else np.zeros(len(ca), bool)
    mid_blocks = int((mid_bands & (cw < gray.shape[1] * p["w_hi_ratio"]) & (cw > gray.shape[1] * p["w_lo_ratio"])
                      & (ca > p["area_min"])).sum())

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
    """MinerU 全量结果里的有图页（基准），页码从 1 起。

    实测批注：结构式/反应式多数判为 image，但部分被判成 chart / equation。
    只收 image 会漏，故一并纳入（保守基准，宁可高估有图页）。
    MinerU 的 page_idx 从 0 起，bbox 归一化到 0-1000。
    """
    visual = {"image", "chart", "equation"}
    return {int(item.get("page_idx", 0)) + 1 for item in content_list
            if item.get("type") in visual}


def compare_with_mineru(scan_rows: list[dict], baseline_pages: set[int],
                        truth_pages: set[int] | None = None) -> dict:
    """把页级判定与 MinerU 基准对照。

    注意：MinerU 不是真值——它也会把结构式判成 chart/equation。
    所以默认只报 agreement（与 MinerU 一致率），不叫 precision/recall。
    只有传入人工标注的 truth_pages 时才输出真正的 precision/recall。
    """
    predicted = {row["page"] for row in scan_rows if row["has_figure"]}
    baseline = set(baseline_pages)
    tp = len(predicted & baseline)
    fp = len(predicted - baseline)
    fn = len(baseline - predicted)
    agreement = tp / (tp + fp + fn) if (tp + fp + fn) else 1.0
    out = {
        "pages": len(scan_rows),
        "baseline_pages": len(baseline),
        "predicted_pages": len(predicted),
        "agreement": round(agreement, 4),
        "agreement_fp": fp,
        "agreement_fn": fn,
        "missed_pages": sorted(baseline - predicted),
        "saved_pages": len(scan_rows) - len(predicted),
    }
    if truth_pages is not None:
        t = set(truth_pages)
        t_tp = len(predicted & t)
        precision = t_tp / len(predicted) if predicted else 1.0
        recall = t_tp / len(t) if t else 1.0
        out["precision"] = round(precision, 4)
        out["recall"] = round(recall, 4)
    return out
