"""记法风格分类：直接从 PDF 文本层读结构式的字符，不再靠像素猜。

用户给的关键洞察（本模块的全部出发点）：
    「正文中的字和结构式用的字体是同一种，只是大小不一样。你可以去使用一下正文中的字体。」

实测验证（1906 Albrecht 第 2 页）：结构式里的 C / H / O 全部在 PDF 文本层里，
带真实字符值与精确 bbox。所以根本不需要位图模板匹配、不需要 OCR、不需要
靠几何猜"这是 C 还是 O"——**直接读字符**。

这解决了之前所有内容泄漏：
    之前：用像素几何猜"这块是不是写了碳" → O 与 C 分不开、杂原子串被当成缩写块
    现在：字符是文本层里的真值 → "写了几个 C"是事实，不是猜测

三档判据（用户定义的连续谱，1985 年前）：
    dense     前期：每个碳都写字（CH3 / CH2 / CH / CO...）→ C 字符数 ≈ 顶点数
    hybrid    中期：主链/环键线，支链写缩写（Me/Et/Ph/CO2R）→ C 少但有大块缩写
    skeletal  后期：现代键线式，碳不写 → C 字符数接近 0

**红线**：只量"怎么写"，不量"写了什么"。
所以判据全部是**比例**，不是绝对数量：
    c_per_vertex  写出的 C 数 / 骨架顶点数 —— 与分子大小无关
    has_multichar 是否存在多字符缩写块（Me/CO2R 这类）—— 与有几个无关
环数、环大小、原子总数、是否有环，一律不进判据。

字体同源的用法（本模块的实际用法）：
结构式里的小字与正文同字体，所以两者的字形宽度/高度比例关系可复用。
用"字号 / 行距"或"字形宽高比"来判断某块文本是否属于结构式标签，
而不必做位图匹配——这是"用正文的字体"最直接、最可靠的落地方式。

用法：
    python -m training.pdf_notation classify --pdf <pdf> --page 2
    python -m training.pdf_notation batch --pdfs <dir> --out <json>
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

TIERS = ("dense", "hybrid", "skeletal")
TIER_LABEL = {"dense": "显式碳式", "hybrid": "混合式", "skeletal": "现代键线式"}

# 结构式标签里可能出现的字符（字母+数字+下标符号）
LABEL_CHARS = set("CHONSPFIBKBrClSi0123456789")
# 判断"某块文本是结构式标签"时用的字号区间（相对该页正文主字号）
SMALL_RATIO = (0.55, 0.95)


@dataclass
class CharTok:
    """文本层里的一个字符。"""
    c: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    font: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class PageNotation:
    page: int
    body_size: float
    label_chars: int = 0
    c_count: int = 0
    carbon_ratio: float = 0.0
    n_blocks: int = 0
    multichar_blocks: int = 0
    max_block_len: int = 0
    tier: str = ""
    confidence: float = 0.0
    samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier_label"] = TIER_LABEL.get(self.tier, "")
        return d


def read_page_chars(page) -> tuple[list[CharTok], float]:
    """读出该页全部字符与正文主字号。

    正文主字号 = 该页出现次数最多的字号。用它做基准，
    比"结构式标签字号"大的是正文，小的是标签/上下标。
    """
    rd = page.get_text("rawdict")
    out: list[CharTok] = []
    sizes: Counter = Counter()
    for blk in rd.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                size = float(span.get("size", 0))
                font = span.get("font", "")
                for ch in span.get("chars", []):
                    c = ch.get("c", "")
                    bb = ch["bbox"]
                    out.append(CharTok(c, bb[0], bb[1], bb[2], bb[3], size, font))
                    if c.strip():
                        sizes[round(size, 1)] += 1
    body = sizes.most_common(1)[0][0] if sizes else 0.0
    return out, body


def group_blocks(chars: list[CharTok], med_h: float) -> list[list[CharTok]]:
    """把相邻字符聚成"词块"。CH3 / CO2R / Me 这种连续标签会聚成一块。

    判据用文本层的坐标（精确，不受扫描质量影响）：
    同一行（cy 差 < 0.5 字高）且水平间隙 < 0.35 字宽 → 同块。
    """
    if not chars:
        return []
    rows: list[list[CharTok]] = []
    for ch in sorted(chars, key=lambda c: c.cy):
        if rows and abs(ch.cy - rows[-1][0].cy) <= 0.5 * med_h:
            rows[-1].append(ch)
        else:
            rows.append([ch])

    blocks: list[list[CharTok]] = []
    for row in rows:
        row = sorted(row, key=lambda c: c.x0)
        cur = [row[0]]
        for ch in row[1:]:
            gap = ch.x0 - cur[-1].x1
            if gap <= 0.35 * med_h:
                cur.append(ch)
            else:
                blocks.append(cur)
                cur = [ch]
        blocks.append(cur)
    return blocks


def _is_label_block(block: list[CharTok]) -> bool:
    """判断一个字符块是不是结构式标签，而不是页码/正文碎块。

    实测的噪声形态（1906 Albrecht 第 3 页）：'7778O'、'04729COP'、'246' —— 全是页码与被
    排版打散的数字串。真标签是 'OH' 'CO' 'CH' 'CHCH' 'CHON' 这种**短且以字母为主**的。

    判据（都要满足）：
      1. 长度 ≤ 6（'04729COP' 这种 8 字符的是垃圾）
      2. 至少一半字符是字母（纯数字块是页码）
      3. 不含大小写混排的长串（'rCli'、'CllH1P00' 这类是 OCR 式的乱码）
    """
    if not block:
        return False
    s = "".join(c.c for c in block)
    if len(block) > 6:
        return False
    letters = sum(1 for c in block if c.c.isalpha())
    if letters < max(1, len(block) / 2):
        return False
    # 全是小写的是普通单词（如 'of' 'the'），不是化学标签
    if all(c.c.islower() for c in block if c.c.isalpha()) and len(block) <= 3:
        return False
    # 化学标签里允许的大写字符集（C/H/O/N/S/P/F/I/B/r/Cl... 与下标数字）
    allowed = set("CHONSPFIBKbrcl0123456789+-#=()[]*/")
    bad = sum(1 for ch in s if ch not in allowed)
    if bad > 0:
        return False
    # 必须至少含一个"化学相关大写字母"——排除 'II'、'Il'、'Pr'（页码罗马数字/单词）
    chem = sum(1 for ch in s if ch in "CHONSPFBrCl")
    if chem == 0:
        return False
    # 排除全是同一字符重复（'III'、'llrr' 这种是页码或装饰）
    if len(set(s)) == 1:
        return False
    return True


def classify_page(page, pno: int) -> PageNotation:
    """对单页做记法分类。只看"结构式标签"那部分字符，避开正文。"""
    chars, body = read_page_chars(page)
    if not chars or body <= 0:
        return PageNotation(page=pno, body_size=body, tier="skeletal")

    # 只取"像结构式标签"的字符：字号小于正文、且字符在标签字符集里
    lo, hi = SMALL_RATIO[0] * body, SMALL_RATIO[1] * body
    labels = [c for c in chars if lo <= c.size <= hi and c.c.strip() in LABEL_CHARS]
    if not labels:
        return PageNotation(page=pno, body_size=body, tier="skeletal",
                            confidence=0.5)

    med_h = sorted(c.h for c in labels)[len(labels) // 2] or 1.0
    blocks = group_blocks(labels, med_h)
    # 过滤掉页码/乱码块，只留真标签
    blocks = [b for b in blocks if _is_label_block(b)]
    if not blocks:
        return PageNotation(page=pno, body_size=body, tier="skeletal", confidence=0.5)

    labels = [c for b in blocks for c in b]
    c_count = sum(1 for c in labels if c.c == "C")
    # 多字符块：块内 ≥2 个字符 —— 这是"缩写"的标志（CH/CO2R/Me）
    multi = [b for b in blocks if len(b) >= 2]
    max_len = max((len(b) for b in blocks), default=0)
    samples = ["".join(c.c for c in b) for b in multi[:8]]

    label_n = max(len(labels), 1)
    carbon_ratio = c_count / label_n

    # ---- 判档：只用量比例，不用绝对数量 ----
    # 关键区分：C 出现在"多字符块"里 ⇒ 是缩写（CH3/CO2R）；
    #          C 孤立出现 ⇒ 是早期那种每个顶点写一个 C 的画法。
    c_in_multi = sum(1 for b in multi for c in b if c.c == "C")
    multi_c_ratio = c_in_multi / label_n

    # 证据不足时不硬判：标签太少（<6）或没有 C 也没有多字符块 → uncertain
    # 这一步很重要：结构式被旋转/遮挡时文本层会乱，硬判出来的档位是假的。
    if len(labels) < 6 or (c_count == 0 and len(multi) == 0):
        return PageNotation(page=pno, body_size=body, label_chars=len(labels),
                            c_count=c_count, carbon_ratio=round(carbon_ratio, 3),
                            n_blocks=len(blocks), multichar_blocks=len(multi),
                            max_block_len=max_len, tier="uncertain", confidence=0.0,
                            samples=samples)

    if carbon_ratio >= 0.28 and multi_c_ratio >= 0.15:
        tier, conf = "dense", min(1.0, 0.55 + carbon_ratio)
    elif carbon_ratio >= 0.10 or len(multi) >= 2:
        tier, conf = "hybrid", min(1.0, 0.55 + multi_c_ratio * 2)
    else:
        tier, conf = "skeletal", min(1.0, 0.55 + (0.10 - carbon_ratio) * 3)

    return PageNotation(page=pno, body_size=body, label_chars=len(labels),
                        c_count=c_count, carbon_ratio=round(carbon_ratio, 3),
                        n_blocks=len(blocks), multichar_blocks=len(multi),
                        max_block_len=max_len, tier=tier, confidence=round(conf, 3),
                        samples=samples)


def classify_pdf(pdf: Path, pages: int = 0) -> dict:
    import pymupdf
    try:
        doc = pymupdf.open(str(pdf))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "pdf": pdf.name}

    out = []
    rng = range(len(doc)) if pages <= 0 else range(min(pages, len(doc)))
    for pno in rng:
        try:
            out.append(classify_page(doc[pno], pno).to_dict())
        except Exception as exc:
            out.append({"page": pno, "error": f"{type(exc).__name__}: {exc}"})
    doc.close()

    tiers = Counter(p.get("tier") for p in out if p.get("tier"))
    return {"pdf": pdf.name, "pages": len(out), "tiers": dict(tiers), "detail": out}


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-pdf-notation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("classify", help="单篇 PDF 逐页判档")
    p1.add_argument("--pdf", required=True)
    p1.add_argument("--pages", type=int, default=0, help="0=全部")

    p2 = sub.add_parser("batch", help="批量跑一个目录")
    p2.add_argument("--pdfs", required=True)
    p2.add_argument("--out", default="")
    p2.add_argument("--limit", type=int, default=0)
    p2.add_argument("--pages", type=int, default=3)

    args = ap.parse_args()

    if args.cmd == "classify":
        res = classify_pdf(Path(args.pdf), args.pages)
        print(json.dumps({k: v for k, v in res.items() if k != "detail"},
                         ensure_ascii=False, indent=2))
        for p in res.get("detail", [])[:12]:
            print(f"  p{p.get('page')}: {p.get('tier','?'):9s} "
                  f"labels={p.get('label_chars')} C={p.get('c_count')} "
                  f"ratio={p.get('carbon_ratio')} multi={p.get('multichar_blocks')} "
                  f"maxlen={p.get('max_block_len')}  {p.get('samples') or ''}")
        return

    pdfs = sorted(Path(args.pdfs).glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[:args.limit]
    results = []
    for i, p in enumerate(pdfs):
        results.append(classify_pdf(p, args.pages))
        if (i + 1) % 20 == 0:
            print(f"  已处理 {i+1}/{len(pdfs)}", flush=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已写", out)

    all_tiers: Counter = Counter()
    for r in results:
        for t, n in (r.get("tiers") or {}).items():
            all_tiers[t] += n
    print("全局页级分布:", dict(all_tiers))


if __name__ == "__main__":
    main()
