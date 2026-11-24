"""下载 MolDet 基础权重到 models/，多源回退 + SHA256 校验。

由 run-windows.bat 在装完 Python 依赖后调用。权重固定不变（不随训练更新）；
训练产物走 assets/，与这里无关。

用法：python bootstrap/fetch_models.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

REPO = "UniParser/MolDet"
FILENAME = "moldet_yolo11l_960_doc.pt"
SHA256 = "6e1cd400e9e423a7e150296444178245244e299871a649b2de5dfce077d7c98e"
SIZE_MB = 49


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _try_direct(url: str, target: Path) -> bool:
    """用 urllib 直连国内镜像下载，主动清掉代理变量（避免代理软件把 HF 请求转成 502）。"""
    tmp = target.with_suffix(".download")
    try:
        print(f"  直连下载 {url.split('/')[2]} ...", flush=True)
        # 国内镜像应直连；有些用户开着代理软件会把请求转发到国外导致失败，这里清掉
        saved = {k: os.environ.pop(k, None) for k in
                 ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy")}
        try:
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=60) as resp, tmp.open("wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        got = _sha(tmp)
        if got != SHA256:
            print(f"  SHA 不符：{got[:16]}...")
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(target)
        print(f"  校验通过：{target.name}")
        return True
    except Exception as exc:
        print(f"  直连异常：{type(exc).__name__}: {str(exc)[:120]}")
        tmp.unlink(missing_ok=True)
        return False


def _try_hub(endpoint: str | None, target: Path) -> bool:
    """用 huggingface_hub 从指定端点下载；成功且校验通过返回 True。"""
    try:
        from huggingface_hub import hf_hub_download
        if endpoint:
            os.environ["HF_ENDPOINT"] = endpoint
        print(f"  尝试 {endpoint or 'huggingface.co'} ...", flush=True)
        p = hf_hub_download(repo_id=REPO, filename=FILENAME, local_dir=str(target.parent))
        got = _sha(Path(p))
        if got != SHA256:
            print(f"  SHA 不符：{got[:16]}...，换下一个源")
            return False
        if Path(p).name != FILENAME:
            Path(p).rename(target)
        print(f"  校验通过：{target.name} ({SIZE_MB} MB)")
        return True
    except Exception as exc:
        print(f"  失败：{type(exc).__name__}: {str(exc)[:160]}")
        return False


def main() -> None:
    # 基于当前工作目录（启动器已 cd 到 BASE=requirements 所在目录），
    # 不用 __file__——开发时脚本在 bootstrap/、引导时在根目录，__file__ 会算错位置。
    target = Path.cwd() / "models" / FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and _sha(target) == SHA256:
        print(f"MolDet 权重已就绪：{target}")
        return
    if target.exists():
        print("已有权重校验失败，重新下载")
        target.unlink()

    print(f"首次准备 MolDet 分子检测权重（约 {SIZE_MB} MB）...")
    # ModelScope（阿里魔搭，国内直连最稳）优先，其次 hf-mirror，最后 HF
    urls = [
        f"https://www.modelscope.cn/models/{REPO}/resolve/master/{FILENAME}",
        f"https://hf-mirror.com/{REPO}/resolve/main/{FILENAME}",
        f"https://huggingface.co/{REPO}/resolve/main/{FILENAME}",
    ]
    for url in urls:
        if _try_direct(url, target):
            break
    else:
        for endpoint in ("https://hf-mirror.com", None):
            if _try_hub(endpoint, target):
                break
        else:
            print("[ERROR] 所有源都失败。检查网络或手动下载到 models/：", file=sys.stderr)
            print(f"  {FILENAME}  SHA256={SHA256}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
