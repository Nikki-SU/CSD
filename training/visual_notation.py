"""视觉记法分类：在结构式裁图上用"正文采来的字体模板"识别字符，再判档。

这是用户洞察的最终落地：
    「正文中的字和结构式用的字体肯定是同一种，只是大小不一样。你可以去使用一下正文中的字体。」

所以路径是：正文（有文本层，字符真值）→ 采字形模板 → 在结构式裁图上做模板匹配 →
得到"这块写的是 CH3 还是 OH"→ 判档。不需要 OCR 训练，不需要人工标注模板。

判档判据（红线：只量怎么写，不量写了什么）：
    sub_ratio    带下标文字块 / 全部文字块   —— CH3/C6H5/CO2R 带下标；OH/NH 不带
    has_sub_ch   含下标的块里是否含 C        —— 这才是"显式碳缩写"的确定证据
    block_ratio  多字符块 / 全部块           —— 缩写 vs 单字母
绝对数量（几个 C、几个环）一律不进判据。

用法：
    python -m training.visual_notation classify --image <png> --templates <pkl>
    python -m training.visual_notation batch --dir <按年份目录> --templates <pkl>
"""
from __future__ import annotations

import argparse
import pickle
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .notation import _ink, _read_gray, _split_lines_and_glyphs
from .pdf_glyphs import match_glyph, normalize

TIERS = ("dense", "hybrid", "skeletal")
TIER_LABEL = {"dense": "显式碳式", "hybrid": "混合式", "skeletal": "现代键线式"}

# 一个字符要被采信，相似度下限
MIN_SCORE = 0.55
DIGITS = set("0123456789")


@dataclass
class Block:
    """结构式里的一块文字（相邻字形聚成）。"""
    chars: str
    n: int
    has_sub: bool          # 是否含"明显更矮"的下标字形
    has_carbon: bool       # 是否含识别为 C 的字形
    score: float           # 该块平均匹配分

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ImageNotation:
    image: str
    tier: str = ""
    confidence: float = 0.0
    glyph_count: int = 0
    recognized: int = 0
    blocks: list[dict] = field(default_factory=list)
    sub_ratio: float = 0.0
    multi_ratio: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier_label"] = TIER_LABEL.get(self.tier, "")
        return d


def _char_of(crop_gray: np.ndarray, templates: dict) -> tuple[str, float]:
    """把结构式里的一个小字形识别成字符。

    两个关键处理，都是实测逼出来的：
    1. **先放大再二值化**：1906 那张图的标签只有 20×27px，直接 Otsu 会把 C 的
       开口填死，C 全被判成 O（'CO'→'OO'、'CH'→'OH'）。
    2. **用自适应阈值而非 Otsu**：古早印刷体笔画粗，Otsu 会偏向"全黑"，
       开口消失；自适应阈值按局部邻域取阈，能保住细小的开口缝隙。
       这是区分 C 与 O 的关键——它们唯一的差别就是那条开口。
    """
    import cv2
    up = cv2.resize(crop_gray, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
    up = cv2.GaussianBlur(up, (3, 3), 0)
    # 自适应阈值：块大小随字号缩放，保证包含整条笔画
    blk = max(11, (min(up.shape) // 3) | 1)
    b = cv2.adaptiveThreshold(up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                              cv2.THRESH_BINARY_INV, blk, 6)
    # 形态学去噪（开运算去掉孤立噪点，闭运算不做——闭运算会把 C 的开口封死）
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))
    if (b > 0).sum() < 12:
        return "", 0.0
    return match_glyph(b, templates)


def analyze_image(image: str | Path, templates: dict) -> ImageNotation:
    gray = _read_gray(image)
    h, w = gray.shape
    diag = (h ** 2 + w ** 2) ** 0.5
    ink = _ink(gray)
    _, boxes, _, inks = _split_lines_and_glyphs(ink, h, w, diag)

    if not boxes:
        return ImageNotation(str(image), tier="skeletal", confidence=0.5,
                             note="无文字")
    med_h = float(np.median([b[3] for b in boxes])) or 1.0

    # 每个字形识别成字符
    glyphs = []
    for (x, y, bw, bh) in boxes:
        crop = gray[y:y + bh, x:x + bw]
        if crop.size == 0:
            continue
        ch, sc = _char_of(crop, templates)
        glyphs.append({"ch": ch, "score": sc,
                       "x": x, "y": y, "w": bw, "h": bh,
                       "is_sub": bh < 0.78 * med_h})
    recognized = sum(1 for g in glyphs if g["score"] >= MIN_SCORE)

    # 聚块：同行且紧挨
    rows: list[list[dict]] = []
    for g in sorted(glyphs, key=lambda g: g["y"] + g["h"] / 2):
        mid = g["y"] + g["h"] / 2
        if rows and abs(mid - (rows[-1][0]["y"] + rows[-1][0]["h"] / 2)) <= 0.55 * med_h:
            rows[-1].append(g)
        else:
            rows.append([g])

    blocks: list[Block] = []
    for row in rows:
        row = sorted(row, key=lambda g: g["x"])
        cur = [row[0]]
        for g in row[1:]:
            gap = g["x"] - (cur[-1]["x"] + cur[-1]["w"])
            if gap <= 0.55 * med_h:
                cur.append(g)
            else:
                blocks.append(_mk_block(cur))
                cur = [g]
        blocks.append(_mk_block(cur))

    n_b = max(len(blocks), 1)
    sub_n = sum(1 for b in blocks if b.has_sub)
    multi_n = sum(1 for b in blocks if b.n >= 2)
    sub_ratio = sub_n / n_b
    multi_ratio = multi_n / n_b

    # ---- 判档 ----
    # 核心：带下标的块里含 C ⇒ 是 CH3/C6H5 这类显式碳缩写。
    # 这是"是不是显式碳"的确定证据，不依赖"有几个"这样的内容量。
    sub_with_c = sum(1 for b in blocks if b.has_sub and b.has_carbon)
    if sub_with_c >= 2 and sub_ratio >= 0.35:
        tier, conf = "dense", min(1.0, 0.55 + sub_ratio * 0.6)
    elif sub_n >= 1 or multi_ratio >= 0.30:
        tier, conf = "hybrid", min(1.0, 0.55 + sub_ratio * 0.5)
    else:
        tier, conf = "skeletal", min(1.0, 0.55 + (0.30 - multi_ratio) * 0.8)

    note = ""
    if recognized < 3:
        note = f"仅识别 {recognized} 个字符，判档不可靠"

    return ImageNotation(str(image), tier=tier, confidence=round(conf, 3),
                         glyph_count=len(glyphs), recognized=recognized,
                         blocks=[b.to_dict() for b in blocks[:12]],
                         sub_ratio=round(sub_ratio, 3),
                         multi_ratio=round(multi_ratio, 3), note=note)


def _mk_block(glyphs: list[dict]) -> Block:
    chars = "".join(g["ch"] for g in glyphs if g["ch"])
    return Block(chars=chars, n=len(glyphs),
                 has_sub=any(g["is_sub"] for g in glyphs),
                 has_carbon=any(g["ch"] == "C" and g["score"] >= MIN_SCORE
                                for g in glyphs),
                 score=round(float(np.mean([g["score"] for g in glyphs])), 3))


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-visual-notation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("classify", help="单图判档并打印识别出的文字块")
    p1.add_argument("--image", required=True)
    p1.add_argument("--templates", required=True)

    p2 = sub.add_parser("batch", help="整个目录（按年份分文件夹）批量判档")
    p2.add_argument("--dir", required=True)
    p2.add_argument("--templates", required=True)
    p2.add_argument("--out", default="")

    args = ap.parse_args()
    with open(args.templates, "rb") as fh:
        templates = pickle.load(fh)["templates"]

    if args.cmd == "classify":
        r = analyze_image(args.image, templates)
        d = r.to_dict()
        print(f"{Path(d['image']).name}: {d['tier']}({d['tier_label']}) "
              f"conf={d['confidence']} glyphs={d['glyph_count']} "
              f"recognized={d['recognized']}")
        print(f"  sub_ratio={d['sub_ratio']} multi_ratio={d['multi_ratio']} {d['note']}")
        for b in d["blocks"]:
            print(f"    块 '{b['chars']}' n={b['n']} sub={b['has_sub']} "
                  f"carbon={b['has_carbon']} score={b['score']}")
        return

    root = Path(args.dir)
    import json
    rows = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not d.name.isdigit():
            continue
        year = int(d.name)
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            try:
                r = analyze_image(p, templates).to_dict()
            except Exception as exc:
                r = {"image": str(p), "error": f"{type(exc).__name__}: {exc}"}
            r["year"] = year
            rows.append(r)
    by_year: dict[int, Counter] = {}
    for r in rows:
        by_year.setdefault(r["year"], Counter())[r.get("tier", "error")] += 1
    print(f"{'年':>5} {'n':>3} {'dense':>6} {'hybrid':>7} {'skeletal':>9}")
    for y in sorted(by_year):
        c = by_year[y]
        n = sum(c.values())
        print(f"{y:>5} {n:>3} {c.get('dense',0):>6} {c.get('hybrid',0):>7} "
              f"{c.get('skeletal',0):>9}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print("已写", args.out)


if __name__ == "__main__":
    main()
