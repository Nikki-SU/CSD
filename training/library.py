"""训练⑥：候选筛选——本地分子库 + 拓扑索引 + 拓扑精确筛。

流程里的第一轮（排除法）：
    真古董图 → topo.py 提取 (环数, 环大小, 标签)
    → 在本地分子库中按拓扑**精确匹配**筛选
    → 指标不全匹配的候选直接排除，只剩极少数进入第二轮

关键点：
- 候选跟「化合物哪年入库」毫无关系。年代只在④渲染时用，不参与筛选。
- 在线 API（PubChem/ChEMBL）不支持按拓扑特征查询，所以必须**本地建索引**。
- 索引与 topo.py 口径一致：环数 = NumRings，环大小 = 各环原子数排序后,
  标签 = 非 C/H 原子符号集合（含取代基缩写解析后的杂原子）。
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


def topo_key_from_smiles(smiles: str):
    """从 SMILES 算拓扑三元组 (环数, 环大小tuple, 标签tuple)。算不出返回 None。"""
    try:
        from rdkit import Chem
    except ImportError as exc:
        raise RuntimeError("需要 RDKit：pip install rdkit") from exc
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    ri = mol.GetRingInfo()
    n_rings = ri.NumRings()
    sizes = tuple(sorted(len(r) for r in ri.AtomRings()))
    labels = tuple(sorted({a.GetSymbol() for a in mol.GetAtoms()
                           if a.GetSymbol() not in ("C", "H")}))
    return n_rings, sizes, labels


def key_from_image_topo(topo: dict):
    """把 topo.py 的 extract_topology 输出转成同一个 key。"""
    rings = int(topo.get("rings") or 0)
    sizes = tuple(sorted(int(s) for s in (topo.get("ring_sizes") or [])))
    labels = tuple(sorted(str(x) for x in (topo.get("labels") or [])))
    return rings, sizes, labels


@dataclass
class Candidate:
    smiles: str
    cid: str
    rings: int
    sizes: list[int]
    labels: list[str]

    def to_dict(self) -> dict:
        return {"smiles": self.smiles, "cid": self.cid, "rings": self.rings,
                "sizes": self.sizes, "labels": self.labels}


class TopoIndex:
    """拓扑 → 候选分子 的倒排索引。可持久化到 json.gz。

    结构：{"by_exact": {"1|6|N,O,S": [ [smiles, cid], ... ]},
            "by_pattern": {"1|6|": [...], "1||": [...]} }
    by_pattern 用「环数 + 环大小」先粗筛（忽略标签），避免标签识别错时全灭。

    大规模库（ChEMBL 2400 万）必须限量：每个拓扑键只保留**最长的 N 个不同 SMILES**
    以外的短分子——古早文献结构式简单，保留短分子即可，不必存全部。
    """

    MAX_PER_KEY = 60  # 每个拓扑键最多保留的候选数

    def __init__(self) -> None:
        self.by_exact: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.by_pattern: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._seen_exact: dict[str, set[str]] = defaultdict(set)
        self._seen_pattern: dict[str, set[str]] = defaultdict(set)

    @staticmethod
    def _labels_key(labels) -> str:
        return ",".join(sorted(labels))

    def add(self, smiles: str, cid: str = "", topo=None) -> bool:
        topo = topo or topo_key_from_smiles(smiles)
        if topo is None:
            return False
        rings, sizes, labels = topo
        exact = f"{rings}|{','.join(map(str, sizes))}|{self._labels_key(labels)}"
        pattern = f"{rings}|{','.join(map(str, sizes))}|"
        added = False
        if smiles not in self._seen_exact[exact] and len(self.by_exact[exact]) < self.MAX_PER_KEY:
            self._seen_exact[exact].add(smiles)
            self.by_exact[exact].append((smiles, cid))
            added = True
        if smiles not in self._seen_pattern[pattern] and len(self.by_pattern[pattern]) < self.MAX_PER_KEY * 2:
            self._seen_pattern[pattern].add(smiles)
            self.by_pattern[pattern].append((smiles, cid))
            added = True
        return added

    def build_from_smiles_file(self, path: str | Path, limit: int = 0) -> int:
        """从 'smiles<tab>cid'（可 .gz）文件建索引。limit=0 表示不限条数。返回入索引条数。"""
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        n = 0
        with opener(path, "rt", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                smi = parts[0].strip()
                cid = parts[1].strip() if len(parts) > 1 else ""
                if smi and self.add(smi, cid):
                    n += 1
                    if limit and n >= limit:
                        break
        return n

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"by_exact": {k: v for k, v in self.by_exact.items()},
                   "by_pattern": {k: v for k, v in self.by_pattern.items()}}
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path) -> "TopoIndex":
        path = Path(path)
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        idx = cls()
        idx.by_exact = defaultdict(list, {k: [tuple(x) for x in v] for k, v in payload.get("by_exact", {}).items()})
        idx.by_pattern = defaultdict(list, {k: [tuple(x) for x in v] for k, v in payload.get("by_pattern", {}).items()})
        # 恢复去重集合，便于之后追加
        for k, v in idx.by_exact.items():
            idx._seen_exact[k] = {x[0] for x in v}
        for k, v in idx.by_pattern.items():
            idx._seen_pattern[k] = {x[0] for x in v}
        return idx

    def query(self, image_topo: dict, limit: int = 200) -> list[Candidate]:
        """按图拓扑筛候选：先精确匹配（全指标一致），不足再用环数+环大小粗匹配。"""
        rings, sizes, labels = key_from_image_topo(image_topo)
        exact = f"{rings}|{','.join(map(str, sizes))}|{self._labels_key(labels)}"
        pattern = f"{rings}|{','.join(map(str, sizes))}|"

        out: list[Candidate] = []
        seen: set[str] = set()
        for smi, cid in self.by_exact.get(exact, [])[:limit]:
            if smi in seen:
                continue
            seen.add(smi)
            out.append(Candidate(smi, cid, rings, list(sizes), list(labels)))
        if len(out) < 3:  # 标签识别未必准，退回忽略标签的一档
            for smi, cid in self.by_pattern.get(pattern, [])[:limit]:
                if smi in seen:
                    continue
                seen.add(smi)
                t = topo_key_from_smiles(smi) or (rings, sizes, ())
                out.append(Candidate(smi, cid, t[0], list(t[1]), list(t[2])))
        # 同拓扑下优先短分子：古早文献的结构式普遍简单，长肽链/大分子几乎不是候选，
        # 但又不能直接砍掉（同拓扑的复杂分子也可能对），所以只做排序偏好不删。
        out.sort(key=lambda c: len(c.smiles))
        return out[:limit]


def build_index_cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="从 SMILES 合集建拓扑索引")
    ap.add_argument("--smiles", required=True, help="smiles<tab>cid 文件（可 .gz）")
    ap.add_argument("--out", required=True, help="输出索引 json.gz")
    args = ap.parse_args(argv)
    idx = TopoIndex()
    n = idx.build_from_smiles_file(args.smiles)
    idx.save(args.out)
    print(f"入索引 {n} 条 → {args.out}；精确键 {len(idx.by_exact)} 个")
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python -m training.library build --smiles <file> --out <index.json.gz>")
        sys.exit(2)
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "build":
        sys.exit(build_index_cli(rest))
    print(f"未知命令: {cmd}")
    sys.exit(2)


if __name__ == "__main__":
    main()
