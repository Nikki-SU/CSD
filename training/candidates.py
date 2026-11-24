"""训练⑦：候选流水线——把真古董图串成 A/B/C 三个带结构的候选。

完整链路（两轮筛选）：
    ① 拓扑识别：topo.py 从真图提取 (环数, 环大小, 标签)
    ② 第一轮·拓扑筛：library.TopoIndex 精确匹配 → 指标不全匹配的直接排除
    ③ 第二轮·渲染：style.render_smiles 把候选按年代画风渲染成假古董图
    ④ 第二轮·比图：matching 的三层比对（pHash/SIFT/SSIM）排序
    ⑤ 取前三 = A/B/C，每个都带 smiles + 渲染图 + 得分

输出结构（写 candidates.json，前端审阅页直接读）：
    {"figure_id": ..., "image_topo": {...},
     "candidates": [
        {"rank": 0, "smiles": ..., "cid": ..., "render": "相对路径", "score": 0.xx},
        ...最多 3 条 ]
    }
"""
from __future__ import annotations

import json
from pathlib import Path

from .library import TopoIndex, Candidate
from .matching import phash, phash_dist, sift_score, ssim_score, _normalize
from .style import render_smiles
from .topo import extract_topology


def _render_and_score(query_img: Path, cand: Candidate, style: dict, out_dir: Path) -> dict | None:
    """渲染一个候选并按三层比对打分。渲染失败返回 None。"""
    import cv2
    import numpy as np

    name = f"{cand.cid or 'c'}_{len(cand.smiles)}_{abs(hash(cand.smiles)) % 10000}"
    png = out_dir / "renders" / f"{name}.png"
    try:
        render_smiles(cand.smiles, style, png)
    except (ValueError, RuntimeError):
        return None
    q = cv2.imread(str(query_img))
    c = cv2.imread(str(png))
    if q is None or c is None:
        return None
    qh = phash(_normalize(q))
    d = phash_dist(qh, phash(_normalize(c)))
    ps = max(0.0, 1.0 - d)
    ss = sift_score(_normalize(q), _normalize(c))
    sm = ssim_score(q, c)
    final = 0.3 * ps + 0.3 * ss + 0.4 * sm
    return {
        "smiles": cand.smiles, "cid": cand.cid,
        "render": png.relative_to(out_dir).as_posix(),
        "score": round(float(final), 3),
        "phash": round(float(ps), 3), "sift": round(float(ss), 3), "ssim": round(float(sm), 3),
    }


def build_candidates(
    figure_id: str,
    query_img: str | Path,
    index: TopoIndex,
    style: dict,
    out_dir: str | Path,
    templates_path: str | Path | None = None,
    prefilter_limit: int = 200,
) -> dict:
    """对一张真图跑完整两轮筛选，返回 A/B/C 候选（带 SMILES）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    query_img = Path(query_img)

    # ① 拓扑识别
    image_topo = dict(extract_topology(query_img, templates_path))

    # ② 第一轮拓扑筛
    cands = index.query(image_topo, limit=prefilter_limit)

    # ③④ 渲染 + 比图
    scored = []
    for cand in cands:
        r = _render_and_score(query_img, cand, style, out_dir)
        if r:
            scored.append(r)

    # ⑤ 取前三
    scored.sort(key=lambda x: x["score"], reverse=True)
    top3 = scored[:3]
    for i, item in enumerate(top3):
        item["rank"] = i  # 0=A 1=B 2=C

    payload = {
        "figure_id": figure_id,
        "image_topo": {"rings": image_topo.get("rings"),
                       "ring_sizes": image_topo.get("ring_sizes"),
                       "labels": image_topo.get("labels"),
                       "warnings": image_topo.get("warnings", [])},
        "prefiltered": len(cands),
        "rendered": len(scored),
        "candidates": top3,
    }
    (out_dir / f"{figure_id}_candidates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
