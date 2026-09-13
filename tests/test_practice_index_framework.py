"""Practice index framework: canonical H1/H2s, 真题 named gap, no body text."""
from __future__ import annotations

import re
from pathlib import Path

from tests.baseline_contract import assert_page_work_keeps_baseline_intact

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"

CANONICAL_H1 = re.compile(r"^# .+（(\d{5})）：练习与真题\s*$")
CANONICAL_H2S = ("## 资料状态", "## 练习流程", "## 记录模板", "## 边界")
PUBLISH_GATE_MARKERS = ("发布闸门", "待签字段")
ZHENTI_STATUS_OK = frozenset({"metadata-only", "missing-source"})
# Quoted passages longer than this are treated as leaked 真题 body text.
MAX_BLOCKQUOTE_CHARS = 80
def _practice_pages() -> list[Path]:
    pages = sorted(COURSES.glob("*/practice.md"))
    assert pages, "no course practice.md files found"
    return pages


def _h2_headings(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.startswith("## ")]


def _section(text: str, heading: str) -> str:
    marker = heading if heading.startswith("## ") else f"## {heading}"
    idx = text.find(marker)
    assert idx != -1, f"missing heading {marker!r}"
    rest = text[idx:]
    nxt = rest.find("\n## ", 1)
    return rest if nxt == -1 else rest[:nxt]


def test_every_practice_page_has_canonical_h1():
    for path in _practice_pages():
        first = path.read_text(encoding="utf-8").splitlines()[0]
        match = CANONICAL_H1.match(first)
        assert match, f"{path.relative_to(ROOT)} H1 is not canonical: {first!r}"
        assert match.group(1) == path.parent.name, (
            f"{path.relative_to(ROOT)} H1 code {match.group(1)} "
            f"!= directory {path.parent.name}"
        )


def test_practice_pages_have_no_publish_gate_placeholder():
    for path in _practice_pages():
        text = path.read_text(encoding="utf-8")
        for marker in PUBLISH_GATE_MARKERS:
            assert marker not in text, (
                f"{path.relative_to(ROOT)} leaked publish-gate marker {marker!r}"
            )


def test_every_practice_page_has_four_canonical_h2s():
    for path in _practice_pages():
        headings = _h2_headings(path.read_text(encoding="utf-8"))
        assert headings == list(CANONICAL_H2S), (
            f"{path.relative_to(ROOT)} H2s {headings} != {list(CANONICAL_H2S)}"
        )


def test_zhenti_named_gap_row_is_metadata_only_or_missing_source():
    for path in _practice_pages():
        block = _section(path.read_text(encoding="utf-8"), "## 资料状态")
        zhenti_rows = []
        for line in block.splitlines():
            if "历年真题" not in line or not line.startswith("|"):
                continue
            if set(line.replace("|", "").replace("-", "").replace(" ", "")) == set():
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            if cells[0] != "历年真题":
                continue
            zhenti_rows.append(cells)
        assert zhenti_rows, f"{path.relative_to(ROOT)} missing 历年真题 row"
        status = zhenti_rows[0][3]
        assert status in ZHENTI_STATUS_OK, (
            f"{path.relative_to(ROOT)} 历年真题 status {status!r} "
            f"not in {sorted(ZHENTI_STATUS_OK)}"
        )


def test_practice_pages_have_no_quoted_question_passages():
    for path in _practice_pages():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.lstrip()
            if not stripped.startswith(">"):
                continue
            quote = stripped.lstrip(">").strip()
            assert len(quote) <= MAX_BLOCKQUOTE_CHARS, (
                f"{path.relative_to(ROOT)} long quoted passage ({len(quote)} chars): "
                f"{quote[:60]}…"
            )
            assert not re.search(r"(选择题|填空题|简答题|材料题|下列.*正确)", quote), (
                f"{path.relative_to(ROOT)} question-like quote: {quote}"
            )


def test_source_links_baseline_unchanged():
    """练习页框架的工作**不得写** baseline（B2-D4 保留的实质意图）。

    原断言是「baseline 零 git diff」；baseline 可被 `--update-baseline` / `refresh-baseline`
    job 合法刷新，故改为「读全部 practice 页不改 baseline 一个字节」+ 语义契约。
    见 tests/baseline_contract.py。
    """

    def _read_all_practice_pages():
        return [path.read_text(encoding="utf-8") for path in _practice_pages()]

    assert_page_work_keeps_baseline_intact(_read_all_practice_pages)
