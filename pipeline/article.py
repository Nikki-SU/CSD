"""单篇文章的完整处理：核 DOI 标题 → 选页 → Mineru → 图注判定 → 保存结构图。

对应 DATASET_WORKFLOW.md 第二、三节。dry_run 不调 Mineru，只用 PDF 文本层核标题，
用于没拿到 API key 时先把取页与核验跑通。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import figures as figures_mod
from . import pdf_ops
from .config import ArticleResult, Config
from .llm import SemanticJudge
from .verify import crossref_metadata, verify_title


def process_article(
    pdf_path: str | Path,
    doi: str,
    out_dir: str | Path,
    config: Config | None = None,
    dry_run: bool = False,
    all_pages: bool = False,
    reuse_mineru: bool = False,
) -> ArticleResult:
    config = config or Config.from_env()
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = ArticleResult(doi=doi, pdf=str(pdf_path))
    meta = crossref_metadata(doi, mailto=config.crossref_mailto, timeout=config.timeout)
    result.title_claim = meta["title"]

    pages, mode = pdf_ops.select_pages(pdf_path, force_all=all_pages)
    result.pages_with_figures = pages

    rendered = pdf_ops.render_pages(pdf_path, pages, out_dir / "pages", dpi=config.dpi)

    if dry_run:
        _verify_from_text(pdf_path, result, config)
        result.figures = [
            {"figure_id": f"p{p:03d}", "page": p, "caption": "", "has_structure": None,
             "judge_method": "dry_run", "judge_reason": "未调用 Mineru"}
            for p in pdf_ops.find_caption_pages(pdf_path)
        ]
        result.outcome = "rejected"
        result.reject_reason = "dry_run"
        _write_outputs(out_dir, result, meta, mode)
        return result

    from .mineru import MineruClient

    if reuse_mineru:
        parsed = {}
        for page in pages:
            root = out_dir / "mineru" / f"p{page:03d}"
            found = MineruClient._find_output_root(root)
            if found:
                parsed[f"p{page:03d}"] = found
    else:
        client = MineruClient(config)
        data_ids = [f"p{page:03d}" for page in pages]
        parsed = client.parse_files(
            [rendered[page] for page in pages], data_ids=data_ids, out_dir=out_dir / "mineru"
        )

    title_text = "\n\n".join(
        _read_markdown(parsed[f"p{page:03d}"])
        for page in pages
        if page <= 2 and f"p{page:03d}" in parsed
    )
    _apply_verify(result, title_text, config)

    judge = SemanticJudge(config)
    records: list[dict] = []
    for page in pages:
        base = parsed.get(f"p{page:03d}")
        if not base:
            continue
        content = figures_mod.load_content_list(base)
        for record in figures_mod.figure_records(content, page_offset=page - 1):
            verdict = figures_mod.judge_caption(record["caption"], judge)
            record["has_structure"] = verdict["has_structure"]
            record["judge_method"] = verdict["method"]
            record["judge_reason"] = verdict["reason"]
            if record["has_structure"] is True:
                saved = figures_mod.save_figure(base, record, out_dir / "figures")
                record["saved_path"] = str(saved) if saved else ""
                if saved:
                    result.structures.append(str(saved))
            elif record["has_structure"] is None:
                # 未判定不等于没结构：存到 review/ 交人工复核，不硬判
                saved = figures_mod.save_figure(base, record, out_dir / "review")
                record["saved_path"] = str(saved) if saved else ""
            records.append(record)
    result.figures = records

    if result.verify_status != "verified":
        result.outcome = "rejected"
        result.reject_reason = result.verify_status
    elif not records:
        result.outcome = "rejected"
        result.reject_reason = "no_figures"
    elif result.structures:
        result.outcome = "accepted"
    elif any(record["has_structure"] is None for record in records):
        result.outcome = "needs_review"
        result.reject_reason = "no_structure_confirmed"
    else:
        result.outcome = "rejected"
        result.reject_reason = "no_structure"

    _write_outputs(out_dir, result, meta, mode)
    return result


def _read_markdown(directory: Path) -> str:
    for name in ("full.md", "main.md"):
        path = directory / name
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _verify_from_text(pdf_path: Path, result: ArticleResult, config: Config) -> None:
    total = pdf_ops.page_count(pdf_path)
    text = pdf_ops.pages_text(pdf_path, list(range(1, min(2, total) + 1)))
    _apply_verify(result, text, config)


def _apply_verify(result: ArticleResult, page_text: str, config: Config) -> None:
    verdict = verify_title(result.title_claim, page_text, SemanticJudge(config))
    result.verify_status = verdict["status"]
    result.title_pdf = verdict["title_pdf"]
    result.title_sim = verdict["similarity"]
    result.verify_method = verdict["method"]
    result.needs_review = verdict["needs_review"]


def _write_outputs(out_dir: Path, result: ArticleResult, meta: dict, mode: str) -> None:
    payload = asdict(result)
    payload["crossref"] = meta
    payload["page_selection"] = mode
    (out_dir / "article.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# {result.title_claim or result.doi}",
        "",
        f"- DOI: {result.doi}",
        f"- 核验: {result.verify_status}（{result.verify_method}，similarity={result.title_sim}）",
        f"- 结论: {result.outcome} / {result.reject_reason}",
        "",
        "| figure_id | page | 结构式 | 判定方式 | 图注 | 理由 |",
        "|---|---|---|---|---|---|",
    ]
    for figure in result.figures:
        caption = (figure.get("caption") or "").replace("|", "/")
        lines.append(
            f"| {figure['figure_id']} | {figure['page']} | {figure.get('has_structure')} "
            f"| {figure.get('judge_method', '')} | {caption} | {figure.get('judge_reason', '')} |"
        )
    (out_dir / "figures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
