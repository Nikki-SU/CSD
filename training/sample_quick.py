"""快速采样：只取几个年代节点、少量页、少量图，用于验证"画法随年代演化"这条规律。

与 sample_style.py 的区别：这个只要几十秒（每个年代 1 篇 × 前 2 页 × 最多 5 张），
够用来确认特征是否单调，跑全量再用 sample_style。

用法：
    python -m training.sample_quick --pdfs <dir> --out <dir> --years 1900,1920,1940,1955,1965,1972
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .detect import detect_page, load_model


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-sample-quick")
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--years", default="1900,1920,1940,1955,1965,1972")
    ap.add_argument("--max-crops", type=int, default=5)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    import cv2
    import numpy as np
    import pymupdf

    pdf_dir = Path(args.pdfs)
    out_root = Path(args.out)
    years = [int(y) for y in args.years.split(",")]
    model = load_model()

    for year in years:
        cand = sorted(p for p in pdf_dir.glob("*.pdf") if p.name.startswith(str(year)))
        if not cand:
            print(f"{year}: 无文件", flush=True)
            continue
        pdf = cand[0]
        dst = out_root / str(year)
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        try:
            doc = pymupdf.open(pdf)
        except Exception as exc:
            print(f"{year}: 打不开 {exc}", flush=True)
            continue
        scale = args.dpi / 150.0
        for pg in range(min(args.pages, len(doc))):
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
                if crop.size == 0 or min(crop.shape[:2]) < 24:
                    continue
                cv2.imwrite(str(dst / f"{year}_p{pg:03d}_f{n:02d}.png"), crop)
                n += 1
        doc.close()
        print(f"{year}: {n} 张  ({pdf.name})", flush=True)


if __name__ == "__main__":
    main()
