"""训练⑥a：把 ChEMBL 全量 SMILES 合集转成建索引用的小格式。

两种来源都支持：
1. REST API 分页（training/build_library_api 方式，见 build_library.py 旧路）
2. **全量离线文件** chembl_XX_chemreps.txt.gz（官方导出，Tab 分隔）

本模块做第 2 种：从 chemreps 的 TSV 里抽 chembl_id + canonical_smiles，
写成 `smiles<TAB>chembl_id` 供 training.library 建拓扑索引。

chemreps 列（官方 README）：chembl_id, smiles, inchi, inchi_key 等（表头在首行）

用法：
    python -m training.ingest_chembl --src data/library/chembl_37_chemreps.txt.gz \
        --out data/library/smiles.tsv
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path


def ingest(src: Path, out: Path) -> tuple[int, int]:
    """返回 (总行数, 有效 SMILES 数)。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    total = valid = 0
    opener = gzip.open if src.suffix == ".gz" else open
    with opener(src, "rt", encoding="utf-8", errors="ignore") as fh, \
            out.open("w", encoding="utf-8") as w:
        header = fh.readline()
        cols = [c.strip().lower() for c in header.rstrip("\n").split("\t")]
        # 定位列：官方是 chembl_id 第0列、smiles 第1列，但仍按表头找，稳妥
        try:
            id_i = cols.index("chembl_id")
        except ValueError:
            id_i = 0
        try:
            smi_i = cols.index("canonical_smiles") if "canonical_smiles" in cols else \
                next(i for i, c in enumerate(cols) if "smiles" in c)
        except (ValueError, StopIteration):
            smi_i = 1
        print(f"  列索引：chembl_id={id_i}, smiles={smi_i}（表头 {cols[:4]}）", flush=True)

        for line in fh:
            total += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= max(id_i, smi_i):
                continue
            smi = parts[smi_i].strip()
            cid = parts[id_i].strip()
            if smi:
                w.write(f"{smi}\t{cid}\n")
                valid += 1
            if total % 1_000_000 == 0:
                print(f"  已处理 {total} 行，有效 {valid}", flush=True)
    return total, valid


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="ChEMBL chemreps → smiles.tsv")
    ap.add_argument("--src", required=True, help="chembl_XX_chemreps.txt(.gz)")
    ap.add_argument("--out", default="data/library/smiles.tsv")
    args = ap.parse_args()
    src = Path(args.src)
    if not src.exists():
        print(f"[ERROR] 源文件不存在：{src}", file=sys.stderr)
        sys.exit(1)
    total, valid = ingest(src, Path(args.out))
    print(f"完成：{total} 行 → {valid} 条有效 SMILES → {args.out}")


if __name__ == "__main__":
    main()
