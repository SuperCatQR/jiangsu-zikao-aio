"""Public 15043/15044 sources must list official jseea URLs; humans own publish flags."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from check_source_links import extract_refs

ROOT = Path(__file__).resolve().parents[1]

OFFICIAL_URLS = {
    "15043": (
        "https://www.jseea.cn/webfile/selflearning_jcdg/2025-02-25/7300038163492245504.html",
        "https://www.jseea.cn/webfile/upload/2025/02-25/14-25-1908861288944883.pdf",
    ),
    "15044": (
        "https://www.jseea.cn/webfile/selflearning_jcdg/2025-02-25/7300038247357353984.html",
        "https://www.jseea.cn/webfile/upload/2025/02-25/14-25-4401912037600155.pdf",
    ),
}


def _sources_urls(code: str) -> set[str]:
    path = ROOT / "content" / "jiangsu" / "courses" / code / "sources.md"
    return {ref.url for ref in extract_refs(path)}


def _index_text(code: str) -> str:
    return (ROOT / "content" / "jiangsu" / "courses" / code / "index.md").read_text(
        encoding="utf-8"
    )


def test_15043_sources_include_official_jseea_urls():
    urls = _sources_urls("15043")
    for expected in OFFICIAL_URLS["15043"]:
        assert expected in urls


def test_15044_sources_include_official_jseea_urls():
    urls = _sources_urls("15044")
    for expected in OFFICIAL_URLS["15044"]:
        assert expected in urls


def test_neither_index_is_reviewed_or_publishable():
    for code in ("15043", "15044"):
        text = _index_text(code)
        assert not re.search(r"(?m)^reviewed:\s*true\s*$", text)
        assert not re.search(r"(?m)^lifecycle:\s*publishable\s*$", text)
