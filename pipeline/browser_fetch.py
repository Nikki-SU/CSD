"""用真实浏览器取免费全文：先过一次 JS 挑战，再下载 PDF。

只在有出版商标注为免费的站点上使用；订阅刊走 batch（用户登录态）。
无显示环境用 xvfb-run 启动：

  xvfb-run -a python -m pipeline browser --year 1955 \\
      --journal "Z. Naturforsch" --limit 20 --pdf-dir .private/pdfs
"""

from __future__ import annotations

import csv
from pathlib import Path

from playwright.sync_api import sync_playwright

from .acquire import MAX_PDF_BYTES, MIN_PDF_BYTES
from .cell import doi_slug, find_pdf
from .config import Config
from .sample import JournalCell, sample_cell

# 必须与真实 Chromium 一致；用爬虫 UA 会被 WAF 挂起
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)

# DOI 前缀 -> 该出版社的落地页与 PDF 直链模板
PREFIX_SITES = {
    "10.1515": {
        "landing": "https://www.degruyterbrill.com/document/doi/{doi}/html",
        "pdf": "https://www.degruyterbrill.com/document/doi/{doi}/pdf",
    },
    "10.1139": {
        "landing": "https://cdnsciencepub.com/doi/{doi}",
        "pdf": "https://cdnsciencepub.com/doi/pdf/{doi}",
    },
}


def _warm_up(ctx, url: str, wait_ms: int) -> None:
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(wait_ms)
    except Exception:  # noqa: BLE001
        pass
    finally:
        page.close()


def fetch_cell(
    cell: JournalCell,
    year: int,
    pdf_dir: str | Path,
    out_dir: str | Path,
    config: Config | None = None,
    limit: int = 20,
    state_path: str | Path | None = None,
    wait_ms: int = 5000,
    headless: bool = False,
) -> dict:
    config = config or Config.from_env()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(pdf_dir).mkdir(parents=True, exist_ok=True)

    rows = sample_cell(cell, year, limit=limit, config=config)
    results: list[dict] = []
    warmed: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chromium",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=BROWSER_UA,
            locale="en-US",
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            storage_state=str(state_path) if state_path else None,
        )
        for index, row in enumerate(rows, start=1):
            doi = (row.get("doi") or "").strip()
            if not doi:
                continue
            if find_pdf(pdf_dir, doi):
                results.append({"doi": doi, "status": "already_have", "detail": ""})
                print(f"[{index}/{len(rows)}] {doi} already_have", flush=True)
                continue

            site = PREFIX_SITES.get(doi.split("/")[0])
            if not site:
                results.append({"doi": doi, "status": "unsupported_prefix", "detail": ""})
                print(f"[{index}/{len(rows)}] {doi} unsupported_prefix", flush=True)
                continue

            if doi.split("/")[0] not in warmed:
                _warm_up(context, site["landing"].format(doi=doi), wait_ms)
                warmed.add(doi.split("/")[0])

            status, detail = "failed", ""
            try:
                resp = context.request.get(
                    site["pdf"].format(doi=doi),
                    headers={"User-Agent": BROWSER_UA, "Accept": "application/pdf,*/*"},
                    timeout=60000,
                )
                body = resp.body()
                if resp.status == 200 and body.startswith(b"%PDF") and len(body) >= MIN_PDF_BYTES:
                    if len(body) <= MAX_PDF_BYTES:
                        dest = Path(pdf_dir) / f"{doi_slug(doi)}.pdf"
                        dest.write_bytes(body)
                        status, detail = "downloaded", f"{len(body)} bytes"
                    else:
                        detail = "too_large"
                else:
                    detail = f"http_{resp.status}"
            except Exception as exc:  # noqa: BLE001
                detail = f"{type(exc).__name__}: {exc}"
            results.append({"doi": doi, "status": status, "detail": detail})
            print(f"[{index}/{len(rows)}] {doi} {status} {detail}", flush=True)

        browser.close()

    result_path = out_dir / f"{year}_{cell.source_id}_browser.csv"
    with result_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "status", "detail"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)

    return {
        "journal": cell.journal,
        "year": year,
        "sampled": len(results),
        "downloaded": sum(1 for r in results if r["status"] == "downloaded"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "unsupported": sum(1 for r in results if r["status"] == "unsupported_prefix"),
        "result_path": str(result_path),
    }
