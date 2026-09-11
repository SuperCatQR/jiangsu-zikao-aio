"""`official_source.fetch_official_source`：域名白名单 + sha256 + 快照落盘。

联网路径一律打桩（monkeypatch `urllib.request.urlopen`），落盘根一律用 `tmp_path`：
B1 不往仓库内写快照（GC15），因此本文件不触碰 `sources/jiangsu/public-official/**`。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

import pytest

from lib.course_pipeline.official_source import fetch_official_source, is_official_url

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "course_pipeline" / "jseea_syllabus_index.html"
# 基线里 15040 的官方考纲 URL（`ops/jiangsu/source-links.baseline.json`，只读输入）
OFFICIAL_URL = "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285134977044320256.html"
OFFICIAL_PDF_URL = "https://www.jseea.cn/webfile/upload/2025/02-25/14-25-1908861288944883.pdf"
NON_OFFICIAL_URLS = (
    "https://www.zikao365.com/x",
    "https://www.bilibili.com/video/BV1xx",
    # `endswith("jseea.cn")` 口径会把下面这个域名误判为官方；它不是 jseea.cn 的子域
    "https://eviljseea.cn/x",
    "http://127.0.0.1:8000/x",
    "file:///etc/passwd",
)


class _FakeResponse:
    """urlopen 的最小替身：上下文管理器 + `read()` + `headers`。"""

    def __init__(self, payload: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self._payload = payload
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def _boom(*args, **kwargs):
    raise AssertionError("offline / 非白名单路径不得联网")


def test_is_official_url_accepts_only_jseea_hosts():
    assert is_official_url(OFFICIAL_URL)
    assert is_official_url("https://jseea.cn/x")
    assert is_official_url(OFFICIAL_PDF_URL)
    for url in NON_OFFICIAL_URLS:
        assert not is_official_url(url), url


def test_fetch_rejects_non_official_host(monkeypatch):
    """白名单只允许 `jseea.cn` 及其子域：第三方站点必须 `ValueError`，且不得发起请求。"""
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    for url in NON_OFFICIAL_URLS:
        with pytest.raises(ValueError):
            fetch_official_source(url)
        with pytest.raises(ValueError):
            fetch_official_source(url, offline=False)


def test_offline_raises(monkeypatch):
    """`offline=True`（默认）必须直接失败，且绝不触网。"""
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    with pytest.raises(RuntimeError, match="^offline: fetch_official_source$"):
        fetch_official_source(OFFICIAL_URL)
    with pytest.raises(RuntimeError, match="^offline: fetch_official_source$"):
        fetch_official_source(OFFICIAL_URL, offline=True)


def test_online_writes_snapshot_to_tmp(tmp_path, monkeypatch):
    """联网分支：落盘到 `tmp_path` 的既有布局，返回 sha256 / snapshot_path / status。"""
    payload = FIXTURE.read_bytes()
    calls: list[tuple[str, object]] = []

    def _fake_urlopen(url, timeout=None):
        calls.append((url, timeout))
        return _FakeResponse(payload)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = fetch_official_source(OFFICIAL_URL, offline=False, root=tmp_path)

    assert calls and calls[0][0] == OFFICIAL_URL
    assert set(result) == {"url", "host", "sha256", "fetched_at", "status", "snapshot_path", "content_type"}
    assert result["url"] == OFFICIAL_URL
    assert result["host"] == "www.jseea.cn"
    assert result["status"] == "ok"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", result["sha256"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", result["fetched_at"])
    assert result["content_type"].startswith("text/html")

    snapshot = tmp_path / result["snapshot_path"]
    expected_root = tmp_path / "sources" / "jiangsu" / "public-official"
    assert snapshot.is_file(), result["snapshot_path"]
    assert snapshot.read_bytes() == payload
    assert snapshot.parent.parent == expected_root / "syllabi"
    assert snapshot.parent.name, "快照必须落在 <kind>/<slug>/ 布局下"

    # 同一 URL 重复抓取是同一条路径（确定性），且不写仓库（GC15）
    again = fetch_official_source(OFFICIAL_URL, offline=False, root=tmp_path)
    assert again["snapshot_path"] == result["snapshot_path"]
    assert subprocess.run(
        ["git", "diff", "--quiet", "--", "sources/jiangsu/public-official"],
        cwd=ROOT,
    ).returncode == 0


def test_snapshot_carries_bytes_not_text(tmp_path, monkeypatch):
    """PDF 等二进制来源必须按字节落盘（不得经过文本解码）。"""
    payload = b"%PDF-1.7\n\x00\x01\x02 binary\xff\n%%EOF\n"
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _FakeResponse(payload, "application/pdf"))
    result = fetch_official_source(OFFICIAL_PDF_URL, offline=False, root=tmp_path)
    snapshot = tmp_path / result["snapshot_path"]
    assert snapshot.read_bytes() == payload
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["content_type"].startswith("application/pdf")


def test_no_secret_in_errors(monkeypatch):
    """异常文案不得泄漏 `ZIKAO_LLM_API_KEY` 的值（GC9 同类约束）。"""
    secret = "sk-do-not-leak-0123456789"
    monkeypatch.setenv("ZIKAO_LLM_API_KEY", secret)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    errors = []
    for url in ("https://www.zikao365.com/" + secret, OFFICIAL_URL):
        with pytest.raises((ValueError, RuntimeError)) as excinfo:
            fetch_official_source(url)
        errors.append(str(excinfo.value))
    assert errors
    assert all(secret not in message for message in errors)


def test_baseline_is_read_only_input():
    """本模块只读基线：跑完白名单 / 抓取路径后基线字节不变（GC14）。"""
    baseline = ROOT / "ops" / "jiangsu" / "source-links.baseline.json"
    before = hashlib.sha256(baseline.read_bytes()).hexdigest()
    data = json.loads(baseline.read_text(encoding="utf-8"))
    official = sorted(url for url in data["urls"] if is_official_url(url))
    assert OFFICIAL_URL in official
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == before
