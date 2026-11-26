"""OCR 文字层：从图像像素认元素符号，不读 PDF 文本层。

依赖：rapidocr_onnxruntime（pip install rapidocr_onnxruntime）。
用户 2026-11-26 口径：影印版没有可用文本层，必须从像素真正识别；
氧(O)与数字0都是圆圈 → 0 纠正为 O。

输出：识别到的符号 → 杂原子 / 取代基（查 substituents 库）。
"""
from __future__ import annotations

import cv2
import numpy as np

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    RapidOCR = None

try:
    from .substituents import SUBSTITUENTS
except ImportError:
    from substituents import SUBSTITUENTS


_OCR = None


def get_ocr():
    global _OCR
    if _OCR is None:
        if RapidOCR is None:
            raise RuntimeError("请先安装 rapidocr_onnxruntime")
        _OCR = RapidOCR()
    return _OCR


def read_pixels(crop_gray, scale=3, conf_min=0.5) -> dict:
    """从裁图像素 OCR，返回 {symbols, hetero, substituents, raw}。"""
    big = cv2.resize(crop_gray, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_CUBIC)
    res, _ = get_ocr()(big)
    raw = []
    if res:
        for item in res:
            txt = str(item[1]).strip()
            conf = float(item[2])
            if conf >= conf_min and txt:
                raw.append((txt, round(conf, 2)))

    symbols = []
    for txt, conf in raw:
        s = txt.replace(" ", "").upper().replace("0", "O")
        symbols.append(s)

    hetero = set()
    for s in symbols:
        for e in ("Cl", "Br", "Si", "N", "O", "S", "P", "F", "I", "B"):
            if e.upper() in s:
                hetero.add(e)

    subs = []
    for s in symbols:
        for name in SUBSTITUENTS:
            if name.upper() == s or (len(name) >= 2 and name.upper() in s):
                subs.append(name)
                break

    return {"symbols": symbols, "hetero": sorted(hetero),
            "substituents": sorted(set(subs)), "raw": raw}


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if g is None:
            print(f"{path}: 无法读取")
            continue
        r = read_pixels(g)
        print(path, "杂原子", r["hetero"], "取代基", r["substituents"],
              "OCR", [x[0] for x in r["raw"]])
