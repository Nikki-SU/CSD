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

# 有机论文的强正向特征：合成、机理、结构、反应类型、化合物类别、人名反应
# 英/德/法三语；德语刊（Chem. Ber.、Liebigs、Angew.、ZfN B）标题不能只看英文
ORGANIC_STRONG = re.compile(
    r"synthes|synthetic|prepar|formed|formation|reaction|mechanism|kinetic|"
    r"catalys|catalyzed|intermediate|structure|stereochem|configur|conformation|"
    r"rearrang|condensat|cycliz|cycloaddit|addition|elimination|substitut|"
    r"hydrolysis|oxidat|reduct|hydrogenat|halogenat|nitrat|sulfonat|"
    r"alkylat|acylat|esterif|amidat|polymeriz|cleavage|protection|"
    r"compound|derivat|ester|amide|amine|alcohol|ketone|aldehyde|ether|"
    r"halide|nitrile|oxime|hydrazone|heterocycl|alkaloid|terpene|steroid|"
    r"peptide|nucleosid|carbohydrat|amino acid|aromatic|aliphatic|alkyl|aryl|"
    r"grignard|diels|wittig|friedel|reformatsky|claisen|aldol|michael|"
    r"mannich|pinacol|beckmann|hofmann|curtius|schmidt|baeyer|perkin|"
    r"knoevenagel|dieckmann|robinson|"
    r"on the action|constitution|studies on|studies in|"
    # 德语
    r"darstellung|synthese|reaktion|verbindung|derivat|säure|ester|amid|"
    r"alkohol|keton|aldehyd|äther|halogenid|nitril|oxim|hydrazon|"
    r"heterocycl|alkaloid|terpen|steroid|peptid|nucleosid|kohlenhydrat|"
    r"aromatisch|aliphatisch|oxydation|reduktion|hydrierung|halogenierung|"
    r"nitrierung|sulfonierung|alkylierung|acylierung|veresterung|"
    r"umlagerung|kondensation|cyclisierung|polymerisation|spaltung|"
    r"isomerie|konfiguration|zur kenntnis|über die|"
    # 法语
    r"synthèse|préparation|réaction|mécanisme|dérivé|composé|acide|alcool|"
    r"cétone|aldéhyde|éther|halogénure|nitrile|oxime|hydrazone|hétérocycle|"
    r"alcaloïde|terpène|stéroïde|peptide|nucléoside|glucide|aromatique|"
    r"aliphatique|oxydation|réduction|hydrogénation|halogénation|nitration|"
    r"sulfonation|acylation|estérification|transposition|condensation|"
    r"cyclisation|polymérisation",
    re.IGNORECASE,
)

# 明显非有机的标题特征：物性、晶体、谱学理论等
NON_ORGANIC_TITLE = re.compile(
    r"conduct|superconduct|magnet|dielectric|ferroelectr|semiconduct|band[ -]gap|"
    r"photovoltaic|luminesc|crystal structure|x-ray|neutron diffraction|"
    r"density functional|ab initio|quantum chemical|thermodynamic|"
    r"electrochem|polarograph|voltammetr|surface tension|viscosity|"
    r"refractive index|phase transition|specific heat|calorimetr",
    re.I,
)


PURE_ORGANIC = re.compile(
    r"(J\. Org\. Chem\.|Tetrahedron|Synthesis|Perkin Trans\. 1|J\. Chem\. Soc\. C|"
    r"Chemische Berichte|Liebigs Ann|Justus Liebigs|Helvetica Chimica Acta|"
    r"Carbohydr\. Res\.|J\. Heterocycl\. Chem\.|Heterocycles|Chemistry Letters|"
    r"J\. Organomet\. Chem\.)",
    re.I,
)


def is_organic_work(work: dict, pure_organic: bool = False) -> bool:
    """判定是否像有机论文。

    - 命中强物性词且没有强正向词 → 直接排除
    - 纯有机刊 → 只要不像物化/无机就收
    - 否则：标题命中英/德/法正向词，或任一学科标签是有机化学
    """
    title = work.get("title") or ""
    strong = bool(ORGANIC_STRONG.search(title))
    if NON_ORGANIC_TITLE.search(title) and not strong:
        return False
    if pure_organic or strong:
        return True
    topics = work.get("topics") or []
    return any(
        (t.get("subfield") or {}).get("display_name") == ORGANIC_SUBFIELD for t in topics
    )


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
    pool = min(pool_size or max(limit * 20, 200), 200)
    works = openalex_works(
        cell.source_id, year, per_page=pool, mailto=config.openalex_mailto, timeout=config.timeout
    )
    if organic_only:
        pure = bool(PURE_ORGANIC.search(cell.journal))
        works = [w for w in works if is_organic_work(w, pure_organic=pure)]
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
