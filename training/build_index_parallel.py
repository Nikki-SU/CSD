"""训练⑥b：并行建全量拓扑索引。

单进程 RDKit 逐个解析 289 万 SMILES 太慢（>几小时）。改成多进程分块：
把 smiles.tsv 切成 N 块，每个进程算自己那块的拓扑键，主进程合并。
每键限额去重在合并阶段做。

用法：
    python -m training.build_index_parallel --smiles smiles_full.tsv \\
        --out index.json.gz --workers 8
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path


def _topo_batch(rows: list[tuple[str, str]], cap: int = 60) -> dict[str, list[tuple[str, str]]]:
    """算一批 SMILES 的拓扑键，返回 {key: [(smiles,cid)...]}。只按精确键归组。"""
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")   # 关掉价态/环警告刷屏
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for smi, cid in rows:
        try:
            mol = Chem.MolFromSmiles(smi)
        except Exception:
            continue
        if mol is None:
            continue
        ri = mol.GetRingInfo()
        rings = ri.NumRings()
        sizes = sorted(len(r) for r in ri.AtomRings())
        labels = sorted({a.GetSymbol() for a in mol.GetAtoms() if a.GetSymbol() not in ("C", "H")})
        key = f"{rings}|{','.join(map(str, sizes))}|{','.join(labels)}"
        if len(out[key]) < cap:
            out[key].append((smi, cid))
    return dict(out)


def _chunks(path: Path, size: int):
    buf: list[tuple[str, str]] = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            buf.append((parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""))
            if len(buf) >= size:
                yield buf
                buf = []
    if buf:
        yield buf


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--smiles", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    ap.add_argument("--cap", type=int, default=60, help="每键每块最多保留候选数")
    ap.add_argument("--chunk", type=int, default=20000)
    args = ap.parse_args()

    src = Path(args.smiles)
    if not src.exists():
        print(f"[ERROR] 找不到 {src}", file=sys.stderr)
        sys.exit(1)

    merged: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total = 0
    from functools import partial
    batch = partial(_topo_batch, cap=args.cap)
    with Pool(args.workers) as pool:
        for i, part in enumerate(pool.imap(batch, _chunks(src, args.chunk))):
            total += 1
            for key, items in part.items():
                if len(merged[key]) >= args.cap:
                    continue
                merged[key].extend(items[: args.cap - len(merged[key])])
            if total % 20 == 0:
                print(f"  已合并块 {total}，拓扑键 {len(merged)}", flush=True)

    # 同时建 pattern 索引（环数+环大小，忽略标签）
    by_pattern: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, items in merged.items():
        rings_sizes = key.rsplit("|", 1)[0] + "|"
        if len(by_pattern[rings_sizes]) < args.cap * 2:
            by_pattern[rings_sizes].extend(items[: args.cap * 2 - len(by_pattern[rings_sizes])])

    payload = {"by_exact": merged, "by_pattern": by_pattern}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if str(out).endswith(".gz") else open
    with opener(out, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    print(f"完成：拓扑精确键 {len(merged)}，pattern 键 {len(by_pattern)} → {out}")


if __name__ == "__main__":
    main()
