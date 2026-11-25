"""按年代抽样评估：验证档位分布是否随年代迁移（这是"分类器能不能用"的硬检验）。

为什么要这个：单篇判档对不代表分类器有价值。真正要证明的是
"随年代推移，显式碳式的占比下降、键线式的占比上升"。
若这个趋势成立，档位就是年代谱，可用于风格档位划分与渲染参数选择。

用法：python -m training.eval_by_year --pdfs <dir> --per-year 3 --out <json>
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .pdf_notation import classify_page


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-eval-by-year")
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--per-year", type=int, default=3)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--range", default="1900-1975")
    args = ap.parse_args()

    import pymupdf

    lo, hi = (int(x) for x in args.range.split("-"))
    pdfs = sorted(Path(args.pdfs).glob("*.pdf"))
    picked: dict[int, list[Path]] = defaultdict(list)
    for p in pdfs:
        m = re.search(r"(19\d{2})", p.name)
        if not m:
            continue
        y = int(m.group(1))
        if lo <= y <= hi and len(picked[y]) < args.per_year:
            picked[y].append(p)

    rows = []
    for y in sorted(picked):
        for pdf in picked[y]:
            try:
                doc = pymupdf.open(str(pdf))
            except Exception:
                continue
            best = None
            for pno in range(min(args.pages, len(doc))):
                try:
                    t = classify_page(doc[pno], pno)
                except Exception:
                    continue
                if t.tier == "uncertain" or not t.tier:
                    continue
                # 取"证据最多"的那页（标签字符数最多）作为该篇代表
                if best is None or t.label_chars > best.label_chars:
                    best = t
            doc.close()
            rows.append({"year": y, "pdf": pdf.name,
                         "tier": best.tier if best else "uncertain",
                         "labels": best.label_chars if best else 0,
                         "carbon_ratio": best.carbon_ratio if best else 0.0})
        if len(rows) % 30 == 0:
            print(f"  进度 {len(rows)} 篇", flush=True)

    by_dec: dict[int, Counter] = defaultdict(Counter)
    for r in rows:
        by_dec[(r["year"] // 10) * 10][r["tier"]] += 1

    print(f"\n共 {len(rows)} 篇\n")
    print(f"{'年段':>10} {'n':>3} {'dense':>6} {'hybrid':>7} {'skeletal':>9} {'uncertain':>10}")
    for b in sorted(by_dec):
        c = by_dec[b]
        n = sum(c.values())
        print(f"{b:>4}-{b+9:<5} {n:>3} "
              f"{c.get('dense',0)/n*100:>5.0f}% {c.get('hybrid',0)/n*100:>6.0f}% "
              f"{c.get('skeletal',0)/n*100:>8.0f}% {c.get('uncertain',0)/n*100:>9.0f}%")

    # 单调性检验：显式碳占比应随年代下降
    decs = sorted(by_dec)
    dense_pct = []
    for b in decs:
        c = by_dec[b]
        n = max(sum(c.values()), 1)
        dense_pct.append(c.get("dense", 0) / n)
    corr = 0.0
    if len(decs) >= 3:
        import numpy as np
        corr = float(np.corrcoef(np.array(decs, dtype=float), np.array(dense_pct))[0, 1])
    print(f"\n显式碳占比 vs 年代 相关系数 = {corr:.3f} "
          f"（负值=随年代下降，符合预期；正值=不符合）")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已写", out)


if __name__ == "__main__":
    main()
