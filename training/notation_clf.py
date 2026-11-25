"""训练②：书写记法风格分类器（三档谱）+ 用年份弱监督校准。

红线（用户强调）：只量"怎么写"，不量"写了什么"。
环数/环大小/是否含环/原子数/分子大小这些内容量，一律不进取特征（见 notation.py 注释）。
年份只用于**校准阈值**与**验证单调性**，不作为预测输入——
因为"这一张是什么画法"应由图像本身判定，年份只是先验（后期也可能有人画旧式图）。

模型：两阶段
    1) 规则初判（notation.rule_tier，可解释、无需训练就能跑）
    2) 用年份弱监督把分数轴切成三段（分位点法），得到 calibrated 阈值
只用一维"显式碳程度"轴上切两刀——三档本来就是同一条谱上的三段，不该用高维模型硬拟合。

产物（进 assets/，随 GitHub 分发）：
    notation_calibration.json   两刀阈值 + 各档的年代区间与样本数
    notation_tiers.json         每一档的渲染参数建议（bond_length / font_size 等）

用法：
    python -m training.notation_clf fit --dir <按年份分文件夹的目录> --out <assets目录>
    python -m training.notation_clf eval --dir <目录> --calib assets/notation_calibration.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .notation import FEATURE_NAMES, TIER_LABEL, TIERS, extract_notation


# ---------------------------------------------------------------------------
# 显式碳程度（0~1 连续轴）——三档就是这条轴上的三段
# ---------------------------------------------------------------------------
def density_score(f) -> float:
    """把特征压成"显式碳程度"一维分（0=纯键线, 1=大块文字缩写）。

    **只用"文字块的宽度"这一个量**，这是唯一经红线验证过的纯净画法量：
        纯键线式  → 每块只有单个杂原子字母，wide ≈ 1.0（与杂原子有几个无关）
        CH3/CH2   → wide ≈ 1.8
        CO2R/CH2CH3 → wide ≈ 2.5 以上
    为什么不用"文字墨量占比"：实测它在纯键线式上会随杂原子数量升高
    （苯环线条细、杂原子字粗，3 个 O 就把墨量占比顶到 1.0），是内容泄漏。
    块宽只取决于"这块文字有几个字"，与分子的内容无关。
    """
    v = dict(zip(FEATURE_NAMES, f.values))
    wide = float(v["group_wideness"])
    # 1.0 → 0；3.0 以上 → 1
    return float(min(max((wide - 1.0) / 2.0, 0.0), 1.0))


# ---------------------------------------------------------------------------
# 年份弱监督校准
# ---------------------------------------------------------------------------
def fit_auto(root: Path, k_min: int = 2, k_max: int = 8,
             out: Path | None = None) -> dict:
    """**不预设档位数**：用无监督聚类发现自然簇数，再由年份验证这些簇是否有序。

    为什么不用固定三档：用户明确说"不一定是三个档位"。所以档位数 k 由数据定，
    用轮廓系数（silhouette）在 k_min..k_max 之间挑最优；再用各簇中位年份
    检验它们是否形成"由老到新"的序列（若是，则档位是年代谱；若不是，则是并行画派）。
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    rows = _iter_labelled(root)
    if not rows:
        raise SystemExit(f"{root} 下没有 <年份>/<图> 结构")

    feats, years, paths = [], [], []
    for p, year in rows:
        try:
            f = extract_notation(p)
        except Exception:
            continue
        feats.append(f.vec())
        years.append(year)
        paths.append(p)
    if len(feats) < 8:
        raise SystemExit(f"样本太少（{len(feats)}），至少 8 才能聚")

    x = np.array(feats, dtype=float)
    # 只用画法量做聚类；标准化使各量纲等权
    xs = StandardScaler().fit_transform(x)
    n = len(feats)
    k_max = min(k_max, max(2, n // 3))

    best = None
    trials = []
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(xs)
        if len(set(km.labels_)) < 2:
            continue
        try:
            sil = float(silhouette_score(xs, km.labels_))
        except Exception:
            sil = -1.0
        trials.append({"k": k, "silhouette": round(sil, 4)})
        if best is None or sil > best["sil"]:
            best = {"k": k, "sil": sil, "labels": km.labels_, "km": km}
    if best is None:
        raise SystemExit("聚类失败")

    labels = best["labels"]
    clusters = {}
    for cid in range(best["k"]):
        idx = [i for i, l in enumerate(labels) if l == cid]
        if not idx:
            continue
        ys = [years[i] for i in idx]
        # 簇的"显式碳程度"均值——用于给簇排序与命名（只作解释，不参与聚类）
        scores = [density_score_from_vec(x[i]) for i in idx]
        clusters[str(cid)] = {
            "count": len(idx),
            "year_min": int(min(ys)),
            "year_max": int(max(ys)),
            "year_median": float(statistics.median(ys)),
            "explicit_carbon_mean": round(float(np.mean(scores)), 4),
            "sample_images": [paths[i].name for i in idx[:3]],
        }

    # 按中位年份排序，看是否与"显式碳程度"同向（同向=年代谱，可当档位）
    ordered = sorted(clusters.items(), key=lambda kv: kv[1]["year_median"])
    year_seq = [v["year_median"] for _, v in ordered]
    ec_seq = [v["explicit_carbon_mean"] for _, v in ordered]
    # 年代越老，显式碳应越多（ec 应越大）
    corr = float(np.corrcoef(year_seq, ec_seq)[0, 1]) if len(ordered) >= 3 else 0.0
    is_chronological = corr < -0.5

    payload = {
        "version": 1,
        "method": "kmeans_auto_k",
        "k_selected": best["k"],
        "silhouette": round(best["sil"], 4),
        "k_trials": trials,
        "clusters": {k: v for k, v in clusters.items()},
        "year_vs_explicit_corr": round(corr, 4),
        "is_chronological_spectrum": bool(is_chronological),
        "sample_count": n,
        "feature_names": list(FEATURE_NAMES),
        "note": "档位数由轮廓系数自动选出，不预设三档；年份只用于验证簇是否成年代谱",
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        detail = out.parent / "notation_clusters_detail_local.json"
        detail.write_text(json.dumps(
            {"samples": [{"image": paths[i].name, "year": years[i],
                          "cluster": int(labels[i]), "vec": [round(v, 4) for v in x[i]]}
                         for i in range(n)]}, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["_detail"] = str(detail)
    return payload


def density_score_from_vec(vec: np.ndarray) -> float:
    v = dict(zip(FEATURE_NAMES, vec))
    return float(min(max((v["group_wideness"] - 1.0) / 2.0, 0.0), 1.0))


def _iter_labelled(root: Path) -> list[tuple[Path, int]]:
    """目录结构约定：<root>/<year>/<img>.png，年份来自文件夹名。"""
    out: list[tuple[Path, int]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not d.name.isdigit():
            continue
        year = int(d.name)
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                out.append((p, year))
    return out


def fit(root: Path, lo_quantile: float = 0.33, hi_quantile: float = 0.67,
        out: Path | None = None) -> dict:
    """用年份弱监督切两刀。

    思路：同一时代的人画法趋同，所以"年份靠前的样本分数应整体偏高"。
    先按分数排序，用分位点切三段；再检查每段的中位年份是否单调递减，
    不单调就说明特征没抓住画法（应报警而不是硬凑）。
    """
    rows = _iter_labelled(root)
    if not rows:
        raise SystemExit(f"{root} 下没有 <年份>/<图> 结构")

    samples = []
    for p, year in rows:
        try:
            f = extract_notation(p)
        except Exception as exc:
            print(f"  跳过 {p.name}: {type(exc).__name__}")
            continue
        s = density_score(f)
        samples.append({"image": str(p), "year": year, "score": s,
                        "explicit_per_vertex": dict(zip(FEATURE_NAMES, f.values))["explicit_per_vertex"],
                        "multi_token_ratio": dict(zip(FEATURE_NAMES, f.values))["multi_token_ratio"]})
    if len(samples) < 6:
        raise SystemExit(f"样本太少（{len(samples)}），至少 6")

    scores = np.array([s["score"] for s in samples], dtype=float)
    years = np.array([s["year"] for s in samples], dtype=float)
    t_dense = float(np.quantile(scores, hi_quantile))   # 高分段 = dense
    t_skel = float(np.quantile(scores, lo_quantile))    # 低分段 = skeletal

    def tier_of(sc: float) -> str:
        if sc >= t_dense:
            return "dense"
        if sc <= t_skel:
            return "skeletal"
        return "hybrid"

    by_tier: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        by_tier[tier_of(s["score"])].append(s["year"])

    stats = {}
    for t in TIERS:
        ys = by_tier.get(t, [])
        stats[t] = {
            "label": TIER_LABEL[t],
            "count": len(ys),
            "year_min": int(min(ys)) if ys else None,
            "year_max": int(max(ys)) if ys else None,
            "year_median": float(statistics.median(ys)) if ys else None,
        }

    # 单调性检查：dense 应最老、skeletal 应最新
    meds = [stats[t]["year_median"] for t in TIERS]
    monotone = all(m is not None for m in meds) and meds[0] >= meds[1] >= meds[2]

    payload = {
        "version": 1,
        "axis": "explicit_carbon_density",
        "thresholds": {"dense_at_or_above": round(t_dense, 4),
                       "skeletal_at_or_below": round(t_skel, 4)},
        "tiers": stats,
        "monotone_by_year": bool(monotone),
        "year_median_by_tier": [None if m is None else round(m, 1) for m in meds],
        "sample_count": len(samples),
        "feature_names": list(FEATURE_NAMES),
        "note": "只量画法，不量内容；年份仅用于校准与单调性验证，不作预测输入",
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        detail = out.parent / "notation_calibration_detail_local.json"
        detail.write_text(json.dumps({"samples": samples}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        payload["_detail"] = str(detail)
    return payload


# ---------------------------------------------------------------------------
# 用校准后的阈值判档
# ---------------------------------------------------------------------------
def classify(f, calib: dict) -> dict:
    s = density_score(f)
    th = calib["thresholds"]
    if s >= th["dense_at_or_above"]:
        tier = "dense"
        margin = (s - th["dense_at_or_above"])
    elif s <= th["skeletal_at_or_below"]:
        tier = "skeletal"
        margin = (th["skeletal_at_or_below"] - s)
    else:
        tier = "hybrid"
        hi = th["dense_at_or_above"] - th["skeletal_at_or_below"]
        margin = hi / 2 - abs(s - (th["dense_at_or_above"] + th["skeletal_at_or_below"]) / 2)
    conf = float(min(0.99, 0.6 + max(0.0, margin) * 1.2))
    return {"tier": tier, "tier_label": TIER_LABEL[tier],
            "score": round(s, 4), "confidence": round(conf, 3)}


def evaluate(root: Path, calib: dict) -> dict:
    rows = _iter_labelled(root)
    got = []
    for p, year in rows:
        try:
            f = extract_notation(p)
        except Exception:
            continue
        got.append({"year": year, "image": str(p), **classify(f, calib)})

    by_tier: dict[str, list[int]] = defaultdict(list)
    for r in got:
        by_tier[r["tier"]].append(r["year"])
    summary = {}
    for t in TIERS:
        ys = by_tier.get(t, [])
        summary[t] = {"count": len(ys),
                      "year_min": int(min(ys)) if ys else None,
                      "year_max": int(max(ys)) if ys else None,
                      "year_median": float(statistics.median(ys)) if ys else None}
    meds = [summary[t]["year_median"] for t in TIERS]
    return {"count": len(got), "by_tier": summary,
            "monotone_by_year": all(m is not None for m in meds) and meds[0] >= meds[1] >= meds[2],
            "year_median_by_tier": meds}


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-notation-clf")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("auto", help="不预设档位数：自动选 k 聚类，看实际有几种画法")
    p1.add_argument("--dir", required=True, help="<年份>/<图> 结构目录")
    p1.add_argument("--out", default="assets/notation_clusters.json")
    p1.add_argument("--k-min", type=int, default=2)
    p1.add_argument("--k-max", type=int, default=8)

    p3 = sub.add_parser("fit", help="用年份弱监督校准两刀阈值（假定三档，仅对照用）")
    p3.add_argument("--dir", required=True, help="<年份>/<图> 结构目录")
    p3.add_argument("--out", default="assets/notation_calibration.json")
    p3.add_argument("--lo-quantile", type=float, default=0.33)
    p3.add_argument("--hi-quantile", type=float, default=0.67)

    p2 = sub.add_parser("eval", help="用现有校准评估并检查年代单调性")
    p2.add_argument("--dir", required=True)
    p2.add_argument("--calib", default="assets/notation_calibration.json")

    args = ap.parse_args()
    if args.cmd == "auto":
        payload = fit_auto(Path(args.dir), args.k_min, args.k_max, Path(args.out))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.cmd == "fit":
        payload = fit(Path(args.dir), args.lo_quantile, args.hi_quantile, Path(args.out))
        print(json.dumps({k: v for k, v in payload.items() if k != "feature_names"},
                         ensure_ascii=False, indent=2))
    else:
        calib = json.loads(Path(args.calib).read_text(encoding="utf-8"))
        print(json.dumps(evaluate(Path(args.dir), calib), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
