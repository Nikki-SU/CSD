"""从结构式裁图识别顶点：擦字 → 边拟合 → 双向延长 → 求交合并。

判据来自用户逐条口述（2026-11-26），不是设计者的自由发挥：

1. 字块要尽量跟实际的字差不多大，把字块换成球/顶点。
2. 擦字：只擦字笔画本身，不按 bbox 整块擦、不膨胀——否则会把穿过字的键一起擦掉。
3. 擦字后剩下的每个连通域就是一条完整的边，拟合成直线（不找骨架端点）。
   用户原话：「画一个六边形，把 6 个角擦掉，只要把这 6 条边双向延长，
   它最终还是会成为一个六边形」。
4. 键一定有两头，不管多短都要沿自身方向往两端延长；最多延长到一个阈值
   （不会超出页面、也不会过于长）。实测阈值取 2.5 字高。
5. 交点合并：距离近 **且** 夹角合理，才并成一个顶点。
   用户画圈说明：一个角上可能挤着好几个两两交点（多线交一点、双键），
   但那仍是一个顶点；阈值不能太激进，否则双键或画得不规范处会被拆成两点。
6. 残笔过滤：真键宽 3~5px，字母残笔宽 1~2px，按宽度分开。
   用户原话：「碳氢没有擦干净，氢的竖线还留着」→ 宽<3px 丢掉；
   「它还是很粗的，它就是键」→ 短但粗的键保留。

状态：顶点识别在人工核对过的样本上成立（1975/1906 六元环均为 6 顶点）。
环的分类（小环/大环/中环、单环/多环）尚未稳定，不在本模块范围。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

ANISO_GLYPH = 0.55
MIN_BOND_WIDTH = 3          # 宽 < 3px 的连通域 = 字母残笔
MIN_AREA_FRAC = 0.02        # 面积下限（按字高平方）
EXTEND_CH = 2.5             # 边延长上限（字高倍数）
MERGE_DIST_CH = 1.2         # 交点合并距离（字高倍数）
MERGE_ANGLE = (35.0, 135.0) # 交点合并的夹角合理区间（取锐角后判定）


def ink_binary(gray):
    """墨的二值化：Otsu ∪ 自适应，细线用自适应兜底。"""
    import cv2

    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ad = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 10)
    return (((bw > 0) | (ad > 0))).astype(np.uint8)


def _char_height(ink):
    import cv2

    n0, _l0, s0, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    hs = [int(s0[i, cv2.CC_STAT_HEIGHT]) for i in range(1, n0)
          if int(s0[i, cv2.CC_STAT_AREA]) >= 20]
    return float(np.median(hs)) if hs else 12.0


def split_glyph_stroke(gray, ink=None, ch=None):
    """按结构张量的局部方向一致性，把墨分为字 / 线。

    线单向延伸 → 各向异性高；字的笔画多向交汇 → 低。
    与斜率、折线、图缩放无关。
    """
    import cv2

    if ink is None:
        ink = ink_binary(gray)
    if ch is None:
        ch = _char_height(ink)
    if int(ink.sum()) < 300:
        return None, None, ch

    ks = int(max(5, ch * 0.55 * 2)) // 2 * 2 + 1
    b = (ink * 255).astype(np.uint8)
    gx = cv2.Sobel(b.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(b.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    m = cv2.blur(ink.astype(np.float32), (ks, ks)) + 1e-6
    sxx = cv2.blur(gx * gx, (ks, ks)) / m
    syy = cv2.blur(gy * gy, (ks, ks)) / m
    sxy = cv2.blur(gx * gy, (ks, ks)) / m
    tr = sxx + syy
    det = sxx * syy - sxy * sxy
    disc = np.sqrt(np.maximum(tr * tr / 4 - det, 0))
    aniso = ((tr / 2 + disc) - (tr / 2 - disc)) / (tr + 1e-6)
    glyph = ((ink > 0) & (aniso < ANISO_GLYPH)).astype(np.uint8) * 255
    stroke = ((ink > 0) & (aniso > 0.75)).astype(np.uint8) * 255
    return glyph, stroke, ch


def remove_glyphs(gray, glyph=None):
    """擦掉字笔画，返回 (去字灰度图, glyph 掩码, ch)。只擦字本身，不膨胀。"""
    if glyph is None:
        glyph, _stroke, ch = split_glyph_stroke(gray)
    else:
        ch = _char_height(ink_binary(gray))
    if glyph is None:
        return None, None, None
    out = gray.copy()
    out[glyph > 0] = 255
    return out, (glyph > 0).astype(np.uint8), ch


def clean_bond(no_glyph_gray, ch, min_width=MIN_BOND_WIDTH):
    """去字图 → 干净的键线（0/1）。按宽度滤掉字母残笔和碎点。"""
    import cv2

    raw = (no_glyph_gray < 200).astype(np.uint8)
    min_area = max(6, int(MIN_AREA_FRAC * ch * ch))
    n, lab, st, _ = cv2.connectedComponentsWithStats(raw, connectivity=8)
    keep = np.zeros_like(raw)
    for i in range(1, n):
        w, h, a = int(st[i, 2]), int(st[i, 3]), int(st[i, 4])
        if a < min_area or min(w, h) < min_width:
            continue
        keep[lab == i] = 1
    return keep


def fit_edges(bond, ch, min_len_frac=0.6):
    """每条连通域 → 一条直线（PCA 拟合整段墨，不找端点）。"""
    import cv2

    n, lab, st, _ = cv2.connectedComponentsWithStats(bond.astype(np.uint8), 8)
    min_px = max(8, int(ch * min_len_frac))
    lines = []
    for i in range(1, n):
        pix = np.argwhere(lab == i)
        if len(pix) < min_px:
            continue
        pts = pix[:, ::-1].astype(float)
        mean = pts.mean(axis=0)
        c = pts - mean
        cov = c.T @ c / len(pts)
        vals, vecs = np.linalg.eigh(cov)
        d = vecs[:, int(np.argmax(vals))]
        t = c @ d
        lines.append({"mean": mean, "dir": d,
                      "t0": float(t.min()), "t1": float(t.max()),
                      "n": int(len(pix)), "id": i})
    return lines


def intersections(lines, ch, H, W, extend=None):
    """双向延长后两两求交 → 按「距离近 + 夹角合理」合并成顶点。

    返回 (clusters, raw_intersections)。
    cluster: {"x", "y", "pts", "lines"}
    """
    if extend is None:
        extend = max(6.0, ch * EXTEND_CH)
    pts = []
    for i in range(len(lines)):
        a, da = lines[i]["mean"], lines[i]["dir"]
        ta0, ta1 = lines[i]["t0"] - extend, lines[i]["t1"] + extend
        for j in range(i + 1, len(lines)):
            b, db = lines[j]["mean"], lines[j]["dir"]
            tb0, tb1 = lines[j]["t0"] - extend, lines[j]["t1"] + extend
            M = np.column_stack([da, -db])
            if abs(float(np.linalg.det(M))) < 1e-6:
                continue
            t, s = np.linalg.solve(M, b - a)
            if not (ta0 <= t <= ta1 and tb0 <= s <= tb1):
                continue
            p = a + t * da
            if not (0 <= p[0] <= W and 0 <= p[1] <= H):
                continue
            pts.append((float(p[0]), float(p[1]), i, j))

    tol = max(4.0, MERGE_DIST_CH * ch)
    lo, hi = MERGE_ANGLE
    clusters = []
    for x, y, i, j in pts:
        placed = False
        for c in clusters:
            if math.hypot(x - c["x"], y - c["y"]) > tol:
                continue
            cos = float(np.clip(abs(lines[i]["dir"] @ lines[j]["dir"]), -1.0, 1.0))
            ang = math.degrees(math.acos(cos))
            ang = min(ang, 180.0 - ang)
            if not (lo <= ang <= hi):
                continue
            c["pts"].append((x, y))
            c["lines"].add(i)
            c["lines"].add(j)
            c["x"] = float(np.mean([p[0] for p in c["pts"]]))
            c["y"] = float(np.mean([p[1] for p in c["pts"]]))
            placed = True
            break
        if not placed:
            clusters.append({"x": x, "y": y, "pts": [(x, y)], "lines": {i, j}})
    return clusters, pts


def find_vertices(gray, extend=None):
    """主入口：返回 dict。gray 为单通道裁图。

    {"ch", "no_glyph", "bond", "lines", "vertices", "raw", "ok"}
    """
    import cv2

    no_glyph, glyph_mask, ch = remove_glyphs(gray)
    if no_glyph is None:
        return {"ok": False, "reason": "墨太少"}
    H, W = gray.shape[:2]
    bond = clean_bond(no_glyph, ch)
    lines = fit_edges(bond, ch)
    clusters, raw = intersections(lines, ch, H, W, extend=extend)
    return {"ok": True, "ch": ch, "no_glyph": no_glyph,
            "bond": bond, "lines": lines,
            "vertices": clusters, "raw": raw,
            "n_vertices": len(clusters)}


def draw_vertices(gray, result):
    """可视化：黑=键线，灰=延长线，红=顶点。"""
    import cv2

    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if not result.get("ok"):
        return vis
    ch = result["ch"]
    vis[result["bond"] > 0] = (0, 0, 0)
    ext = max(6.0, ch * EXTEND_CH)
    for L in result["lines"]:
        m, d = L["mean"], L["dir"]
        p0 = m - (L["t0"] - ext) * d
        p1 = m + (L["t1"] + ext) * d
        cv2.line(vis, (int(p0[0]), int(p0[1])),
                 (int(p1[0]), int(p1[1])), (150, 150, 150), 1)
    for c in result["vertices"]:
        cv2.circle(vis, (int(c["x"]), int(c["y"])), 3, (0, 0, 255), -1)
    return vis


if __name__ == "__main__":
    import sys

    for name in sys.argv[1:]:
        img = cv2.imread(name, cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(name, "读不了")
            continue
        r = find_vertices(img)
        if r.get("ok"):
            print(f"{Path(name).name}: ch={r['ch']:.1f} "
                  f"edges={len(r['lines'])} vertices={r['n_vertices']}")
        else:
            print(f"{Path(name).name}: {r['reason']}")
