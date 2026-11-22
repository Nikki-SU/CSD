"""语义判定的可插拔接口：优先调小模型（OpenAI 兼容），没配置则返回 None 交给规则兜底。"""

from __future__ import annotations

import json
import re

import requests

from .config import Config


class SemanticJudge:
    def __init__(self, config: Config):
        self.base_url = config.judge_base_url
        self.api_key = config.judge_api_key
        self.model = config.judge_model
        self.timeout = config.timeout

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def json(self, system: str, user: str) -> dict | None:
        if not self.available:
            return None
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _loads_json(content)
        except Exception:
            return None


def _loads_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
