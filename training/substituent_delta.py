"""取代基拓扑增幅：从 substituents 库查 SMILES → RDKit 真算指标。

用户 2026-11-26："去库里查 SMILES，再把 SMILES 给 RDKit，用 RDKit 把指标增幅算出来。"
不再手填 ring_sizes/hetero。指标口径与 layer1_graph 一致。
"""
from __future__ import annotations

try:
    from .substituents import SUBSTITUENTS
    from .layer1_graph import truth_from_rdkit, ring_systems
except ImportError:
    from substituents import SUBSTITUENTS
    from layer1_graph import truth_from_rdkit, ring_systems

from rdkit import Chem


def delta_from_smiles(smiles: str) -> dict | None:
    """从 SMILES 用 RDKit 算取代基自身的六个拓扑指标。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    t = truth_from_rdkit(mol)
    hetero = sorted({a.GetSymbol() for a in mol.GetAtoms()
                     if a.GetSymbol() not in ("C", "H", "*")})
    rings = [set(r) for r in mol.GetRingInfo().AtomRings()]
    systems = ring_systems(rings) if rings else []
    sizes = t["ring_sizes"]
    return {
        "smiles": smiles,
        "ring_sizes": sizes,
        "hetero": hetero,
        "has_ring": len(rings) > 0,
        "has_multi_ring": len(rings) >= 2,
        "has_fused_fragment": any(len(s) >= 2 for s in systems),
        # 非稠环片段 = 存在孤立单环（Ph 自身即满足）
        "has_disconnected_fragment": any(len(s) == 1 for s in systems),
        "small_ring": any(3 <= s <= 4 for s in sizes),
        "big_ring": any(s >= 7 for s in sizes),
        "n_v": mol.GetNumAtoms(), "n_e": mol.GetNumBonds(),
    }


def delta_of(notation: str) -> dict | None:
    """按缩写查库取 SMILES，再用 RDKit 算增幅。"""
    e = SUBSTITUENTS.get(notation)
    return delta_from_smiles(e["smiles"]) if e else None


if __name__ == "__main__":
    print(f"{'缩写':<8} {'SMILES':<20} {'环':<12} {'杂原子':<12} {'多稠碎':<6}")
    for name, e in SUBSTITUENTS.items():
        d = delta_from_smiles(e["smiles"])
        if not d:
            print(f"{name:<8} SMILES 无法解析")
            continue
        flags = (int(d["has_multi_ring"]), int(d["has_fused_fragment"]),
                 int(d["has_disconnected_fragment"]))
        print(f"{name:<8} {e['smiles']:<20} {str(d['ring_sizes']):<12} "
              f"{','.join(d['hetero']):<12} {flags[0]}{flags[1]}{flags[2]}")
