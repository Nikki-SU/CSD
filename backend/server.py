"""CSD 本地后端（标准库，无 Web 框架）。

职责：任务登记、任务状态、结果读取、标注写入、缩略图静态服务、zip 导出。
数据全部落本地 data/，人可读；不连 GitHub，不进仓库。

启动：
  python -m backend.server                 # 仅本机 127.0.0.1:8765
  python -m backend.server --lan           # 绑 0.0.0.0，写接口仍需本机，只读接口要访问码
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    from .worker import Worker
except ImportError:  # 允许直接 python backend/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from worker import Worker

APP_VERSION = "0.5.1"

# 引导部署的四段版本号：任何嵌入文件（后端源码/启动器）改动后 bump 对应段。
# 前端 bootstrapFiles.ts 里的 BUNDLE_VERSION 由 embed 脚本从这段读，比对后提示用户更新本地文件。
# 0.5.1: 修编排KeyError/评估0样本/真300dpi裁图/渲染hash/路径防护/页级口径/字体跨平台。
VERSION = {"frontend": 2, "backend": 2, "model": 1, "data": 1}
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
FRONTEND_DIST = ROOT / "dist" if (ROOT / "dist").exists() else ROOT / "frontend" / "dist"

JOB_ID_RE = re.compile(r"^j_\d{8}_\d{4}_[0-9a-f]{6}$")
STAGES = ("queued", "ingest", "docverify", "render", "coarse", "fine", "chemcheck", "done", "failed")

_label_lock = threading.Lock()
_data_root = DEFAULT_DATA
_access_code = ""
_lan_mode = False
_worker: Worker | None = None


# ---------- 通用工具 ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_job_id() -> str:
    return datetime.now(timezone.utc).strftime("j_%Y%m%d_%H%M_") + secrets.token_hex(3)


def job_dir(job_id: str) -> Path:
    return _data_root / "inbox" / job_id


def outbox_dir(job_id: str) -> Path:
    return _data_root / "outbox" / job_id


def read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_join(base: Path, relative: str) -> Path | None:
    """把相对路径限制在 base 内，挡住 ../ 穿越。"""
    target = (base / unquote(relative)).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def client_is_local(client_ip: str) -> bool:
    return client_ip in ("127.0.0.1", "::1", "localhost")


# ---------- 任务 ----------

def create_job(payload: dict) -> dict:
    source_type = payload.get("source_type") or "pdf"
    if source_type not in ("pdf", "image"):
        raise ValueError("source_type 只能是 pdf 或 image")
    source_ref = (payload.get("source_ref") or "").strip()
    if not source_ref:
        raise ValueError("source_ref 不能为空")
    if not Path(source_ref).exists():
        raise ValueError(f"source_ref 指向的路径不存在: {source_ref}")

    job_id = new_job_id()
    job = {
        "job_id": job_id,
        "schema": 2,
        "created_at": now_iso(),
        "source_type": source_type,
        "source_ref": source_ref,
        "doi": None,
        "style_profile": payload.get("style_profile") or "",
        # 文件夹任务默认只跑 50 篇一批（MolDet 约 10s/篇），避免一次跑几千篇卡死
        "params": {"max_candidates": 3, "limit": 50, **(payload.get("params") or {}), **({"topo_mode": payload["topo_mode"]} if payload.get("topo_mode") else {})},
        "reviewer": payload.get("reviewer"),
        "year": payload.get("year") or "",
        "status": "queued",
    }
    write_json(job_dir(job_id) / "job.json", job)
    write_json(outbox_dir(job_id) / ".progress.json",
               {"stage": "queued", "pct": 0, "message": "已登记，等待处理", "updated_at": now_iso()})
    return job


def list_jobs(status: str | None = None) -> list[dict]:
    inbox = _data_root / "inbox"
    jobs = []
    if not inbox.exists():
        return jobs
    for path in sorted(inbox.glob("*/job.json")):
        job = read_json(path)
        if not job:
            continue
        progress = read_json(outbox_dir(job["job_id"]) / ".progress.json") or {}
        item = {**job, "progress": progress}
        if status and progress.get("stage") != status:
            continue
        jobs.append(item)
    jobs.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    return jobs


def get_job(job_id: str) -> dict | None:
    job = read_json(job_dir(job_id) / "job.json")
    if not job:
        return None
    job["progress"] = read_json(outbox_dir(job_id) / ".progress.json") or {}
    return job


def job_artifact(job_id: str, name: str):
    return read_json(outbox_dir(job_id) / name)


def save_labels(payload: dict) -> dict:
    job_id = payload.get("job_id") or ""
    if not JOB_ID_RE.match(job_id):
        raise ValueError("job_id 非法")
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        raise ValueError("rows 必须是数组")
    path = _data_root / "labels" / f"{job_id}.csv"
    fields = ["job_id", "figure_id", "selected_rank", "verdict", "redrawn_smiles", "reviewer", "reviewed_at"]
    with _label_lock:
        existing = {}
        if path.exists():
            for row in csv.DictReader(path.open(encoding="utf-8-sig")):
                existing[(row["figure_id"], row["reviewer"])] = row
        for row in rows:
            key = (str(row.get("figure_id")), str(row.get("reviewer") or ""))
            existing[key] = {
                "job_id": job_id,
                "figure_id": key[0],
                "selected_rank": row.get("selected_rank") if row.get("selected_rank") is not None else "",
                "verdict": row.get("verdict") or "",
                "redrawn_smiles": row.get("redrawn_smiles") or "",
                "reviewer": key[1],
                "reviewed_at": row.get("reviewed_at") or now_iso(),
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(existing.values())
    return {"job_id": job_id, "count": len(existing)}


def load_labels(job_id: str) -> list[dict]:
    """读某任务的人工判定（供审阅/报告/风格/归因页显示真实结果）。"""
    if not JOB_ID_RE.match(job_id):
        raise ValueError("job_id 非法")
    path = _data_root / "labels" / f"{job_id}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def overview() -> dict:
    """聚合所有任务的真实统计，供归因对比页。数字从 job/figures/labels 算，不造假。"""
    jobs = list_jobs()
    total_figures = 0
    reviewed = 0
    rejected = 0
    for job in jobs:
        figs = job_artifact(job["job_id"], "figures.json") or {}
        total_figures += int(figs.get("count") or 0)
        rows = load_labels(job["job_id"])
        reviewed += len({r.get("figure_id") for r in rows})
        rejected += sum(1 for r in rows if r.get("verdict") in {"wrong", "none", "bad", "false", "style_bad"})
    return {
        "jobs": len(jobs),
        "figures": total_figures,
        "reviewed": reviewed,
        "rejected": rejected,
        "by_status": {
            s: sum(1 for j in jobs if j.get("status") == s)
            for s in {j.get("status") for j in jobs}
        },
    }


def save_topo(payload: dict) -> dict:
    job_id = payload.get("job_id") or ""
    if not JOB_ID_RE.match(job_id):
        raise ValueError("job_id 非法")
    rows = payload.get("rows") or []
    fields = ["job_id", "figure_id", "feature", "expected", "detected", "reviewer", "reviewed_at"]
    path = _data_root / "labels" / f"{job_id}_topo.csv"
    with _label_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "job_id": job_id,
                    "figure_id": row.get("figure_id") or "",
                    "feature": row.get("feature") or "",
                    "expected": row.get("expected") or "",
                    "detected": row.get("detected") or "",
                    "reviewer": row.get("reviewer") or "",
                    "reviewed_at": row.get("reviewed_at") or now_iso(),
                })
    return {"job_id": job_id, "count": len(rows)}


def export_zip(job_id: str) -> bytes:
    base = outbox_dir(job_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file():
                    bundle.write(path, path.relative_to(base).as_posix())
        labels = _data_root / "labels" / f"{job_id}.csv"
        if labels.exists():
            bundle.write(labels, f"labels/{job_id}.csv")
    return buffer.getvalue()


def delete_job(job_id: str) -> bool:
    removed = False
    for path in (job_dir(job_id), outbox_dir(job_id)):
        if path.exists():
            shutil.rmtree(path)
            removed = True
    labels = _data_root / "labels" / f"{job_id}.csv"
    if labels.exists():
        labels.unlink()
    return removed


# ---------- 设置与目录扫描 ----------

def settings_path() -> Path:
    return _data_root / "config.json"


def load_settings() -> dict:
    return read_json(settings_path()) or {}


def public_settings() -> dict:
    saved = load_settings()
    key = (saved.get("mineru_api_key") or "").strip()
    return {
        "mineru_key_set": bool(key),
        "mineru_key_tail": key[-4:] if key else "",
        "mineru_model": saved.get("mineru_model") or "vlm",
    }


def save_settings(payload: dict) -> dict:
    saved = load_settings()
    if "mineru_key" in payload:
        key = (payload.get("mineru_key") or "").strip()
        if key:
            saved["mineru_api_key"] = key
        else:
            saved.pop("mineru_api_key", None)
    if payload.get("mineru_model"):
        saved["mineru_model"] = payload["mineru_model"]
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return public_settings()


def scan_directory(raw_path: str, limit: int = 500) -> dict:
    base = Path(raw_path).expanduser().resolve()
    if not base.exists():
        raise ValueError(f"路径不存在: {base}")
    if not base.is_dir():
        raise ValueError(f"不是目录: {base}")
    kinds = {".pdf": "pdf", ".png": "image", ".jpg": "image", ".jpeg": "image",
             ".tif": "image", ".tiff": "image"}
    items = []
    for path in sorted(base.iterdir()):
        if not path.is_file() or path.suffix.lower() not in kinds:
            continue
        match = re.search(r"(1[89]\d{2}|20\d{2})", path.stem)
        items.append({
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "kind": kinds[path.suffix.lower()],
            "year": int(match.group(1)) if match else None,
        })
        if len(items) >= limit:
            break
    return {"path": str(base), "count": len(items), "items": items}


def create_jobs_batch(payload: dict) -> dict:
    paths = payload.get("paths") or []
    if not isinstance(paths, list) or not paths:
        raise ValueError("paths 不能为空")
    source_type = payload.get("source_type") or "pdf"
    style = payload.get("style_profile") or ""
    jobs, errors = [], []
    for raw in paths:
        try:
            job = create_job({
                "source_type": source_type,
                "source_ref": raw,
                "style_profile": style,
                "year": payload.get("year") or "",
            })
            if _worker:
                _worker.submit(job["job_id"])
            jobs.append(job)
        except ValueError as exc:
            errors.append({"path": raw, "error": str(exc)})
    return {"created": len(jobs), "jobs": jobs, "errors": errors}


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    server_version = f"CSD/{APP_VERSION}"
    protocol_version = "HTTP/1.1"

    def _client_is_local(self) -> bool:
        return client_is_local((self.client_address or ("",))[0])

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8",
              extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send(204, b"")

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message, "status": status})

    def _authorized(self) -> bool:
        if not _lan_mode or self._client_is_local():
            return True
        return self.headers.get("X-Access-Code", "") == _access_code

    def _write_allowed(self) -> bool:
        return self._client_is_local()

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("请求体不是合法 JSON")
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def log_message(self, fmt: str, *args) -> None:  # 安静些，只留错误
        if args and str(args[0]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._authorized():
            return self._error(403, "需要访问码")

        if path == "/api/health":
            return self._json(200, {
                "status": "ok", "version": APP_VERSION, "versions": VERSION, "lan": _lan_mode,
                "data_dir": str(_data_root), "time": now_iso(),
            })

        if path == "/api/version":
            return self._json(200, VERSION)

        if path == "/api/jobs":
            status = (parse_qs(parsed.query).get("status") or [None])[0]
            jobs = list_jobs(status)
            return self._json(200, {"count": len(jobs), "jobs": jobs})

        if path == "/api/settings":
            return self._json(200, public_settings())

        if path == "/api/overview":
            try:
                return self._json(200, overview())
            except ValueError as exc:
                return self._error(400, str(exc))

        if path == "/api/labels":
            job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
            try:
                return self._json(200, {"job_id": job_id, "rows": load_labels(job_id)})
            except ValueError as exc:
                return self._error(400, str(exc))

        if path == "/api/scan":
            if not self._write_allowed():
                return self._error(403, "扫描目录仅限本机")
            target = (parse_qs(parsed.query).get("path") or [""])[0]
            try:
                return self._json(200, scan_directory(target))
            except ValueError as exc:
                return self._error(400, str(exc))

        match = re.match(r"^/api/jobs/([^/]+)$", path)
        if match:
            job = get_job(match.group(1))
            return self._json(200, job) if job else self._error(404, "任务不存在")

        match = re.match(r"^/api/jobs/([^/]+)/(result|doc|metrics|figures)$", path)
        if match:
            job_id, name = match.group(1), match.group(2)
            data = job_artifact(job_id, f"{name}.json")
            return self._json(200, data) if data is not None else self._error(404, "尚未生成")

        # 单个结构式图的 A/B/C 候选（含 SMILES，供审阅页 + 重绘预置）
        match = re.match(r"^/api/jobs/([^/]+)/candidates/([^/]+)$", path)
        if match:
            job_id, figure_id = match.group(1), match.group(2)
            data = job_artifact(job_id, f"candidates/{figure_id}_candidates.json")
            if data is None:
                # 尚未跑过候选流程：返回明确的空结构，前端显示"候选未生成"
                return self._json(200, {"figure_id": figure_id, "candidates": [], "generated": False})
            return self._json(200, data)

        match = re.match(r"^/api/export/([^/]+)$", path)
        if match:
            if not self._write_allowed():
                return self._error(403, "导出仅限本机")
            job_id = match.group(1)
            if not outbox_dir(job_id).exists():
                return self._error(404, "没有可导出的结果")
            data = export_zip(job_id)
            return self._send(200, data, "application/zip", {
                "Content-Disposition": f'attachment; filename="{job_id}.zip"'
            })

        match = re.match(r"^/files/([^/]+)/(.+)$", path)
        if match:
            target = safe_join(outbox_dir(match.group(1)), match.group(2))
            if target is None or not target.is_file():
                return self._error(404, "文件不存在")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), ctype)

        return self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._authorized():
            return self._error(403, "需要访问码")
        if not self._write_allowed():
            return self._error(403, "写操作仅限本机")
        try:
            payload = self._body()
            if path == "/api/jobs":
                job = create_job(payload)
                if _worker:
                    _worker.submit(job["job_id"])
                return self._json(201, job)
            if path == "/api/labels":
                return self._json(200, save_labels(payload))
            if path == "/api/labels/topo":
                return self._json(200, save_topo(payload))
            if path == "/api/settings":
                return self._json(200, save_settings(payload))
            if path == "/api/jobs/batch":
                return self._json(201, create_jobs_batch(payload))
        except ValueError as exc:
            return self._error(400, str(exc))
        return self._error(404, "接口不存在")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        match = re.match(r"^/api/jobs/([^/]+)$", parsed.path)
        if not match:
            return self._error(404, "接口不存在")
        if not self._authorized():
            return self._error(403, "需要访问码")
        if not self._write_allowed():
            return self._error(403, "删除仅限本机")
        confirm = (parse_qs(parsed.query).get("confirm") or [""])[0]
        if confirm != "true":
            return self._error(400, "需要 confirm=true 才删除")
        removed = delete_job(match.group(1))
        return self._json(200, {"deleted": removed})

    def _serve_static(self, path: str) -> None:
        if not FRONTEND_DIST.exists():
            body = ("前端尚未构建。先在 frontend/ 执行 npm run build，"
                    "或直接用 CLI 处理数据。\n").encode("utf-8")
            return self._send(200, body, "text/plain; charset=utf-8")
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = safe_join(FRONTEND_DIST, rel)   # 挡住 ../ 穿越读源码
        if target is None or not target.is_file():
            target = FRONTEND_DIST / "index.html"
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return self._send(200, target.read_bytes(), ctype)


def main() -> None:
    global _data_root, _access_code, _lan_mode, _worker
    parser = argparse.ArgumentParser(prog="csd-server")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=8765)
    # 引导部署时数据落在启动器所在目录；也支持 CSD_DATA_DIR 环境变量覆盖（测试/多实例）。
    parser.add_argument("--data-dir", default=os.environ.get("CSD_DATA_DIR") or str(DEFAULT_DATA))
    parser.add_argument("--lan", action="store_true", help="绑 0.0.0.0，生成访问码")
    parser.add_argument("--dry-run", action="store_true", help="不调 MinerU，只跑核验与页处理")
    args = parser.parse_args()

    _data_root = Path(args.data_dir).resolve()
    for name in ("inbox", "outbox", "labels"):
        (_data_root / name).mkdir(parents=True, exist_ok=True)

    _lan_mode = args.lan
    host = args.host or ("0.0.0.0" if _lan_mode else "127.0.0.1")
    if _lan_mode:
        _access_code = os.environ.get("CSD_ACCESS_CODE") or secrets.token_hex(4)
        print(f"[局域网] 访问码: {_access_code}（用 --lan 启动时加请求头 X-Access-Code）")

    _worker = Worker(_data_root, dry_run=args.dry_run)
    _worker.start()
    print(f"任务执行: {'dry-run（不调 MinerU）' if _worker.dry_run else '完整处理'}")

    server = ThreadingHTTPServer((host, args.port), Handler)
    print(f"CSD 后端已启动: http://{host}:{args.port}")
    print(f"数据目录: {_data_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
