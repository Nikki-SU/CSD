"""训练⑤：真古董（原始图）↔ 假古董（渲染候选）的匹配排序。

三层：pHash 粗筛 → SIFT 几何对齐 → SSIM 精排。
古早图与渲染图差异大（旋转/缩放/手写体），单一 pHash 不够，故三层。

可单独调试：
    python -m training.matching --query <图> --candidates <目录> --out <json>

输出：候选排序 + 每层分数（可调试每一层为什么排成这样）
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class CandidateScore:
    path: str
    phash: float
    sift: float
    ssim: float
    final: float

    def to_dict(self) -> dict:
        return asdict(self)


def phash(img: np.ndarray, hash_size: int = 16, highfreq: int = 4) -> np.ndarray:
    """感知哈希：DCT 低频，抗缩放与轻微形变。"""
    size = hash_size * highfreq
    small = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(small)[:hash_size, :hash_size]
    return dct > np.median(dct[1:])


def phash_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.count_nonzero(a != b) / a.size)


def sift_score(a: np.ndarray, b: np.ndarray) -> float:
    """SIFT 特征匹配比例：几何对齐程度。无足够特征点时返回 0。"""
    try:
        sift = cv2.SIFT_create()
    except AttributeError:
        return 0.0
    kp1, d1 = sift.detectAndCompute(a, None)
    kp2, d2 = sift.detectAndCompute(b, None)
    if d1 is None or d2 is None or len(kp1) < 4 or len(kp2) < 4:
        return 0.0
    matches = cv2.BFMatcher().knnMatch(d1, d2, k=2)
    good = [m for m, n in matches if m.distance < 0.7 * n.distance]
    return min(len(good) / 20.0, 1.0)


def ssim_score(a: np.ndarray, b: np.ndarray) -> float:
    """结构相似度：对齐后逐像素比。先统一尺寸与前景方向。"""
    from skimage.metrics import structural_similarity
    x = _normalize(a)
    y = _normalize(b)
    if x.shape != y.shape:
        y = cv2.resize(y, (x.shape[1], x.shape[0]))
    return float(structural_similarity(x, y))


def _normalize(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (bw > 0).astype(np.uint8)


def rank_candidates(query_path: str | Path, candidate_dir: str | Path) -> list[CandidateScore]:
    q = cv2.imread(str(query_path))
    if q is None:
        raise ValueError(f"读不了原图: {query_path}")
    qh = phash(_normalize(q))
    results = []
    for p in sorted(Path(candidate_dir).glob("*")):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        c = cv2.imread(str(p))
        if c is None:
            continue
        d = phash_dist(qh, phash(_normalize(c)))
        ps = max(0.0, 1.0 - d)
        ss = sift_score(_normalize(q), _normalize(c))
        sm = ssim_score(q, c)
        final = 0.3 * ps + 0.3 * ss + 0.4 * sm
        results.append(CandidateScore(str(p), round(ps, 3), round(ss, 3), round(sm, 3), round(final, 3)))
    return sorted(results, key=lambda x: x.final, reverse=True)[:3]


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="训练⑤：真古董 ↔ 假古董匹配排序")
    ap.add_argument("--query", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", default="data/training/match.json")
    args = ap.parse_args()
    ranked = rank_candidates(args.query, args.candidates)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([r.to_dict() for r in ranked], ensure_ascii=False, indent=2), encoding="utf-8")
    for i, r in enumerate(ranked, 1):
        print(f"{i}. {Path(r.path).name}  final={r.final} phash={r.phash} sift={r.sift} ssim={r.ssim}")
    print(f"写出 {out}")


if __name__ == "__main__":
    main()
