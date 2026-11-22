"""运行配置。密钥一律从环境变量读，不落盘、不进仓库。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


@dataclass(frozen=True)
class Config:
    # 产出目录：默认在 .private/ 下，公库零数据
    workdir: Path = Path(".private/work")
    dpi: int = 200

    # 抽样口径
    target_per_cell: int = 4
    # 「抽了 5 次」的“次”尚未定义（一轮抽样 / 一篇 / 一次重试），不得擅自当作 5 篇
    max_attempts_per_cell: int | None = None

    # Mineru 精准解析 API
    mineru_base: str = "https://mineru.net"
    mineru_api_key: str | None = None
    mineru_model: str = "vlm"  # pipeline | vlm

    # 语义判定（标题比对 / 图注判结构式）；可选，不配则退回规则辅助
    judge_base_url: str | None = None
    judge_api_key: str | None = None
    judge_model: str | None = None

    # 元数据 API 礼貌标识
    crossref_mailto: str | None = None
    openalex_mailto: str | None = None

    timeout: int = 60

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            workdir=Path(os.environ.get("CSD_WORKDIR", ".private/work")),
            mineru_base=os.environ.get("MINERU_BASE", "https://mineru.net"),
            mineru_api_key=_env("MINERU_API_KEY", "MINERU_TOKEN"),
            mineru_model=os.environ.get("MINERU_MODEL", "vlm"),
            judge_base_url=_env("CSD_JUDGE_BASE_URL", "OPENAI_BASE_URL"),
            judge_api_key=_env("CSD_JUDGE_API_KEY", "OPENAI_API_KEY"),
            judge_model=_env("CSD_JUDGE_MODEL", "OPENAI_MODEL"),
            crossref_mailto=_env("CROSSREF_MAILTO"),
            openalex_mailto=_env("OPENALEX_MAILTO"),
        )


@dataclass
class ArticleResult:
    """单篇文章的处理结论，对应 DATASET_WORKFLOW 第二、三节。"""

    doi: str
    pdf: str
    verify_status: str = "unreadable"  # verified | mismatch | unreadable
    title_claim: str = ""
    title_pdf: str = ""
    title_sim: float | None = None
    verify_method: str = ""
    needs_review: bool = False
    pages_with_figures: list[int] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    structures: list[str] = field(default_factory=list)
    outcome: str = "rejected"  # accepted | needs_review | rejected
    reject_reason: str = ""  # no_figures | no_structure | no_structure_confirmed | mismatch | unreadable | error
