"""DOI 元数据与「PDF 是不是这一篇」的核验。

口径见 DATASET_WORKFLOW.md 第三节：不搜正文 DOI，用首页/前两页的标题与 DOI
元数据标题做**语义**比对；语义拿不准按不匹配处理并标待人工复核。
"""

from __future__ import annotations

import re
import unicodedata

import requests

from .llm import SemanticJudge

CROSSREF_URL = "https://api.crossref.org/works/{doi}"


def normalize_doi(doi: str) -> str:
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def crossref_metadata(doi: str, mailto: str | None = None, timeout: int = 60) -> dict:
    doi = normalize_doi(doi)
    params = {"mailto": mailto} if mailto else {}
    resp = requests.get(
        CROSSREF_URL.format(doi=doi),
        params=params,
        headers={"User-Agent": f"csd-pipeline/0.1 (mailto:{mailto or 'unknown'})"},
        timeout=timeout,
    )
    resp.raise_for_status()
    message = resp.json()["message"]
    title = " ".join(message.get("title") or [])
    title = re.sub(r"<[^>]+>", "", title)  # Crossref 标题里会带 <scp> 等标记
    title = " ".join(title.split())
    year = None
    for key in ("published-print", "published-online", "issued"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    return {
        "doi": doi,
        "title": title,
        "journal": " ".join(message.get("container-title") or []),
        "year": year,
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "page": message.get("page"),
    }


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text).split())


def _compact(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", text).lower())


def token_coverage(claim: str, page_text: str) -> float:
    """声称标题的词有多少比例出现在页面文本里（OCR 噪声下的兜底指标）。"""
    claim_tokens = [t for t in _normalize(claim).split() if len(t) >= 3]
    if not claim_tokens:
        return 0.0
    page_tokens = set(_normalize(page_text).split())
    return sum(1 for t in claim_tokens if t in page_tokens) / len(claim_tokens)


def verify_title(
    claim_title: str,
    page_text: str,
    judge: SemanticJudge,
) -> dict:
    """返回 {status, title_pdf, similarity, method, needs_review}。"""
    if not claim_title.strip():
        return {"status": "unreadable", "title_pdf": "", "similarity": None,
                "method": "none", "needs_review": True}
    if len(page_text.strip()) < 100:
        return {"status": "unreadable", "title_pdf": "", "similarity": None,
                "method": "none", "needs_review": True}

    if judge.available:
        result = judge.json(
            system=(
                "你是文献核验助手。只输出 JSON，不要输出解释。"
                "判断 PDF 页面文字中是否出现与声称标题指向同一篇文章的标题。"
                "忽略大小写、标点、连字符、副标题、上下标、排版与 OCR 噪声；"
                "只看语义是否同一篇。拿不准时 same 为 false。"
            ),
            user=(
                f"声称标题（来自 DOI 元数据）：{claim_title}\n\n"
                f"PDF 前两页 OCR 文本：\n{page_text[:6000]}\n\n"
                '输出：{"title_pdf": "从页面中提取的标题原文", '
                '"same": true/false, "confidence": 0到1}'
            ),
        )
        if result is not None and isinstance(result.get("same"), bool):
            same = result["same"]
            confidence = float(result.get("confidence") or 0.0)
            status = "verified" if same else "mismatch"
            return {
                "status": status,
                "title_pdf": str(result.get("title_pdf") or ""),
                "similarity": round(confidence, 4),
                "method": "semantic",
                "needs_review": status == "mismatch" and confidence > 0.25,
            }

    # 无模型时的兜底：整串子串命中看 1.0，否则看词覆盖率
    similarity = 1.0 if _compact(claim_title) in _compact(page_text) else token_coverage(
        claim_title, page_text
    )
    similarity = round(similarity, 4)
    if similarity >= 0.85:
        status, needs_review = "verified", False
    elif similarity <= 0.6:
        status, needs_review = "mismatch", False
    else:
        status, needs_review = "mismatch", True
    return {
        "status": status,
        "title_pdf": claim_title if status == "verified" else "",
        "similarity": similarity,
        "method": "token_overlap_fallback",
        "needs_review": needs_review,
    }
