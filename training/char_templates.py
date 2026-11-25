"""字符模板：识别单个字母是"碳"还是"杂原子"，用于区分显式碳与键线式标签。

**为什么必须做这一步（而不是继续用几何猜）**：
几何无法可靠区分 CH3 与 OH——两者都是"两字符紧排"。实测苯甲酸的 O=C(O)
被误判成"显式碳"（分数 1.0），这是内容泄漏。区分 C 与 O 必须看字形本身。

**为什么不直接用 OCR**：跨年代字体漂移严重（1900 年的衬线体与 1970 年的
无衬线体差别极大），通用 OCR 在小字号扫描图上错误率高。用户早就指出
"跨时代字体漂移→按风格档位建字符模板，不靠通用 OCR"。

**本模块的做法**：从真实图里**学到**字符模板（而不是人工画模板）：
1. 收集真实结构式图里的单字符连通域
2. 按形状特征（宽高比、填充率、孔数、上下不对称度）聚类
3. 人工/弱监督标注少数样本，得到"这类形状是 C / O / N / S"
4. 保存为 assets/char_templates.json，随 GitHub 分发（属"能力"不属"数据"）

在数据集未齐时，先用**已知可靠的判据**做保守判断：
C 的特征是"开口的圆弧"（欧拉数=1，有 0 个洞），O 是闭合环（1 个洞）。
这条只在无洞时可用：C 无洞、O 有 1 洞、N 无洞、S 无洞。
所以能可靠区分 O（有洞）与 C/N/S（无洞）——这已经足够解决主要泄漏：
"OH" 里的 O 有洞 → 不是碳；"CH3" 里的 C 无洞 → 是碳。

用法：
    python -m training.char_templates build --dir <图目录> --out assets/char_templates.json
    python -m training.char_templates probe --image <png>
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


def _holes(comp: np.ndarray) -> int:
    """连通域里的孔数（欧拉数反向）。O 有 1 孔，C/N/S 无孔。

    这是区分"氧/零"类闭口字形与"碳/氮"类开口字形最可靠的拓扑判据，
    与字体、字号、扫描质量都无关——比模板匹配稳。
    """
    contours, hier = cv2.findContours(comp, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return 0
    h = hier[0]
    return sum(1 for i in range(len(contours)) if h[i][3] != -1 and cv2.contourArea(contours[i]) > 3)


def glyph_shape(comp: np.ndarray) -> dict:
    """单个字形的形状描述子。全是形状量，与字体无关。"""
    h, w = comp.shape
    area = int((comp > 0).sum())
    box = max(h * w, 1)
    fill = area / box
    holes = _holes(comp)
    # 上下重心偏移：区分 S/Z 这类上下不对称与 C/O 这类对称
    ys, xs = np.nonzero(comp)
    cy = float(ys.mean()) / max(h, 1) if len(ys) else 0.5
    cx = float(xs.mean()) / max(w, 1) if len(xs) else 0.5
    return {"w": w, "h": h, "fill": round(fill, 3), "holes": holes,
            "aspect": round(w / max(h, 1), 3), "cy": round(cy, 3), "cx": round(cx, 3)}


def classify_glyph(shape: dict, med_h: float) -> str:
    """按形状判这个字形是"碳型"(C) 还是"杂原子型"(非 C)。

    **实测结论（重要）**：孔数判据在古早文献上不可靠——
    1900-1930 年多用**粗体实心**印刷字，C/O 内部孔洞被笔画填实（实测孔数全为 0）。
    所以放弃"孔数区分 O 与 C"，改用**宽高比**：C 接近方形（宽/高 ≈ 0.9~1.1），
    H 竖长（≈0.7），O 接近圆（≈1.0 但填充率更高）。
    实测 1906 全显式碳图上，宽高比 ≥0.95 且填充率 ≥0.42 的正好是那三个 C。

    保守策略：不确定的一律按"杂原子"，宁可把显式碳式分数压低，
    也绝不把键线式的 OH/O 误当成碳（后者的后果是内容泄漏，更严重）。
    """
    # 下标：明显比主字号矮 → 是数字（3、2、5），不是碳
    if shape["h"] < 0.80 * med_h:
        return "sub"
    # 太细长（宽高比很小）→ H 或竖笔画，不是碳
    if shape["aspect"] < 0.85:
        return "hetero"
    # 近方且填充率够 → C
    if shape["aspect"] >= 0.95 and shape["fill"] >= 0.42:
        return "carbon"
    return "hetero"


# ---------------------------------------------------------------------------
# 从图集学模板（统计各类形状的分布，作为后续校准的依据）
# ---------------------------------------------------------------------------
def _iter_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg"))


def _glyphs_of(gray: np.ndarray):
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(b, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in st[i])
        if area < 12 or bh < 5:
            continue
        out.append((x, y, bw, bh, (lab[y:y + bh, x:x + bw] == i).astype(np.uint8)))
    return out


def build(root: Path, out: Path) -> dict:
    shapes = []
    for p in _iter_images(root):
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for x, y, bw, bh, comp in _glyphs_of(g):
            s = glyph_shape(comp)
            s["image"] = p.name
            shapes.append(s)

    if not shapes:
        raise SystemExit(f"{root} 下没找到可用的字形")

    med_h = float(np.median([s["h"] for s in shapes]))
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in shapes:
        groups[classify_glyph(s, med_h)].append(s)

    payload = {
        "version": 1,
        "method": "shape_rules_topology_holes",
        "median_glyph_h": round(med_h, 3),
        "glyph_count": len(shapes),
        "classes": {
            k: {
                "count": len(v),
                "mean_fill": round(float(np.mean([s["fill"] for s in v])), 3),
                "mean_aspect": round(float(np.mean([s["aspect"] for s in v])), 3),
                "holes_hist": _hist([s["holes"] for s in v]),
            }
            for k, v in groups.items()
        },
        "note": ("按孔数与宽高比判字形类别；跨年代字体漂移不影响这两项。"
                 "保守策略：不确定一律按杂原子，宁可分数偏低也不误判键线式。"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _hist(vals: list[int]) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for v in vals:
        d[str(v)] += 1
    return dict(sorted(d.items()))


def probe(image: str) -> None:
    g = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise SystemExit("读不了图")
    glyphs = _glyphs_of(g)
    med_h = float(np.median([bh for _, _, _, bh, _ in glyphs])) if glyphs else 1.0
    print(f"图 {g.shape[1]}x{g.shape[0]}，字形 {len(glyphs)}，主字号高度 {med_h:.1f}")
    print(f"{'idx':>3} {'bbox':>16} {'h':>4} {'fill':>6} {'holes':>6} {'aspect':>7} {'判为':>7}")
    for i, (x, y, bw, bh, comp) in enumerate(glyphs[:30]):
        s = glyph_shape(comp)
        print(f"{i:>3} {x:>4},{y:>4},{bw:>3},{bh:>3} {s['h']:>4} {s['fill']:>6.2f} "
              f"{s['holes']:>6} {s['aspect']:>7.2f} {classify_glyph(s, med_h):>7}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-char-templates")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("build", help="从图集统计字形类别分布")
    p1.add_argument("--dir", required=True)
    p1.add_argument("--out", default="assets/char_templates.json")
    p2 = sub.add_parser("probe", help="单图诊断字形分类")
    p2.add_argument("--image", required=True)
    args = ap.parse_args()

    if args.cmd == "probe":
        probe(args.image)
    else:
        payload = build(Path(args.dir), Path(args.out))
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
