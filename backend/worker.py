"""任务执行队列：串行跑 job，写 outbox 与 progress。

一次一个 job，避免 MinerU 与 PDF 渲染并发抢资源；失败写 failed 与错误信息，
不吞异常。
"""

from __future__ import annotations

import json
import queue
import threading
import traceback
from dataclasses import replace
from pathlib import Path

from pipeline.article import process_article
from pipeline.config import Config
from pipeline.result_build import doi_from_filename, write_outputs


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class Worker:
    def __init__(self, data_root: str | Path, config: Config | None = None, dry_run: bool = False):
        self.data_root = Path(data_root)
        self.config = config or Config.from_env()
        self.force_dry_run = bool(dry_run)
        self.dry_run = self.force_dry_run or not self.config.mineru_api_key
        self.queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self.current: str | None = None

    def _effective_config(self) -> Config:
        """每次执行前重读 data/config.json，前端刚保存的 key 立即生效。"""
        config = Config.from_env()
        saved = _read_json(self.data_root / "config.json") or {}
        key = (saved.get("mineru_api_key") or "").strip()
        if key:
            config = replace(config, mineru_api_key=key)
        if saved.get("mineru_model"):
            config = replace(config, mineru_model=saved["mineru_model"])
        return config

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="csd-worker", daemon=True)
        self._thread.start()

    def submit(self, job_id: str) -> None:
        self.queue.put(job_id)

    def _loop(self) -> None:
        while self._running:
            try:
                job_id = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._run(job_id)
            except Exception:  # noqa: BLE001
                self._progress(job_id, "failed", 0, "执行异常，见 worker 日志")
                print(f"[worker] {job_id} 异常:\n{traceback.format_exc()}", flush=True)
            finally:
                self.queue.task_done()

    def _progress(self, job_id: str, stage: str, pct: int, message: str) -> None:
        _write_json(
            self.data_root / "outbox" / job_id / ".progress.json",
            {"stage": stage, "pct": pct, "message": message, "updated_at": _now()},
        )

    def _set_status(self, job_id: str, status: str) -> None:
        path = self.data_root / "inbox" / job_id / "job.json"
        job = _read_json(path)
        if job:
            job["status"] = status
            _write_json(path, job)

    def _run(self, job_id: str) -> None:
        self.current = job_id
        job = _read_json(self.data_root / "inbox" / job_id / "job.json")
        if not job:
            return
        out_dir = self.data_root / "outbox" / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = Path(job.get("source_ref") or "")
        if not pdf_path.exists():
            self._progress(job_id, "failed", 0, f"源文件不存在: {pdf_path}")
            self._set_status(job_id, "failed")
            return

        doi = (job.get("doi") or doi_from_filename(pdf_path)).strip()
        self._progress(job_id, "ingest", 10, "读取 PDF 与元数据")
        self._set_status(job_id, "running")

        config = self._effective_config()
        dry_run = self.force_dry_run or not config.mineru_api_key

        try:
            self._progress(job_id, "docverify", 30, "核验标题与页选择")
            result = process_article(
                pdf_path,
                doi,
                out_dir / "work",
                config=config,
                dry_run=dry_run,
            )
            self._progress(job_id, "render", 70, "生成结果与缩略图")
            payload = write_outputs(job, result, pdf_path, out_dir)
            stage = "done"
            suffix = "（dry-run，未解析图片）" if dry_run else ""
            message = f"完成：{payload['counts']['figures']} 张图，结论 {result.outcome}{suffix}"
            self._progress(job_id, stage, 100, message)
            self._set_status(job_id, "done" if result.outcome == "accepted" else "partial")
        except Exception as exc:  # noqa: BLE001
            self._progress(job_id, "failed", 0, f"{type(exc).__name__}: {exc}")
            self._set_status(job_id, "failed")
            raise
        finally:
            self.current = None


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
