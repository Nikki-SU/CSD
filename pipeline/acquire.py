"""取全文：从合法 OA 聚合源自动下载；取不到的登记人工清单。

同一个 DOI 依次问 OpenAlex / Semantic Scholar / Unpaywall / Europe PMC，
拿到候选 PDF 链接就下载，并用 %PDF 魔数与文件大小校验；
全部失败则写入待人工清单，清单带卷期页，方便按机构权限精确取件。
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import requests

from .cell import doi_slug, find_pdf
from .config import Config
from .sample import JournalCell, sample_cell

UA = "csd-pipeline/0.2 (dataset build; polite crawler)"
MIN_PDF_BYTES = 20_000
MAX_PDF_BYTES = 80_000_000


def _get_json(url: str, params: dict | None = None, timeout: int = 60):
    try:
        resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": UA})
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def candidate_urls(doi: str, config: Config) -> list[tuple[str, str]]:
    """按可信度排序的 (来源, PDF 链接)。同一链接只留一次。"""
    found: list[tuple[str, str]] = []

    def add(source: str, url: str | None) -> None:
        if not url or not url.startswith("http"):
            return
        if any(url == existing for _, existing in found):
            return
        found.append((source, url))

    params = {"select": "locations,best_oa_location"}
    if config.oa_mailto:
        params["mailto"] = config.oa_mailto
    work = _get_json(f"https://api.openalex.org/works/doi:{doi}", params, config.timeout)
    if work:
        locations = list(work.get("locations") or [])
        if work.get("best_oa_location"):
            locations.insert(0, work["best_oa_location"])
        for loc in locations:
            if loc and loc.get("is_oa"):
                add("openalex", loc.get("pdf_url"))

    s2 = _get_json(
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
        {"fields": "openAccessPdf,externalIds"},
        config.timeout,
    )
    if s2:
        add("semanticscholar", (s2.get("openAccessPdf") or {}).get("url"))
        arxiv = (s2.get("externalIds") or {}).get("ArXiv")
        if arxiv:
            add("arxiv", f"https://arxiv.org/pdf/{arxiv}")

    if config.oa_mailto:
        up = _get_json(
            f"https://api.unpaywall.org/v2/{doi}",
            {"email": config.oa_mailto},
            config.timeout,
        )
        if up:
            add("unpaywall", (up.get("best_oa_location") or {}).get("url_for_pdf"))

    epmc = _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        {"query": f'DOI:"{doi}"', "format": "json", "resultType": "core"},
        config.timeout,
    )
    hits = ((epmc or {}).get("resultList") or {}).get("result") or []
    for hit in hits:
        pmcid = hit.get("pmcid")
        if pmcid and hit.get("isOpenAccess") == "Y":
            add("europepmc", f"https://europepmc.org/articles/{pmcid}?pdf=render")

    return found


def download_pdf(
    url: str,
    dest: Path,
    timeout: int = 120,
    session: requests.Session | None = None,
) -> tuple[bool, str]:
    client = session or requests
    headers = {"User-Agent": UA}
    try:
        with client.get(
            url, timeout=timeout, headers=headers, stream=True, allow_redirects=True
        ) as resp:
            if resp.status_code != 200:
                return False, f"http_{resp.status_code}"
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    return False, "too_large"
    except requests.RequestException as exc:
        return False, type(exc).__name__

    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        return False, "not_pdf"
    if len(data) < MIN_PDF_BYTES:
        return False, "too_small"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True, "ok"


def crossref_meta(doi: str, config: Config) -> dict:
    params = {"mailto": config.crossref_mailto} if config.crossref_mailto else None
    data = _get_json(f"https://api.crossref.org/works/{doi}", params, config.timeout)
    msg = (data or {}).get("message") or {}
    return {
        "volume": msg.get("volume") or "",
        "issue": msg.get("issue") or "",
        "page": msg.get("page") or "",
        "publisher": msg.get("publisher") or "",
    }


def acquire_one(doi: str, pdf_dir: str | Path, config: Config, max_tries: int = 3) -> dict:
    existing = find_pdf(pdf_dir, doi)
    if existing:
        return {
            "doi": doi,
            "status": "already_have",
            "source": "",
            "url": "",
            "detail": str(existing),
        }

    failures: list[str] = []
    for source, url in candidate_urls(doi, config)[:max_tries]:
        dest = Path(pdf_dir) / f"{doi_slug(doi)}.pdf"
        ok, detail = download_pdf(url, dest, config.timeout)
        if ok:
            return {"doi": doi, "status": "downloaded", "source": source, "url": url, "detail": detail}
        failures.append(f"{source}:{detail}")

    return {
        "doi": doi,
        "status": "no_oa",
        "source": "",
        "url": "",
        "detail": ";".join(failures) or "no_candidate",
    }


def acquire_cell(
    cell: JournalCell,
    year: int,
    pdf_dir: str | Path,
    out_dir: str | Path,
    config: Config | None = None,
    limit: int = 20,
    seed_suffix: str = "",
) -> dict:
    config = config or Config.from_env()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(pdf_dir).mkdir(parents=True, exist_ok=True)

    rows = sample_cell(cell, year, limit=limit, config=config, seed_suffix=seed_suffix)
    results: list[dict] = []
    for row in rows:
        doi = row.get("doi") or ""
        if not doi:
            continue
        result = acquire_one(doi, pdf_dir, config)
        result["title"] = row.get("title") or ""
        results.append(result)

    acquire_path = out_dir / f"{year}_{cell.source_id}_acquire.csv"
    with acquire_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["doi", "status", "source", "url", "detail", "title"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(results)

    pending = [r for r in results if r["status"] == "no_oa"]
    manual_path = out_dir / f"{year}_{cell.source_id}_manual.csv"
    with manual_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "doi", "title", "journal", "year", "volume", "issue", "page",
                "publisher_url", "reason",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in pending:
            meta = crossref_meta(row["doi"], config)
            writer.writerow(
                {
                    "doi": row["doi"],
                    "title": row["title"],
                    "journal": cell.journal,
                    "year": year,
                    "volume": meta["volume"],
                    "issue": meta["issue"],
                    "page": meta["page"],
                    "publisher_url": f"https://doi.org/{row['doi']}",
                    "reason": row["detail"],
                }
            )

    summary = {
        "journal": cell.journal,
        "source_id": cell.source_id,
        "year": year,
        "sampled": len(results),
        "downloaded": sum(1 for r in results if r["status"] == "downloaded"),
        "already_have": sum(1 for r in results if r["status"] == "already_have"),
        "pending": len(pending),
        "acquire_path": str(acquire_path),
        "manual_path": str(manual_path),
    }
    return summary
