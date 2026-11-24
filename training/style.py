"""训练②④：风格聚类定档（约束聚类）→ 参数化仿古渲染。

② 风格识别：主分类器是聚类，人的标注只作初筛种子（must-link / cannot-link）。
年份是强特征（DOI / 文件名已知），参与聚类并用于验证同档一致性。
档位数量由数据决定，不预设年代档；只考虑 1985 年前的画风。

④ 仿古渲染：RDKit MolDraw2DCairo 参数化 + 取代基库。
RDKit 无法逐片段设置渲染参数，segment_styles 仅作接口预留并显式警告。

可单独调试：
    python -m training.style cluster --images <dir> --out <dir>
    python -m training.style eval --profiles <_cluster_detail.json> --truth <truth.json>
    python -m training.style render --smiles <smi> --style <style.json> --out <png>
    python -m training.style batch --style-dir <dir> --out <dir> --smiles "<smi>" ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # 允许模块先于图像依赖可用；extract_features 调用时再明确报错
    cv2 = None

YEAR_WEIGHT = 1.5          # 年份是强特征，标准化后加权
MAX_AUTO_CLUSTERS = 8      # 无种子时层次聚类最多保留的档位数
IMAGE_EXTS = (".png", ".jpg", ".jpeg")
DEFAULT_FONT_PATH = r"C:\Windows\Fonts\times.ttf"


# --------------------------------------------------------------------------
# 数据结构（均可用 dataclasses.asdict 转 dict → json 序列化）
# --------------------------------------------------------------------------
@dataclass
class StyleFeatures:
    image: str
    stroke_width: float
    ink_density: float
    aspect: float
    has_circle_aromatic: int
    year: int | None = None
    year_missing: bool = False

    FEATURE_NAMES = ("stroke_width", "ink_density", "aspect", "has_circle_aromatic", "year")

    def vector(self) -> list[float]:
        y = 0.0 if self.year is None else float(self.year)
        return [float(self.stroke_width), float(self.ink_density),
                float(self.aspect), float(self.has_circle_aromatic), y]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["feature_names"] = list(self.FEATURE_NAMES)
        d["vector"] = self.vector()
        return d


@dataclass
class StyleProfile:
    """一个画风档位。前 7 个字段与原版一致，保证 pipeline.py 的 StyleProfile(**json) 可用。"""
    name: str
    stroke_width: float
    font_size: float
    bond_length: float
    mono: bool
    sample_count: int = 0
    note: str = ""
    # 扩展字段（约束聚类 / 评估 / 渲染所需，均有默认值以兼容旧 json）
    line_width: float = 0.0
    font_path: str = DEFAULT_FONT_PATH
    seed_label: str = ""                                  # 对应人的标注档位名
    centroid: list[float] = field(default_factory=list)   # 标准化空间中的簇中心
    members: list[dict] = field(default_factory=list)     # [{image, year, vector}]
    year_median: float | None = None
    year_span: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# ② 风格识别
# --------------------------------------------------------------------------
def year_from_filename(name: str) -> int | None:
    """从 'ABRAHAMSON1948_xxx.pdf' / 'xxx_1948.pdf' 提取年份，无则 None。"""
    m = re.search(r"(?<!\d)(1[8-9]\d{2}|20[0-2]\d)(?!\d)", str(name))
    if not m:
        return None
    year = int(m.group(1))
    return year if 1800 <= year <= 2029 else None


def _runs(values: np.ndarray) -> list[tuple[int, int]]:
    if len(values) == 0:
        return []
    out, start, prev = [], int(values[0]), int(values[0])
    for v in values[1:]:
        v = int(v)
        if v == prev + 1:
            prev = v
        else:
            out.append((start, prev))
            start = prev = v
    out.append((start, prev))
    return out


def extract_features(image_path: str | Path, year: int | None = None) -> dict:
    """提取可聚类的画风特征；返回 dict，含 vector 与 feature_names。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python-headless 才能提取图像特征（pip install -r requirements.txt）")
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"读不了图片: {image_path}")
    h, w = img.shape
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = binary > 0
    density = float(ink.mean())

    # 线宽 = 单行内水平墨迹段的宽度中位数（不是整列跨度——那会把整个分子宽度当线宽）
    widths = []
    for row in ink:
        cols = np.where(row)[0]
        for start, end in _runs(cols):
            widths.append(end - start + 1)
    stroke = float(np.median(widths)) if widths else 1.0

    try:
        circles = cv2.HoughCircles(img, cv2.HOUGH_GRADIENT, dp=1.2, minDist=18,
                                   param1=100, param2=22, minRadius=8, maxRadius=70)
    except cv2.error:
        circles = None

    if year is None:
        year = year_from_filename(Path(image_path).name)
    feat = StyleFeatures(
        image=str(image_path),
        stroke_width=round(stroke, 3),
        ink_density=round(density, 4),
        aspect=round(w / max(h, 1), 3),
        has_circle_aromatic=1 if circles is not None else 0,
        year=year,
        year_missing=year is None,
    )
    return feat.to_dict()


def _as_dict(obj) -> dict:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return dict(obj)
    raise TypeError(f"需要 dict 或 dataclass，收到 {type(obj).__name__}")


def _matrix(features: list[dict]) -> tuple[np.ndarray, np.ndarray, int]:
    """构造原始矩阵、标准化矩阵（年份加权、缺失填中位数），返回 (raw, x, year_col)。"""
    rows = [_as_dict(f) for f in features]
    names = rows[0].get("feature_names", list(StyleFeatures.FEATURE_NAMES))
    year_col = names.index("year") if "year" in names else len(names) - 1
    raw = np.array([f.get("vector") or [f[n] for n in names] for f in rows], dtype=float)

    years = np.array([r.get("year") if r.get("year") else np.nan for r in rows], dtype=float)
    if not np.all(np.isnan(years)):
        years = np.where(np.isnan(years), float(np.nanmedian(years)), years)
    else:
        years = np.full(len(rows), 1900.0)
    raw[:, year_col] = years

    x = raw.copy()
    std = x.std(axis=0)
    std[std < 1e-9] = 1.0
    x = (x - x.mean(axis=0)) / std
    x[:, year_col] *= YEAR_WEIGHT
    return raw, x, year_col


def _auto_labels(x: np.ndarray) -> np.ndarray:
    """无种子：ward 层次聚类按距离自动定档，限制最多 MAX_AUTO_CLUSTERS。"""
    n = len(x)
    if n <= 1:
        return np.ones(n, dtype=int)
    try:
        from scipy.cluster.hierarchy import fcluster, linkage
    except ImportError:  # 无 scipy 时退化为按笔画/圈标记分箱
        warnings.warn("scipy 不可用，退化为笔画/圈标记分箱（档位较粗糙）。", UserWarning)
        return np.clip((x[:, 0] > 0).astype(int) + (x[:, 3] > 0).astype(int), 0, 3) + 1

    z = linkage(x, method="ward")
    cap = max(2, min(MAX_AUTO_CLUSTERS, max(2, n // 2)))
    threshold = 1.5
    labels = fcluster(z, t=threshold, criterion="distance")
    for _ in range(8):
        if len(np.unique(labels)) <= cap:
            break
        threshold *= 1.35
        labels = fcluster(z, t=threshold, criterion="distance")
    return labels.astype(int)


def _seeded_labels(x: np.ndarray, seed_pairs: list[tuple[int, str]]) -> tuple[np.ndarray, np.ndarray]:
    """约束聚类：人的标注作种子，同标签 must-link / 异标签 cannot-link。

    种子样本固定归属其标注档位并作为初始中心，其余样本按距离归入；
    迭代重算中心直到收敛。返回 (labels, centers)。
    """
    n = len(x)
    names = sorted({label for _, label in seed_pairs})
    index = {name: j for j, name in enumerate(names)}
    k = len(names)
    centers = np.array([x[[i for i, lab in seed_pairs if lab == name]].mean(axis=0)
                        for name in names], dtype=float)

    labels = np.full(n, -1, dtype=int)
    for i, lab in seed_pairs:
        labels[i] = index[lab]

    for _ in range(100):
        for i in range(n):
            if labels[i] < 0:
                labels[i] = int(np.argmin(((x[i] - centers) ** 2).sum(axis=1)))
        new_centers = centers.copy()
        for j in range(k):
            mask = labels == j
            if mask.any():
                new_centers[j] = x[mask].mean(axis=0)
        if np.allclose(new_centers, centers):
            break
        centers = new_centers
    return labels, centers


def cluster_styles(features: list[dict], out_dir, seed_labels: dict | None = None) -> list[dict]:
    """聚类定档。seed_labels: {image_path: '档位A'} 人的标注作种子。

    返回 list[dict]（可 json 序列化）；写出每档 <档位_*.json> 及
    _cluster_detail.json（含 members，供 evaluate_clusters 使用）。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not features:
        warnings.warn("② 没有图像特征可聚类：features 为空（数据尚未到位？）")
        return []

    rows = [_as_dict(f) for f in features]
    raw, x, year_col = _matrix(rows)
    n = len(rows)

    seed_pairs: list[tuple[int, str]] = []
    if seed_labels:
        for i, f in enumerate(rows):
            image = str(f.get("image", ""))
            label = seed_labels.get(image)
            if label is None:
                label = seed_labels.get(Path(image).name)
            if label is not None:
                seed_pairs.append((i, str(label)))

    centers = None
    if seed_pairs:
        labels, centers = _seeded_labels(x, seed_pairs)
    else:
        labels = _auto_labels(x)

    groups: dict[int, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        groups[int(lab)].append(i)

    profiles: list[dict] = []
    for order, lab in enumerate(sorted(groups), start=1):
        idxs = groups[lab]
        members = []
        for i in idxs:
            f = rows[i]
            members.append({
                "image": str(f.get("image", "")),
                "year": f.get("year"),
                "vector": [float(v) for v in raw[i]],
            })
        years = [m["year"] for m in members if m["year"]]
        med = np.median(raw[idxs], axis=0)
        seed_names = sorted({seed_labels.get(str(rows[i].get("image", "")))
                             or seed_labels.get(Path(str(rows[i].get("image", ""))).name)
                             for i in idxs} - {None}) if seed_pairs else []
        stroke = float(med[0])
        profile = StyleProfile(
            name=f"档位 {order}",
            stroke_width=round(stroke, 3),
            font_size=14.0,
            bond_length=-1.0,
            mono=True,
            sample_count=len(idxs),
            note="由约束聚类得出，非预设年代档" if seed_pairs else "由聚类得出，非预设年代档",
            line_width=round(stroke, 3),
            seed_label="/".join(seed_names),
            centroid=[float(v) for v in (centers[lab] if centers is not None
                                         else x[idxs].mean(axis=0))],
            members=members,
            year_median=float(np.median(years)) if years else None,
            year_span=int(max(years) - min(years)) if years else 0,
        )
        data = profile.to_dict()
        profiles.append(data)
        (out_dir / f"档位_{order}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "_cluster_detail.json").write_text(
        json.dumps({
            "feature_names": list(rows[0].get("feature_names", StyleFeatures.FEATURE_NAMES)),
            "year_weight": YEAR_WEIGHT,
            "has_seed": bool(seed_pairs),
            "profiles": profiles,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return profiles


def _find_truth(image: str, truth: dict):
    if image in truth:
        return truth[image]
    base = Path(image).name
    if base in truth:
        return truth[base]
    for key, value in truth.items():
        if Path(str(key)).name == base:
            return value
    return None


def evaluate_clusters(profiles, truth: dict) -> dict:
    """训练/测试准确度 + silhouette + 同档一致性。

    profiles: cluster_styles 的返回（list[dict] 或 list[StyleProfile]）。
    truth: {image_path: '档位A'} 人的标注真值。
    """
    result: dict = {"accuracy": None, "n_train": 0, "n_test": 0,
                    "silhouette": None, "cluster_purity": None,
                    "year_consistency": [], "per_cluster": [], "warnings": []}
    if not truth:
        result["warnings"].append("没有 truth 标注，无法评估准确度。")
        return result

    profiles = [p if isinstance(p, dict) else asdict(p) for p in (profiles or [])]
    samples = []
    for cid, prof in enumerate(profiles):
        for m in prof.get("members", []):
            label = _find_truth(str(m.get("image", "")), truth)
            if label is not None and m.get("vector"):
                samples.append((str(m["image"]), m.get("year"), np.array(m["vector"], float),
                                cid, label))
    if len(samples) < 2:
        result["warnings"].append(f"只有 {len(samples)} 个可对照样本，至少需要 2 个。")
        return result

    x = np.array([s[2] for s in samples], dtype=float)
    std = x.std(axis=0)
    std[std < 1e-9] = 1.0
    x = (x - x.mean(axis=0)) / std
    labels = [s[4] for s in samples]
    classes = sorted(set(labels))

    rng = random.Random(42)
    idx_by_label: dict[str, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        idx_by_label[lab].append(i)
    train_idx, test_idx = [], []
    for lab in classes:
        idxs = idx_by_label[lab]
        rng.shuffle(idxs)
        if len(idxs) >= 2:
            n_test = min(max(1, round(len(idxs) * 0.2)), len(idxs) - 1)
            test_idx.extend(idxs[:n_test])
            train_idx.extend(idxs[n_test:])
        else:
            train_idx.extend(idxs)
            result["warnings"].append(f"档位 '{lab}' 只有 1 个样本，仅用于训练。")

    result["n_train"], result["n_test"] = len(train_idx), len(test_idx)
    if test_idx:
        centers = {lab: x[[i for i in train_idx if labels[i] == lab]].mean(axis=0)
                   for lab in classes if any(labels[i] == lab for i in train_idx)}
        preds = [min(centers, key=lambda lab: float(((x[i] - centers[lab]) ** 2).sum()))
                 for i in test_idx]
        actual = [labels[i] for i in test_idx]
        result["accuracy"] = round(sum(p == a for p, a in zip(preds, actual)) / len(actual), 4)
    else:
        result["warnings"].append("没有测试样本，无法计算准确度。")

    if len(classes) >= 2 and len(samples) >= 3:
        try:
            from sklearn.metrics import silhouette_score
            result["silhouette"] = round(float(silhouette_score(x, labels)), 4)
        except (ImportError, ValueError) as exc:
            result["warnings"].append(f"silhouette 不可用: {exc}")

    # 同档一致性：每个聚类簇里 truth 众数占比；年份跨度作辅助验证信号
    correct = total = 0
    for cid, prof in enumerate(profiles):
        rows = [s for s in samples if s[3] == cid]
        if not rows:
            continue
        counts = Counter(s[4] for s in rows)
        correct += max(counts.values())
        total += len(rows)
        years = [s[1] for s in rows if s[1]]
        result["per_cluster"].append({
            "cluster": prof.get("name"),
            "n": len(rows),
            "dominant_label": counts.most_common(1)[0][0],
            "purity": round(max(counts.values()) / len(rows), 4),
            "year_span": int(max(years) - min(years)) if years else None,
        })
        if years:
            result["year_consistency"].append({"cluster": prof.get("name"),
                                               "span": int(max(years) - min(years))})
    result["cluster_purity"] = round(correct / total, 4) if total else None
    return result


# --------------------------------------------------------------------------
# ④ 仿古渲染
# --------------------------------------------------------------------------
def _render_params(style) -> dict:
    d = _as_dict(style)

    def pick(*keys, default):
        for key in keys:
            if d.get(key) is not None:
                return d[key]
        return default

    return {
        "line_width": float(pick("line_width", "stroke_width", default=1.0)),
        "font_size": float(pick("font_size", default=14.0)),
        "bond_length": float(pick("bond_length", "fixed_bond_length", default=-1.0)),
        "mono": bool(pick("mono", "useBWAtomPalette", default=True)),
        "font_path": str(pick("font_path", default=DEFAULT_FONT_PATH)),
    }


def render_cache_key(smiles: str, style, segment_styles: dict | None = None) -> str:
    """仅依据真正影响渲染的参数做 sha256，避免 members 变动导致缓存失效。"""
    payload = {"version": 1, "smiles": smiles, "params": _render_params(style),
               "segment_styles": segment_styles or {}}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def render_smiles(smiles: str, style, out_png, segment_styles: dict | None = None) -> None:
    """参数化渲染单分子。style 可为 dict 或 StyleProfile（兼容 pipeline.py）。

    segment_styles 仅作接口预留：RDKit 不支持对主链/侧链分别设线宽字体，
    传入非空值时显式警告，绝不假装做到了分段画法。
    """
    if segment_styles:
        warnings.warn(
            "segment_styles 已接收但被忽略：RDKit MolDraw2DCairo 不支持对主链/侧链"
            "分别设置线宽/字体/键长；整个分子将使用同一套参数（未实现分段画法）。",
            UserWarning, stacklevel=2)
    params = _render_params(style)
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw, rdDepictor
    except ImportError as exc:
        raise RuntimeError("需要 RDKit：pip install rdkit（仿古渲染依赖它）") from exc

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"非法 SMILES: {smiles}")
    rdDepictor.Compute2DCoords(mol)

    opts = Draw.MolDrawOptions()
    # RDKit 新版属性名：bondLineWidth / fixedFontSize（旧版 lineWidth/fontSize 已废弃）
    for name in ("bondLineWidth", "lineWidth"):
        if hasattr(opts, name):
            setattr(opts, name, float(params["line_width"]))
            break
    for name in ("fixedFontSize", "fontSize"):
        if hasattr(opts, name):
            setattr(opts, name, int(params["font_size"]))
            break
    if params["bond_length"] > 0:
        opts.fixedBondLength = int(params["bond_length"])
    if params["mono"] and hasattr(opts, "useBWAtomPalette"):
        opts.useBWAtomPalette()
    font_path = Path(params["font_path"])
    if params["font_path"] and font_path.exists():
        try:
            opts.fontFile = str(font_path)
        except Exception as exc:  # 版本差异时退回默认字体
            warnings.warn(f"无法设置字体 {font_path}: {exc}", UserWarning)

    drawer = Draw.MolDraw2DCairo(600, 400)
    drawer.SetDrawOptions(opts)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_png.write_bytes(drawer.GetDrawingText())


def _load_substituents_safe() -> dict:
    """取代基库由另一模块提供；模块暂不存在时降级为空，不中断渲染。"""
    load = None
    for module in ("training.substituents", ".substituents"):
        try:
            if module.startswith("."):
                from importlib import import_module
                load = getattr(import_module(module, __package__), "load_substituents")
            else:
                from training.substituents import load_substituents as load
            break
        except (ImportError, AttributeError):
            continue
    if load is None:
        warnings.warn("training.substituents 尚不可用，跳过取代基库渲染。", UserWarning)
        return {}
    try:
        return load() or {}
    except Exception as exc:
        warnings.warn(f"load_substituents 调用失败，跳过取代基库: {exc}", UserWarning)
        return {}


def render_batch(smiles_list: list[str], style_dir, out_dir, cache_dir=None) -> list[dict]:
    """按所有档位批量渲染（含共享取代基库），命中缓存则复用 PNG。"""
    style_dir, out_dir = Path(style_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cache_dir) if cache_dir else out_dir / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    styles = []
    for path in sorted(style_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "name" in data:
                styles.append((path.stem, data))
        except (ValueError, OSError) as exc:
            warnings.warn(f"跳过无效风格档 {path.name}: {exc}", UserWarning)
    if not styles:
        warnings.warn(f"④ 风格档目录没有可用 json：{style_dir}（先跑 cluster）")
        return []

    smiles = list(dict.fromkeys(s for s in smiles_list if s))
    substituents = _load_substituents_safe()
    for item in substituents.values():
        s = item.get("smiles") if isinstance(item, dict) else getattr(item, "smiles", None)
        if s:
            smiles.append(s)
    smiles = list(dict.fromkeys(smiles))
    if not smiles:
        warnings.warn("render_batch 没有任何 SMILES 可渲染。")
        return []

    results = []
    for smi in smiles:
        for stem, style in styles:
            key = render_cache_key(smi, style)
            cached = cache_dir / f"{key}.png"
            hit = cached.exists()
            if not hit:
                try:
                    render_smiles(smi, style, cached)
                except (ValueError, RuntimeError) as exc:
                    warnings.warn(f"渲染失败 {smi} / {stem}: {exc}", UserWarning)
                    continue
            target = out_dir / f"{stem}_{key[:8]}.png"
            if not target.exists():
                target.write_bytes(cached.read_bytes())
            results.append({"smiles": smi, "style": style.get("name", stem),
                            "png": str(target), "cache_key": key, "cache_hit": hit})
    return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="训练②④：风格聚类 / 评估 / 仿古渲染")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cluster", help="② 约束聚类定档")
    c.add_argument("--images", required=True)
    c.add_argument("--out", default="data/training/styles")
    c.add_argument("--seed-labels", help="人的标注 json: {image_path: '档位A'}")

    e = sub.add_parser("eval", help="训练/测试准确度与同档一致性")
    e.add_argument("--profiles", required=True, help="cluster 输出的 _cluster_detail.json")
    e.add_argument("--truth", required=True, help="人的标注 json")

    r = sub.add_parser("render", help="④ 渲染单个分子")
    r.add_argument("--smiles", required=True)
    r.add_argument("--style", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--segment-styles", help="预留的分段画法参数 json（当前会被忽略并警告）")

    b = sub.add_parser("batch", help="④ 批量渲染（含取代基库 + 缓存）")
    b.add_argument("--smiles", nargs="*", default=[])
    b.add_argument("--style-dir", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--cache-dir")

    args = ap.parse_args()

    if args.cmd == "cluster":
        images = [p for p in Path(args.images).rglob("*") if p.suffix.lower() in IMAGE_EXTS]
        if not images:
            print(f"⚠ 没有图片：{args.images}（数据尚未到位？）")
            return
        seeds = _read_json(args.seed_labels) if args.seed_labels else None
        feats = [extract_features(p) for p in images]
        profiles = cluster_styles(feats, Path(args.out), seed_labels=seeds)
        print(f"从 {len(feats)} 张图聚出 {len(profiles)} 档（种子={'是' if seeds else '否'}）→ {args.out}")
        for p in profiles:
            print(f"  {p['name']}: stroke={p['stroke_width']} samples={p['sample_count']} "
                  f"year_span={p['year_span']} seed={p['seed_label'] or '-'}")
    elif args.cmd == "eval":
        detail = _read_json(args.profiles)
        profiles = detail["profiles"] if isinstance(detail, dict) and "profiles" in detail else detail
        metrics = evaluate_clusters(profiles, _read_json(args.truth))
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    elif args.cmd == "render":
        segments = _read_json(args.segment_styles) if args.segment_styles else None
        render_smiles(args.smiles, _read_json(args.style), Path(args.out), segment_styles=segments)
        print(f"渲染到 {args.out}")
    else:
        results = render_batch(args.smiles, args.style_dir, args.out, args.cache_dir)
        hits = sum(1 for r in results if r["cache_hit"])
        print(f"渲染 {len(results)} 张（缓存命中 {hits}）→ {args.out}")


if __name__ == "__main__":
    main()
