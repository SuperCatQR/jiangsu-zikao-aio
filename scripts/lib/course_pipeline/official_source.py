"""官方来源抓取：jseea.cn 域名白名单 + sha256 + 快照落盘。

**B1 边界（GC15）**：本迭代只提供库函数，联网分支仅由 monkeypatch 测试覆盖（落盘根传 `tmp_path`）；
仓库内不新增 / 不修改 `sources/jiangsu/public-official/**`，也不写 `ops/jiangsu/source-links.baseline.json`（GC14）。
真实官方原件入库按 spec § Roadmap 的 **B2 启动门槛③** 执行。

判定口径：白名单 = `jseea.cn` 及其**子域**（`host == "jseea.cn"` 或 `host.endswith(".jseea.cn")`）。
既有 `scripts/snapshot-official-sources.py` 用 `host.endswith("jseea.cn")`，会把 `eviljseea.cn` 误判为官方；
本模块不复刻该缺陷（那个脚本不改，本模块也不复用它的判定）。

检查顺序：先白名单（`ValueError`），再 `offline`（`RuntimeError`），再显式 `root`（`RuntimeError`）——
非官方 URL 在任何模式下都不得触网，也不得因为 `offline=True` 而把「域名不合规」报成「离线不可用」。
"""
from __future__ import annotations

import hashlib
import re
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

OFFICIAL_DOMAIN = "jseea.cn"
SNAPSHOT_DIR = Path("sources") / "jiangsu" / "public-official"
DEFAULT_KIND = "syllabi"
TIMEOUT_SECONDS = 30

_SLUG_SAFE_RE = re.compile(r"[^0-9A-Za-z._-]+")


def is_official_url(url: str) -> bool:
    """`jseea.cn` 及其子域才算官方来源。"""
    host = (urlparse(url).hostname or "").lower()
    return host == OFFICIAL_DOMAIN or host.endswith("." + OFFICIAL_DOMAIN)


def _slug(url: str) -> str:
    """URL 末段 → 文件名安全的 slug（无末段时用 `index`）。"""
    path = urlparse(url).path
    tail = Path(path).name
    stem = Path(tail).stem if tail else ""
    slug = _SLUG_SAFE_RE.sub("-", stem).strip("-.")
    return slug or "index"


def _snapshot_target(root: Path, url: str) -> Path:
    # simplify: kind/slug 由 URL 推导，与既有手工整理的目录名（如 `xi-thought-gaogang`）不同名；
    # B2 的真实取证流程按内容类别决定目录，届时把 kind/slug 变成入参即可。
    slug = _slug(url)
    suffix = Path(urlparse(url).path).suffix or ".html"
    return root / SNAPSHOT_DIR / DEFAULT_KIND / slug / f"{slug}{suffix}"


def fetch_official_source(url: str, *, offline: bool = True, root: Path | None = None) -> dict:
    """抓取单个官方来源并落盘快照，返回 `{url, host, sha256, fetched_at, status, snapshot_path, content_type}`。

    `offline=True`（默认）→ `RuntimeError("offline: fetch_official_source")`；非 `jseea.cn` 域名 → `ValueError`。
    联网落盘必须**显式**传 `root`，省略即 `RuntimeError`：默认目标曾从模块路径推导出仓库根，正是 GC15
    本迭代禁止写入的路径（`sources/jiangsu/public-official/**`），因此失败关闭而不是静默落盘（B2 再定默认）。
    `snapshot_path` 是相对 `root` 的 POSIX 路径；B1 只由测试传 `tmp_path`。
    唯一网络调用是 `urllib.request.urlopen`（stdlib，GC12），`read()` 的输出按**字节**落盘并现算 sha256。
    """
    if not is_official_url(url):
        raise ValueError(f"non-official host: {urlparse(url).hostname or ''!r}")
    if offline:
        raise RuntimeError("offline: fetch_official_source")
    if root is None:
        raise RuntimeError("root: 联网落盘必须显式传入 root（B1 不写仓库 sources/jiangsu/public-official/**，见 GC15）")

    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read()
        headers = getattr(response, "headers", None)
        content_type = (headers.get("Content-Type", "") if headers else "") or ""

    target = _snapshot_target(root, url)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {
        "url": url,
        "host": urlparse(url).hostname or "",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "fetched_at": date.today().isoformat(),
        "status": "ok",
        "snapshot_path": target.relative_to(root).as_posix(),
        "content_type": content_type,
    }
