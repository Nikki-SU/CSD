"""训练②：书写记法风格（显式碳程度谱）的**画法特征提取**。

用户定义的三段（1985 年前，结构式 → 结构简式 的连续演化）：
    dense     前期：每个碳基本都写字（CH3 / CH2 / CH / CO...），介于结构式与结构简式之间
    hybrid    中期：混合式——主链/环用键线，支链用结构简式（Me/Et/Ph 或 CH2CH3）
    skeletal  后期：现代键线式——碳不写，只标杂原子

**红线（用户反复强调）：只量"怎么写"，绝不量"写了什么"。**
因此下列内容量一律不进特征：
    环数、环大小、是否含环、原子个数、分子个数、分子大小、键的类型
所有特征都按"结构顶点数"或"图尺寸"归一化，使内容被除掉。
年度只用于校准与验证，不做预测输入。

实现要点（都是踩过坑后确定的）：
1. **不能用轮廓法分离线与字**：键线把字包在里面时外轮廓会把整幅图吞成一个
   （实测苯环外轮廓吞掉内部全部结构，只数到 3 个轮廓、0 条键）。
   正确做法：键 = 长直线段（LSD），字 = 从墨迹里扣掉直线后剩下的连通域。
2. **不能用 HoughCircles 判环**：实测会把 ⊕ 电荷与杂原子小圈误判成苯环（已弃用）。
3. **不用 OCR**：跨年代字体漂移，OCR 不可靠也无必要。用几何判"多字符紧排 / 带下标"
   即可识别 CH3、C6H5、CH₂ 这类显式碳标记。
4. **分母必须用顶点数**：用键数会失真（CCO 只有 1 根键却有 3 个顶点），
   用墨迹面积会让小分子虚高。显式碳式的定义是"每个顶点都写字"。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from .char_templates import classify_glyph, glyph_shape

TIERS = ("dense", "hybrid", "skeletal")
TIER_LABEL = {"dense": "显式碳式", "hybrid": "混合式", "skeletal": "现代键线式"}

FEATURE_NAMES = (
    # 核心思路（用户校正）：不数字数，量"多少被画、多少被写"。
    # 而"写的这块文字是不是显式碳"由**带下标**判定——这是最纯净的判据：
    #   CH3 / CH2 / C6H5 / C2H5 / CO2R / MeO 都带下标数字；
    #   键线式里剩的 O / N / S / OH / NH 都不带下标。
    # 下标是"显式碳缩写"的普遍特征，而"有几个杂原子"是内容，与它无关。
    "sub_block_ratio",      # 带下标的文字块 / 全部文字块  ← 核心判别量
    "block_per_diag",       # 文字块数 / 图尺寸：文字有多密
    "text_ink_fraction",    # 文字墨量占比（辅助，红线验证不过，仅诊断用）
    "group_wideness",       # 文字块平均宽度（辅助）
    "stroke_rel",           # 相对线宽
    "bond_len_ratio",       # 键长 / 图对角
    "bond_len_cv",          # 键长一致性
    "ring_straight",        # 环是直边多边形还是圆弧（画法，非"有没有环"）
)


@dataclass
class NotationFeatures:
    image: str
    width: int
    height: int
    glyph_count: int = 0
    bond_count: int = 0
    ring_count: int = 0
    values: list[float] = field(default_factory=list)

    def vec(self) -> np.ndarray:
        return np.array(self.values, dtype=float)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["feature_names"] = list(FEATURE_NAMES)
        return d


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
def _read_gray(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"读不了图片: {path}")
    return img


def _ink(gray: np.ndarray) -> np.ndarray:
    """墨迹为 255、背景 0（Otsu 自适应，抗扫描灰度不均）。"""
    if gray.mean() > 127:
        _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return b


# ---------------------------------------------------------------------------
# 键（直线段）识别：LSD
# ---------------------------------------------------------------------------
def _lsd_segments(gray: np.ndarray) -> list[tuple[float, float, float, float]]:
    """检测长直线段，返回 [(x1,y1,x2,y2)]。化学键是直线，字母笔画是曲线。"""
    try:
        lsd = cv2.createLineSegmentDetector()
    except Exception:
        return []
    try:
        lines = lsd.detect(gray)[0]
    except cv2.error:
        return []
    if lines is None:
        return []
    out = []
    arr = np.asarray(lines, dtype=float).reshape(-1, 4)
    for x1, y1, x2, y2 in arr:
        out.append((float(x1), float(y1), float(x2), float(y2)))
    return out


def _lsd_bond_lengths(gray: np.ndarray, min_rel: float = 0.018) -> list[float]:
    """过滤出"像化学键"的线段。

    长度下限不能用固定比例：实测取 0.045*diag 时苯环的短键全被滤掉
    （bond_count=1，而图上有 6+ 根键），分母偏小导致分数虚高。
    改为按**该图所有线段长度的中位数**自适应取阈，短键也能进来。
    """
    h, w = gray.shape
    diag = math.hypot(w, h) or 1.0
    segs = _lsd_segments(gray)
    if not segs:
        return []

    lens = np.array([math.hypot(x2 - x1, y2 - y1) for x1, y1, x2, y2 in segs], dtype=float)
    if lens.size == 0:
        return []
    med = float(np.median(lens))
    # 一个"化学键"至少要是中位线段的 0.45 倍，且不低于图尺寸的 1.8%
    thr = max(min_rel * diag, 0.45 * med)

    picked: list[tuple[float, float, float]] = []
    for (x1, y1, x2, y2), L in zip(segs, lens):
        if L < thr:
            continue
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dup = False
        for px, py, pl in picked:
            if math.hypot(mx - px, my - py) < 0.05 * diag and abs(L - pl) < 0.22 * pl:
                dup = True
                break
        if not dup:
            picked.append((mx, my, float(L)))
    return [p[2] for p in picked]


def _hole_ratio(comp: np.ndarray) -> float:
    """成分内部空洞占包围盒的比例。字母是实心笔画+小孔；空心环是大空洞。"""
    h, w = comp.shape
    box = max(h * w, 1)
    filled = int((comp > 0).sum())
    return 1.0 - filled / box


def _bond_count_from_segments(gray: np.ndarray, diag: float) -> int:
    """用 LSD 线段端点去重后估键数——比连通域稳。

    为什么不用连通域数：相邻的键在 Otsu 二值化后常连成一片，一根环上的
    6 根键可能只产生 1~2 个连通域，导致分母严重偏小、epv 虚高
    （实测 1957 那张双苯环图只数到 7 根，实际 15+）。
    LSD 是按局部梯度方向找直线段，能把环的每条边分别找出，
    再用端点聚类去重（同一顶点的多条边共享端点）。
    """
    segs = _lsd_segments(gray)
    if not segs:
        return 0
    min_len = 0.022 * diag
    keep = [(x1, y1, x2, y2) for x1, y1, x2, y2 in segs
            if math.hypot(x2 - x1, y2 - y1) >= min_len]
    if not keep:
        return 0
    # 端点聚类：距离小于 0.035*diag 的端点视为同一个顶点
    eps = 0.035 * diag
    centers: list[tuple[float, float]] = []

    def add_point(px: float, py: float) -> None:
        for cx, cy in centers:
            if math.hypot(px - cx, py - cy) <= eps:
                return
        centers.append((px, py))

    # 同一根线 LSD 常给出两侧边界，先用中点去重
    dedup: list[tuple[float, float, float, float]] = []
    for x1, y1, x2, y2 in keep:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        L = math.hypot(x2 - x1, y2 - y1)
        if any(math.hypot(mx - d[0], my - d[1]) < 0.03 * diag and abs(L - d[2]) < 0.3 * d[2]
               for d in dedup):
            continue
        dedup.append((mx, my, L, x1, y1, x2, y2))

    for _, _, _, x1, y1, x2, y2 in dedup:
        add_point(x1, y1)
        add_point(x2, y2)
    return len(centers)


def _component_linearity(pts: np.ndarray) -> float:
    """一个连通域的点集有多像"一条直线"（0=不像, 1=极像）。

    这是分离"化学键"与"字母"的正确判据：
    - 键：所有墨点落在一条细线附近 → 拟合残差极小
    - 字母：笔画有横有竖有弧 → 拟合到一条线的残差大
    只看形状，不看字体，因此跨年代通用。
    """
    if len(pts) < 8:
        return 0.0
    xy = pts.reshape(-1, 2).astype(np.float32)
    mean = xy.mean(axis=0)
    u = xy - mean
    # PCA：第一主方向的能量占比 = 线性度
    cov = u.T @ u / max(len(u) - 1, 1)
    try:
        ev = np.linalg.eigvalsh(cov)
    except np.linalg.LinAlgError:
        return 0.0
    ev = np.sort(np.maximum(ev, 0))
    total = ev.sum()
    if total <= 1e-9:
        return 0.0
    return float(ev[-1] / total)


def _split_lines_and_glyphs(ink: np.ndarray, h: int, w: int, diag: float):
    """把墨迹连通域分成"键线"与"字"，返回 (bond_lengths, glyph_boxes, glyph_comps, glyph_ink)。

    glyph_ink 是每个字形真实的墨迹像素数（不是 bbox 面积）——
    后者会把空白也算进去，导致"文字墨量占比"恒为 1（实测踩到）。
    """
    closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)

    bonds: list[float] = []
    boxes: list[tuple[int, int, int, int]] = []
    comps: list[np.ndarray] = []
    inks: list[int] = []
    min_bond = 0.030 * diag
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < 10:
            continue
        comp = (labels[y:y + bh, x:x + bw] == i).astype(np.uint8)
        pts = cv2.findNonZero(comp)
        if pts is None or len(pts) < 8:
            continue
        lin = _component_linearity(pts)
        length = math.hypot(bw, bh)
        if lin >= 0.92 and length >= min_bond:
            bonds.append(float(length))
        elif lin < 0.92 and 0.010 * h <= bh <= 0.32 * h and bw <= 0.45 * w:
            if bw * bh > 0.10 * w * h:
                continue
            boxes.append((x, y, bw, bh))
            comps.append(comp)
            inks.append(int(area))
    return bonds, boxes, comps, inks


# ---------------------------------------------------------------------------
# token 化：区分"写了碳"与"只标杂原子"
# ---------------------------------------------------------------------------
def _group_tokens(boxes: list[tuple[int, int, int, int]], comps: list[np.ndarray] | None = None) -> list[dict]:
    """水平紧挨 / 带下标的字形并成 token，返回 {n_chars, has_sub, has_carbon}。

    判据（决定"这是不是显式碳"，不是"有没有字"）：
    - 纯键线式只剩单个杂原子字母 O / N / S —— 单字符、无碳字形
    - 显式碳式写 CH3 / CH2 / C2H5 / C6H5 —— **含碳字形**（按字形形状判，见 char_templates）

    has_carbon 是关键：它用字形形状（宽高比+填充率）判"这个字是不是 C"，
    而不是靠"多字符"——因为 OH、Me 也是多字符，但都不是碳。
    这正是用户强调的红线：不能把内容（有几个杂原子）当画法（写不写碳）。
    """
    if not boxes:
        return []
    heights = [b[3] for b in boxes]
    med_h = float(np.median(heights)) or 1.0

    # 先给每个字形判类（carbon / hetero / sub）
    kinds: list[str] = []
    for i, (x, y, bw, bh) in enumerate(boxes):
        if comps is not None and i < len(comps):
            kinds.append(classify_glyph(glyph_shape(comps[i]), med_h))
        else:
            kinds.append("hetero" if bw / max(bh, 1) < 0.95 else "carbon")

    rows: list[list[int]] = []
    mids = [b[1] + b[3] / 2 for b in boxes]
    order = sorted(range(len(boxes)), key=lambda i: mids[i])
    for i in order:
        if rows and abs(mids[i] - mids[rows[-1][0]]) <= 0.55 * med_h:
            rows[-1].append(i)
        else:
            rows.append([i])

    tokens: list[dict] = []
    for row in rows:
        row = sorted(row, key=lambda i: boxes[i][0])
        cur = {"n": 1, "sub": False, "carbon": kinds[row[0]] == "carbon"}
        cur_right = boxes[row[0]][0] + boxes[row[0]][2]
        cur_h = boxes[row[0]][3]
        for i in row[1:]:
            x, y, w2, h2 = boxes[i]
            gap = x - cur_right
            is_sub = kinds[i] == "sub"
            close = gap <= 0.50 * max(med_h, cur_h)
            if (is_sub and gap <= 0.65 * med_h) or (close and gap >= -0.18 * med_h):
                cur["n"] += 1
                cur["sub"] = cur["sub"] or is_sub
                cur["carbon"] = cur["carbon"] or kinds[i] == "carbon"
                cur_right = max(cur_right, x + w2)
                cur_h = max(cur_h, h2)
            else:
                tokens.append(cur)
                cur = {"n": 1, "sub": False, "carbon": kinds[i] == "carbon"}
                cur_right, cur_h = x + w2, h2
        tokens.append(cur)
    return tokens


# ---------------------------------------------------------------------------
# 环（仅用于画法判断与诊断；环数本身属内容，不进特征）
# ---------------------------------------------------------------------------
def _ring_count(ink: np.ndarray) -> int:
    closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6, 6)))
    contours, hier = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return 0
    hier = hier[0]
    return sum(1 for i, c in enumerate(contours)
               if hier[i][3] == -1 and hier[i][2] != -1 and cv2.contourArea(c) >= 300)


def _ring_straightness(ink: np.ndarray) -> float:
    """环是"直边多边形"还是"圆弧"的比例（画法量，不等于"有没有环"这个内容）。

    直边多边形 ≈ 后期键线式；圆弧/圆圈 ≈ 早期画法。无环时返回中性 0.5。
    """
    closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6, 6)))
    contours, hier = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return 0.5
    hier = hier[0]
    straight = total = 0
    for i, c in enumerate(contours):
        if hier[i][3] != -1 or hier[i][2] == -1:
            continue
        if cv2.contourArea(c) < 300:
            continue
        inner = contours[hier[i][2]]
        peri = cv2.arcLength(inner, True)
        if peri < 20:
            continue
        total += 1
        if 4 <= len(cv2.approxPolyDP(inner, 0.045 * peri, True)) <= 9:
            straight += 1
    return straight / total if total else 0.5


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def extract_notation(image_path: str | Path) -> NotationFeatures:
    if cv2 is None:
        raise RuntimeError("需要 opencv-python-headless（pip install -r requirements.txt）")
    gray = _read_gray(image_path)
    h, w = gray.shape
    diag = math.hypot(w, h) or 1.0
    ink = _ink(gray)
    ink_area = int((ink > 0).sum())
    if ink_area < 20:
        return NotationFeatures(str(image_path), w, h, values=[0.0] * len(FEATURE_NAMES))

    # ---- 分离"键线"与"字"：按连通域线性度判，不用 LSD ----
    # LSU/LSD 会把 C/H 的竖笔画也判成直线，扣线时把字整块抹掉
    # （实测 1906 全显式碳图被抹成 9 个残片、特征全 0）。
    # 线性度（PCA 第一主方向能量占比）更稳：键≈1，字母有横有竖有弧→低。
    bonds, glyph_boxes, glyph_comps, glyph_inks = _split_lines_and_glyphs(ink, h, w, diag)
    bond_count = len(bonds)
    glyph_count = len(glyph_boxes)

    # ---- 文字块的"大小"：不数字数，量每个文字块的宽度与墨量 ----
    # 用户校正的核心：块大 = 缩写支链（CH2CH3 / CO2R / MeO 这种"写出来"的整块）；
    # 块小 = 单个杂原子（O / N / S，键线式里剩下的零散标记）。
    blocks = _text_blocks(glyph_boxes, glyph_inks, h)
    text_ink = int(sum(b["ink"] for b in blocks))
    widen = float(np.mean([b["wideness"] for b in blocks])) if blocks else 0.0
    sub_ratio = (sum(1 for b in blocks if b["has_sub"]) / len(blocks)) if blocks else 0.0

    ring_straight = _ring_straightness(ink)

    # 笔画宽度：单行水平墨迹段宽度的中位数
    widths: list[int] = []
    for row in (ink > 0):
        cols = np.where(row)[0]
        if cols.size == 0:
            continue
        splits = np.where(np.diff(cols) > 1)[0]
        starts = np.concatenate(([0], splits + 1))
        ends = np.concatenate((splits, [cols.size - 1]))
        for s, e in zip(starts, ends):
            widths.append(int(cols[e] - cols[s] + 1))
    stroke = float(np.median(widths)) if widths else 1.0

    # ---- 归一化：文字块数用"图尺寸"归、文字墨量用"总墨量"归 ----
    # 不用 bond_count 做分母——它本身就不稳（纯键线的 1950 图因二值化断裂被数成 0 键，
    # 导致 group_per_bond=2.0 荒谬）。图尺寸是唯一稳定的尺度。
    # 文字块数按"每 100px 图对角"计，这个量与分子画得多大无关（都是同一版式）。
    diag100 = diag / 100.0
    ink_total = max(ink_area, 1)
    bond_len_median = float(np.median(bonds)) if bonds else 0.0
    bond_cv = float(np.std(bonds) / (bond_len_median or 1.0)) if bonds else 0.0

    values = [
        round(sub_ratio, 3),                                 # sub_block_ratio（核心）
        round(len(blocks) / diag100, 3),                      # block_per_diag
        round(min(text_ink / ink_total, 1.0), 3),           # text_ink_fraction（辅助）
        round(widen, 3),                                    # group_wideness（辅助）
        round(stroke / diag, 4),                            # stroke_rel
        round(bond_len_median / diag, 3),                   # bond_len_ratio
        round(min(bond_cv, 3.0), 3),                         # bond_len_cv
        round(ring_straight, 3),                            # ring_straight
    ]
    return NotationFeatures(str(image_path), w, h, glyph_count, bond_count,
                            _ring_count(ink), values)


def _text_blocks(boxes: list[tuple[int, int, int, int]], inks: list[int], h: int) -> list[dict]:
    """把相邻字形聚成"文字块"，返回每块的 {wideness, ink}。

    这是"块有多大"的实现：CH2CH3 是 6 个字形紧排的一大块；
    键线式里只剩单个 O，是一小块。wideness = 块宽 / 块高，
    直接表达"这块文字有几个字宽"——与具体是哪个字母无关，因此不依赖 OCR。
    """
    if not boxes:
        return []
    heights = [b[3] for b in boxes]
    med_h = float(np.median(heights)) or 1.0

    rows: list[list[int]] = []
    mids = [b[1] + b[3] / 2 for b in boxes]
    for i in sorted(range(len(boxes)), key=lambda i: mids[i]):
        if rows and abs(mids[i] - mids[rows[-1][0]]) <= 0.55 * med_h:
            rows[-1].append(i)
        else:
            rows.append([i])

    out: list[dict] = []
    for row in rows:
        row = sorted(row, key=lambda i: boxes[i][0])
        cur = [row[0]]
        right = boxes[row[0]][0] + boxes[row[0]][2]
        for i in row[1:]:
            gap = boxes[i][0] - right
            if gap <= 0.55 * med_h:          # 紧挨 → 同属一块文字
                cur.append(i)
                right = max(right, boxes[i][0] + boxes[i][2])
            else:
                out.append(_block_of(cur, boxes, inks))
                cur, right = [i], boxes[i][0] + boxes[i][2]
        out.append(_block_of(cur, boxes, inks))
    return out


def _block_of(idxs: list[int], boxes: list[tuple[int, int, int, int]], inks: list[int]) -> dict:
    left = min(boxes[i][0] for i in idxs)
    right = max(boxes[i][0] + boxes[i][2] for i in idxs)
    bh = max(boxes[i][3] for i in idxs) or 1
    bw = right - left
    # 带下标：块内存在"明显更矮"的字形（高度 < 0.78 块高）。
    # 这是区分"显式碳缩写"与"杂原子标签"的关键纯净判据：
    #   CH3 / C6H5 / CO2R / C2H5 必带下标数字；OH / NH / N≡C 不带下标。
    n_sub = sum(1 for i in idxs if boxes[i][3] < 0.78 * bh)
    return {"wideness": min(bw / bh, 8.0),
            "ink": sum(inks[i] for i in idxs),
            "n_boxes": len(idxs),
            "has_sub": n_sub > 0}


# ---------------------------------------------------------------------------
# 规则初判（档位数最终由数据聚类定，见 notation_clf）
# ---------------------------------------------------------------------------
def rule_tier(f: NotationFeatures) -> tuple[str, float]:
    """按"带下标的文字块占比"判三档，返回 (档位, 把握度 0~1)。

    **下标是显式碳缩写最纯净的标志**：
        CH3 / CH2 / C6H5 / C2H5 / CO2R / MeO  —— 都带下标数字
        键线式里剩的 O / N / S / OH / NH        —— 都不带下标
    这个比例与"有几个杂原子、有几个环"完全无关，是纯画法量。

    配合"文字块密度"（每单位图尺寸有几个文字块）分前期/后期：
        前期：每个顶点都写 → 块多且多数带下标 → sub 高
        中期：只写画不出的支链 → 块少但带下标 → sub 中等偏高
        后期：只剩杂原子 → 块有但不带下标 → sub 接近 0
    """
    v = dict(zip(FEATURE_NAMES, f.values))
    sub = v["sub_block_ratio"]
    dens = min(v["block_per_diag"] / 2.0, 1.0)

    if sub >= 0.42:
        # 带下标的块多：可以用"块密度"再分前期（块极多）与中期（块适中）
        if dens >= 0.75:
            return "dense", min(1.0, 0.5 + (sub - 0.42) * 1.2)
        return "hybrid", min(1.0, 0.55 + (sub - 0.42) * 0.9)
    return "skeletal", min(1.0, 0.5 + (0.42 - sub) * 1.4)


def describe(f: NotationFeatures) -> dict:
    v = dict(zip(FEATURE_NAMES, f.values))
    tier, conf = rule_tier(f)
    return {
        "image": f.image,
        "tier": tier,
        "tier_label": TIER_LABEL[tier],
        "confidence": round(conf, 3),
        "glyph_count": f.glyph_count,
        "bond_count": f.bond_count,
        "ring_count": f.ring_count,
        "sub_block_ratio": v["sub_block_ratio"],
        "block_per_diag": v["block_per_diag"],
        "text_ink_fraction": v["text_ink_fraction"],
        "group_wideness": v["group_wideness"],
        "ring_straight": v["ring_straight"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _iter_images(root: str | Path) -> list[Path]:
    root = Path(root)
    exts = (".png", ".jpg", ".jpeg")
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in exts)


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="csd-notation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("features", help="对目录内每张图打印画法特征")
    p1.add_argument("--dir", required=True)
    p1.add_argument("--limit", type=int, default=0)
    p1.add_argument("--out", default="")

    p2 = sub.add_parser("one", help="单图诊断")
    p2.add_argument("--image", required=True)

    args = ap.parse_args()
    if args.cmd == "one":
        print(json.dumps(describe(extract_notation(args.image)), ensure_ascii=False, indent=2))
        return

    files = _iter_images(args.dir)
    if args.limit:
        files = files[:args.limit]
    rows = []
    for p in files:
        try:
            rows.append(describe(extract_notation(p)))
        except Exception as exc:
            rows.append({"image": str(p), "error": f"{type(exc).__name__}: {exc}"})
    by_tier: dict[str, int] = {}
    for r in rows:
        t = r.get("tier", "error")
        by_tier[t] = by_tier.get(t, 0) + 1
    print(json.dumps({"count": len(rows), "tiers": by_tier}, ensure_ascii=False))
    for r in rows[:20]:
        print(f"  {r.get('tier','?'):9s} ink={r.get('text_ink_fraction')} "
              f"wide={r.get('group_wideness')} per_bond={r.get('group_per_bond')} "
              f"{Path(r['image']).name}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已写", args.out)


if __name__ == "__main__":
    main()
