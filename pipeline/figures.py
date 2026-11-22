"""图注解析与结构式判定。

Mineru 输出的 content_list.json 里，图片条目形如：
{"type": "image", "img_path": "images/x.jpg", "image_caption": ["Fig. 1. ..."], "page_idx": 0}

判定口径见 DATASET_WORKFLOW.md 第二、五步：读图注判图里有没有结构式；拿不准
不硬判，留给人工复核。
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .llm import SemanticJudge


def load_content_list(mineru_dir: str | Path) -> list[dict]:
    """Mineru 的输出名可能带 UUID 前缀，如 {uuid}_content_list.json。"""
    directory = Path(mineru_dir)
    path = directory / "content_list.json"
    if not path.exists():
        candidates = [
            p
            for p in sorted(directory.glob("*_content_list.json"))
            if not p.name.endswith("_content_list_v2.json")
        ]
        if not candidates:
            return []
        path = candidates[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def figure_records(content_list: list[dict], page_offset: int = 0) -> list[dict]:
    """按阅读顺序给每张图编号：p{页:03d}_f{页内序号:02d}。

    只收 Mineru 判为 image 的区块。实测：结构图/反应式多为 image，折线图多为
    chart，表格为 table；后两者不进候选。
    """
    counters: dict[int, int] = {}
    records: list[dict] = []
    for item in content_list:
        if item.get("type") != "image":
            continue
        page = int(item.get("page_idx", 0)) + 1 + page_offset
        counters[page] = counters.get(page, 0) + 1
        caption = " ".join(item.get("image_caption") or []).strip()
        footnote = " ".join(item.get("image_footnote") or []).strip()
        bbox = item.get("bbox") or item.get("box") or []
        if isinstance(bbox, dict):
            bbox = [bbox.get("x1", 0), bbox.get("y1", 0), bbox.get("x2", 0), bbox.get("y2", 0)]
        records.append(
            {
                "figure_id": f"p{page:03d}_f{counters[page]:02d}",
                "page": page,
                "bbox": [int(v) for v in bbox] if len(bbox) == 4 else [],
                "img_path": item.get("img_path", ""),
                "caption": caption,
                "footnote": footnote,
                "has_structure": None,
                "judge_method": "",
                "judge_reason": "",
            }
        )
    return records


_SCHEME_WORDS = re.compile(
    r"\b(scheme|synthesis|synthetic|reaction|reagent|compound|derivative|"
    r"preparation|conversion|equation)\b",
    re.IGNORECASE,
)
_NON_STRUCTURE_WORDS = re.compile(
    r"\b(spectrum|spectra|nmr|infrared|ir\b|uv\b|mass|plot|graph|curve|"
    r"photograph|apparatus|cell|column|chromatogram|yield versus|"
    r"temperature dependence|kinetic)\b",
    re.IGNORECASE,
)


def judge_caption(caption: str, judge: SemanticJudge) -> dict:
    """返回 {has_structure: True/False/None, method, reason}。"""
    caption = (caption or "").strip()
    if not caption:
        return {"has_structure": None, "method": "none", "reason": "无图注"}

    if judge.available:
        result = judge.json(
            system=(
                "你是化学文献图注判定助手，只输出 JSON。"
                "判断图注所描述的这张图里是否包含化学结构式："
                "分子骨架结构图、反应式、合成路线式都算；"
                "谱图、折线图、装置照片、表格、电子显微镜照片不算。"
                "拿不准时 has_structure 填 \"unknown\"，不要猜。"
            ),
            user=(
                f"图注：{caption}\n\n"
                '输出：{"has_structure": true/false/"unknown", "reason": "一句话理由"}'
            ),
        )
        if result is not None:
            value = result.get("has_structure")
            if value is True or value == "true":
                has = True
            elif value is False or value == "false":
                has = False
            else:
                has = None
            return {
                "has_structure": has,
                "method": "semantic",
                "reason": str(result.get("reason") or ""),
            }

    # 无模型时的兜底：只认最明确的信号，其余标 unknown 待复核
    if re.match(r"^\s*scheme\b", caption, re.IGNORECASE):
        return {"has_structure": True, "method": "keyword_fallback", "reason": "图注以 SCHEME 开头"}
    if _NON_STRUCTURE_WORDS.search(caption) and not _SCHEME_WORDS.search(caption):
        return {"has_structure": False, "method": "keyword_fallback", "reason": "图注指向谱图/曲线/装置"}
    return {"has_structure": None, "method": "unknown", "reason": "无语义判定模型，待人工复核"}


def save_figure(mineru_dir: str | Path, record: dict, out_dir: str | Path) -> Path | None:
    src = Path(mineru_dir) / record["img_path"]
    if not record["img_path"] or not src.exists():
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{record['figure_id']}{src.suffix.lower() or '.jpg'}"
    shutil.copy2(src, dest)
    return dest
