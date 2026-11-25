"""采样：按年代分层，从 PDF 里裁出真实结构式图，供记法分类器验证/校准。

为什么必须采样：分类器要能证明"画法随年代单调演化"，不能只在一两篇上看着像。
年份从文件名取（用户已标注年份在文件名里）。

用法：
    python -m training.sample_style --pdfs <目录> --out <目录> --per-year 6 --years 1900-1980
产物：
    <out>/<year>/<pdfstem>_p<PAGE>_f<i>.png   每个年代一个文件夹
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .detect import detect_page, load_model
from .style import year_from_filename


def _pdfs_by_year(pdf_dir: Path) -> dict[int, list[Path]]:
    out: dict[int, list[Path]] = {}
    for p in sorted(pdf_dir.glob("*.pdf")):
        y = year_from_filename(p.name)
        if y is None:
            continue
        out.setdefault(y, []).append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-sample-style")
    ap.add_argument("--pdfs", required=True, help="PDF 目录")
    ap.add_argument("--out", required=True, help="输出目录（按年份分文件夹）")
    ap.add_argument("--per-year", type=int, default=6, help="每年最多采多少篇")
    ap.add_argument("--years", default="1900-1980", help="年份范围 a-b")
    ap.add_argument("--max-crops", type=int, default=8, help="每篇最多留几张图")
    ap.add_argument("--dpi", type=int, default=300, help="裁图 dpi（300 是环检测可用的下限）")
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.years.split("-"))
    pdf_dir = Path(args.pdfs)
    out_root = Path(args.out)
    by_year = _pdfs_by_year(pdf_dir)

    import cv2
    import numpy as np
    import pymupdf

    model = load_model()
    total = 0
    for year in sorted(y for y in by_year if lo <= y <= hi):
        picked = by_year[year][:args.per_year]
        dst = out_root / str(year)
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for pdf in picked:
            if n >= args.max_crops:
                break
            try:
                doc = pymupdf.open(pdf)
            except Exception:
                continue
            for pinfo in (detect_page(model, page, dpi=args.dpi) for page in doc):
                if n >= args.max_crops:
                    break
                if not pinfo["boxes"]:
                    continue
                # 用 150dpi 坐标系做 detect，裁图用 300dpi → 坐标乘 2
                scale = args.dpi / 150.0
                pix = doc[pinfo["page"] - 1].get_pixmap(dpi=args.dpi)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n >= 3 else arr
                for box in pinfo["boxes"]:
                    if n >= args.max_crops:
                        break
                    x1, y1, x2, y2 = (int(v * scale) for v in box["bbox"])
                    pad = int(6 * scale)
                    crop = img[max(0, y1 - pad):min(img.shape[0], y2 + pad),
                               max(0, x1 - pad):min(img.shape[1], x2 + pad)]
                    if crop.size == 0 or crop.shape[0] < 24 or crop.shape[1] < 24:
                        continue
                    name = f"{pdf.stem}_p{pinfo['page']:03d}_f{n:02d}.png"
                    cv2.imwrite(str(dst / name), crop)
                    n += 1
                    total += 1
            doc.close()
        print(f"{year}: {n} 张", flush=True)
    print(f"共 {total} 张，输出 {out_root}")


if __name__ == "__main__":
    main()
