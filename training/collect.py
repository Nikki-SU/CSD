"""训练①：采集阶段的实质代码——DOI 清洗、Crossref 元数据、文本-图对齐、结构式图二分类与回流重训。

覆盖的古早文献坑：
  - PDF 文件名里的 DOI 混着作者/年份/_pdf 等后缀，先正则洗净再去 Crossref 查元数据。
  - 古早文献的结构式图没有图注；正文里的编号标记（compound 3a / 3 was obtained）通常印在图下方或左侧，
    故按 MinerU 输出里的图片引用位置取上下文窗口做对齐，而不是依赖 Scheme/Fig. 图注。
  - 正文直接给结构名称时只产出「需人工确认的候选」，不假装能把名称自动转成 SMILES。
  - 结构式 vs 表格/谱图/线图/仪器图的判别用可解释轻量特征 + 线性 SVM，不用深度模型。
  - 瀑布流首审被剔除的图回流为负样本重训分类器。

可单独调试：
    python -m training.collect doi <filename>
    python -m training.collect align <mineru_dir> [--out <json>]
    python -m training.collect train --positive <dir> --negative <dir> --model <path>
    python -m training.collect classify <image_dir> --model <path> [--out <json>]
    python -m training.collect refine <rejected_dir> --model <path>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
TEXT_EXTS = (".md", ".markdown", ".txt")

# extract_features 返回向量的固定顺序（可解释，便于人工核对每一维在判什么）
FEATURE_NAMES = (
    "log_n_components",   # 连通域数量 log1p
    "ink_ratio",          # 墨迹占比
    "line_density",       # 线段数归一化
    "circle_ratio",       # 圆占（圆+线）比例
    "straight_ratio",     # 直线占（圆+线）比例
    "component_size_cv",  # 连通域面积变异系数
    "aspect_ratio",       # 原始宽高比
    "hole_ratio",         # 含内轮廓（环洞）的连通域比例
)

# Crossref 建议 User-Agent 带 mailto 以便对方联系；这里用本地占位标识。
USER_AGENT = "CSD-train-collect/0.1 (mailto:csd-collect@localhost)"


# --------------------------------------------------------------------------- #
# ① DOI 清洗
# --------------------------------------------------------------------------- #
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s]+", re.IGNORECASE)
_TAIL_YEAR_RE = re.compile(r"([_\-\s\[\(]\s*(?:19|20)\d{2}\s*[\]\)]?)$")
_TAIL_TAG_RE = re.compile(r"[_\-](?:pdf|doi|ocr|scan|fulltext|text)$", re.IGNORECASE)
_TAIL_AUTHOR_RE = re.compile(r"_[A-Za-z][A-Za-z0-9\-']{1,30}$")
_TAIL_VERSION_RE = re.compile(r"_[vV]\d+$")
_DOI_FULL_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


def _trim_doi_suffix(candidate: str) -> str:
    """逐步剥离 DOI 尾部的作者/年份/pdf 等噪声段，带长度下限保护以免误伤合法短后缀。"""
    s = candidate.rstrip(".,;:)]}")
    while True:
        for pat in (_TAIL_YEAR_RE, _TAIL_TAG_RE, _TAIL_VERSION_RE, _TAIL_AUTHOR_RE):
            m = pat.search(s)
            if m and len(s) - len(m.group(0)) >= 11:
                s = s[:m.start()]
                break
        else:
            return s


def clean_doi(filename: str) -> str | None:
    """从 PDF 文件名中洗净 DOI。

    支持纯 DOI、DOI+一坨后缀（_pdf / 作者_年份 等）、带元数据前缀三种命名。
    返回规范化后的 ``10.xxxx/yyy`` 字符串；识别不出返回 None。
    后缀剥离是启发式（下划线分隔），极少数自身含下划线的 DOI 可能被误截，需人工复核。
    """
    if not filename or not isinstance(filename, str):
        return None
    name = re.sub(r"\.[Pp][Dd][Ff]$", "", filename.strip())
    m = _DOI_RE.search(name)
    if not m:
        # DOI 编码命名把斜杠换成了下划线：10.1002_anie.196602311_x
        # 先只在 "10.NNNN_" 之后的第一个下划线处试还原成斜杠
        m2 = re.search(r"(10\.\d{4,9})_([^\s_]+)", name, re.IGNORECASE)
        if m2:
            restored = m2.group(1) + "/" + name[m2.end(1) + 1:]
            m = _DOI_FULL_RE.search(restored)
    if not m:
        return None
    doi = _trim_doi_suffix(m.group(0))
    return doi if _DOI_FULL_RE.fullmatch(doi) else None


# --------------------------------------------------------------------------- #
# ② Crossref 元数据
# --------------------------------------------------------------------------- #
def lookup_crossref(doi: str, timeout: float = 10.0) -> dict:
    """用 Crossref REST API 查 DOI 元数据。

    返回 ``{'doi','year','journal','title'}``（查不到的字段为 None）；
    网络错误 / 超时 / 非 200 / 解析失败一律返回 ``{'error': ...}``，不抛异常。
    """
    if not doi:
        return {"error": "空 DOI，无法查询 Crossref"}
    try:
        import requests
    except ImportError as e:
        raise RuntimeError("需要 requests：pip install requests（Crossref 查询依赖它）") from e

    url = "https://api.crossref.org/works/" + quote(doi, safe="/")
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.Timeout:
        return {"error": f"Crossref 请求超时（{timeout}s）：{doi}"}
    except requests.RequestException as e:
        return {"error": f"Crossref 请求失败：{e}"}

    if resp.status_code == 404:
        return {"error": f"Crossref 未找到该 DOI：{doi}"}
    if resp.status_code != 200:
        return {"error": f"Crossref 返回 HTTP {resp.status_code}：{doi}"}
    try:
        msg = (resp.json() or {}).get("message") or {}
    except ValueError as e:
        return {"error": f"Crossref 响应不是合法 JSON：{e}"}

    titles = msg.get("title") or []
    journals = msg.get("container-title") or msg.get("short-container-title") or []
    year = None
    for key in ("published-print", "published", "issued", "published-online"):
        parts = (msg.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    return {
        "doi": msg.get("DOI", doi),
        "year": year,
        "journal": journals[0] if journals else None,
        "title": titles[0] if titles else None,
    }


# --------------------------------------------------------------------------- #
# ③ 文本-图对齐（无图注场景）
# --------------------------------------------------------------------------- #
_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_IMG_HTML_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_IMG_CLEAN_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>", re.IGNORECASE)

_LABEL_PATTERNS = (
    re.compile(r"\bcompound\s*(?:no\.?\s*)?(\d{1,3}[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3}[a-z]?)\s+was\s+(?:obtained|prepared|isolated|synthesized|formed|produced)\b", re.IGNORECASE),
    re.compile(r"\b(?:product|intermediate|ligand|ester)\s+(\d{1,3}[a-z]?)\b", re.IGNORECASE),
    re.compile(r"^\s*(\d{1,3}[a-z]?)\s*$", re.MULTILINE),  # 图下方单独一行的标记
)

_CHEM_SUFFIX = (
    r"(?:anes?|enes?|ynes?|ols?|ones?|als?|ic acids?|acids?|amides?|esters?|amines?|"
    r"aldehydes?|ketones?|ethers?|benzenes?|benzoates?|oates?|phenols?|pyridines?|"
    r"nitriles?|oxides?|chlorides?|bromides?|sulfoxides?|sulfones?)"
)
# 允许小写开头与 `2-` 这类 IUPAC 前导，抓的是结构名称核心片段而非完整名称。
_NAME_RE = re.compile(rf"\b((?:\d{{1,2}}-)?[A-Za-z][A-Za-z\-]{{3,}}{_CHEM_SUFFIX})\b")
_COMMON_NAMES = (
    "aspirin", "acetone", "toluene", "aniline", "naphthalene", "anthracene",
    "benzaldehyde", "cyclohexanone", "ethyl acetate", "acetic acid",
)


def _find_label(text: str) -> str | None:
    for pat in _LABEL_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).lower()
    return None


def _label_near(line_slice) -> str | None:
    """逐行找编号标记，兼容图下方单独成行的 '3a'。"""
    for s in line_slice:
        cleaned = _IMG_CLEAN_RE.sub(" ", s).strip()
        if cleaned:
            lab = _find_label(cleaned)
            if lab:
                return lab
    return None


def _find_name_hint(text: str) -> str | None:
    m = _NAME_RE.search(text)
    if m:
        return m.group(1)
    for name in _COMMON_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            return name
    return None


def resolve_name_to_smiles(name: str) -> str | None:
    """名称→SMILES 的扩展点；当前未实现，恒返回 None，绝不编造结构。

    接入 RDKit / 外部名称解析服务时替换本函数；任何返回值都必须经人工确认后才能当真值。
    """
    return None


def align_text_figures(mineru_dir: str | Path) -> list[dict]:
    """从 MinerU 输出目录做「正文引用 ↔ 图片」对齐（无图注场景）。

    通用假设：目录里有 .md/.txt 文本与图片文件；图片经 ``![alt](path)`` 或 ``<img src>``
    被文本引用。对每张被引用的图，取其引用行前后窗口（下方权重更大）提取编号标记，
    再提取直接给出的结构名称作为候选。

    每项输出 ``{'image_path', 'label', 'context_text', 'direct_name_hint'}``：
      - label：编号标记（如 '3a'），找不到为 None；
      - direct_name_hint：正文中的结构名称候选，**未转 SMILES，需人工确认**，找不到为 None。
    未在文本中被引用的图片也会输出（label 为 None）并向 stderr 警告，不静默丢弃。
    目录缺 md 或缺图片时抛异常。
    """
    root = Path(mineru_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"MinerU 输出目录不存在：{root}")
    md_files = sorted(p for p in root.rglob("*")
                      if p.is_file() and p.suffix.lower() in TEXT_EXTS)
    img_files = [p for p in root.rglob("*")
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    if not md_files:
        raise FileNotFoundError(f"{root} 下没有 .md/.txt 文件，无法做文本-图对齐")
    if not img_files:
        raise FileNotFoundError(f"{root} 下没有图片文件，无法做文本-图对齐")

    by_name: dict[str, list[Path]] = {}
    for p in img_files:
        by_name.setdefault(p.name, []).append(p.resolve())

    used: set[Path] = set()
    results: list[dict] = []
    for md in md_files:
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            print(f"[警告] 读不了文本文件 {md}：{e}", file=sys.stderr)
            continue
        refs: list[tuple[int, str]] = []
        for i, line in enumerate(lines):
            for pat in (_IMG_MD_RE, _IMG_HTML_RE):
                for m in pat.finditer(line):
                    refs.append((i, m.group(1)))

        for i, ref in refs:
            candidates = list(by_name.get(Path(ref).name, []))
            if not candidates:
                local = (md.parent / ref).resolve()
                if local.is_file():
                    candidates = [local]
            if not candidates:
                print(f"[警告] md 引用的图片找不到：{ref}（{md}）", file=sys.stderr)
                continue

            img = candidates[0]
            used.add(img)
            lo, hi = max(0, i - 2), min(len(lines), i + 7)  # 图下方标记权重更大
            window = [_IMG_CLEAN_RE.sub(" ", s).strip() for s in lines[lo:hi]]
            window = [s for s in window if s]
            context = " ".join(window)
            # 标记常印在图下方或左侧：先逐行扫下方，再扫上方；逐行才能识别独立编号行
            label = _label_near(lines[i + 1:hi]) or _label_near(lines[lo:i])
            results.append({
                "image_path": str(img),
                "label": label,
                "context_text": context[:600],
                "direct_name_hint": _find_name_hint(context),
            })

    for img in img_files:
        if img.resolve() not in used:
            print(f"[警告] 图片未在 md 中被引用，label 留空待人工确认：{img}", file=sys.stderr)
            results.append({
                "image_path": str(img.resolve()),
                "label": None,
                "context_text": "",
                "direct_name_hint": None,
            })

    results.sort(key=lambda r: r["image_path"])
    return results


# --------------------------------------------------------------------------- #
# ④ 可解释轻量特征
# --------------------------------------------------------------------------- #
def extract_features(image_path: str | Path) -> list[float]:
    """从一张图提取 8 维可解释特征（顺序见 FEATURE_NAMES）。

    先按高度 400px 等比缩放以消除尺度差异；二值化后统计连通域、墨迹、Hough 直线/圆、
    连通域面积变异系数与环洞比例。读不了图抛 ValueError。
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"读不了图片：{image_path}")
    h, w = img.shape
    aspect = w / max(h, 1)
    scale = 400.0 / max(h, 1)
    nw = max(1, int(round(w * scale)))
    img = cv2.resize(img, (nw, 400), interpolation=cv2.INTER_AREA)

    blur = cv2.GaussianBlur(img, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    fg = binary > 0
    ink_ratio = float(fg.mean()) if fg.size else 0.0

    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary.astype(np.uint8), 8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    areas = areas[areas >= 3]
    n_comp = int(len(areas))
    log_n_comp = float(np.log1p(n_comp))
    size_cv = float(np.std(areas) / np.mean(areas)) if n_comp else 0.0

    edges = cv2.Canny(blur, 50, 150)
    min_len = max(10, int(min(img.shape[:2]) * 0.08))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=20,
                            minLineLength=min_len, maxLineGap=5)
    n_lines = 0 if lines is None else len(lines)
    line_density = n_lines / max(sum(img.shape[:2]), 1) * 100.0

    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=18,
                               param1=100, param2=20, minRadius=6, maxRadius=90)
    n_circles = 0 if circles is None else len(circles[0])
    denom = n_circles + n_lines + 1e-6

    contours, hier = cv2.findContours(binary.astype(np.uint8), cv2.RETR_CCOMP,
                                      cv2.CHAIN_APPROX_SIMPLE)
    outer = holes = 0
    if hier is not None:
        for entry in hier[0]:
            if entry[3] == -1:
                outer += 1
                if entry[2] != -1:
                    holes += 1
    hole_ratio = holes / max(outer, 1)

    return [
        round(log_n_comp, 4), round(ink_ratio, 4), round(line_density, 4),
        round(n_circles / denom, 4), round(n_lines / denom, 4),
        round(size_cv, 4), round(aspect, 4), round(hole_ratio, 4),
    ]


# --------------------------------------------------------------------------- #
# ⑤ 结构式二分类器（SVM）+ 回流重训
# --------------------------------------------------------------------------- #
def _sklearn():
    try:
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import LinearSVC
    except ImportError as e:
        raise RuntimeError("需要 scikit-learn：pip install scikit-learn（结构式分类器依赖它）") from e
    return StandardScaler, LinearSVC


def _joblib():
    try:
        import joblib
    except ImportError as e:
        raise RuntimeError("需要 joblib：pip install joblib（模型持久化依赖它）") from e
    return joblib


def _iter_images(directory: str | Path) -> list[Path]:
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(f"图片目录不存在：{d}")
    imgs = sorted(p for p in d.rglob("*")
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not imgs:
        raise FileNotFoundError(f"{d} 下没有图片（支持 {', '.join(IMAGE_EXTS)}）")
    return imgs


def _features_of(image_paths: list[Path], label: int, warnings: list[str]):
    """提特征并打标；单张读图失败只警告并跳过，不静默伪造。"""
    feats, labels, paths = [], [], []
    for p in image_paths:
        try:
            feats.append(extract_features(p))
        except (ValueError, cv2.error) as e:
            warnings.append(f"跳过 {p}：{e}")
            continue
        labels.append(label)
        paths.append(str(p))
    return feats, labels, paths


def _fit_model(X: np.ndarray, y: np.ndarray):
    StandardScaler, LinearSVC = _sklearn()
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    clf = LinearSVC(C=1.0, class_weight="balanced", random_state=0, max_iter=10000)
    clf.fit(Xs, y)
    return scaler, clf, float(clf.score(Xs, y))


def _dump_model(model_path: Path, scaler, clf, X: np.ndarray, y: np.ndarray, paths: list[str]) -> None:
    joblib = _joblib()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "version": 1,
        "feature_names": list(FEATURE_NAMES),
        "scaler": scaler,
        "clf": clf,
        "train_features": X,
        "train_labels": y,
        "train_paths": paths,
    }, str(model_path))


def _load_model(model_path: str | Path) -> dict:
    p = Path(model_path)
    if not p.is_file():
        raise FileNotFoundError(f"模型文件不存在：{p}（先跑 train）")
    joblib = _joblib()
    payload = joblib.load(str(p))
    if not isinstance(payload, dict) or "scaler" not in payload or "clf" not in payload:
        raise ValueError(f"模型文件格式不对：{p}")
    if payload.get("feature_names") and list(payload["feature_names"]) != list(FEATURE_NAMES):
        raise ValueError(f"模型特征定义与当前代码不一致：{p}（请用新版 train 重训）")
    return payload


def train_classifier(positive_dir, negative_dir, model_path) -> dict:
    """用正（结构式）/负（表格、谱图、线图、仪器图等）样本目录训练 LinearSVC。

    模型（joblib）内含 scaler、clf 与训练特征/标签快照，供 refine 在无原始目录时重训。
    返回样本数、特征名、训练集准确率与警告列表；任一类无样本则抛错。
    """
    pos, neg = _iter_images(positive_dir), _iter_images(negative_dir)
    warnings: list[str] = []
    fp, lp, pp = _features_of(pos, 1, warnings)
    fn, ln, pn = _features_of(neg, 0, warnings)
    if not fp:
        raise ValueError(f"正样本目录没有可用图片：{positive_dir}")
    if not fn:
        raise ValueError(f"负样本目录没有可用图片：{negative_dir}")

    X = np.asarray(fp + fn, dtype=float)
    y = np.asarray(lp + ln, dtype=int)
    if min(len(fp), len(fn)) < 2:
        warnings.append("某一类样本少于 2 张，训练准确率参考意义有限")
    scaler, clf, acc = _fit_model(X, y)
    out = Path(model_path)
    _dump_model(out, scaler, clf, X, y, pp + pn)
    return {
        "model_path": str(out),
        "n_positive": len(fp),
        "n_negative": len(fn),
        "n_features": len(FEATURE_NAMES),
        "feature_names": list(FEATURE_NAMES),
        "train_accuracy": round(acc, 4),
        "warnings": warnings,
    }


def classify_images(image_dir, model_path) -> dict:
    """对目录内每张图给出 ``{image_path: {'is_structure': bool, 'score': float}}``。

    score 为 SVM decision_function 原始值（>0 判为结构式，越大越确信）；
    只读模型、不改模型。无图片或无模型时抛错。
    """
    imgs = _iter_images(image_dir)
    payload = _load_model(model_path)
    X = np.asarray([extract_features(p) for p in imgs], dtype=float)
    if X.shape[1] != len(FEATURE_NAMES):
        raise ValueError("图片特征维度与模型不一致（模型版本不匹配）")
    Xs = payload["scaler"].transform(X)
    scores = np.asarray(payload["clf"].decision_function(Xs)).ravel()
    return {
        str(p): {"is_structure": bool(s > 0), "score": round(float(s), 4)}
        for p, s in zip(imgs, scores)
    }


def refine_classifier(rejected_dir, model_path) -> dict:
    """回流闭环：把首审被手动剔除的图作为新负样本并入训练集，重训并覆盖模型。

    旧模型先备份到 ``<model_path>.bak``（返回 backup 路径）；原始训练特征从模型快照取回，
    因此不要求原 positive/negative 目录仍存在。rejected_dir 无图片时抛错。
    """
    rejected = _iter_images(rejected_dir)
    payload = _load_model(model_path)
    base_X = payload.get("train_features")
    base_y = payload.get("train_labels")
    base_paths = payload.get("train_paths") or []
    if base_X is None or base_y is None:
        raise ValueError("模型缺少训练快照，无法 refine；请用新版 train_classifier 重新训练")

    warnings: list[str] = []
    fnew, lnew, pnew = _features_of(rejected, 0, warnings)
    if not fnew:
        raise ValueError(f"被剔除目录没有可用图片：{rejected_dir}")

    X = np.vstack([np.asarray(base_X, dtype=float), np.asarray(fnew, dtype=float)])
    y = np.concatenate([np.asarray(base_y, dtype=int), np.asarray(lnew, dtype=int)])
    scaler, clf, acc = _fit_model(X, y)

    out = Path(model_path)
    backup = Path(str(out) + ".bak")
    shutil.copy2(str(out), str(backup))
    _dump_model(out, scaler, clf, X, y, list(base_paths) + pnew)
    return {
        "model_path": str(out),
        "backup_path": str(backup),
        "n_negative_added": len(fnew),
        "n_samples_before": int(len(base_y)),
        "n_samples_after": int(len(y)),
        "train_accuracy": round(acc, 4),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="训练①：采集阶段（DOI / 对齐 / 结构式分类器）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doi", help="从文件名提取 DOI 并查 Crossref 元数据")
    d.add_argument("filename")
    d.add_argument("--timeout", type=float, default=10.0)

    a = sub.add_parser("align", help="MinerU 输出目录的文本-图对齐")
    a.add_argument("mineru_dir")
    a.add_argument("--out")

    t = sub.add_parser("train", help="训练结构式二分类器")
    t.add_argument("--positive", required=True)
    t.add_argument("--negative", required=True)
    t.add_argument("--model", required=True)

    c = sub.add_parser("classify", help="用模型分类目录内的图")
    c.add_argument("image_dir")
    c.add_argument("--model", required=True)
    c.add_argument("--out")

    r = sub.add_parser("refine", help="用被剔除的图回流重训")
    r.add_argument("rejected_dir")
    r.add_argument("--model", required=True)

    args = ap.parse_args()
    if args.cmd == "doi":
        doi = clean_doi(args.filename)
        if doi is None:
            result = {"filename": args.filename, "error": "未从文件名中识别出 DOI"}
        else:
            result = {"doi": doi, "crossref": lookup_crossref(doi, args.timeout)}
    elif args.cmd == "align":
        result = align_text_figures(args.mineru_dir)
    elif args.cmd == "train":
        result = train_classifier(args.positive, args.negative, args.model)
    elif args.cmd == "classify":
        result = classify_images(args.image_dir, args.model)
    else:
        result = refine_classifier(args.rejected_dir, args.model)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    out = getattr(args, "out", None)
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
        print(f"写出 {p}")
    else:
        print(text)


if __name__ == "__main__":
    main()
