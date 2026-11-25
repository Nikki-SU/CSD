"""看风格谱：按年份打印每张图的"显式碳程度"分数与关键特征，判断是连续谱还是离散簇。

为什么先做这个而不是直接聚类：用户要求"看有多少种风格"。若分数随年代**连续渐变**，
则"档位"只是人为切段（早期/中期/晚期），而不是数据里的天然簇；
若出现明显**双峰/多峰**，才说明真有并行画派，需要多档。

用法：python -m training.style_spectrum --dir <按年份目录>
"""
from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from pathlib import Path

from .notation import FEATURE_NAMES, describe, extract_notation
from .notation_clf import density_score


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-style-spectrum")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--step", type=int, default=10, help="每多少年汇总一行")
    args = ap.parse_args()

    root = Path(args.dir)
    rows = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not d.name.isdigit():
            continue
        year = int(d.name)
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            try:
                f = extract_notation(p)
            except Exception:
                continue
            v = dict(zip(FEATURE_NAMES, f.values))
            rows.append({"year": year, "score": density_score(f), "name": p.name,
                         "ink": v["text_ink_fraction"], "wide": v["group_wideness"],
                         "pb": v["group_per_bond"], "tier": describe(f)["tier"]})

    if not rows:
        raise SystemExit("没有样本")

    print(f"总样本 {len(rows)} 张，年份 {min(r['year'] for r in rows)}~{max(r['year'] for r in rows)}")
    print()
    print(f"{'年段':>10} {'n':>3} {'score均值':>9} {'ink':>6} {'wide':>6} {'pb':>6}")
    buckets: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[(r["year"] // args.step) * args.step].append(r)
    for b in sorted(buckets):
        rs = buckets[b]
        sc = [r["score"] for r in rs]
        print(f"{b:>4}-{b+args.step-1:<5} {len(rs):>3} {statistics.mean(sc):>9.3f} "
              f"{statistics.mean([r['ink'] for r in rs]):>6.2f} "
              f"{statistics.mean([r['wide'] for r in rs]):>6.2f} "
              f"{statistics.mean([r['pb'] for r in rs]):>6.2f}")

    # 分数分布：是单峰渐变还是多峰（多峰=真有多画派）
    scores = sorted(r["score"] for r in rows)
    print()
    print("分数分布直方（10 桶，看是单峰还是多峰）：")
    lo, hi = scores[0], scores[-1]
    span = max(hi - lo, 1e-6)
    hist = [0] * 10
    for s in scores:
        hist[min(9, int((s - lo) / span * 10))] += 1
    peak = max(hist)
    for i, h in enumerate(hist):
        bar = "#" * int(60 * h / peak) if peak else ""
        print(f"  {lo + span*i/10:5.2f}~{lo + span*(i+1)/10:5.2f} | {h:>3} {bar}")

    # 关键：三档占比随年代推移——风格是同期并存的，主流占比才会迁移。
    # 所以判定标准不是"每年只有一种风格"，而是"占比重心逐年移动"。
    print()
    print("按年段的三档占比（显式碳程度高→低）：")
    print(f"{'年段':>10} {'n':>3} {'高显式%':>8} {'中混合%':>8} {'纯键线%':>8}")
    hi_t, lo_t = 0.62, 0.34
    for b in sorted(buckets):
        rs = buckets[b]
        hh = sum(1 for r in rs if r["score"] >= hi_t) / len(rs) * 100
        mm = sum(1 for r in rs if lo_t <= r["score"] < hi_t) / len(rs) * 100
        ll = sum(1 for r in rs if r["score"] < lo_t) / len(rs) * 100
        print(f"{b:>4}-{b+args.step-1:<5} {len(rs):>3} {hh:>8.1f} {mm:>8.1f} {ll:>8.1f}")


if __name__ == "__main__":
    main()
