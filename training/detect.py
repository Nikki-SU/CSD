"""用 MolDet-Doc 批量标注 PDF 页里的分子结构式——攒数据集的第一步。

MolDet 输出的是「这里有一个分子结构式」的检测框，正是我们要的标注：
  - 它当 baseline（衡量手写判据准不准）
  - 它批量跑出的结果进瀑布流，人审后成为训练集

输入：PDF 目录（或 workspace.json 里纳入的文献）
输出：每页的检测框，落 rounds/round_NNN/detections.json

用法：
    python -m training.detect run --pdf-dir <目录> --out <detections.json> [--limit N]
    python -m training.detect status --out <detections.json>
"""
from __future__ import annotations

import json
import time
from pathlib import Path

WEIGHT = "models/moldet_yolo11l_960_doc.pt"


def load_model(weight_path: str | Path | None = None):
    """加载 MolDet。权重默认在项目 models/ 下。非商用许可。"""
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError("需要 ultralytics：pip install ultralytics") from e
    wp = Path(weight_path) if weight_path else Path(__file__).resolve().parent.parent / WEIGHT
    if not wp.exists():
        raise FileNotFoundError(
            f"找不到 MolDet 权重：{wp}\n"
            "下载：huggingface-cli download UniParser/MolDet moldet_yolo11l_960_doc.pt --local-dir models/\n"
            "注意：权重仅非商用（cc-by-nc-sa-4.0）。"
        )
    return YOLO(str(wp))


def detect_page(model, page, dpi: int = 150, imgsz: int = 960, conf: float = 0.3) -> dict:
    """对单页做分子检测，返回检测框列表。conf 用 0.3（比官方 0.5 低，提召回）。"""
    import numpy as np
    import cv2
    pix = page.get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n >= 3 else arr
    res = model.predict(img, imgsz=imgsz, conf=conf, device="cpu", verbose=False)
    boxes = []
    if res and len(res[0].boxes):
        for b in res[0].boxes:
            xyxy = [round(float(v), 1) for v in b.xyxy[0].tolist()]
            boxes.append({"bbox": xyxy, "conf": round(float(b.conf[0]), 3)})
    return {"page": int(page.number) + 1, "boxes": boxes, "has_molecule": bool(boxes)}


def run(pdf_dir: Path, out: Path, limit: int | None = None,
        dpi: int = 150, conf: float = 0.3, weight: str | None = None) -> dict:
    import pymupdf
    model = load_model(weight)
    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    if limit:
        pdfs = pdfs[:limit]
    results = {}
    t0 = time.time()
    for i, pdf in enumerate(pdfs, 1):
        doc = pymupdf.open(pdf)
        pages = [detect_page(model, page, dpi=dpi, conf=conf) for page in doc]
        doc.close()
        n_mol = sum(1 for p in pages if p["has_molecule"])
        results[pdf.name] = {
            "source": "moldet-doc",
            "conf": conf,
            "dpi": dpi,
            "pages": pages,
            "molecule_pages": [p["page"] for p in pages if p["has_molecule"]],
        }
        print(f"  [{i}/{len(pdfs)}] {pdf.name}: {n_mol} 页有结构式 ({time.time()-t0:.0f}s)", flush=True)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {out}（{len(results)} 篇）")
    return results


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="MolDet 批量标注分子结构式")
    ap.add_argument("cmd", choices=["run", "status"])
    ap.add_argument("--pdf-dir", help="PDF 目录")
    ap.add_argument("--out", required=True, help="detections.json")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--weight")
    args = ap.parse_args()
    if args.cmd == "run":
        if not args.pdf_dir:
            raise SystemExit("run 需要 --pdf-dir")
        run(Path(args.pdf_dir), Path(args.out), args.limit, args.dpi, args.conf, args.weight)
    else:
        data = json.loads(Path(args.out).read_text(encoding="utf-8"))
        total_pages = sum(len(v["pages"]) for v in data.values())
        mol_pages = sum(len(v["molecule_pages"]) for v in data.values())
        print(f"{len(data)} 篇 · {total_pages} 页 · {mol_pages} 页检出结构式")
        for name, v in list(data.items())[:5]:
            print(f"  {name}: {v['molecule_pages']}")


if __name__ == "__main__":
    main()
