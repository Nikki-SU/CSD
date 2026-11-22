"""按格子跑轮次：每轮 20 篇，最多 5 轮，每格目标 5 篇。

对应 DATASET_WORKFLOW v0.6 第一节与第二节。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Callable

from .config import Config
from .sample import JournalCell, sample_cell
from .screen import screen_article


def doi_slug(doi: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")


def find_pdf(pdf_dir: str | Path, doi: str) -> Path | None:
    """在本地 PDF 目录里按 DOI 找文件；文件名包含 DOI 的 slug 即可。"""
    target = doi_slug(doi)
    if not target:
        return None
    for path in Path(pdf_dir).rglob("*.pdf"):
        if target in doi_slug(path.stem):
            return path
    return None


def _row_to_record(round_no: int, attempt: int, doi: str, pdf: Path | None, screened: dict) -> dict:
    record = {
        "round": round_no,
        "attempt": attempt,
        "doi": doi,
        "pdf": str(pdf) if pdf else "",
        **screened,
    }
    status = screened.get("status", "error")
    if pdf is None:
        outcome = "pdf_missing"
    elif screened.get("verify_status") != "verified":
        outcome = "rejected_" + str(screened.get("verify_status"))
    elif status == "no_figures":
        outcome = "rejected_no_figures"
    elif status == "non_structure":
        outcome = "rejected_non_structure"
    elif status == "structure":
        outcome = "accepted"
    elif status == "captionless":
        outcome = "skipped_captionless"
    else:
        outcome = "needs_review"
    record["outcome"] = outcome
    return record


def run_cell(
    cell: JournalCell,
    year: int,
    pdf_dir: str | Path,
    out_dir: str | Path,
    config: Config | None = None,
    sample_fn: Callable[..., list[dict]] = sample_cell,
    screen_fn: Callable[..., dict] = screen_article,
) -> dict:
    config = config or Config.from_env()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tried: set[str] = set()
    records: list[dict] = []
    accepted: list[dict] = []
    rounds_done = 0
    alarm = False
    captionless_rate = 0.0
    figure_count = 0
    captionless_count = 0

    for round_no in range(1, config.max_rounds_per_cell + 1):
        rows = sample_fn(
            cell, year, limit=config.pool_per_round, config=config, seed_suffix=str(round_no)
        )
        rows = [row for row in rows if row.get("doi") and row["doi"] not in tried]
        if not rows:
            break
        rounds_done = round_no

        for attempt, row in enumerate(rows, start=1):
            if len(accepted) >= config.target_per_cell:
                break
            doi = row["doi"]
            tried.add(doi)
            pdf = find_pdf(pdf_dir, doi)
            if pdf is None:
                records.append(_row_to_record(round_no, attempt, doi, None, {"status": "error"}))
                continue
            try:
                screened = screen_fn(pdf, doi, out_dir / "articles" / doi_slug(doi), config)
            except Exception as exc:  # noqa: BLE001
                screened = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            record = _row_to_record(round_no, attempt, doi, pdf, screened)
            records.append(record)
            if record["outcome"] == "accepted":
                accepted.append(record)

        figure_articles = [r for r in records if r.get("has_figures")]
        captionless_articles = [r for r in figure_articles if r.get("captionless")]
        figure_count = len(figure_articles)
        captionless_count = len(captionless_articles)
        captionless_rate = captionless_count / figure_count if figure_count else 0.0

        # 目标已满就先收工；此时无图注占比不影响这一格
        if len(accepted) >= config.target_per_cell:
            break

        # 20% 是报警线：达到就停这一格，交人类决定，不自动处理
        if captionless_rate >= config.captionless_threshold:
            alarm = True
            for record in records:
                if record["outcome"] == "skipped_captionless":
                    record["outcome"] = "pending_human"
            break

    summary = {
        "journal": cell.journal,
        "source_id": cell.source_id,
        "year": year,
        "rounds": rounds_done,
        "accepted": len(accepted),
        "target": config.target_per_cell,
        "alarm": alarm,
        "captionless_rate": round(captionless_rate, 4),
        "captionless_threshold": config.captionless_threshold,
        "figure_articles": figure_count,
        "captionless_articles": captionless_count,
        "records": records,
    }
    _write_cell(out_dir, cell, year, records, summary)
    return summary


def _write_cell(out_dir: Path, cell: JournalCell, year: int, records: list[dict], summary: dict) -> None:
    fields = [
        "round", "attempt", "doi", "outcome", "status", "verify_status",
        "has_figures", "captionless", "structure", "mineru_used", "figure_pages", "pdf",
    ]
    cell_path = out_dir / f"{year}_{cell.source_id}.csv"
    with cell_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["figure_pages"] = "|".join(str(p) for p in row.get("figure_pages") or [])
            writer.writerow(row)

    if summary.get("alarm"):
        alarm_path = out_dir / f"{year}_{cell.source_id}.alarm.md"
        lines = [
            "# 无图注报警",
            "",
            f"- 格子：{cell.journal} / {year} / `{cell.source_id}`",
            f"- 有图文章：{summary['figure_articles']}",
            f"- 无图注文章：{summary['captionless_articles']}",
            f"- 比例：{summary['captionless_rate']:.2%}",
            f"- 阈值：{summary['captionless_threshold']:.0%}",
            "",
            "无图注文章占比达到报警线。继续剔除会让数据集系统性缺失这类刊物/年代的样本。",
            "已停止该格，等人类决定怎么处理无图注的图；不得自动纳入或作废。",
            "",
            "| DOI | 页码 |",
            "|---|---|",
        ]
        for record in records:
            if record.get("captionless"):
                pages = "|".join(str(p) for p in record.get("figure_pages") or [])
                lines.append(f"| {record['doi']} | {pages} |")
        alarm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        summary["alarm_path"] = str(alarm_path)
    elif summary["accepted"] < summary["target"]:
        gaps_path = out_dir / "gaps.csv"
        exists = gaps_path.exists()
        with gaps_path.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            if not exists:
                writer.writerow(["journal", "source_id", "year", "accepted", "target", "rounds"])
            writer.writerow([
                cell.journal, cell.source_id, year,
                summary["accepted"], summary["target"], summary["rounds"],
            ])
