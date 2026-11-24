"""造小数据集：合成几张模拟古早结构式图，用来跑通管道每一步。

不是真实文献数据（公库零数据红线），只是管道自测的原料。
真实数据晚点到时，把图放进 training/01-collect 即可，管道不改。

    python -m training.make_sample --out <工作区>/training/01-collect
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def draw_benzene(canvas: np.ndarray, cx: int, cy: int, r: int, circle: bool = False) -> None:
    if circle:
        cv2.circle(canvas, (cx, cy), r, 0, 2, cv2.LINE_AA)
    else:
        pts = [(cx + int(r * np.cos(a)), cy + int(r * np.sin(a))) for a in np.linspace(0, 2 * np.pi, 7)[:-1]]
        for i in range(6):
            cv2.line(canvas, pts[i], pts[(i + 1) % 6], 0, 2, cv2.LINE_AA)


def make_sample(idx: int, out: Path) -> Path:
    img = np.full((300, 400), 255, np.uint8)
    draw_benzene(img, 150, 130, 55, circle=(idx % 2 == 0))
    if idx % 3 == 1:
        cv2.line(img, (205, 130), (260, 95), 0, 2, cv2.LINE_AA)
        cv2.putText(img, "N", (262, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
    if idx % 3 == 2:
        cv2.line(img, (205, 130), (260, 165), 0, 2, cv2.LINE_AA)
        cv2.putText(img, "O", (262, 172), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
    path = out / f"sample_{idx:02d}.png"
    cv2.imwrite(str(path), img)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="造模拟结构式图（管道自测原料）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(args.count):
        p = make_sample(i, out)
        print(f"  {p}")
    print(f"造了 {args.count} 张到 {out}")


if __name__ == "__main__":
    main()
