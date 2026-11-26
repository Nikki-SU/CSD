"""第一件事：确保图层算法在 RDKit 好图上 100% 正确。

真值 = RDKit 分子对象本身（原子=顶点、键=边），这是纯 Graph，不碰图片。
算法 = networkx 在这个 Graph 上算拓扑指标。
两者独立：真值从 RDKit 的 RingInfo 取，算法从邻接关系算。

拓扑指标（用户 2026-11-26 口径）：
  1. 有没有环
  2. 小环(3/4) / 大环(>=7) 的存在性；都没有则中环(5/6) 靠排除法
  3. 多环：环总数 >= 2
  4. 稠环片段 / 非稠环片段：按「环系」判，两者可并存，不是互斥二选一
     - 环系 = 环与环共享至少 1 个原子就连成一片（不管共享边还是共享点）
     - 稠环片段 = 存在某个环系含 >= 2 个环
     - 非稠环片段 = 存在 >= 2 个环系（环分散在多个片段，如多个苯基）
  5. 顶点数、边数
"""
from __future__ import annotations

from rdkit import Chem
import networkx as nx


MOLECULES = [
    ("丁烷", "CCCC"),
    ("乙醇", "CCO"),
    ("环丙烷", "C1CC1"),
    ("环丁烷", "C1CCC1"),
    ("环戊烷", "C1CCCC1"),
    ("呋喃", "c1ccoc1"),
    ("苯", "c1ccccc1"),
    ("环己烷", "C1CCCCC1"),
    ("环庚烷", "C1CCCCCC1"),
    ("环辛烷", "C1CCCCCCC1"),
    ("萘(一片2环)", "c1ccc2ccccc2c1"),
    ("茚(稠环5+6)", "c1ccc2c(c1)CC=C2"),
    ("联苯(两环系)", "c1ccccc1-c1ccccc1"),
    ("环己基苯(两环系)", "C1CCCCC1-c1ccccc1"),
    ("2-苯基萘(两环系,一片2环)", "c1ccc2ccccc2c1-c1ccccc1"),
    ("螺[2.2]戊烷(共享1原子)", "C1CC12CC2"),
    ("两个独立苯(不连通)", "c1ccccc1.c1ccccc1"),
]


FIELDS = [
    "has_ring", "has_multi_ring", "has_fused_fragment",
    "has_disconnected_fragment", "n_ring_systems",
    "ring_sizes", "n_v", "n_e",
]


def graph_of(mol):
    """从 RDKit 分子对象建 Graph：原子=节点，键=边。"""
    G = nx.Graph()
    G.add_nodes_from(range(mol.GetNumAtoms()))
    for b in mol.GetBonds():
        G.add_edge(b.GetBeginAtomIdx(), b.GetEndAtomIdx())
    return G


def ring_systems(cycles):
    """把环按「共享至少 1 个原子」合并成环系。

    返回环系列表，每项是该环系里的环集合。
    这是用户口径里的「连通区域」：不是整个分子的原子连通分量，
    而是环与环通过共享原子连成的那一片。
    """
    n = len(cycles)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    sets = [set(c) for c in cycles]
    for i in range(n):
        for j in range(i + 1, n):
            if sets[i] & sets[j]:
                union(i, j)
    groups = {}
    for i, c in enumerate(cycles):
        groups.setdefault(find(i), []).append(c)
    return list(groups.values())


def topology_of(cycles):
    """三个独立存在性指标 + 环系统计。真值侧和算法侧共用这层拓扑逻辑。"""
    systems = ring_systems(cycles)
    return {
        "has_ring": len(cycles) > 0,
        "has_multi_ring": len(cycles) >= 2,
        "has_fused_fragment": any(len(s) >= 2 for s in systems),
        # 非稠环片段 = 存在某一片环系只有 1 个环（孤立单环，如一个苯基）。
        # 不是"整图有≥2个环系"——那是多环的意思，跟稠不稠无关。
        "has_disconnected_fragment": any(len(s) == 1 for s in systems),
        "n_ring_systems": len(systems),
    }


def truth_from_rdkit(mol):
    """真值：环从 RDKit 的 RingInfo 取，不用 networkx 的 cycle_basis。"""
    ri = mol.GetRingInfo()
    rings = [set(r) for r in ri.AtomRings()]
    t = topology_of(rings)
    t.update({
        "ring_sizes": sorted(len(r) for r in rings),
        "n_rings": len(rings),
        "n_v": mol.GetNumAtoms(),
        "n_e": mol.GetNumBonds(),
    })
    return t


def our_algorithm(G):
    """我们的算法：环从 networkx 的 cycle_basis 取，路径与 RDKit 独立。"""
    cycles = list(nx.cycle_basis(G))
    a = topology_of(cycles)
    a.update({
        "ring_sizes": sorted(len(c) for c in cycles),
        "n_rings": len(cycles),
        "n_v": G.number_of_nodes(),
        "n_e": G.number_of_edges(),
    })
    sizes = a["ring_sizes"]
    if not a["has_ring"]:
        a["kind"] = "none"
    elif any(s >= 7 for s in sizes):
        a["kind"] = "big"
    elif any(s <= 4 for s in sizes):
        a["kind"] = "small"
    else:
        a["kind"] = "mid"
    return a


def main():
    hdr = (f"{'分子':<26} {'环':<12} {'多':<3} {'稠':<3} {'碎':<3} "
           f"{'环系':<4} {'V/E':<8} 判定")
    print(hdr)
    ok_all = True
    for name, smi in MOLECULES:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            print(f"{name:<26} SMILES 无效: {smi}")
            ok_all = False
            continue
        G = graph_of(mol)
        t = truth_from_rdkit(mol)
        a = our_algorithm(G)
        diff = [f for f in FIELDS if t[f] != a[f]]
        ok = not diff
        ok_all = ok_all and ok
        flags = ("1" if a["has_multi_ring"] else "0",
                 "1" if a["has_fused_fragment"] else "0",
                 "1" if a["has_disconnected_fragment"] else "0")
        print(f"{name:<26} {str(a['ring_sizes']):<12} {flags[0]:<3} {flags[1]:<3} "
              f"{flags[2]:<3} {a['n_ring_systems']:<4} "
              f"{a['n_v']}/{a['n_e']:<6} {'✓' if ok else '✗ ' + str(diff)}")
    print("\n全部正确" if ok_all else "\n有错误，必须修算法")


if __name__ == "__main__":
    main()
