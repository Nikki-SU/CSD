"""并行按年代采样：每年抽多篇，多进程跑，用于统计"画法的主流占比随年代推移"。

为什么需要并行与多篇：每年只抽 1 篇会抽到异常作者（实测 1950 年就有纯键线式），
无法反映同期主流。每年代需要 5~10 篇才能在统计上站稳。

用法：
    python -m training.sample_parallel --pdfs <dir> --out <dir> --range 1900-1975 \
        --per-year 6 --pages 3 --workers 6
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

from .style import year_from_filename


def _scan_one(args: tuple[str, int, int, int, str]) -> tuple[int, int, str]:
    """处理一篇 PDF：返回 (年份, 裁出张数, 文件名)。子进程内才 import 重库。"""
    pdf_path, year, pages, dpi, out_dir = args
    import cv2
    import numpy as np
    import pymupdf
    from .detect import detect_page, load_model

    model = load_model()
    scale = dpi / 150.0
    dst = Path(out_dir) / str(year)
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return year, 0, Path(pdf_path).name
    stem = Path(pdf_path).stem
    for pg in range(min(pages, len(doc))):
        try:
            pinfo = detect_page(model, doc[pg], dpi=150)
        except Exception:
            continue
        if not pinfo["boxes"]:
            continue
        pix = doc[pg].get_pixmap(dpi=dpi)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n >= 3 else arr
        for box in pinfo["boxes"]:
            x1, y1, x2, y2 = (int(v * scale) for v in box["bbox"])
            pad = int(5 * scale)
            crop = img[max(0, y1 - pad):min(img.shape[0], y2 + pad),
                       max(0, x1 - pad):min(img.shape[1], x2 + pad)]
            # 太小的是碎片/文字，不是结构式；留 40px 下限减少噪声
            if crop.size == 0 or min(crop.shape[:2]) < 40:
                continue
            cv2.imwrite(str(dst / f"{stem}_p{pg:03d}_f{n:02d}.png"), crop)
            n += 1
    doc.close()
    return year, n, Path(pdf_path).name


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-sample-parallel")
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--range", default="1900-1975")
    ap.add_argument("--per-year", type=int, default=6)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-crops", type=int, default=10, help="每篇最多留几张（0=不限）")
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.range.split("-"))
    pdf_dir = Path(args.pdfs)
    by_year: dict[int, list[Path]] = {}
    for p in sorted(pdf_dir.glob("*.pdf")):
        y = year_from_filename(p.name)
        if y and lo <= y <= hi:
            by_year.setdefault(y, []).append(p)

    tasks = []
    for year in sorted(by_year):
        for pdf in by_year[year][:args.per_year]:
            tasks.append((str(pdf), year, args.pages, args.dpi, args.out))

    total = 0
    done = 0
    with mp.Pool(args.workers) as pool:
        for year, n, name in pool.imap_unordered(_scan_one, tasks, chunksize=1):
            total += n
            done += 1
            if done % 20 == 0:
                print(f"  已处理 {done}/{len(tasks)} 篇，累计 {total} 张", flush=True)
    print(f"完成：{done} 篇 → {total} 张，输出 {args.out}")


if __name__ == "__main__":
    main()
