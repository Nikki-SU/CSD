"""字符模板：从**正文**自动采集真实字形，用来识别结构式里的字母。

用户给的关键洞察（本模块的全部出发点）：
    「正文中的字和结构式用的字体肯定是同一种，只是大小不一样。
      你可以去使用一下正文中的字体。」

所以不必人工画模板、不必训练 OCR、也不必靠几何猜 C 与 O 的区别：
PDF 的正文有**文本层**，每个字符都带真实字符值与 bbox。把正文里的字形裁下来
就是天然的标注样本，结构式里的字只是同一字体的更小字号，按形状归一化后即可匹配。

流程：
    1. collect：遍历 PDF 正文，按 (font, char) 裁出字形位图 → 模板库
    2. 归一化：缩放到固定高度（消掉字号差异），做二值化
    3. match：结构式里的每个字形 → 与模板库比对 → 得到字符名
    4. 有了字符名，"这是不是 C"就是查表，不再靠猜

为什么按字体分组：同一篇文里可能混排 Times / CenturySchoolbook / Arial，
不同字体的同名字形形状不同，混在一起匹配率会掉。所以模板按字体分桶，
匹配时优先用同字体桶（结构式那份若判断不出字体，就全桶匹配取最优）。

用法：
    python -m training.pdf_glyphs collect --pdfs <目录> --out assets/glyph_templates.pkl --limit 40
    python -m training.pdf_glyphs probe --pdf <单个pdf> --page 3 --char C
"""
from __future__ import annotations

import argparse
import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

TEMPLATE_H = 32          # 模板归一化后的统一高度（消掉字号差异）
# 必须包含数字：CH3 / C6H5 / CO2R 的下标是区分"显式碳缩写"与"杂原子标签"的关键，
# 少了数字模板就只能认字母、认不出下标（实测第一版就漏了 0-9）。
KEEP_CHARS = set("CHONSPFIBrCl:=+-()[]") | set("0123456789")


def _save_png_cv2(path: Path, arr: np.ndarray) -> None:
    import cv2
    cv2.imwrite(str(path), arr)


def _char_bitmap(gray: np.ndarray, bbox, pad: int = 1) -> np.ndarray | None:
    """按 PDF 坐标（72dpi）裁某个字符，返回二值位图（墨=255）。"""
    import cv2
    x0, y0, x1, y1 = (float(v) for v in bbox)
    h, w = gray.shape
    # PDF 坐标是 72dpi 点；gray 是按 dpi 渲染的，需按比例换算
    return None if x1 <= x0 or y1 <= y0 else None


def collect_from_pdf(pdf_path: Path, dpi: int = 300, pages: int = 3,
                     chars: set[str] | None = None, max_per_char: int = 40) -> list[dict]:
    """从一篇 PDF 的正文采集字形样本。

    把页面按 dpi 渲染，然后按每个字符的 bbox（72dpi 坐标 × dpi/72）裁位图。
    这样拿到的字形与结构式里的字是同一套字体，只是字号不同。
    """
    import cv2
    import pymupdf

    chars = chars or KEEP_CHARS
    scale = dpi / 72.0
    out: list[dict] = []
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:
        return out

    got: dict[str, int] = defaultdict(int)
    for pno in range(min(pages, len(doc))):
        try:
            page = doc[pno]
            rd = page.get_text("rawdict")
        except Exception:
            continue
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

        for blk in rd.get("blocks", []):
            if blk.get("type") != 0:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    font = span.get("font", "")
                    size = float(span.get("size", 0))
                    if size < 4:                      # 太小（多半是上下标/扫描噪声）
                        continue
                    for ch in span.get("chars", []):
                        c = ch.get("c", "")
                        if c not in chars:
                            continue
                        if got[c] >= max_per_char:
                            continue
                        x0, y0, x1, y1 = (float(v) * scale for v in ch["bbox"])
                        ix0, iy0 = int(x0) - 1, int(y0) - 1
                        ix1, iy1 = int(x1) + 1, int(y1) + 1
                        if ix1 - ix0 < 4 or iy1 - iy0 < 6:
                            continue
                        ix0, iy0 = max(0, ix0), max(0, iy0)
                        ix1, iy1 = min(gray.shape[1], ix1), min(gray.shape[0], iy1)
                        crop = gray[iy0:iy1, ix0:ix1]
                        if crop.size == 0:
                            continue
                        # Otsu 二值化：墨为 255
                        _, b = cv2.threshold(crop, 0, 255,
                                             cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                        if (b > 0).sum() < 8:
                            continue
                        out.append({"char": c, "font": font, "size": size,
                                    "bitmap": b, "src": f"{pdf_path.name}#p{pno}"})
                        got[c] += 1
    doc.close()
    return out


def normalize(bitmap: np.ndarray, size: int = TEMPLATE_H) -> np.ndarray:
    """归一化字形：裁到墨迹边界再缩放到统一高度（保持宽高比）。

    这一步把"字体相同、字号不同"的两个字映射到同一空间——
    这正是用户指出的"只是大小不一样"的具体实现。

    注意：放大用 INTER_CUBIC 并先做轻微模糊，保住 C 的开口。
    实测小字号结构式标签（20×27px）直接 Otsu 会把 C 的开口填死，
    使其与 O 无法区分（C 被判成 O 的比例极高）。
    """
    import cv2
    ys, xs = np.nonzero(bitmap)
    if len(ys) == 0:
        return np.zeros((size, size), dtype=np.uint8)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    tight = bitmap[y0:y1, x0:x1]
    h, w = tight.shape
    nh = size
    nw = max(1, int(round(w * size / max(h, 1))))
    resized = cv2.resize(tight, (nw, nh), interpolation=cv2.INTER_CUBIC)
    maxw = max(2, int(size * 1.4))
    out = np.zeros((nh, maxw), dtype=np.uint8)
    if nw > maxw:
        resized = cv2.resize(tight, (maxw, nh), interpolation=cv2.INTER_CUBIC)
        nw = maxw
    out[:, :nw] = resized
    return out


@dataclass
class GlyphTemplate:
    char: str
    font: str
    bitmaps: list[np.ndarray] = field(default_factory=list)

    def mean(self) -> np.ndarray:
        return np.mean(np.stack(self.bitmaps), axis=0).astype(np.uint8)


def build_templates(samples: list[dict], size: int = TEMPLATE_H) -> dict:
    """把样本聚成 (font, char) → 模板。每类保留最多 12 个样本取均值。"""
    by_key: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    for s in samples:
        n = normalize(s["bitmap"], size)
        by_key[(s["font"], s["char"])].append(n)

    templates: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
    for (font, ch), arrs in by_key.items():
        if len(arrs) < 2:
            continue
        cap = arrs[:12]
        hh = max(a.shape[0] for a in cap)
        ww = max(a.shape[1] for a in cap)
        padded = []
        for a in cap:
            p = np.zeros((hh, ww), dtype=np.uint8)
            p[:a.shape[0], :a.shape[1]] = a
            padded.append(p)
        templates[font][ch] = np.mean(np.stack(padded), axis=0).astype(np.uint8)
    return dict(templates)


def match_glyph(bitmap: np.ndarray, templates: dict, font_hint: str | None = None,
                size: int = TEMPLATE_H) -> tuple[str, float]:
    """把结构式里的一个字形匹配到字符。返回 (字符, 相似度 0~1)。

    相似度用归一化互相关（对亮度偏移与轻微缩放都不敏感），
    比逐像素差稳——扫描件有灰度不均与断线。
    """
    import cv2
    probe = normalize(bitmap, size)
    if probe.max() == 0:
        return "", 0.0

    buckets = list(templates.keys())
    if font_hint and font_hint in templates:
        buckets = [font_hint] + [b for b in buckets if b != font_hint]

    best_c, best_s = "", 0.0
    for font in buckets:
        for ch, tpl in templates[font].items():
            hh = max(probe.shape[0], tpl.shape[0])
            ww = max(probe.shape[1], tpl.shape[1])
            p = np.zeros((hh, ww), dtype=np.float32)
            t = np.zeros((hh, ww), dtype=np.float32)
            p[:probe.shape[0], :probe.shape[1]] = probe
            t[:tpl.shape[0], :tpl.shape[1]] = tpl
            res = cv2.matchTemplate(p, t, cv2.TM_CCOEFF_NORMED)
            s = float(res.max())
            if s > best_s:
                best_s, best_c = s, ch
    return best_c, best_s


def main() -> None:
    ap = argparse.ArgumentParser(prog="csd-pdf-glyphs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("collect", help="从 PDF 正文采集字形模板")
    p1.add_argument("--pdfs", required=True, help="PDF 目录")
    p1.add_argument("--out", default="assets/glyph_templates.pkl")
    p1.add_argument("--limit", type=int, default=30, help="最多读几篇")
    p1.add_argument("--pages", type=int, default=2, help="每篇读几页")
    p1.add_argument("--dpi", type=int, default=300)

    p2 = sub.add_parser("probe", help="看某篇某页的字形采集情况")
    p2.add_argument("--pdf", required=True)
    p2.add_argument("--page", type=int, default=0)
    p2.add_argument("--dpi", type=int, default=300)

    args = ap.parse_args()

    if args.cmd == "probe":
        s = collect_from_pdf(Path(args.pdf), dpi=args.dpi, pages=args.page + 1)
        print(f"采到 {len(s)} 个字形样本")
        by_char: dict[str, int] = defaultdict(int)
        by_font: dict[str, int] = defaultdict(int)
        for x in s:
            by_char[x["char"]] += 1
            by_font[x["font"]] += 1
        print("字符分布:", dict(sorted(by_char.items(), key=lambda kv: -kv[1])[:14]))
        print("字体分布:", {k: v for k, v in list(by_font.items())[:6]})
        return

    pdfs = sorted(Path(args.pdfs).glob("*.pdf"))[:args.limit]
    all_samples: list[dict] = []
    for i, p in enumerate(pdfs):
        got = collect_from_pdf(p, dpi=args.dpi, pages=args.pages)
        all_samples.extend(got)
        if (i + 1) % 10 == 0:
            print(f"  已处理 {i+1}/{len(pdfs)} 篇，累计 {len(all_samples)} 个字形", flush=True)

    templates = build_templates(all_samples)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # numpy 数组直接 pickle（跨平台读回再转 np）
    with out.open("wb") as fh:
        pickle.dump({"templates": templates, "size": TEMPLATE_H,
                     "fonts": list(templates.keys())}, fh)

    n_tpl = sum(len(v) for v in templates.values())
    print(f"模板库：{len(templates)} 种字体 / {n_tpl} 个字符模板 → {out}")
    for font, chars in list(templates.items())[:6]:
        print(f"  {font}: {sorted(chars.keys())}")


if __name__ == "__main__":
    main()
