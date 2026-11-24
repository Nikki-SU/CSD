"""训练产物自动回传到 assets/——每轮训练结束自动调用，人只需 push。

红线：只回传"训练出来的能力"，绝不回传数据（原图/原图路径/文章索引）。
数据来源文件带 _local 后缀，被 gitignore，不会被收进来。

收集映射（工作区产物 → assets/）：
    training/models/structure_svc.joblib  → assets/classifier.joblib
    training/templates/templates.json     → assets/templates.json
    <root>/calibration.json               → assets/calibration.json
    training/03-style/档位_*.json          → assets/style_profiles/档位_*.json

用法：
    python -m training.publish --root <工作区>
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _is_data(path: Path) -> bool:
    """红线判定：文件名带 _local 即数据明细，跳过。"""
    return "_local" in path.name


def _copy_if_exists(src: Path, dst: Path, label: str) -> bool:
    if not src.exists() or _is_data(src):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  回传 {label}: {src.name} → {dst.relative_to(ASSETS.parent)}")
    return True


def publish(root: Path) -> dict:
    root = Path(root).resolve()
    t = root / "training"
    copied = []

    candidates = [
        (t / "models" / "structure_svc.joblib", ASSETS / "classifier.joblib", "分类器"),
        (t / "templates" / "templates.json", ASSETS / "templates.json", "字符模板"),
        (root / "calibration.json", ASSETS / "calibration.json", "校准参数"),
        (t / "calibration.json", ASSETS / "calibration.json", "校准参数"),
    ]
    for src, dst, label in candidates:
        if _copy_if_exists(src, dst, label):
            copied.append(label)

    # 风格档位：只收纯参数档位 json，跳过 _local 明细
    style_dir = t / "03-style"
    if style_dir.exists():
        for p in style_dir.glob("档位_*.json"):
            if _is_data(p):
                continue
            # 二次红线：内容里若有 members/image 字段，说明混了数据，剥掉再写
            data = json.loads(p.read_text(encoding="utf-8"))
            data.pop("members", None)
            out = ASSETS / "style_profiles" / p.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  回传 风格档位: {p.name}（已确认无原图索引）")
            copied.append(f"档位 {p.stem}")

    # 记录回传时间，便于确认是哪一轮
    (ASSETS / ".last_publish.json").write_text(
        json.dumps({"root": str(root), "items": copied}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"回传完成：{len(copied)} 项 → {ASSETS}（下一步：git commit + push）")
    return {"items": copied}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="训练产物自动回传")
    ap.add_argument("--root", required=True, help="工作区根目录")
    args = ap.parse_args()
    publish(Path(args.root))


if __name__ == "__main__":
    main()
