"""取代基拓扑增量库：识别到某个图上缩写后，拓扑指标怎么变。

与 training/substituents.py 的分工（不覆盖、不混用）：
  - substituents.py 管"风格渲染/文字匹配"：字段 hetero/ring/smiles
  - 本库管"拓扑指标增量"：识别到缩写 → 六个存在性指标各自怎么变

用户口径（2026-11-26）：
  - 取代基库不是跨时代归一化，同一个符号恒代表同一含义。
  - 只收"图和字对不上"的缩写（Me/Ph/SO3H...）；显式 CH3 所见即所得不进库。
  - 取代基是压缩包(ZIP)：图上写 Me，实际是 CH3；不解压就会漏拓扑指标。
  - 输出的是存在性层面的改变，不是精确计数（对齐"只判有无"原则）。

六个指标（与 layer1_graph.py 一致）：
  has_ring, has_multi_ring, has_fused_fragment, has_disconnected_fragment,
  small_ring(3/4), big_ring(>=7), heteroatoms(类型)
  中环(5/6) 靠排除法，不直接给。

每条规则字段：
  notation      图上写法
  expanded      展开代表
  ring_sizes    展开带来的环大小列表（Ph→[6]，非连通环）
  hetero        展开带来的杂原子类型 set（N/O/S/P/卤素/Si...）
  adds_ring     是否新增环 → 触发 has_ring
  ring_conn     新环的连接方式：'isolated'(非连通,自身成一片) / 'none'
                —— 自身单环缩写都算自身一片；不可能与主环稠合（距离上连不上）
  注：一个缩写自身带 ≥2 环且共享原子(如萘系缩写)才触发 fused，本库暂无此类。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Delta:
    """一个取代基对拓扑指标的增量。"""
    notation: str
    expanded: str
    ring_sizes: tuple[int, ...] = ()
    hetero: tuple[str, ...] = ()
    adds_ring: bool = False
    # 缩写自身带来的环是否彼此连成一片（≥2 环且共享原子才可能 fused）
    self_fused: bool = False
    # 出处：wiki=ChemInform/Wikipedia 伪元素表；html=有机化学教材；chemist=常见化学常识
    source: str = ""

    @property
    def contributes_multi(self) -> bool:
        """这个展开式自身是否贡献"多环"（≥2 个环）。"""
        return len(self.ring_sizes) >= 2

    @property
    def contributes_disconnected(self) -> bool:
        """这个展开式自身是否贡献"非稠环片段"（≥2 个彼此不连通的环系）。"""
        # 单环缩写接到主结构上：它自己是一片环系。若主结构已有环系，则整体
        # 变成 ≥2 个环系 → 非稠环片段。这个判定在合成层做（要看主结构）。
        # 这里只标记"该缩写自带一个独立环系"。
        return len(self.ring_sizes) == 1


def _d(notation, expanded, ring_sizes=(), hetero=(), self_fused=False, source="wiki"):
    return Delta(
        notation=notation,
        expanded=expanded,
        ring_sizes=tuple(ring_sizes),
        hetero=tuple(sorted(set(hetero))),
        adds_ring=bool(ring_sizes),
        self_fused=self_fused,
        source=source,
    )


# 只收"图和字对不上"的缩写。显式 CH3/C2H5 等所见即所得，不进库。
# 出处：
#   wiki    = Wikipedia "Skeletal formula" + Wikiwand "Chemical symbol" 的伪元素表
#   cheminfo= Wiley《ChemInform》官方缩写表（Abbreviations used in ChemInform）
#   common  = 有机化学通用官能团/保护基写法（教材常见，未逐条引上表）
LIBRARY: dict[str, Delta] = {d.notation: d for d in [
    # —— 烷基 / 通用基（无环、无杂原子）—— wiki
    _d("Me",   "CH3",          source="wiki"),
    _d("Et",   "C2H5",         source="wiki"),
    _d("Pr",   "C3H7",         source="wiki"),
    _d("n-Pr", "CH2CH2CH3",    source="wiki"),
    _d("i-Pr", "CH(CH3)2",     source="wiki"),
    _d("Bu",   "C4H9",         source="wiki"),
    _d("n-Bu", "CH2CH2CH2CH3", source="wiki"),
    _d("i-Bu", "CH2CH(CH3)2",  source="wiki"),
    _d("s-Bu", "CH(CH3)CH2CH3",source="wiki"),
    _d("t-Bu", "C(CH3)3",      source="wiki"),
    _d("Pn",   "C5H11",        source="wiki"),
    _d("Am",   "C5H11",        source="wiki"),
    _d("Hx",   "C6H13",        source="ipfs"),
    _d("Hp",   "C7H15",        source="ipfs"),
    _d("Np",   "CH2C(CH3)3",   source="wiki"),          # new=新戊基；有机金属里也指 neophyl
    _d("Neo",  "CH2C(CH3)3",   source="wiki"),
    _d("Nph",  "C(CH3)2C6H5",  source="wiki"),          # neophyl，带苯环
    _d("Ad",   "1-金刚烷基",    source="wiki"),
    _d("Vi",   "CH=CH2",       source="wiki"),
    _d("All",  "CH2CH=CH2",    source="wiki"),
    _d("R",    "通式烷基",      source="wiki"),
    _d("R'",   "通式烷基(变体1)", source="common"),
    _d("R''",  "通式烷基(变体2)", source="common"),
    _d("Alk",  "通式烷基",      source="wiki"),
    _d("Het",  "通式杂芳基",    source="wiki", hetero=["N", "O", "S"]),
    _d("E",    "通式亲电基",    source="wiki"),
    _d("Nu",   "通式亲核基",    source="wiki"),
    _d("Ar",   "通式芳基",      source="wiki"),
    _d("Alk",  "通式烷基",      source="ipfs"),
    _d("X",    "通式卤素",      source="wiki", hetero=["F", "Cl", "Br", "I"]),
    _d("D",    "氘(2H)",        source="ipfs"),
    _d("T",    "氚(3H)",        source="ipfs"),

    # —— 芳香基（带非连通环）—— wiki
    _d("Ph",  "C6H5",          ring_sizes=[6], source="wiki"),
    _d("Φ",   "C6H5",          ring_sizes=[6], source="wiki"),
    _d("Tol", "CH3C6H4",       ring_sizes=[6], source="wiki"),
    _d("Mes", "(CH3)3C6H2",    ring_sizes=[6], source="wiki"),
    _d("Cp",  "C5H5",          ring_sizes=[5], source="wiki"),
    _d("Cp*", "C5(CH3)5",      ring_sizes=[5], source="wiki"),
    _d("Cyp", "C5H9",          ring_sizes=[5], source="wiki"),
    _d("Cy",  "C6H11",         ring_sizes=[6], source="wiki"),
    _d("Chx", "C6H11",         ring_sizes=[6], source="ipfs"),
    _d("Bn",  "CH2C6H5",       ring_sizes=[6], source="wiki"),
    _d("Bzl", "CH2C6H5",       ring_sizes=[6], source="ipfs"),
    _d("Tr",  "C(C6H5)3",      ring_sizes=[6, 6, 6], source="wiki"),
    _d("Trt", "C(C6H5)3",      ring_sizes=[6, 6, 6], source="wiki"),
    _d("φ",   "C6H5",          ring_sizes=[6], source="wiki"),
    _d("An",  "p-CH3OC6H4",   ring_sizes=[6], hetero=["O"], source="wiki"),
    _d("Dipp","2,6-(iPr)2C6H3", ring_sizes=[6], source="wiki"),
    _d("Is",  "2,4,6-(iPr)3C6H2", ring_sizes=[6], source="wiki"),
    _d("Tipp","2,4,6-(iPr)3C6H2", ring_sizes=[6], source="wiki"),

    # —— 酰基 / 含氧官能团（无环）—— cheminfo / common
    _d("Ac",   "COCH3",        hetero=["O"], source="cheminfo"),
    _d("Bz",   "COC6H5",       ring_sizes=[6], hetero=["O"], source="cheminfo"),
    _d("Piv",  "COC(CH3)3",    hetero=["O"], source="wiki"),
    _d("CHO",  "CHO",          hetero=["O"], source="common"),
    _d("CO2H", "COOH",         hetero=["O"], source="common"),
    _d("CO2R", "COOR",         hetero=["O"], source="common"),
    _d("CONH2","CONH2",        hetero=["N", "O"], source="common"),
    _d("Bt",   "1-苯并三唑基",  ring_sizes=[6], hetero=["N"], source="wiki"),
    _d("Im",   "1-咪唑基",      ring_sizes=[5], hetero=["N"], source="wiki"),
    _d("NPhth","邻苯二甲酰亚胺基", ring_sizes=[6], hetero=["N", "O"], source="wiki"),
    _d("OMe",  "OCH3",         hetero=["O"], source="cheminfo"),
    _d("OEt",  "OC2H5",        hetero=["O"], source="cheminfo"),
    _d("OH",   "OH",           hetero=["O"], source="common"),

    # —— 含氮 —— common
    _d("NH2",  "NH2",          hetero=["N"], source="common"),
    _d("NMe2", "N(CH3)2",      hetero=["N"], source="common"),
    _d("NEt2", "N(C2H5)2",     hetero=["N"], source="common"),
    _d("NHMe", "NHCH3",        hetero=["N"], source="common"),
    _d("CN",   "CN",           hetero=["N"], source="common"),
    _d("NC",   "N=C",          hetero=["N"], source="common"),
    _d("NO2",  "NO2",          hetero=["N", "O"], source="common"),
    _d("NO",   "NO",           hetero=["N", "O"], source="common"),
    _d("N3",   "N3",           hetero=["N"], source="common"),

    # —— 含硫 / 磺酰基 —— wiki / cheminfo
    _d("SO3H", "SO3H",         hetero=["S", "O"], source="common"),
    _d("SO2R", "SO2R",         hetero=["S", "O"], source="common"),
    _d("SR",   "SR",           hetero=["S"], source="common"),
    _d("Ms",   "SO2CH3",       hetero=["S", "O"], source="wiki"),
    _d("Tf",   "SO2CF3",       hetero=["S", "O", "F"], source="wiki"),
    _d("Ts",   "p-CH3C6H4SO2", ring_sizes=[6], hetero=["S", "O"], source="wiki"),
    _d("Tos",  "p-CH3C6H4SO2", ring_sizes=[6], hetero=["S", "O"], source="wiki"),
    _d("Bs",   "p-BrC6H4SO2",  ring_sizes=[6], hetero=["S", "O", "Br"], source="wiki"),
    _d("Ns",   "p-NO2C6H4SO2", ring_sizes=[6], hetero=["N", "O", "S"], source="wiki"),
    _d("Nf",   "CF3(CF2)3SO2", hetero=["F", "S", "O"], source="wiki"),
    _d("PhSO2","SO2C6H5",      ring_sizes=[6], hetero=["S", "O"], source="common"),
    # —— 离去基（含氧磺酸酯，wiki 明确列出）——
    _d("OBz",  "OCOC6H5",      ring_sizes=[6], hetero=["O"], source="wiki"),
    _d("OPiv", "OCOC(CH3)3",   hetero=["O"], source="wiki"),
    _d("OBs",  "OSO2C6H4Br",   ring_sizes=[6], hetero=["O", "S", "Br"], source="wiki"),
    _d("OMs",  "OSO2CH3",      hetero=["O", "S"], source="wiki"),
    _d("ONs",  "OSO2C6H4NO2",  ring_sizes=[6], hetero=["O", "S", "N"], source="wiki"),
    _d("OTf",  "OSO2CF3",      hetero=["O", "S", "F"], source="wiki"),
    _d("ONf",  "OSO2(CF2)3CF3", hetero=["O", "S", "F"], source="wiki"),
    _d("OTs",  "OSO2C6H4CH3",  ring_sizes=[6], hetero=["O", "S"], source="wiki"),

    # —— 含卤素 / 硅 —— common / cheminfo
    _d("CF3",  "CF3",          hetero=["F"], source="common"),
    _d("CCl3", "CCl3",         hetero=["Cl"], source="common"),
    _d("TMS",  "Si(CH3)3",     hetero=["Si"], source="cheminfo"),
    _d("Tbs",  "Si(CH3)2C(CH3)3", hetero=["Si"], source="cheminfo"),
    _d("Tes",  "Si(C2H5)3",    hetero=["Si"], source="cheminfo"),
    _d("Tips", "Si(CH(CH3)2)3", hetero=["Si"], source="cheminfo"),
    _d("Sem",  "CH2OCH2CH2Si(CH3)3", hetero=["O", "Si"], source="cheminfo"),

    # —— 保护基（cheminfo 明确列出）——
    _d("Boc",  "COOC(CH3)3",   hetero=["O"], source="cheminfo"),
    _d("Cbz",  "COOCH2C6H5",   ring_sizes=[6], hetero=["O"], source="cheminfo"),
    _d("Z",    "COOCH2C6H5",   ring_sizes=[6], hetero=["O"], source="wiki"),
    _d("Cbo",  "COOCH2C6H5",   ring_sizes=[6], hetero=["O"], source="ipfs"),
    _d("Fmoc", "COOCH2-芴",     ring_sizes=[6, 6], hetero=["O"], source="cheminfo"),
    _d("Alloc","COOCH2CH=CH2", hetero=["O"], source="common"),
    _d("Mom",  "CH2OCH3",      hetero=["O"], source="cheminfo"),
    _d("Mem",  "CH2OCH2CH2OCH3", hetero=["O"], source="cheminfo"),
    _d("EE",   "OCH(CH3)OC2H5", hetero=["O"], source="cheminfo"),
    _d("Pmb",  "p-CH3OC6H4CH2", ring_sizes=[6], hetero=["O"], source="cheminfo"),
    _d("Dmt",  "4,4'-二甲氧基三苯甲基", ring_sizes=[6, 6, 6], hetero=["O"], source="cheminfo"),
    _d("Troc", "COOCH2CCl3",   hetero=["O", "Cl"], source="cheminfo"),
    _d("PMB",  "p-CH3OC6H4CH2", ring_sizes=[6], hetero=["O"], source="wiki"),
    _d("MOM",  "CH2OCH3",      hetero=["O"], source="wiki"),
    _d("THP",  "2-四氢吡喃基",  ring_sizes=[6], hetero=["O"], source="wiki"),
    _d("TBDMS","Si(CH3)2C(CH3)3", hetero=["Si"], source="wiki"),
    _d("TBDPS","Si(C6H5)2C(CH3)3", ring_sizes=[6, 6], hetero=["Si"], source="wiki"),
]}


def delta_of(notation: str) -> Delta | None:
    """按图上写法取增量。大小写不敏感，去下标/上标数字已由调用方 normalize。"""
    if notation in LIBRARY:
        return LIBRARY[notation]
    low = notation.lower()
    for name, d in LIBRARY.items():
        if name.lower() == low:
            return d
    return None


def apply_deltas(base: dict, notations: list[str]) -> dict:
    """把一组识别到的取代基增量合成到 base 指标上（存在性 OR）。

    base 形如：
      {has_ring, has_multi_ring, has_fused_fragment,
       has_disconnected_fragment, ring_sizes:[...], heteroatoms:[...]}
    规则：
      - 每个带环缩写贡献一个独立环系 → 整体环系计数 +1
      - 存在只有 1 个环的孤立环系 → has_disconnected_fragment=True（Ph 自身即满足）
      - 环数 ≥2 → has_multi_ring=True
      - 任一环 3/4 → small_ring；任一 ≥7 → big_ring
      - 杂原子类型取并集
    """
    out = dict(base)
    ring_sizes = list(base.get("ring_sizes", []))
    hetero = set(base.get("heteroatoms", []))
    n_systems = int(base.get("n_ring_systems", 1 if ring_sizes else 0))
    # 是否存在孤立单环（非稠环片段）：Ph 自身即满足
    has_isolated = bool(base.get("has_disconnected_fragment"))

    for notation in notations:
        d = delta_of(notation)
        if d is None:
            continue
        ring_sizes.extend(d.ring_sizes)
        hetero.update(d.hetero)
        if d.ring_sizes:
            # 缩写带来的环系数：自身 fused 的算一片，其余每个环各一片
            # （如 Tr 三苯甲基 = 3 个苯环 = 3 个互不连通的环系）
            n_systems += 1 if d.self_fused else len(d.ring_sizes)
            # 非自身 fused 的单环缩写贡献一个孤立单环
            if not d.self_fused and len(d.ring_sizes) == 1:
                has_isolated = True

    out["ring_sizes"] = sorted(ring_sizes)
    out["heteroatoms"] = sorted(hetero)
    out["has_ring"] = bool(ring_sizes) or bool(base.get("has_ring"))
    out["has_multi_ring"] = len(ring_sizes) >= 2 or bool(base.get("has_multi_ring"))
    out["has_fused_fragment"] = bool(base.get("has_fused_fragment"))
    out["has_disconnected_fragment"] = has_isolated
    out["n_ring_systems"] = n_systems
    any_small = any(3 <= s <= 4 for s in ring_sizes)
    any_big = any(s >= 7 for s in ring_sizes)
    out["small_ring"] = any_small or bool(base.get("small_ring"))
    out["big_ring"] = any_big or bool(base.get("big_ring"))
    return out


if __name__ == "__main__":
    print(f"取代基拓扑增量库：{len(LIBRARY)} 条")
    for name in ("Me", "Ph", "SO3H", "PhSO2", "NO2", "Bn"):
        d = delta_of(name)
        print(f"  {name:<8} → {d.expanded:<14} 环={list(d.ring_sizes)} "
              f"杂原子={list(d.hetero)} 多环={d.contributes_multi}")

    base = {"ring_sizes": [], "heteroatoms": [], "n_ring_systems": 0,
            "has_ring": False, "has_multi_ring": False,
            "has_fused_fragment": False, "has_disconnected_fragment": False}
    r = apply_deltas(base, ["Ph", "NO2"])
    print("\n示例：图上只有 Ph + NO2（主结构无环）")
    print(f"  → 环={r['ring_sizes']} 杂原子={r['heteroatoms']} "
          f"多环={r['has_multi_ring']} 非稠环片段={r['has_disconnected_fragment']}")
