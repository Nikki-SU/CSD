"""验证：正文采集的字符模板能否识别结构式里的小字。

这是用户洞察的直接检验：
    「正文中的字和结构式用的字体是同一种，只是大小不一样。」

若能识别，则"是不是 C"变成查表，不再靠几何猜——
所有内容泄漏（把 O 当碳、把杂原子串当缩写块）都会随之消失。

用法：
    python -m training.verify_glyph_match --templates <pkl> --image <结构式裁图>
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

from .notation import _ink, _read_gray, _split_lines_and_glyphs
from .pdf_glyphs import match_glyph


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-verify-glyph")
    ap.add_argument("--templates", required=True)
    ap.add_argument("--images", nargs="+", required=True, help="一个或多个结构式裁图")
    args = ap.parse_args()

    with open(args.templates, "rb") as fh:
        pack = pickle.load(fh)
    templates = pack["templates"]

    for img in args.images:
        gray = _read_gray(img)
        h, w = gray.shape
        diag = (h ** 2 + w ** 2) ** 0.5
        ink = _ink(gray)
        _, boxes, _, _ = _split_lines_and_glyphs(ink, h, w, diag)
        print(f"\n=== {Path(img).name}  字形 {len(boxes)}")

        import cv2
        # 逐个字形裁出来匹配
        results = []
        for (x, y, bw, bh) in boxes:
            crop = gray[y:y + bh, x:x + bw]
            if crop.size == 0:
                continue
            _, b = cv2.threshold(crop, 0, 255,
                                 cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            ch, score = match_glyph(b, templates)
            results.append((ch, score, bw, bh))

        # 汇总：这张图里有几个 C、几个 O
        from collections import Counter
        cnt = Counter(ch for ch, _, _, _ in results if ch)
        strong = Counter(ch for ch, s, _, _ in results if ch and s >= 0.55)
        print(f"  识别(全): {dict(sorted(cnt.items(), key=lambda kv: -kv[1])[:10])}")
        print(f"  识别(≥0.55): {dict(sorted(strong.items(), key=lambda kv: -kv[1])[:10])}")
        c_n = strong.get("C", 0)
        o_n = strong.get("O", 0)
        n_n = strong.get("N", 0)
        print(f"  → C={c_n}  O={o_n}  N={n_n}   "
              f"（有 C 且 C 占多数 ⇒ 显式碳式；只有 O/N ⇒ 键线式）")
        for ch, s, bw, bh in results[:10]:
            print(f"     '{ch}' {s:.2f}  bbox={bw}x{bh}")


if __name__ == "__main__":
    main()
