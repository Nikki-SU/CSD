"""训练流程总调度：①采集→②风格→③拓扑→④渲染→⑤匹配，每步可单独调试。

数据是管道的内容物，不是管道本身。管道先立住，数据晚点到只是喂进来跑。
每一步输入输出都是本地人可读文件，随时能停在某一步看产物。

用法见 README.md。每步：python -m training.pipeline run --root <工作区> --step <步骤>
"""
from __future__ import annotations

import json
from pathlib import Path

STEPS = [
    ("detect", "①0 MolDet批量标注(baseline+攒数据)", "training/01-collect"),
    ("classify", "①a 结构式二分类", "training/01-collect"),
    ("align", "①b 文本-图对齐", "training/01-collect"),
    ("topo", "③ 拓扑指标提取", "training/02-topo"),
    ("style", "② 风格聚类定档", "training/03-style"),
    ("render", "④ 仿古渲染", "training/04-render"),
    ("match", "⑤ 匹配排序", "training/05-match"),
]


def step_dirs(root: Path) -> dict[str, Path]:
    return {key: root / rel for key, _, rel in STEPS}


def init(root: Path) -> None:
    dirs = step_dirs(root)
    for key, label, _ in STEPS:
        d = dirs[key]
        d.mkdir(parents=True, exist_ok=True)
        (d / "README.txt").write_text(f"{label}\n输入/输出都放本目录，每步可单独调试。\n", encoding="utf-8")
    extra = ["training/templates", "training/models", "training/00-pdfs"]
    for rel in extra:
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "training" / "state.json").write_text(
        json.dumps({"initialized": True, "steps": [k for k, _, _ in STEPS]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"训练管道目录已建在 {root / 'training'}")


def status(root: Path) -> None:
    dirs = step_dirs(root)
    for key, label, rel in STEPS:
        d = dirs[key]
        files = [p for p in d.iterdir() if p.is_file() and p.name != "README.txt"] if d.exists() else []
        print(f"{key:9} {label:18} {len(files):4} 文件  {'有产物' if files else '空（待数据）'}")


def _images(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")]


def run_step(root: Path, step: str) -> None:
    dirs = step_dirs(root)
    root_t = root / "training"

    if step == "detect":
        from .detect import run
        pdf_dir = root_t / "00-pdfs"
        out = root_t / "detections.json"
        if not list(pdf_dir.glob("*.pdf")):
            print(f"还没有 PDF：{pdf_dir}；先把文献放进去或跑 workspace sync")
            return
        run(pdf_dir, out)
        print(f"①0 MolDet 标注完成 → {out}（下一步：人审瀑布流，再训小模型）")

    elif step == "classify":
        from .collect import classify_images
        model = root_t / "models" / "structure_svc.joblib"
        src = dirs["classify"]
        if not model.exists():
            print(f"还没有分类器：{model}\n先用 training.collect train 训一个（见 README）")
            return
        imgs = _images(src)
        if not imgs:
            print(f"① 目录还没有图片：{src}")
            return
        result = classify_images(src, model)
        out = root_t / "classify_result.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        yes = sum(1 for v in result.values() if v.get("is_structure"))
        print(f"①a 二分类：{len(imgs)} 张，判为结构式 {yes} 张 → {out}")

    elif step == "align":
        from .collect import align_text_figures
        mineru = root_t / "00-pdfs"
        out = dirs["align"] / "align.json"
        items = align_text_figures(mineru)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        with_label = sum(1 for x in items if x.get("label"))
        print(f"①b 文本-图对齐：{len(items)} 张图，{with_label} 张有编号标记 → {out}")

    elif step == "topo":
        from .topo import extract_topology, evaluate
        src = dirs["collect"]
        out = dirs["topo"]
        templates = root_t / "templates" / "templates.json"
        imgs = _images(src)
        if not imgs:
            print(f"① 目录还没有图片：{src}")
            return
        for p in imgs:
            r = extract_topology(p, templates if templates.exists() else None)
            data = r if isinstance(r, dict) else json.loads(r.to_json())
            (out / (p.stem + ".topo.json")).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {p.name}: {data['rings']} 环 {data['ring_sizes']} {data['labels']}")
        truth = root_t / "topo_truth.csv"
        if truth.exists():
            report = evaluate(out, truth)
            (out / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  准确率评估 → {out / 'evaluation.json'}")
        else:
            print(f"  提示：放一个 topo_truth.csv 到 {root_t} 可评估准确率")
        print(f"③ 完成，{len(imgs)} 张 → {out}")

    elif step == "style":
        from .style import cluster_styles, extract_features, year_from_filename
        src = dirs["collect"]
        out = dirs["style"]
        imgs = _images(src)
        if not imgs:
            print(f"① 目录还没有图片：{src}")
            return
        feats = [extract_features(p, year_from_filename(p.name)) for p in imgs]
        seeds_path = root_t / "style_seeds.json"
        seeds = json.loads(seeds_path.read_text(encoding="utf-8")) if seeds_path.exists() else None
        profiles = cluster_styles(feats, out, seeds)
        print(f"② 完成，{len(imgs)} 张聚出 {len(profiles)} 档 → {out}")

    elif step == "render":
        from .style import render_batch
        style_dir = dirs["style"]
        out = dirs["render"]
        profiles = [p for p in style_dir.glob("*.json") if p.name.startswith("档位")]
        if not profiles:
            print(f"② 还没有风格档位：{style_dir}；先跑 style")
            return
        smiles = ["c1ccccc1", "CC(=O)Nc1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"]
        results = render_batch(smiles, style_dir, out, cache_dir=root_t / "render_cache")
        print(f"④ 完成，渲染 {len(results)} 张 → {out}")

    elif step == "match":
        from .matching import rank_candidates
        queries = dirs["collect"]
        candidates = dirs["render"]
        out = dirs["match"]
        out.mkdir(parents=True, exist_ok=True)
        imgs = _images(queries)
        if not imgs or not list(candidates.glob("*.png")):
            print("① 或 ④ 还没有产物；先跑 collect 和 render")
            return
        all_results = []
        for q in imgs:
            ranked = rank_candidates(q, candidates)
            all_results.append({"query": str(q), "candidates": [r.to_dict() for r in ranked]})
        target = out / "match.json"
        target.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"⑤ 完成，{len(all_results)} 张 → {target}")
    else:
        raise SystemExit(f"未知步骤 {step}；可选：{[k for k, _, _ in STEPS]}")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="训练流程总调度")
    ap.add_argument("cmd", choices=["init", "status", "run"])
    ap.add_argument("--root", required=True, help="工作区根目录")
    ap.add_argument("--step", choices=[k for k, _, _ in STEPS])
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.cmd == "init":
        init(root)
    elif args.cmd == "status":
        status(root)
    else:
        if not args.step:
            raise SystemExit("run 需要 --step")
        run_step(root, args.step)


if __name__ == "__main__":
    main()
