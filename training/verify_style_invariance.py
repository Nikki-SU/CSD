"""红线验证：同一画法、不同内容（环数/原子数/支链多少）→ 分数必须相近。

用户明确要求："注意不要混淆绘画风格和内容（比如是否有环是内容）"。
这个脚本就是对这条红线的**实证检验**，不是口头保证：
用 RDKit 按同一种渲染参数画不同分子（1环/2环/3环/链状/多原子），
若特征分数随内容大幅波动，说明特征泄漏了内容，必须修。

用法：python -m training.verify_style_invariance
"""
from __future__ import annotations

from pathlib import Path

from .notation import FEATURE_NAMES, extract_notation
from .notation_clf import density_score

# 同一画法下内容差异极大的分子组
GROUPS = {
    "chain_small": ["CCO", "CCCC", "CC(C)C"],
    "chain_large": ["CCCCCCCC", "CCCCCCCCCCCC", "CCCCCCCCCCCCCCCCCC"],
    "ring_one": ["c1ccccc1", "C1CCCCC1", "c1ccncc1"],
    "ring_two": ["c1ccc2ccccc2c1", "C1CC2CCC1C2"],
    "ring_three": ["c1ccc2c(c1)ccc1ccccc12", "C1CC2CC3CC1C2C3"],
    "hetero_many": ["O=C(O)c1ccccc1", "N#Cc1ccc(O)cc1", "O=S(=O)(O)c1ccccc1"],
}


def _render(smiles: str, out: Path, font: str, line_w: float, font_size: int) -> bool:
    """用固定渲染参数画图——参数完全不随分子变化，这就是"同一种画法"。"""
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw
    from rdkit.Chem.Draw import rdMolDraw2D

    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return False
    AllChem.Compute2DCoords(m)
    d = rdMolDraw2D.MolDraw2DCairo(320, 240)
    o = d.drawOptions()
    o.bondLineWidth = line_w
    o.baseFontSize = font_size
    o.addStereoAnnotation = False
    o.clearBackground = True
    o.useBWAtomPalette()          # 单色，避免颜色成为额外线索
    if font and Path(font).exists():
        o.fontFile = font
    rdMolDraw2D.PrepareAndDrawMolecule(d, m)
    d.FinishDrawing()
    out.write_bytes(d.GetDrawingText())
    return True


def main() -> None:
    # 输出到 ASCII 路径：cv2.imread 读不了含中文的路径
    out_dir = Path("F:/2026-11-22-10-10-52/.workbuddy/invariance_ascii")
    out_dir.mkdir(parents=True, exist_ok=True)
    font = r"C:\Windows\Fonts\times.ttf"

    print("同一画法（固定线宽/字号/单色），只改分子内容，看分数是否稳定：\n")
    print(f"{'组':>10} {'n':>3} {'score均值':>9} {'标准差':>7} {'极差':>7}  明细")
    worst = 0.0
    for gname, smis in GROUPS.items():
        scores = []
        detail = []
        for i, smi in enumerate(smis):
            p = out_dir / f"{gname}_{i}.png"
            if _render(smi, p, font, 1.2, 14):
                f = extract_notation(p)
                s = density_score(f)
                scores.append(s)
                detail.append(f"{s:.3f}")
        if not scores:
            print(f"{gname:>10} 渲染失败")
            continue
        import statistics
        mean = statistics.mean(scores)
        sd = statistics.pstdev(scores) if len(scores) > 1 else 0.0
        rng = max(scores) - min(scores)
        worst = max(worst, rng)
        print(f"{gname:>10} {len(scores):>3} {mean:>9.3f} {sd:>7.3f} {rng:>7.3f}  {' '.join(detail)}")

    print()
    print("判读标准：同一画法下，分数极差应远小于不同画法之间的差异（约 0.3）。")
    print(f"本次最大极差 {worst:.3f} → " +
          ("通过：内容差异没有污染风格分数" if worst < 0.15 else "未通过：特征泄漏了内容，需修"))


if __name__ == "__main__":
    main()
