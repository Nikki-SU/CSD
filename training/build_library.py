"""训练⑥a：建本地 SMILES 库（两种来源）。

来源一（推荐，全量离线）：ChEMBL 官方 chemreps 文件（Tab 分隔，含 chembl_id + SMILES）
    下载：curl -L -o chembl_37_chemreps.txt.gz \\
        https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/chembl_37_chemreps.txt.gz
    转换：python -m training.ingest_chembl --src chembl_37_chemreps.txt.gz --out smiles.tsv

来源二（小批量，REST API 分页）：本文件 download()，适合先试跑
    实测：PubChem（NCBI）从中国网络超时；ChEMBL（EBI 欧洲）可达，故用 ChEMBL。

建索引（两种来源产物都一样）：
    python -m training.library build --smiles smiles.tsv --out index.json.gz
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

API = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
PAGE = 100


def _fetch(offset: int, limit: int) -> dict:
    url = f"{API}?limit={min(limit, PAGE)}&offset={offset}&only=molecule_structures"
    req = urllib.request.Request(url, headers={"User-Agent": "CSD-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def download(limit: int, out: Path) -> int:
    """分页拉 ChEMBL 分子，写 smiles<tab>chembl_id。返回写入条数。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    offset = 0
    with out.open("w", encoding="utf-8") as fh:
        while limit == 0 or written < limit:
            try:
                page = _fetch(offset, PAGE)
            except Exception as exc:
                print(f"  分页 {offset} 失败: {type(exc).__name__}: {str(exc)[:100]}", flush=True)
                break
            mols = page.get("molecules") or []
            if not mols:
                break
            for m in mols:
                struct = m.get("molecule_structures") or {}
                smi = struct.get("canonical_smiles")
                cid = m.get("molecule_chembl_id") or ""
                if smi:
                    fh.write(f"{smi}\t{cid}\n")
                    written += 1
            offset += len(mols)
            print(f"  已拉 {written} 条（offset {offset}）", flush=True)
            if len(mols) < PAGE:
                break
            time.sleep(0.3)  # 温和限速
    return written


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="从 ChEMBL 下载 SMILES 合集")
    ap.add_argument("--limit", type=int, default=2000, help="0 = 全部（极大）")
    ap.add_argument("--out", default="data/library/smiles.tsv")
    args = ap.parse_args()
    n = download(args.limit, Path(args.out))
    print(f"完成：{n} 条 SMILES → {args.out}")
    if n == 0:
        print("[ERROR] 一条都没拉到。检查到 www.ebi.ac.uk 的网络连通性。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
