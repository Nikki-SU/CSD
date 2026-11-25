"""反向验证：同一个分子，用不同画法渲染 → 分数必须拉开。

红线有两面：
    正面（已过 verify_style_invariance）：同画法不同内容 → 分数稳定
    反面（本脚本）：  同内容不同画法 → 分数必须显著不同
两面都过，才证明特征量的是"画法"而不是"内容"或别的杂物。

三种画法用 RDKit 参数模拟：
    dense     把所有碳的 H 显式写出来（Chem.AddHs + 显式 C 标签）
    hybrid    只给部分原子加显式标签
    skeletal  标准键线式（碳原子隐式）

用法：python -m training.verify_style_separation
"""
from __future__ import annotations

from pathlib import Path

from .notation import extract_notation
from .notation_clf import density_score

MOLS = ["c1ccccc1", "CCCCCC", "c1ccc(cc1)C(=O)O", "C1CCCCC1"]


def _render(smiles: str, mode: str, out: Path) -> bool:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem.Draw import rdMolDraw2D

    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return False

    d = rdMolDraw2D.MolDraw2DCairo(420, 320)
    o = d.drawOptions()
    o.useBWAtomPalette()
    o.clearBackground = True
    o.addStereoAnnotation = False

    if mode == "dense":
        # 早期"所有碳都画"：每个碳顶点直接写 CH3 / CH2 / CH / C（这就是 JACS 1900
        # 那批图的真实画法），并加大键长让标签放得下，避免字压线。
        for a in m.GetAtoms():
            if a.GetSymbol() != "C":
                continue
            nh = a.GetTotalNumHs()
            a.SetProp("atomLabel", f"CH{nh}" if nh else "C")
        AllChem.Compute2DCoords(m)
        o.bondLineWidth = 1.0
        o.baseFontSize = 13
        o.fixedBondLength = 58          # 加大键长，给字腾地方
        d.DrawMolecule(m)
        for a in m.GetAtoms():     # 画完清掉，避免污染后续复用
            if a.HasProp("atomLabel"):
                a.ClearProp("atomLabel")
    elif mode == "hybrid":
        # 混合式：骨架键线，甲基显式写出（Me/CH3），其余碳隐式
        o.bondLineWidth = 1.2
        o.baseFontSize = 14
        o.explicitMethyl = True
        o.fixedBondLength = 48
        AllChem.Compute2DCoords(m)
        d.DrawMolecule(m)
    else:
        o.bondLineWidth = 1.2
        o.baseFontSize = 14
        o.fixedBondLength = 48
        AllChem.Compute2DCoords(m)
        d.DrawMolecule(m)

    d.FinishDrawing()
    out.write_bytes(d.GetDrawingText())
    return True


def main() -> None:
    out_dir = Path("F:/2026-11-22-10-10-52/.workbuddy/sep_ascii")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("同一个分子换画法 → 分数应显著上升（skeletal < hybrid < dense）\n")
    print(f"{'分子':>22} {'skeletal':>9} {'hybrid':>9} {'dense':>9}  {'dense-sk':>9}")
    gaps = []
    for i, smi in enumerate(MOLS):
        got = {}
        for mode in ("skeletal", "hybrid", "dense"):
            p = out_dir / f"m{i}_{mode}.png"
            if not _render(smi, mode, p):
                continue
            got[mode] = density_score(extract_notation(p))
        if len(got) < 3:
            print(f"{smi:>22} 渲染不全")
            continue
        gap = got["dense"] - got["skeletal"]
        gaps.append(gap)
        print(f"{smi:>22} {got['skeletal']:>9.3f} {got['hybrid']:>9.3f} {got['dense']:>9.3f}  {gap:>9.3f}")

    print()
    if gaps:
        import statistics
        mean_gap = statistics.mean(gaps)
        print(f"平均分离度 {mean_gap:.3f} → " +
              ("通过：不同画法被明确区分" if mean_gap > 0.25 else "未通过：画法区分不足"))


if __name__ == "__main__":
    main()
