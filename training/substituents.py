"""训练③共享取代基库：元素 / 常见缩写 / 通式 / 烷基。

条目固定三字段：hetero（含杂原子）、ring（自身带环）、smiles（SMILES 片段）。
style.py 渲染与 topo.py 识别共用这一份；外部 JSON 通过 load_substituents 扩展。
"""
from __future__ import annotations

import json
from pathlib import Path

_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def normalize_label_text(text: str) -> str:
    """下标/上标数字归一为普通数字并去空白——古早图下标极小，OCR 常丢。"""
    return "".join(str(text).strip().translate(_SUB).translate(_SUP).split())


def _entry(smiles: str, hetero: bool = False, ring: bool = False) -> dict:
    return {"hetero": hetero, "ring": ring, "smiles": smiles}


SUBSTITUENTS: dict[str, dict] = {
    # 元素
    "C": _entry("C"),
    "N": _entry("N", hetero=True),
    "O": _entry("O", hetero=True),
    "S": _entry("S", hetero=True),
    "P": _entry("P", hetero=True),
    "F": _entry("F", hetero=True),
    "Cl": _entry("Cl", hetero=True),
    "Br": _entry("Br", hetero=True),
    "I": _entry("I", hetero=True),
    "Si": _entry("[Si]", hetero=True),
    # 常见缩写
    "Me": _entry("C"),
    "Et": _entry("CC"),
    "Pr": _entry("CCC"),
    "i-Pr": _entry("C(C)C"),
    "t-Bu": _entry("CC(C)(C)"),
    "Bu": _entry("CCCC"),
    "s-Bu": _entry("CCC(C)"),
    "Ph": _entry("c1ccccc1", ring=True),
    "Bn": _entry("Cc1ccccc1", ring=True),
    "Bz": _entry("C(=O)c1ccccc1", ring=True),
    "Cy": _entry("C1CCCCC1", ring=True),
    "Ac": _entry("CC(=O)"),
    "OMe": _entry("OC", hetero=True),
    "OEt": _entry("OCC", hetero=True),
    "OPh": _entry("Oc1ccccc1", hetero=True, ring=True),
    "OH": _entry("O", hetero=True),
    "NH2": _entry("N", hetero=True),
    "NMe2": _entry("N(C)C", hetero=True),
    "NEt2": _entry("N(CC)CC", hetero=True),
    "NHMe": _entry("NC", hetero=True),
    "NO2": _entry("[N+](=O)[O-]", hetero=True),
    "NO": _entry("N=O", hetero=True),
    "N3": _entry("N=[N+]=[N-]", hetero=True),
    "CN": _entry("C#N", hetero=True),
    "NC": _entry("[N+]#[C-]", hetero=True),
    "CO2Me": _entry("C(=O)OC", hetero=True),
    "CO2Et": _entry("C(=O)OCC", hetero=True),
    "CHO": _entry("C=O", hetero=True),
    "CONH2": _entry("C(=O)N", hetero=True),
    "SO3H": _entry("S(=O)(=O)O", hetero=True),
    "CF3": _entry("C(F)(F)F", hetero=True),
    "CCl3": _entry("C(Cl)(Cl)Cl", hetero=True),
    "TMS": _entry("[Si](C)(C)C", hetero=True),
    "Vi": _entry("C=C"),
    "All": _entry("CC=C"),
    # 带撇号的通式（用不同 attachment map 号区分）
    "R": _entry("[*:1]"),
    "R'": _entry("[*:2]"),
    "R''": _entry("[*:3]"),
    # 烷基 / 分子式写法
    "CH3": _entry("C"),
    "C2H5": _entry("CC"),
    "C3H7": _entry("CCC"),
    "C4H9": _entry("CCCC"),
    "C6H5": _entry("c1ccccc1", ring=True),
}


def load_substituents(path: str | Path | None = None) -> dict:
    """返回内置库的副本；path 给定时把外部 JSON 条目合并进去（同名覆盖）。

    JSON 形状：{"新缩写": {"hetero": bool, "ring": bool, "smiles": str}, ...}
    """
    data = {name: dict(entry) for name, entry in SUBSTITUENTS.items()}
    if path is None:
        return data
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"取代基扩展文件不存在: {p}")
    extra = json.loads(p.read_text(encoding="utf-8"))
    if extra is None:
        return data
    if not isinstance(extra, dict):
        raise ValueError("取代基 JSON 顶层必须是对象")
    for name, raw in extra.items():
        if not isinstance(raw, dict):
            raise ValueError(f"取代基 {name} 的条目必须是对象")
        data[str(name)] = {
            "hetero": bool(raw.get("hetero", False)),
            "ring": bool(raw.get("ring", False)),
            "smiles": str(raw.get("smiles", "")),
        }
    return data


def match_substituent(text: str) -> dict | None:
    """在文本中找取代基：先整体精确（忽略大小写），再取最长子串。"""
    s = normalize_label_text(text)
    if not s:
        return None
    if s in SUBSTITUENTS:
        return dict(SUBSTITUENTS[s])
    low = s.lower()
    for name in sorted(SUBSTITUENTS, key=len, reverse=True):
        if name.lower() == low:
            return dict(SUBSTITUENTS[name])
    for name in sorted(SUBSTITUENTS, key=len, reverse=True):
        if name.lower() in low:
            return dict(SUBSTITUENTS[name])
    return None


def save_substituents(data: dict, path: str | Path) -> None:
    """把库写成 UTF-8 JSON（中文注释可读）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
