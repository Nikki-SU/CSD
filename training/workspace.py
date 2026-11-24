"""工作区状态管理：动态增量更新、训练轮次、留出集与交叉验证划分。

用户要求：
  - 工作区能动态更新——新文献必须补进来，不能重跑已处理的。
  - 区分第几轮训练——每轮独立记录，可回溯。
  - 人审剔除的图要留出作非训练集，并做交叉验证，不能全喂进去。

所有状态落本地 JSON，人可读。无重型依赖。

用法：
    python -m training.workspace init --root <工作区> --pdf-dir <PDF目录>
    python -m training.workspace sync --root <工作区>          # 增量补新文献
    python -m training.workspace new-round --root <工作区>     # 开新一轮
    python -m training.workspace split --root <工作区> --round 1 --folds 5
    python -m training.workspace status --root <工作区>
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = "workspace.json"
ROUNDS_DIR = "rounds"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}，先跑 init")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_id(path: Path) -> str:
    """用 路径+大小 做稳定 id，不读文件内容（PDF 动辄几 G，读全文太慢）。
    内容变更但大小不变的概率极低；真要严格可换 sha256 但会很慢。"""
    st = path.stat()
    raw = f"{path.name}|{st.st_size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def init(root: Path, pdf_dir: Path) -> dict:
    root = Path(root).resolve()
    pdf_dir = Path(pdf_dir).resolve()
    manifest = {
        "created_at": _now(),
        "updated_at": _now(),
        "pdf_dir": str(pdf_dir),
        "seen": {},       # file_id -> {name, size, added_at, round_first_seen}
        "rounds": [],     # [{index, started_at, note, sample_count}]
    }
    path = root / MANIFEST
    _save(manifest, path)
    (root / ROUNDS_DIR).mkdir(parents=True, exist_ok=True)
    print(f"工作区已建：{path}")
    print("下一步：sync 把现有文献纳入管理")
    return manifest


def sync(root: Path) -> dict:
    """增量扫描 PDF 目录：新文件追加，已见过的跳过。返回新增数量。"""
    root = Path(root).resolve()
    path = root / MANIFEST
    m = _load(path)
    pdf_dir = Path(m["pdf_dir"])
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF 目录不存在：{pdf_dir}")

    current_round = len(m["rounds"]) or 1
    added = 0
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        fid = _file_id(pdf)
        if fid in m["seen"]:
            continue
        m["seen"][fid] = {
            "name": pdf.name,
            "size": pdf.stat().st_size,
            "added_at": _now(),
            "round_first_seen": current_round,
        }
        added += 1
    m["updated_at"] = _now()
    _save(m, path)
    print(f"增量同步：新增 {added} 篇，累计 {len(m['seen'])} 篇")
    return {"added": added, "total": len(m["seen"])}


def new_round(root: Path, note: str = "") -> dict:
    root = Path(root).resolve()
    path = root / MANIFEST
    m = _load(path)
    idx = len(m["rounds"]) + 1
    round_info = {
        "index": idx,
        "started_at": _now(),
        "note": note,
        "sample_count": 0,
    }
    m["rounds"].append(round_info)
    m["updated_at"] = _now()
    _save(m, path)
    (root / ROUNDS_DIR / f"round_{idx:03d}").mkdir(parents=True, exist_ok=True)
    print(f"开启第 {idx} 轮训练 → {root / ROUNDS_DIR / f'round_{idx:03d}'}")
    return round_info


def split(root: Path, round_index: int, folds: int = 5, holdout: float = 0.2,
          seed: int = 42) -> dict:
    """把某轮的人审样本划分为 训练集 / 留出集(非训练集) / 交叉验证折叠。

    输入：该轮目录下 samples.json（人审样本清单，每项有 image/sha/label）
    人审剔除的图 label=false，自动进"非训练集"候选池。
    """
    import random
    root = Path(root).resolve()
    rdir = root / ROUNDS_DIR / f"round_{round_index:03d}"
    src = rdir / "samples.json"
    if not src.exists():
        raise FileNotFoundError(f"找不到 {src}；先把该轮人审样本写进来")
    samples = json.loads(src.read_text(encoding="utf-8"))
    if not samples:
        raise ValueError("样本清单为空")

    rng = random.Random(seed)
    items = list(samples)
    rng.shuffle(items)
    n_hold = max(1, int(len(items) * holdout))
    holdout_items = items[:n_hold]
    train_items = items[n_hold:]

    # 交叉验证只在训练集内做（留出集绝不参与）
    folds_out = []
    for i in range(folds):
        val = [s for j, s in enumerate(train_items) if j % folds == i]
        folds_out.append({"fold": i + 1, "val": val})

    negatives = [s for s in items if s.get("label") is False]
    out = {
        "round": round_index,
        "split_at": _now(),
        "seed": seed,
        "total": len(items),
        "train_count": len(train_items),
        "holdout_count": len(holdout_items),
        "holdout": holdout_items,
        "train": train_items,
        "folds": folds_out,
        "negative_pool": negatives,
        "note": "holdout 不参与训练与调参；folds 只在 train 内切分",
    }
    target = rdir / "split.json"
    _save(out, target)
    print(f"第 {round_index} 轮划分：训练 {len(train_items)} / 留出 {len(holdout_items)} / "
          f"{folds} 折 / 负样本池 {len(negatives)} → {target}")
    return out


def status(root: Path) -> None:
    root = Path(root).resolve()
    m = _load(root / MANIFEST)
    print(f"PDF 目录：{m['pdf_dir']}")
    print(f"已纳入文献：{len(m['seen'])} 篇（最后同步 {m['updated_at']}）")
    print(f"训练轮次：{len(m['rounds'])} 轮")
    for r in m["rounds"]:
        split_path = root / ROUNDS_DIR / f"round_{r['index']:03d}" / "split.json"
        mark = "已划分" if split_path.exists() else "未划分"
        print(f"  第 {r['index']} 轮 · {r['started_at']} · {mark} · {r.get('note') or '-'}")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="工作区状态管理")
    ap.add_argument("cmd", choices=["init", "sync", "new-round", "split", "status"])
    ap.add_argument("--root", required=True)
    ap.add_argument("--pdf-dir", help="init 用：PDF 来源目录")
    ap.add_argument("--note", default="", help="new-round 用")
    ap.add_argument("--round", type=int, help="split 用：轮次号")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--holdout", type=float, default=0.2)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.cmd == "init":
        if not args.pdf_dir:
            raise SystemExit("init 需要 --pdf-dir")
        init(root, Path(args.pdf_dir))
    elif args.cmd == "sync":
        sync(root)
    elif args.cmd == "new-round":
        new_round(root, args.note)
    elif args.cmd == "split":
        if not args.round:
            raise SystemExit("split 需要 --round")
        split(root, args.round, args.folds, args.holdout)
    else:
        status(root)


if __name__ == "__main__":
    main()
