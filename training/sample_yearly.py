"""每年抽一篇，看实际有几种画法（不预设档位数）。

用户指示：不一定是三个档位，每年抽一篇跑小量，自己看有多少种风格。
所以这里只采样 + 出特征，**不做任何档位假设**，交给聚类去发现自然簇数。

用法：
    python -m training.sample_yearly --pdfs <dir> --out <dir> --range 1900-1975
产物：<out>/<year>/<year>_p<page>_f<i>.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .detect import detect_page, load_model
from .style import year_from_filename


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-sample-yearly")
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--range", default="1900-1975")
    ap.add_argument("--per-year", type=int, default=1, help="每年抽几篇")
    ap.add_argument("--max-crops", type=int, default=4, help="每篇最多留几张")
    ap.add_argument("--pages", type=int, default=2, help="每篇扫前几页")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    import cv2
    import numpy as np
    import pymupdf

    lo, hi = (int(x) for x in args.range.split("-"))
    pdf_dir = Path(args.pdfs)
    out_root = Path(args.out)

    by_year: dict[int, list[Path]] = {}
    for p in sorted(pdf_dir.glob("*.pdf")):
        y = year_from_filename(p.name)
        if y and lo <= y <= hi:
            by_year.setdefault(y, []).append(p)

    model = load_model()
    scale = args.dpi / 150.0
    total = 0
    for year in sorted(by_year):
        for pdf in by_year[year][:args.per_year]:
            dst = out_root / str(year)
            dst.mkdir(parents=True, exist_ok=True)
            n = 0
            try:
                doc = pymupdf.open(pdf)
            except Exception:
                continue
            for pg in range(min(args.pages, len(doc))):
                if n >= args.max_crops:
                    break
                pinfo = detect_page(model, doc[pg], dpi=150)
                if not pinfo["boxes"]:
                    continue
                pix = doc[pg].get_pixmap(dpi=args.dpi)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n >= 3 else arr
                for box in pinfo["boxes"]:
                    if n >= args.max_crops:
                        break
                    x1, y1, x2, y2 = (int(v * scale) for v in box["bbox"])
                    pad = int(6 * scale)
                    crop = img[max(0, y1 - pad):min(img.shape[0], y2 + pad),
                               max(0, x1 - pad):min(img.shape[1], x2 + pad)]
                    if crop.size == 0 or min(crop.shape[:2]) < 28:
                        continue
                    cv2.imwrite(str(dst / f"{year}_p{pg:03d}_f{n:02d}.png"), crop)
                    n += 1
                    total += 1
            doc.close()
        print(f"{year}: 累计 {total} 张", flush=True)
    print(f"完成，共 {total} 张")


if __name__ == "__main__":
    main()
