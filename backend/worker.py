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

        用 MolDet 检分子结构式（第一批直接用现成模型攒数据），裁图落 crops/（原图）
        与 thumbs/（缩略图），写 figures.json 供前端读取。

        裁图必须 300dpi：150dpi 下古早细线条的环会断、检测不出（实测 135×124 图
        环数=0，270×248 图环数=1、环大小=6 正确）。下游拓扑识别与匹配都读 crops/。
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
        crops = out_dir / "crops"
        crops.mkdir(parents=True, exist_ok=True)
        import pymupdf, cv2, numpy as np
        figures = []
        # MolDet 在 150dpi 上检测（速度），裁原图用 300dpi（环检测需要）
        DETECT_DPI, CROP_DPI = 150, 300
        for i, pdf in enumerate(pdfs):
            pct = 5 + int(90 * (i + 1) / len(pdfs))
            self._progress(job_id, "detect", pct, f"识别 {i+1}/{len(pdfs)}: {pdf.name}")
            try:
                doc = pymupdf.open(pdf)
                for pinfo in [detect_page(model, page) for page in doc]:
                    if not pinfo["boxes"]:
                        continue
                    # 直接用原分辨率渲染到 300dpi（不是 150dpi 插值放大——
                    # 插值不会增加信息，细键线仍是模糊的 2px，拓扑检测检不出环）。
                    pix = doc[pinfo["page"]-1].get_pixmap(dpi=CROP_DPI)
                    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n >= 3 else arr
                    scale = CROP_DPI / DETECT_DPI  # 检测框来自 150dpi，换算到 300dpi
                    for box in pinfo["boxes"]:
                        x1, y1, x2, y2 = [int(v * scale) for v in box["bbox"]]
                        pad = 6 * int(scale)
                        crop = img[max(0, y1-pad):min(img.shape[0], y2+pad),
                                   max(0, x1-pad):min(img.shape[1], x2+pad)]
                        if crop.size == 0:
                            continue
                        fid = f"p{pinfo['page']:03d}_f{len(figures):04d}"
                        cv2.imwrite(str(crops / f"{fid}.png"), crop)
                        # 缩略图给瀑布流（限宽 320，保持比例）
                        h, w = crop.shape[:2]
                        if w > 320:
                            th = cv2.resize(crop, (320, int(h * 320 / w)), interpolation=cv2.INTER_AREA)
                        else:
                            th = crop
                        cv2.imwrite(str(thumbs / f"{fid}.png"), th)
                        figures.append({
                            "figure_id": fid,
                            "image": f"crops/{fid}.png",        # 原图：拓扑识别/匹配用
                            "thumb": f"thumbs/{fid}.png",       # 缩略图：瀑布流用
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

        # 候选生成（两轮筛选）：拓扑筛 → 渲染假古董 → 比图 → A/B/C（带 SMILES）。
        # 依赖本地 SMILES 拓扑索引；索引不存在时跳过并给出明确提示（不假装有候选）。
        self._progress(job_id, "coarse", 95, f"生成候选：{len(figures)} 个结构式的两轮筛选")
        made = self._build_candidates(job_id, figures, crops, out_dir)
        self._progress(job_id, "done", 100,
                       f"完成：{len(pdfs)} 篇识别出 {len(figures)} 个结构式，"
                       f"{made} 个已生成 A/B/C 候选，待审阅")
        self._set_status(job_id, "done")

    def _build_candidates(self, job_id: str, figures: list[dict], crops: Path, out_dir: Path) -> int:
        """对每个结构式图跑两轮筛选，写 candidates/<fid>_candidates.json。返回成功数。"""
        index_path = Path(self.data_root) / "library" / "index.json.gz"
        if not index_path.exists():
            print(f"[worker] 拓扑索引不存在（{index_path}），跳过候选生成。"
                  f" 先跑 python -m training.build_library 再 build 索引。", flush=True)
            return 0
        try:
            from training.library import TopoIndex
            from training.candidates import build_candidates
        except Exception as exc:
            print(f"[worker] 导入候选模块失败: {exc}", flush=True)
            return 0
        try:
            index = TopoIndex.load(index_path)
        except Exception as exc:
            print(f"[worker] 加载拓扑索引失败: {exc}", flush=True)
            return 0

        # 风格档：用 assets/style_profiles 里第一档；没有就用默认参数（不阻断）
        style = {"name": "default", "line_width": 1.2, "font_size": 14,
                 "bond_length": -1, "mono": True, "font_path": ""}
        style_dir = Path(__file__).resolve().parent.parent / "assets" / "style_profiles"
        if style_dir.exists():
            for p in sorted(style_dir.glob("*.json")):
                try:
                    d = _read_json(p)
                    if isinstance(d, dict) and "name" in d:
                        style = d
                        break
                except Exception:
                    continue

        # 字符模板：让 topo.py 能读出结构式里的 N/O/S 标签（没有则 labels 为空）。
        # 找不到时不阻断，但 warnings 会提示"未提供字符模板"。
        tpl = Path(__file__).resolve().parent.parent / "assets" / "templates.json"
        if not tpl.exists():
            tpl = Path(self.data_root) / "templates.json"
        templates_path = str(tpl) if tpl.exists() else None

        cand_root = out_dir / "candidates"
        made = 0
        for f in figures:
            img = crops / f"{f['figure_id']}.png"
            if not img.exists():
                continue
            try:
                build_candidates(f["figure_id"], img, index, style, cand_root,
                                 templates_path=templates_path)
                made += 1
            except Exception as exc:
                print(f"[worker] 候选生成失败 {f['figure_id']}: {exc}", flush=True)
        return made

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
