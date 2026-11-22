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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="按 JOURNALS_BY_ERA.md 抽样候选 DOI")
    sample.add_argument("--year", type=int, required=True)
    sample.add_argument("--era", help="如 1970s；不填则不限")
    sample.add_argument("--journal", help="刊名子串过滤，如 J. Org. Chem.")
    sample.add_argument("--limit", type=int, default=25)
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
