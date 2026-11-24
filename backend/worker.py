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

    def _run_folder(self, job_id: str, job: dict, folder: Path, out_dir: Path) -> None:
        """文件夹任务：PDF 串行识别 → 结构式裁图合集 → 瀑布流。

        用 MolDet 检分子结构式（第一批直接用现成模型攒数据），裁图落 thumbs/，
        写 figures.json 供前端 ScreenPage 读取。剔除由前端回写 labels。
        """
        import shutil
        from training.detect import load_model, detect_page, resolve_pdf

        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            self._progress(job_id, "failed", 0, f"文件夹没有 PDF: {folder}")
            self._set_status(job_id, "failed")
            return
        limit = int(job.get("params", {}).get("limit") or 0)  # 0 = 全部
        if limit:
            pdfs = pdfs[:limit]

        self._set_status(job_id, "running")
        self._progress(job_id, "ingest", 5, f"加载 MolDet，{len(pdfs)} 篇 PDF 待识别")
        try:
            model = load_model()
        except Exception as exc:
            self._progress(job_id, "failed", 0, f"MolDet 加载失败: {exc}")
            self._set_status(job_id, "failed")
            return

        thumbs = out_dir / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        import pymupdf, cv2, numpy as np
        figures = []
        for i, pdf in enumerate(pdfs):
            pct = 5 + int(90 * (i + 1) / len(pdfs))
            self._progress(job_id, "detect", pct, f"识别 {i+1}/{len(pdfs)}: {pdf.name}")
            try:
                doc = pymupdf.open(pdf)
                for pinfo in [detect_page(model, page) for page in doc]:
                    if not pinfo["boxes"]:
                        continue
                    pix = doc[pinfo["page"]-1].get_pixmap(dpi=150)
                    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n >= 3 else arr
                    for box in pinfo["boxes"]:
                        x1, y1, x2, y2 = [int(v) for v in box["bbox"]]
                        pad = 6
                        crop = img[max(0, y1-pad):min(img.shape[0], y2+pad),
                                   max(0, x1-pad):min(img.shape[1], x2+pad)]
                        if crop.size == 0:
                            continue
                        fid = f"p{pinfo['page']:03d}_f{len(figures):04d}"
                        cv2.imwrite(str(thumbs / f"{fid}.png"), crop)
                        figures.append({
                            "figure_id": fid,
                            "image": f"thumbs/{fid}.png",
                            "article": pdf.name,
                            "page": pinfo["page"],
                            "conf": round(float(box["conf"]), 3),
                            "bbox": box["bbox"],
                            "has_structure": None,
                        })
                doc.close()
            except Exception as exc:
                print(f"[worker] {pdf.name} 识别失败: {exc}", flush=True)

        _write_json(out_dir / "figures.json", {
            "job_id": job_id,
            "source": "moldet-doc",
            "count": len(figures),
            "figures": figures,
        })
        self._progress(job_id, "done", 100, f"完成：{len(pdfs)} 篇识别出 {len(figures)} 个结构式，待瀑布流筛选")
        self._set_status(job_id, "done")

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

        # 文件夹路径 → MolDet 批量识别所有 PDF，产出结构式图合集进瀑布流
        if pdf_path.is_dir():
            return self._run_folder(job_id, job, pdf_path, out_dir)

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
