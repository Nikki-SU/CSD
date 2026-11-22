"""抽样：直接解析 JOURNALS_BY_ERA.md（单一事实源），按（刊, 年）向 OpenAlex 取候选。

不在这里判断结构式；抽样只产出 DOI 候选列表，后续逐篇过 PDF 核验与提图。
"""

from __future__ import annotations

import csv
import random
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import Config

ROOT = Path(__file__).resolve().parent.parent
JOURNALS_MD = ROOT / "JOURNALS_BY_ERA.md"

SECTION_RE = re.compile(r"^##\s*[一二三四五六七八九十]+、\s*(\d{4})s")
SOURCE_RE = re.compile(r"S\d{6,}")

ORGANIC_SUBFIELD = "Organic Chemistry"

# 明显非有机的标题特征：物性、晶体、谱学理论等
NON_ORGANIC_TITLE = re.compile(
    r"conduct|superconduct|magnet|dielectric|ferroelectr|semiconduct|band[ -]gap|"
    r"photovoltaic|luminesc|crystal structure|x-ray|neutron diffraction|"
    r"density functional|ab initio|quantum chemical|thermodynamic|"
    r"electrochem|polarograph|voltammetr|surface tension|viscosity|"
    r"refractive index|phase transition|specific heat|calorimetr",
    re.I,
)
ORGANIC_TITLE_HINT = re.compile(
    r"synthes|prepar|reaction|derivat|compound|ester|amide|amine|alcohol|"
    r"ketone|aldehyde|ether|halide|cycli|condensat|rearrang|stereochem|"
    r"alkyl|aryl|heterocycl|oxidation|reduction|catalys",
    re.I,
)


def is_organic_work(work: dict) -> bool:
    """用 OpenAlex 学科标签 + 标题特征挡掉明显非有机的文章。

    topics 按相关度排序，要求第一标签就是有机化学，避免把「材料化学 + 有机」
    这类混挂文章当成有机论文。
    """
    topics = work.get("topics") or []
    title = work.get("title") or ""
    if topics:
        primary = (topics[0].get("subfield") or {}).get("display_name")
        if primary != ORGANIC_SUBFIELD:
            return False
    else:
        # 早期文献常没有学科标签，退回标题判断
        if not ORGANIC_TITLE_HINT.search(title):
            return False
    if NON_ORGANIC_TITLE.search(title) and not ORGANIC_TITLE_HINT.search(title):
        return False
    return True


@dataclass(frozen=True)
class JournalCell:
    journal: str
    era: str
    year_start: int
    year_end: int
    source_id: str
    level: str

    def active_in(self, year: int) -> bool:
        return self.year_start <= year <= self.year_end


def parse_journals(path: str | Path = JOURNALS_MD) -> list[JournalCell]:
    era: str | None = None
    cells: list[JournalCell] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        section = SECTION_RE.match(line)
        if section:
            era = f"{section.group(1)}s"
            continue
        if line.startswith("## "):
            era = None
            continue
        if not era or not line.startswith("|"):
            continue
        if set(line) <= {"|", "-", " ", ":"}:
            continue
        cells_raw = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells_raw) < 4:
            continue
        journal, years, source, level = cells_raw[:4]
        source_match = SOURCE_RE.search(source)
        year_match = re.search(r"(\d{4})\s*[–-]\s*(\d{4})", years)
        single_match = re.search(r"(\d{4})", years)
        if not source_match or not (year_match or single_match):
            continue
        if "排除" in level:
            continue
        start, end = (
            (int(year_match.group(1)), int(year_match.group(2)))
            if year_match
            else (int(single_match.group(1)), int(single_match.group(1)))
        )
        cells.append(JournalCell(journal, era, start, end, source_match.group(0), level))
    return cells


def openalex_works(
    source_id: str,
    year: int,
    per_page: int = 20,
    mailto: str | None = None,
    timeout: int = 60,
) -> list[dict]:
    params = {
        "filter": (
            f"primary_location.source.id:{source_id},"
            f"publication_year:{year},type:article,has_doi:true"
        ),
        "per-page": per_page,
        "select": "id,doi,title,publication_year,best_oa_location,topics",
    }
    if mailto:
        params["mailto"] = mailto
    resp = requests.get("https://api.openalex.org/works", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("results") or []


def sample_cell(
    cell: JournalCell,
    year: int,
    limit: int = 20,
    config: Config | None = None,
    seed_suffix: str = "",
    organic_only: bool = True,
    pool_size: int | None = None,
) -> list[dict]:
    config = config or Config.from_env()
    pool = min(pool_size or max(limit * 6, 60), 200)
    works = openalex_works(
        cell.source_id, year, per_page=pool, mailto=config.openalex_mailto, timeout=config.timeout
    )
    if organic_only:
        works = [w for w in works if is_organic_work(w)]
    seed = f"{cell.source_id}:{year}" + (f":{seed_suffix}" if seed_suffix else "")
    random.Random(seed).shuffle(works)
    rows = []
    for position, work in enumerate(works[:limit], start=1):
        oa = work.get("best_oa_location") or {}
        rows.append(
            {
                "journal": cell.journal,
                "era": cell.era,
                "year": year,
                "source_id": cell.source_id,
                "position": position,
                "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
                "title": work.get("title") or "",
                "openalex_id": work.get("id") or "",
                "pdf_url": oa.get("pdf_url") or "",
            }
        )
    return rows


def write_rows(rows: list[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["journal", "era", "year", "source_id", "position", "doi", "title",
                        "openalex_id", "pdf_url"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path
