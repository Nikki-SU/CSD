"""命令行入口。

用法：
  python -m pipeline sample --year 1970 [--journal JOC] [--limit 25]
  python -m pipeline article --pdf a.pdf --doi 10.1021/jo00836a008 [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .article import process_article
from .acquire import acquire_cell
from .batch_download import batch_download
from .cell import run_cell
from .config import Config
from .sample import parse_journals, sample_cell, write_rows


def _cmd_sample(args: argparse.Namespace) -> int:
    config = Config.from_env()
    cells = [c for c in parse_journals() if c.active_in(args.year)]
    if args.journal:
        cells = [c for c in cells if args.journal.lower() in c.journal.lower()]
    if args.era:
        cells = [c for c in cells if c.era == args.era]
    if not cells:
        print("没有匹配的刊物/年份，检查 JOURNALS_BY_ERA.md 的有效年段。", file=sys.stderr)
        return 1

    all_rows: list[dict] = []
    for cell in cells:
        rows = sample_cell(cell, args.year, limit=args.limit, config=config)
        print(f"{cell.journal} {args.year}: {len(rows)} 条候选")
        all_rows.extend(rows)

    out = Path(args.out) if args.out else config.workdir / "sample" / f"sample_{args.year}.csv"
    path = write_rows(all_rows, out)
    print(f"已写入 {path}（{len(all_rows)} 条）")
    return 0


def _cmd_article(args: argparse.Namespace) -> int:
    config = Config.from_env()
    out = Path(args.out) if args.out else config.workdir / "articles" / Path(args.pdf).stem
    result = process_article(
        args.pdf,
        args.doi,
        out,
        config=config,
        dry_run=args.dry_run,
        all_pages=args.all_pages,
        reuse_mineru=args.reuse,
    )
    print(f"标题核验: {result.verify_status} ({result.verify_method}, sim={result.title_sim})")
    print(f"选页: {result.pages_with_figures}")
    print(f"结构式图: {len(result.structures)}")
    print(f"结论: {result.outcome} / {result.reject_reason}")
    print(f"输出目录: {out}")
    if result.outcome == "accepted":
        return 0
    if result.outcome == "needs_review":
        return 3
    return 2


def _cmd_acquire(args: argparse.Namespace) -> int:
    config = Config.from_env()
    cells = [c for c in parse_journals() if c.active_in(args.year)]
    if args.journal:
        cells = [c for c in cells if args.journal.lower() in c.journal.lower()]
    if args.era:
        cells = [c for c in cells if c.era == args.era]
    if not cells:
        print("没有匹配的刊物/年份，检查 JOURNALS_BY_ERA.md 的有效年段。", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else config.workdir / "acquire"
    for cell in cells:
        summary = acquire_cell(
            cell, args.year, args.pdf_dir, out, config=config,
            limit=args.limit, seed_suffix=args.seed,
        )
        print(
            f"{cell.journal} {args.year}: 抽样 {summary['sampled']}，"
            f"下载 {summary['downloaded']}，已有 {summary['already_have']}，"
            f"待人工 {summary['pending']}"
        )
        print(f"  明细: {summary['acquire_path']}")
        if summary["pending"]:
            print(f"  清单: {summary['manual_path']}")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    config = Config.from_env()
    out = Path(args.out) if args.out else config.workdir / "batch"
    summary = batch_download(
        args.rows, args.pdf_dir, out,
        cookies_path=args.cookies, config=config, delay=args.delay,
    )
    print(
        f"总计 {summary['total']}：下载 {summary['downloaded']}，"
        f"已有 {summary['already_have']}，失败 {summary['failed']}"
    )
    print(f"明细: {summary['result_path']}")
    if not summary["cookie_names"]:
        print("警告：未读到 cookies，闭源站会返回 401/403")
    return 0


def _cmd_browser(args: argparse.Namespace) -> int:
    from .browser_fetch import fetch_cell as run_browser

    config = Config.from_env()
    cells = [c for c in parse_journals() if c.active_in(args.year)]
    if args.journal:
        cells = [c for c in cells if args.journal.lower() in c.journal.lower()]
    if args.era:
        cells = [c for c in cells if c.era == args.era]
    if not cells:
        print("没有匹配的刊物/年份，检查 JOURNALS_BY_ERA.md 的有效年段。", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else config.workdir / "browser"
    for cell in cells:
        summary = run_browser(
            cell, args.year, args.pdf_dir, out, config=config,
            limit=args.limit, state_path=args.state,
            wait_ms=args.wait, headless=args.headless,
        )
        print(
            f"{cell.journal} {args.year}: 抽样 {summary['sampled']}，"
            f"下载 {summary['downloaded']}，失败 {summary['failed']}，"
            f"不支持 {summary['unsupported']}"
        )
        print(f"  明细: {summary['result_path']}")
    return 0


def _cmd_cell(args: argparse.Namespace) -> int:
    config = Config.from_env()
    cells = [c for c in parse_journals() if c.active_in(args.year)]
    if args.journal:
        cells = [c for c in cells if args.journal.lower() in c.journal.lower()]
    if args.era:
        cells = [c for c in cells if c.era == args.era]
    if not cells:
        print("没有匹配的刊物/年份，检查 JOURNALS_BY_ERA.md 的有效年段。", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else config.workdir / "cells"
    for cell in cells:
        if args.acquire:
            summary = acquire_cell(cell, args.year, args.pdf_dir, out, config=config)
            print(
                f"{cell.journal} {args.year} 取全文: 下载 {summary['downloaded']}，"
                f"待人工 {summary['pending']}"
            )
        summary = run_cell(cell, args.year, args.pdf_dir, out, config=config)
        print(
            f"{cell.journal} {args.year}: accepted {summary['accepted']}/{summary['target']} "
            f"in {summary['rounds']} round(s), captionless={summary['captionless_rate']:.0%}"
            f"{' [ALARM]' if summary['alarm'] else ''}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="按 JOURNALS_BY_ERA.md 抽样候选 DOI")
    sample.add_argument("--year", type=int, required=True)
    sample.add_argument("--era", help="如 1970s；不填则不限")
    sample.add_argument("--journal", help="刊名子串过滤，如 J. Org. Chem.")
    sample.add_argument("--limit", type=int, default=20)
    sample.add_argument("--out")
    sample.set_defaults(func=_cmd_sample)

    article = sub.add_parser("article", help="处理单篇文章（选页→Mineru→图注→存图）")
    article.add_argument("--pdf", required=True)
    article.add_argument("--doi", required=True)
    article.add_argument("--out")
    article.add_argument("--dry-run", action="store_true", help="不调 Mineru，只做取页与标题核验")
    article.add_argument("--all-pages", action="store_true", help="整篇送 Mineru，不做图注页预筛")
    article.add_argument("--reuse", action="store_true", help="复用 out/mineru 下已有解析结果，不重新调用 API")
    article.set_defaults(func=_cmd_article)

    cell = sub.add_parser("cell", help="按格子跑轮次：每轮 20 篇、最多 5 轮、目标 5 篇")
    cell.add_argument("--year", type=int, required=True)
    cell.add_argument("--pdf-dir", required=True, help="本地 PDF 目录，文件名含 DOI 的 slug")
    cell.add_argument("--journal", help="刊名子串过滤")
    cell.add_argument("--era", help="如 1970s")
    cell.add_argument("--out")
    cell.add_argument("--acquire", action="store_true", help="先自动取一轮全文，再进入逐篇筛查")
    cell.set_defaults(func=_cmd_cell)

    acquire = sub.add_parser("acquire", help="自动取全文；取不到的写待人工清单")
    acquire.add_argument("--year", type=int, required=True)
    acquire.add_argument("--pdf-dir", required=True)
    acquire.add_argument("--journal", help="刊名子串过滤")
    acquire.add_argument("--era", help="如 1970s")
    acquire.add_argument("--limit", type=int, default=20)
    acquire.add_argument("--seed", default="", help="抽样种子后缀，换一批候选时改这里")
    acquire.add_argument("--out")
    acquire.set_defaults(func=_cmd_acquire)

    batch = sub.add_parser("batch", help="带登录态批量下载出版社 PDF")
    batch.add_argument("--rows", required=True, help="含 doi 列的 CSV")
    batch.add_argument("--pdf-dir", required=True)
    batch.add_argument("--cookies", help="cookies.txt / Cookie 头 / Copy as cURL")
    batch.add_argument("--out")
    batch.add_argument("--delay", type=float, default=1.0)
    batch.set_defaults(func=_cmd_batch)

    browser = sub.add_parser("browser", help="真实浏览器过 JS 挑战，取免费 PDF")
    browser.add_argument("--year", type=int, required=True)
    browser.add_argument("--pdf-dir", required=True)
    browser.add_argument("--journal", help="刊名子串过滤")
    browser.add_argument("--era", help="如 1950s")
    browser.add_argument("--limit", type=int, default=20)
    browser.add_argument("--state", help="Playwright storage_state.json（登录态）")
    browser.add_argument("--wait", type=int, default=5000, help="过挑战后等待毫秒数")
    browser.add_argument("--headless", action="store_true")
    browser.add_argument("--out")
    browser.set_defaults(func=_cmd_browser)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
