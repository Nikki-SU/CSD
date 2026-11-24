"""训练⑥a：从 ChEMBL 下载 SMILES 建本地拓扑索引。

为什么是 ChEMBL 而不是 PubChem：
- PubChem 在 FTP/API 上都从中国网络常超时（实测 code=000）
- ChEMBL（EBI，欧洲）可达（实测 200，1.7s），且提供 REST API 分页拉取
所以来源：ChEMBL REST API（https://www.ebi.ac.uk/chembl/api/data/molecule.json）

用法：
    python -m training.build_library --limit 2000 --out data/library/smiles.tsv
    python -m training.build_library --limit 0        # 0 = 全部（很大，慎用）
再建索引：
    python -m training.library build --smiles <smiles.tsv> --out <index.json.gz>
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

API = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
PAGE = 100  # ChEMBL 单页上限较大，100 稳妥


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
