"""页级判据调参：拿现成模型/MinerU 当 baseline，自动搜参数逼近它。

用户要求：先用现成模型当 baseline 批量跑，再自动调参让自己的判据逼近 baseline。
这里不重新实现判据，只做「给定标注 → 网格搜 page_scan 参数 → 选最优」。

baseline 标注格式（baseline.json）：
    {"ALLEN1937_Indole.pdf": {"has_figure_pages": [1,2,3], "source": "moldet"},
     ...}

source 记来源（moldet / doclayout / mineru / human），便于区分基准质量。

用法：
    python -m training.calibrate run --pdf-dir <目录> --baseline <baseline.json> --out <best.json>
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from pipeline.page_scan import DEFAULT_PARAMS, page_profile

# 搜索网格：围绕实图量测的默认值，扩一圈
GRID = {
    "kernel_ratio": [0.005, 0.007, 0.010],
    "h_low": [3.0, 4.0, 5.0],
    "w_hi_ratio": [0.4, 0.5, 0.6],
    "area_min": [800, 1500, 2500],
}


def load_baseline(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def score_params(pdf_dir: Path, baseline: dict, params: dict, dpi: int = 150) -> dict:
    """用一组参数扫所有 baseline PDF，算与 baseline 的一致度。

    召回优先：漏判有图页（FN）罚得比误判（FP）重——结构式丢了就没法补。
    """
    tp = fp = fn = tn = 0
    for name, info in baseline.items():
        pdf = pdf_dir / name
        if not pdf.exists():
            continue
        import pymupdf
        doc = pymupdf.open(pdf)
        truth = set(info.get("has_figure_pages") or [])
        for page in doc:
            pred = page_profile(page, dpi=dpi, params=params)["has_figure"]
            pnum = int(page.number) + 1
            if pred and pnum in truth: tp += 1
            elif pred and pnum not in truth: fp += 1
            elif not pred and pnum in truth: fn += 1
            else: tn += 1
        doc.close()
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    # F2：召回权重是精确率的两倍（漏图代价大）
    f2 = (5 * precision * recall) / (4 * precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3), "recall": round(recall, 3), "f2": round(f2, 3)}


def tune(pdf_dir: Path, baseline: dict, grid: dict | None = None, dpi: int = 150) -> dict:
    grid = grid or GRID
    keys = list(grid)
    best = None
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = {**DEFAULT_PARAMS, **dict(zip(keys, combo))}
        s = score_params(pdf_dir, baseline, params, dpi=dpi)
        results.append({"params": params, "score": s})
        if best is None or s["f2"] > best["score"]["f2"]:
            best = {"params": params, "score": s}
    results.sort(key=lambda x: x["score"]["f2"], reverse=True)
    return {"best": best, "top": results[:10], "tried": len(results)}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="页级判据调参")
    ap.add_argument("cmd", choices=["run", "score"])
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--baseline", required=True, help="baseline 标注 JSON")
    ap.add_argument("--params", help="score 用：单组参数 JSON")
    ap.add_argument("--out", default="assets/calibration.json")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    pdf_dir = Path(args.pdf_dir).resolve()
    baseline = load_baseline(args.baseline)
    if args.cmd == "run":
        out = tune(pdf_dir, baseline, dpi=args.dpi)
    else:
        params = json.loads(Path(args.params).read_text(encoding="utf-8")) if args.params else dict(DEFAULT_PARAMS)
        out = {"score": score_params(pdf_dir, baseline, params, dpi=args.dpi), "params": params}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out.get("best", out), ensure_ascii=False, indent=2))
    print(f"写出 {target}")


if __name__ == "__main__":
    main()
