"""训练③：结构式图 → 拓扑指标（环数 / 环大小 / 标签）。

只用环数、环大小、标签，绝不用边数：缩写/显式氢让扫描图的边数不可数。

关键取舍：
  - 不用 cv2.HoughCircles——古早图的正电荷 ⊕ 是“小圆圈加号”，会被当成苯环。
    改用轮廓闭合/嵌套 + skimage 骨架化 + 并查集数独立环，并按半径过滤。
  - 字符识别用按风格档位建立的字符模板（cv2.matchTemplate），通用 OCR 默认不启用。

可单独调试：
    python -m training.topo templates --samples <dir> --out <templates.json>
    python -m training.topo rings <image>
    python -m training.topo topo <image> --templates <templates.json> --out <json>
    python -m training.topo evaluate --results <dir> --truth <truth.csv>
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import skeletonize

try:
    from .substituents import match_substituent, normalize_label_text
except ImportError:  # 允许 python training/topo.py 直接跑
    from substituents import match_substituent, normalize_label_text

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


class TopoResult(dict):
    """dict 子类：保留旧版 .to_json() / 属性访问，pipeline.py 不用跟着改。"""

    def to_json(self) -> str:
        return json.dumps(self, ensure_ascii=False, indent=2)

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None


def _warn(warnings: list[str] | None, msg: str) -> None:
    if warnings is not None and msg not in warnings:
        warnings.append(msg)
    print(f"[topo 警告] {msg}", file=sys.stderr)


def _read_gray(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"读不了图片: {path}")
    return img


def _ink_binary(gray: np.ndarray) -> np.ndarray:
    """墨的二值化。

    全图 Otsu 的阈值由面积大、墨浓的原子标签主导；遇到极细或印刷点状的
    键线，最细的那批可能被判成背景。改成 **Otsu ∪ 自适应**：
    正常图两者重合（不影响原有行为），极细线由自适应兜底。
    实测（40 张、以原图灰度为真值）：旧 Otsu 找回中位 0.991 / p10 0.972，
    新并集 1.000 / 0.999，每图平均多找回 54 像素。

    高斯模糊保留：它对扫描噪点有抗噪作用，且实测不伤害 2~3px 的键线。
    """
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ad = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 10)
    return (((bw > 0) | (ad > 0))).astype(np.uint8) * 255


def _finding(kind: str, size: int, confidence: float, bbox: list[int]) -> dict:
    return {"kind": kind, "size": int(size), "confidence": round(float(confidence), 3),
            "bbox": [int(v) for v in bbox]}


# --------------------------------------------------------------------------
# 坑2 / 坑4：按风格档位建字符模板 + 模板匹配（数字模板低阈值 + 警告）
# --------------------------------------------------------------------------

def build_templates(sample_dir: str | Path, out_path: str | Path) -> dict:
    """从标注字符小图建模板库；文件名（去扩展名）即字符，如 N.png / Me.png / 2.png。

    sample_dir 下有子目录时，子目录名即风格档位（如 1937 / 1971）；否则用 default 单档。
    模板图裁到墨迹外接框并二值化，base64 存进 JSON，便于随结果一起归档。
    """
    root = Path(sample_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"模板样本目录不存在: {root}")
    tiers = [p for p in sorted(root.iterdir()) if p.is_dir()]
    groups = [(p.name, p) for p in tiers] if tiers else [("default", root)]

    templates: list[dict] = []
    warnings: list[str] = []
    for style, folder in groups:
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in IMAGE_EXTS:
                continue
            text = p.stem
            if not text:
                continue
            crop = _ink_binary(_read_gray(p))
            ys, xs = np.nonzero(crop)
            if len(xs) == 0:
                _warn(warnings, f"模板 {p.name} 全白，已跳过")
                continue
            crop = crop[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            ok, buf = cv2.imencode(".png", crop)
            if not ok:
                _warn(warnings, f"模板 {p.name} 编码失败，已跳过")
                continue
            templates.append({
                "text": text,
                "style": style,
                "w": int(crop.shape[1]),
                "h": int(crop.shape[0]),
                "image": base64.b64encode(buf.tobytes()).decode("ascii"),
            })

    if not templates:
        _warn(warnings, f"模板目录没有可用字符图: {root}（先标注 N.png / Me.png / 2.png 等）")
    payload = {
        "version": 1,
        "threshold": 0.72,
        "digit_threshold": 0.58,
        "templates": templates,
        "warnings": warnings,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _decode_template(item: dict) -> np.ndarray:
    arr = np.frombuffer(base64.b64decode(item["image"]), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"模板 {item.get('text')!r} 解码失败")
    return (img > 127).astype(np.uint8) * 255


def _nms(items: list[dict], threshold: float = 0.5) -> list[dict]:
    order = sorted(range(len(items)), key=lambda i: (-items[i]["confidence"], -len(items[i]["text"])))
    kept: list[dict] = []
    for i in order:
        a = items[i]
        ax, ay, aw, ah = a["bbox"]
        if any(_overlap_ratio(a["bbox"], b["bbox"]) > threshold for b in kept):
            continue
        kept.append(a)
    return kept


def _overlap_ratio(a: list[int], b: list[int]) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(1, min(a[2] * a[3], b[2] * b[3]))


def _merge_subscripts(findings: list[dict], warnings: list[str] | None) -> list[dict]:
    """把紧邻前字的数字（C₂H₅ 的 2、5）并回去，孤立数字单独保留并告警。"""
    digits = [f for f in findings if f["text"].isdigit()]
    others = [f for f in findings if not f["text"].isdigit()]
    merged: set[int] = set()
    for d in digits:
        dx, dy, dw, dh = d["bbox"]
        best, best_gap = None, 1e9
        for o in others:
            ox, oy, ow, oh = o["bbox"]
            gap = dx - (ox + ow)
            if -2 <= gap <= 6 and abs((oy + oh / 2) - (dy + dh / 2)) <= max(8, dh) and gap < best_gap:
                best, best_gap = o, gap
        if best is None:
            _warn(warnings, f"孤立数字标签 {d['text']!r} 未并入相邻字符，已单独保留")
            continue
        best["text"] = normalize_label_text(best["text"] + d["text"])
        best["confidence"] = round(min(best["confidence"], d["confidence"]), 3)
        merged.add(id(d))
    return others + [d for d in digits if id(d) not in merged]


def read_labels_with_templates(image_path, templates_path, warnings: list[str] | None = None) -> list[dict]:
    """用 cv2.matchTemplate 找标签，返回 [{'text','bbox','confidence'}]。

    warnings 为可选外部列表，便于 extract_topology 汇总；数字模板用更低阈值并写明告警。
    通用 OCR（pytesseract 等）不作为默认路径——跨时代字体漂移下不可靠。
    """
    payload = json.loads(Path(templates_path).read_text(encoding="utf-8"))
    templates = payload.get("templates", [])
    if not templates:
        _warn(warnings, f"模板库为空: {templates_path}")
        return []
    ink = _ink_binary(_read_gray(image_path))
    base_t = float(payload.get("threshold", 0.72))
    digit_t = float(payload.get("digit_threshold", max(0.5, base_t - 0.14)))

    raw: list[dict] = []
    for item in templates:
        tpl = _decode_template(item)
        th, tw = tpl.shape
        if th > ink.shape[0] or tw > ink.shape[1]:
            continue
        text = str(item["text"])
        threshold = digit_t if text.isdigit() else base_t
        res = cv2.matchTemplate(ink, tpl, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        for y, x in zip(ys, xs):
            conf = float(res[y, x])
            if text.isdigit() and conf < base_t:
                _warn(warnings, f"数字模板 {text!r} 置信度仅 {conf:.2f}（下标极小，易漏，已按低阈值收录）")
            raw.append({"text": text, "bbox": [int(x), int(y), int(tw), int(th)],
                        "confidence": round(conf, 3)})
    return _merge_subscripts(_nms(raw), warnings)


# --------------------------------------------------------------------------
# 坑1 / 坑5：环检测不用 HoughCircles
# --------------------------------------------------------------------------

def _contour_rings(ink: np.ndarray, warnings: list[str] | None) -> list[dict]:
    """轮廓环检测。手绘/扫描图线条常断裂，先做闭运算接缝再找内洞。

    实测：同一张真结构式（六元环手绘圆圈），不闭合时环数=0；
    MORPH_CLOSE k=6 后内洞成形、近似边数=6 正确。k 太小接不上，太大把相邻环并一起，
    取 6 是这几类古早图的折中（更细的图可用 4）。
    """
    # 断线修补：闭运算把笔画间的 1~3px 缺口接上，否则 findContours 拿不到内洞
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6, 6))
    ink_closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel)

    contours, hierarchy = cv2.findContours(ink_closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]
    out: list[dict] = []
    for i, c in enumerate(contours):
        area = cv2.contourArea(c)
        if area < 120:
            continue
        peri = cv2.arcLength(c, True)
        if peri <= 0:
            continue
        x, y, w, h = cv2.boundingRect(c)
        _, encloser_r = cv2.minEnclosingCircle(c)
        fill_ratio = area / max(1e-6, np.pi * encloser_r ** 2)
        # 电荷 ⊕ 半径 <10px：明确忽略，绝不当苯环（HoughCircles 在这里必错）
        if encloser_r < 10:
            continue
        if fill_ratio > 0.9 and encloser_r > 15 and encloser_r <= 90:
            # 古早圆苯环半径 >15px；10~15px 的多为电荷/符号，不认。
            # 用最小外接圆填充率而非圆度：正六边形圆度也有 0.9，但填充率只有约 0.83。
            out.append(_finding("circle", 6, round(0.6 + 0.3 * fill_ratio, 3), [x, y, w, h]))
            continue
        child = hierarchy[i][2]
        if child == -1 or cv2.contourArea(contours[child]) < 0.15 * area:
            continue
        inner = contours[child]
        # 真环的内洞必须够大：小内洞多是被闭运算粘住的字母/符号（O、S、⊕ 之类）。
        # 实测真六元环内洞面积 ≈160，误报的字母内洞 45~57，取 100 作为下限。
        inner_area = cv2.contourArea(inner)
        if inner_area < 100:
            continue
        n = len(cv2.approxPolyDP(inner, 0.045 * cv2.arcLength(inner, True), True))
        if not 3 <= n <= 9:
            n = len(cv2.approxPolyDP(c, 0.05 * peri, True))
        if not 3 <= n <= 9:
            n = 6
        if not 0.35 < w / max(h, 1) < 3.0:
            continue
        out.append(_finding("polygon", n, 0.7 if n <= 7 else 0.62, [x, y, w, h]))
    return out


def _skeleton_rings(ink: np.ndarray, existing: list[dict], warnings: list[str] | None) -> list[dict]:
    """骨架图论补环：并查集数独立环 E-V+C，只补轮廓没确认到的部分。"""
    try:
        skel = skeletonize(ink > 0)
    except Exception as exc:
        _warn(warnings, f"骨架化失败，跳过图论补环: {exc}")
        return []
    pts = np.argwhere(skel)
    if len(pts) == 0:
        return []
    height, width = skel.shape
    index = np.full((height, width), -1, dtype=np.int64)
    for k, (y, x) in enumerate(pts):
        index[y, x] = k
    # 只连右/下邻居：8 邻域会在拐角处造出假环
    edges = []
    for y, x in pts:
        a = index[y, x]
        for dy, dx in ((0, 1), (1, 0)):
            ny, nx = int(y) + dy, int(x) + dx
            if ny < height and nx < width:
                b = index[ny, nx]
                if b >= 0:
                    edges.append((a, b))
    parent = list(range(len(pts)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    stats: dict[int, list[int]] = {}
    for k in range(len(pts)):
        stats.setdefault(find(k), [0, 0])[0] += 1
    for a, b in edges:
        stats[find(a)][1] += 1

    out: list[dict] = []
    for root, (v, e) in stats.items():
        cycles = e - v + 1
        if cycles <= 0:
            continue
        component = np.array([p for k, p in enumerate(pts) if find(k) == root])
        y0, x0 = component.min(axis=0)
        y1, x1 = component.max(axis=0) + 1
        bbox = [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]
        if bbox[2] < 12 or bbox[3] < 12 or any(_overlap_ratio(bbox, f["bbox"]) > 0.5 for f in existing):
            continue
        for _ in range(min(cycles, 4)):
            out.append(_finding("skeleton", 6, 0.55, bbox))
        _warn(warnings, "骨架图论检出环但轮廓未确认：环大小按 6 估计，可信度低")
    return out


def _dedupe_rings(findings: list[dict]) -> list[dict]:
    priority = {"polygon": 0, "circle": 1, "skeleton": 2}
    kept: list[dict] = []
    for f in sorted(findings, key=lambda x: (priority.get(x["kind"], 9), -x["confidence"])):
        if not any(_overlap_ratio(f["bbox"], g["bbox"]) > 0.5 for g in kept):
            kept.append(f)
    return kept


def detect_rings(image_path, warnings: list[str] | None = None) -> list[dict]:
    """返回 [{'kind','size','confidence','bbox'}]；不用 HoughCircles（⊕ 会冒充苯环）。"""
    ink = _ink_binary(_read_gray(image_path))
    findings = _contour_rings(ink, warnings)
    findings += _skeleton_rings(ink, findings, warnings)
    return _dedupe_rings(findings)


# --------------------------------------------------------------------------
# 汇总与人工真值回流
# --------------------------------------------------------------------------

def extract_topology(image_path, templates_path=None) -> dict:
    """汇总拓扑：{'image','rings','ring_sizes','labels', 两类 findings, 'warnings'}。"""
    warnings: list[str] = []
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {path}")
    ring_findings = detect_rings(path, warnings)
    ring_sizes = sorted(f["size"] for f in ring_findings if f["size"] > 0)

    label_findings: list[dict] = []
    if templates_path is None:
        _warn(warnings, "未提供字符模板：labels 为空（通用 OCR 默认不启用）")
    else:
        label_findings = read_labels_with_templates(path, templates_path, warnings)
    labels = sorted({normalize_label_text(f["text"]) for f in label_findings if f["text"]})
    for text in labels:
        if match_substituent(text) is None:
            _warn(warnings, f"标签 {text!r} 不在取代基库中，拓扑比对可能不准")
    if not ring_findings:
        _warn(warnings, "未检出环：可能是无环结构或图像质量不足")

    return TopoResult(
        image=str(path),
        rings=len(ring_findings),
        ring_sizes=ring_sizes,
        labels=labels,
        ring_findings=ring_findings,
        label_findings=label_findings,
        warnings=warnings,
    )


_IMG_KEYS = ("image", "file", "filename", "name", "path", "stem", "图片")
_RING_KEYS = ("rings", "ring_count", "n_rings", "环数")
_SIZE_KEYS = ("ring_sizes", "ringsizes", "ring size", "环大小")
_LABEL_KEYS = ("labels", "label", "标签")


def _cell(row: dict, keys: tuple[str, ...]) -> str | None:
    lut = {str(k).strip().lower(): k for k in row if k}
    for key in keys:
        if key in lut:
            return row[lut[key]]
    return None


def _parse_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        values = [str(v) for v in value]
    else:
        s = str(value).strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                values = [str(v) for v in parsed] if isinstance(parsed, list) else [s]
            except json.JSONDecodeError:
                values = [s]
        else:
            values = next((s.split(sep) for sep in (";", "|", ",", "/") if sep in s), s.split())
    return [v.strip() for v in values if str(v).strip()]


def _ints(values) -> list[int]:
    out = []
    for v in values:
        try:
            out.append(int(float(str(v).strip())))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def evaluate(result_dir, truth_csv) -> dict:
    """用人工标注真值算准确率：逐字段 + 三字段全对（exact）。

    truth CSV 需含图片名、rings、ring_sizes、labels 四列（列名大小写不敏感，
    ring_sizes/labels 支持 JSON 数组或 ;|,/ 分隔）。结果目录取 *.topo.json。
    """
    root = Path(result_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"结果目录不存在: {root}")
    results: dict[str, dict] = {}
    for p in root.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "rings" not in data:
            continue
        stem = p.stem[:-5] if p.stem.endswith(".topo") else p.stem
        results[stem] = data
        image_stem = Path(str(data.get("image", ""))).stem
        if image_stem:
            results[image_stem] = data

    with open(truth_csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    warnings: list[str] = []
    if not rows:
        _warn(warnings, f"真值 CSV 没有数据行: {truth_csv}")
    if not results:
        _warn(warnings, f"结果目录没有 topo JSON: {root}")

    details: list[dict] = []
    field_ok = {"rings": [], "ring_sizes": [], "labels": []}
    for row in rows:
        name = (_cell(row, _IMG_KEYS) or "").strip()
        key = Path(name).stem
        data = results.get(key)
        if data is None:
            _warn(warnings, f"真值 {name!r} 找不到对应结果 JSON")
            details.append({"image": name, "matched": False, "ok_rings": False,
                            "ok_ring_sizes": False, "ok_labels": False, "ok_all": False})
            continue

        t_rings_raw = _cell(row, _RING_KEYS)
        t_sizes_raw = _cell(row, _SIZE_KEYS)
        t_labels_raw = _cell(row, _LABEL_KEYS)
        p_sizes = _ints(data.get("ring_sizes", []))
        p_labels = {normalize_label_text(str(v)) for v in data.get("labels", [])}
        ok_rings = ok_sizes = ok_labels = False
        if t_rings_raw not in (None, ""):
            ok_rings = _ints([t_rings_raw]) == [int(data.get("rings", -1))]
            field_ok["rings"].append(ok_rings)
        if t_sizes_raw not in (None, ""):
            ok_sizes = _ints(_parse_list(t_sizes_raw)) == p_sizes
            field_ok["ring_sizes"].append(ok_sizes)
        if t_labels_raw not in (None, ""):
            ok_labels = {normalize_label_text(v) for v in _parse_list(t_labels_raw)} == p_labels
            field_ok["labels"].append(ok_labels)
        details.append({"image": name, "matched": True, "ok_rings": ok_rings,
                        "ok_ring_sizes": ok_sizes, "ok_labels": ok_labels,
                        "ok_all": ok_rings and ok_sizes and ok_labels})

    exact = sum(1 for d in details if d["ok_all"])
    matched = sum(1 for d in details if d["matched"])

    def rate(values: list[bool]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "total": len(rows),
        "matched": matched,
        "accuracy": round(exact / matched, 4) if matched else 0.0,
        "exact_accuracy": round(exact / matched, 4) if matched else 0.0,
        "rings_accuracy": rate(field_ok["rings"]),
        "ring_sizes_accuracy": rate(field_ok["ring_sizes"]),
        "labels_accuracy": rate(field_ok["labels"]),
        "details": details,
        "warnings": warnings,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="训练③：结构式图 → 拓扑指标")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("templates", help="从标注字符小图建模板库")
    t.add_argument("--samples", required=True, help="字符小图目录（子目录=风格档位）")
    t.add_argument("--out", required=True, help="模板 JSON 输出路径")

    r = sub.add_parser("rings", help="只检测环（不用 HoughCircles）")
    r.add_argument("image")

    p = sub.add_parser("topo", help="提取完整拓扑")
    p.add_argument("image")
    p.add_argument("--templates", help="字符模板 JSON；不给则 labels 为空")
    p.add_argument("--out", help="结果 JSON 文件；不给则打印到 stdout")

    e = sub.add_parser("evaluate", help="人工真值回流算准确率")
    e.add_argument("--results", required=True, help="topo JSON 所在目录")
    e.add_argument("--truth", required=True, help="人工标注 CSV")
    e.add_argument("--out", help="评估报告 JSON；不给则打印到 stdout")

    args = ap.parse_args()
    if args.cmd == "templates":
        payload = build_templates(args.samples, args.out)
        print(f"写入 {len(payload['templates'])} 个模板 → {args.out}")
        for msg in payload["warnings"]:
            print(f"[topo 警告] {msg}", file=sys.stderr)
    elif args.cmd == "rings":
        findings = detect_rings(args.image)
        if not findings:
            print("[topo 警告] 未检出环：可能无环或图像质量不足", file=sys.stderr)
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    elif args.cmd == "topo":
        result = extract_topology(args.image, args.templates)
        text = result.to_json()
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"写出 {out}")
        else:
            print(text)
        print(f"环数 {result['rings']} · 环大小 {result['ring_sizes']} · 标签 {result['labels']}")
    else:
        report = evaluate(args.results, args.truth)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"写出 {out}")
        else:
            print(text)
        print(f"准确率 {report['accuracy']}（{report['matched']}/{report['total']}）")


if __name__ == "__main__":
    main()
