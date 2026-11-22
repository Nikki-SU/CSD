"""带登录态的批量取全文。

用户只需在自己的浏览器里登录出版商一次，导出 cookies
（Netscape cookies.txt / Cookie 请求头 / DevTools 的 Copy as cURL 均可），
脚本按 DOI 找出版商的 PDF 直链，逐篇下载并用 %PDF 魔数校验。

用法：
  python -m pipeline batch --rows .private/acquire/rows.csv \\
      --cookies .private/auth/acs.txt --pdf-dir .private/pdfs \\
      --out .private/batch

rows.csv 至少要有 doi 列；可选 title/journal/year/volume/issue/page。
"""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

import requests

from .acquire import UA, acquire_one, download_pdf
from .cell import doi_slug, find_pdf
from .config import Config

# 没有 Crossref link 时的兜底模板；{doi} 为不带 https://doi.org/ 的 DOI
PDF_TEMPLATES = {
    "10.1021": "https://pubs.acs.org/doi/pdf/{doi}",
    "10.1002": "https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
    "10.1006": "https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?download=true",
    "10.1016": "https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?download=true",
    "10.1039": "https://pubs.rsc.org/en/content/articlepdf/{year}/{doi}",
    "10.1007": "https://link.springer.com/content/pdf/{doi}.pdf",
    "10.1515": "https://www.degruyter.com/document/doi/{doi}/pdf",
    "10.1139": "https://cdnsciencepub.com/doi/pdf/{doi}",
    "10.1055": "https://www.thieme-connect.com/products/ejournals/pdf/{doi}.pdf",
    "10.1246": "https://www.jstage.jst.go.jp/article/{code}/_pdf/-char/en",
}

COOKIE_HEADER_RE = re.compile(r"(?:-H\s+)?['\"]?[Cc]ookie:\s*([^'\"]+)", re.S)


def load_cookies(path: str | Path | None) -> dict[str, str]:
    """兼容 Netscape cookies.txt、Cookie 请求头、Copy as cURL 三种导出。"""
    if not path:
        return {}
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    cookies: dict[str, str] = {}

    # Cookie-Editor 等扩展导出的 JSON 数组
    if text.lstrip().startswith("["):
        try:
            for item in json.loads(text):
                if isinstance(item, dict) and item.get("name"):
                    cookies[item["name"]] = item.get("value", "")
        except ValueError:
            pass
        if cookies:
            return cookies

    if "\t" in text and not text.lstrip().startswith("["):
        for line in text.splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
        return cookies

    match = COOKIE_HEADER_RE.search(text)
    if match:
        for pair in match.group(1).split(";"):
            if "=" in pair:
                name, value = pair.split("=", 1)
                cookies[name.strip()] = value.strip()
        return cookies

    pairs = [p for p in text.strip().split(";") if "=" in p]
    for pair in pairs:
        name, value = pair.split("=", 1)
        cookies[name.strip().strip("'\"")] = value.strip().strip("'\"")
    return cookies


def crossref_pdf_links(doi: str, config: Config) -> list[str]:
    params = {"mailto": config.crossref_mailto} if config.crossref_mailto else None
    try:
        resp = requests.get(
            f"https://api.crossref.org/works/{doi}",
            params=params,
            headers={"User-Agent": UA},
            timeout=config.timeout,
        )
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    links = (resp.json().get("message") or {}).get("link") or []
    return [item.get("URL") for item in links if item.get("URL")]


def pdf_candidates(doi: str, row: dict, config: Config) -> list[str]:
    urls = [u for u in crossref_pdf_links(doi, config) if "/pdf" in u.lower() or "pdfdirect" in u.lower()]
    prefix = doi.split("/")[0] if "/" in doi else ""
    template = PDF_TEMPLATES.get(prefix)
    if template:
        values = {
            "doi": doi,
            "year": row.get("year") or "",
            "pii": row.get("pii") or "",
            "code": row.get("code") or "",
        }
        if "{pii}" in template and not values["pii"]:
            pass
        elif "{code}" in template and not values["code"]:
            pass
        else:
            urls.append(template.format(**values))
    seen: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.append(url)
    return seen


def batch_download(
    rows_path: str | Path,
    pdf_dir: str | Path,
    out_dir: str | Path,
    cookies_path: str | Path | None = None,
    config: Config | None = None,
    delay: float = 1.0,
) -> dict:
    config = config or Config.from_env()
    cookies = load_cookies(cookies_path)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    if cookies:
        session.cookies.update(cookies)

    rows = list(csv.DictReader(Path(rows_path).open(encoding="utf-8-sig")))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for row in rows:
        doi = (row.get("doi") or "").strip()
        if not doi:
            continue
        if find_pdf(pdf_dir, doi):
            results.append({"doi": doi, "status": "already_have", "url": "", "detail": ""})
            continue

        # 先用公开 OA 源，不消耗也不依赖登录态
        oa = acquire_one(doi, pdf_dir, config)
        if oa["status"] in ("downloaded", "already_have"):
            results.append(
                {"doi": doi, "status": "downloaded", "url": oa["url"], "detail": f"oa:{oa['source']}"}
            )
            time.sleep(delay)
            continue

        status, used_url, detail = "failed", "", oa["detail"] or "no_pdf_url"
        for url in pdf_candidates(doi, row, config)[:4]:
            dest = Path(pdf_dir) / f"{doi_slug(doi)}.pdf"
            ok, why = download_pdf(url, dest, config.timeout, session=session)
            if ok:
                status, used_url, detail = "downloaded", url, "ok"
                break
            detail = why
        results.append({"doi": doi, "status": status, "url": used_url, "detail": detail})
        time.sleep(delay)

    result_path = out_dir / "batch.csv"
    with result_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "status", "url", "detail"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)

    return {
        "total": len(results),
        "downloaded": sum(1 for r in results if r["status"] == "downloaded"),
        "already_have": sum(1 for r in results if r["status"] == "already_have"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "cookie_names": sorted(cookies)[:5],
        "result_path": str(result_path),
    }
