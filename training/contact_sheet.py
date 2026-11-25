"""拼图页（contact sheet）：把各年代样本拼成一张，用于"一眼看出有几种画法"。

为什么做这个：聚类指标（silhouette 0.17）不足以判断有几种风格，
必须人眼扫一遍真实结构式才知道。按年代横排，同一年代多张竖排，
一眼即可看出画法演变与并存情况。

用法：python -m training.contact_sheet --dir <年份目录> --out <png> --cols 8 --cell 150
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-contact-sheet")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cell", type=int, default=150, help="每格边长 px")
    ap.add_argument("--cols", type=int, default=8, help="一行几个年代")
    ap.add_argument("--per-year", type=int, default=3, help="每个年代取前几张")
    ap.add_argument("--years", default="", help="只取这些年代，逗号分隔")
    ap.add_argument("--step", type=int, default=10, help="年代分组步长，用于抽代表年")
    args = ap.parse_args()

    root = Path(args.dir)
    years = sorted(int(d.name) for d in root.iterdir() if d.is_dir() and d.name.isdigit())
    if args.years:
        years = [int(y) for y in args.years.split(",")]

    picks: list[tuple[int, list[Path]]] = []
    for y in years:
        d = root / str(y)
        if not d.is_dir():
            continue
        ps = sorted(d.glob("*.png"))[:args.per_year]
        if ps:
            picks.append((y, ps))
    if not picks:
        raise SystemExit("没有可拼的图")

    cell = args.cell
    label_h = 18
    rows = (len(picks) + args.cols - 1) // args.cols
    grid = np.full((rows * (cell + label_h), args.cols * cell, 3), 255, dtype=np.uint8)

    def place(img: np.ndarray, x: int, y: int) -> None:
        ih, iw = img.shape[:2]
        s = min(cell / iw, cell / ih)
        nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
        r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        ox = x + (cell - nw) // 2
        oy = y + label_h + (cell - nh) // 2
        grid[oy:oy + nh, ox:ox + nw] = r

    for i, (year, ps) in enumerate(picks):
        r, c = divmod(i, args.cols)
        x0, y0 = c * cell, r * (cell + label_h)
        for j, p in enumerate(ps[:args.per_year]):
            img = cv2.imread(str(p))
            if img is None:
                continue
            # 同一年代多张时横向错开，但格子有限：只拼第一张为主，其余缩小叠加在角落
            if j == 0:
                place(img, x0, y0)
            else:
                small = cv2.resize(img, (cell // 3, cell // 3), interpolation=cv2.INTER_AREA)
                grid[y0 + label_h:y0 + label_h + cell // 3,
                     x0 + cell - cell // 3:x0 + cell] = small
        cv2.putText(grid, str(year), (x0 + 3, y0 + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1, cv2.LINE_AA)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, grid)
    print(f"拼图 {grid.shape[1]}x{grid.shape[0]}，{len(picks)} 个年代 → {args.out}")


if __name__ == "__main__":
    main()
