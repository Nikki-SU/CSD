"""诊断：看轮廓被分成"字"还是"线"，中间量一图可见。

为什么要这个：特征方向反了（全显式碳的图 multi_token_ratio 反而低），
必须看具体轮廓的几何量与判定分支，而不是猜阈值。

用法：python -m training.diag_notation --image <png>
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-diag-notation")
    ap.add_argument("--image", required=True)
    args = ap.parse_args()

    p = Path(args.image)
    gray = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SystemExit(f"读不了 {p}")
    h, w = gray.shape
    diag = math.hypot(w, h)
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = b > 0
    ink_area = int(ink.sum())

    closed = cv2.morphologyEx(ink.astype(np.uint8) * 255, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    print(f"图 {w}x{h} 对角 {diag:.1f} 墨迹 {ink_area} ({ink_area/(w*h)*100:.1f}%)")
    print(f"轮廓数 {len(contours)}")
    print(f"{'idx':>3} {'bbox':>18} {'area':>8} {'fill':>6} {'elong':>6} {'long':>6} {'判为':>6}")
    glyphs, bonds = [], []
    for i, c in enumerate(sorted(contours, key=lambda c: -cv2.contourArea(c))):
        area = cv2.contourArea(c)
        if area < 6:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        box = bw * bh
        if box <= 0:
            continue
        fill = area / box
        long_side = max(bw, bh)
        short_side = min(bw, bh) or 1
        elong = long_side / short_side
        kind = "?"
        if elong >= 2.6 and fill < 0.42 and long_side >= 0.045 * diag:
            kind = "线"
            bonds.append(float(long_side))
        elif elong < 2.6 and fill >= 0.16 and 0.012 * h <= bh <= 0.24 * h:
            kind = "字"
            glyphs.append((x, y, bw, bh))
        else:
            kind = "-"
        if i < 40:
            print(f"{i:>3} {x:>4},{y:>4},{bw:>3},{bh:>3} {area:>8.1f} {fill:>6.2f} "
                  f"{elong:>6.2f} {long_side:>6.1f} {kind:>6}")

    print(f"\n字 {len(glyphs)} 个, 线 {len(bonds)} 条")
    if glyphs:
        heights = [g[3] for g in glyphs]
        med_h = float(np.median(heights))
        print(f"字高中位数 {med_h:.1f}，字面积和 {sum(g[2]*g[3] for g in glyphs)} / 墨迹 {ink_area}")
        # 打印字块的横向间隙分布，判断 token 合并阈值是否合适
        gs = sorted(glyphs, key=lambda g: (g[1], g[0]))
        gaps = []
        for a, bb in zip(gs, gs[1:]):
            if abs(a[1] - bb[1]) < 0.5 * med_h:
                gaps.append(bb[0] - (a[0] + a[2]))
        if gaps:
            gs_arr = np.array(gaps, dtype=float)
            print(f"同行字间间隙: min={gs_arr.min():.1f} med={np.median(gs_arr):.1f} "
                  f"max={gs_arr.max():.1f}  （阈值 0.3*med_h={0.3*med_h:.1f}）")


if __name__ == "__main__":
    main()
