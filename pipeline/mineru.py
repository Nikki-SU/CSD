"""Mineru 精准解析 API 客户端（批量上传 → 轮询 → 下载解压）。

接口依据：https://mineru.net/doc/docs/ （v4）
- 申请上传链接：POST /api/v4/file-urls/batch
- 查询批量结果：GET  /api/v4/extract-results/batch/{batch_id}
"""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import requests

from .config import Config


class MineruError(RuntimeError):
    pass


class MineruClient:
    def __init__(self, config: Config, poll_interval: int = 5, poll_timeout: int = 1800):
        if not config.mineru_api_key:
            raise MineruError("缺少 MinerU API key：请设置环境变量 MINERU_API_KEY")
        self.token = config.mineru_api_key
        self.base = config.mineru_base.rstrip("/")
        self.model = config.mineru_model
        self.timeout = config.timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    def parse_files(
        self,
        files: list[Path],
        data_ids: list[str] | None = None,
        out_dir: str | Path = ".",
        is_ocr: bool = True,
    ) -> dict[str, Path]:
        """批量解析本地文件，返回 data_id → 解压目录（含 full.md / content_list.json）。"""
        files = [Path(f) for f in files]
        if not files:
            return {}
        data_ids = data_ids or [f.stem for f in files]
        if len(data_ids) != len(files):
            raise ValueError("data_ids 数量必须与 files 一致")

        batch_id, upload_urls = self._request_upload_urls(files, data_ids, is_ocr)
        for path, url in zip(files, upload_urls):
            self._upload(path, url)

        results = self._poll(batch_id)
        return self._download_all(results, out_dir)

    def _request_upload_urls(
        self, files: list[Path], data_ids: list[str], is_ocr: bool
    ) -> tuple[str, list[str]]:
        payload = {
            "files": [
                {"name": path.name, "data_id": data_id, "is_ocr": is_ocr}
                for path, data_id in zip(files, data_ids)
            ],
            "model_version": self.model,
            "enable_formula": True,
            "enable_table": True,
            "language": "en",
        }
        resp = requests.post(
            f"{self.base}/api/v4/file-urls/batch",
            headers=self._headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise MineruError(f"申请上传链接失败：{body.get('msg') or body}")
        data = body["data"]
        return data["batch_id"], data["file_urls"]

    def _upload(self, path: Path, url: str) -> None:
        with path.open("rb") as handle:
            resp = requests.put(url, data=handle, timeout=max(self.timeout, 300))
        if resp.status_code not in (200, 201):
            raise MineruError(f"上传失败 {path.name}：HTTP {resp.status_code}")

    def _poll(self, batch_id: str) -> list[dict]:
        deadline = time.monotonic() + self.poll_timeout
        url = f"{self.base}/api/v4/extract-results/batch/{batch_id}"
        while time.monotonic() < deadline:
            resp = requests.get(url, headers=self._headers, timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                raise MineruError(f"查询批量结果失败：{body.get('msg') or body}")
            results = body["data"].get("extract_result") or []
            states = {item.get("state") for item in results}
            if results and states <= {"done", "failed"}:
                return results
            time.sleep(self.poll_interval)
        raise MineruError(f"等待解析超时（batch_id={batch_id}）")

    def _download_all(self, results: list[dict], out_dir: str | Path) -> dict[str, Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        mapping: dict[str, Path] = {}
        for item in results:
            data_id = item.get("data_id") or Path(item.get("file_name", "x")).stem
            if item.get("state") != "done" or not item.get("full_zip_url"):
                raise MineruError(
                    f"解析失败 {item.get('file_name')}：{item.get('err_msg') or item.get('state')}"
                )
            target = out_dir / data_id
            if not self._find_output_root(target):
                self._download_zip(item["full_zip_url"], target)
            root = self._find_output_root(target)
            if root is None:
                raise MineruError(f"解析结果缺少 content_list.json：{item.get('file_name')}")
            mapping[data_id] = root
        return mapping

    @staticmethod
    def _find_output_root(directory: Path) -> Path | None:
        """Mineru 的输出文件可能带 UUID 前缀，且 zip 可能多套一层目录。"""
        direct = directory / "content_list.json"
        if direct.exists():
            return directory
        if not directory.exists():
            return None
        for candidate in sorted(directory.rglob("*_content_list.json")):
            if candidate.name.endswith("_content_list_v2.json"):
                continue
            return candidate.parent
        return None

    def _download_zip(self, url: str, target: Path) -> None:
        resp = requests.get(url, timeout=max(self.timeout, 300))
        resp.raise_for_status()
        zip_path = target.with_suffix(".zip")
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(resp.content)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                name = Path(member.filename)
                if name.is_absolute() or ".." in name.parts:
                    continue
                archive.extract(member, target)
        zip_path.unlink(missing_ok=True)
