"""Publish gate: only lifecycle=publishable pages block the build."""
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lib.publish_gate import CoursePage, GateResult, check_page


def _page(tmp_path: Path, fm: dict, body: str = "# t\n") -> CoursePage:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append(body)
    p = tmp_path / "15044" / "index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    text = p.read_text(encoding="utf-8")
    # load via helper would re-read; build CoursePage directly for unit isolation
    from lib.mdutil import parse_meta_table, split_frontmatter

    frontmatter, b = split_frontmatter(text)
    return CoursePage(
        code="15044",
        source=p,
        meta=parse_meta_table(b),
        frontmatter=frontmatter,
        body=b,
    )


def test_non_publishable_does_not_error(tmp_path):
    page = _page(tmp_path, {"lifecycle": "machine_ready", "reviewed": "false"})
    result = GateResult()
    check_page(page, result)
    assert result.errors == []
    assert result.publishable_pages == 0


def test_publishable_requires_review(tmp_path):
    body = """# 课

| 字段 | 内容 |
| --- | --- |
| 数据状态 | 已校对 |
| 发布日期 | 2026-07-01 |
"""
    page = _page(
        tmp_path,
        {
            "lifecycle": "publishable",
            "reviewed": "false",
            "reviewer": "",
            "replacement_confirmed": "true",
        },
        body,
    )
    result = GateResult()
    check_page(page, result)
    assert any(e.startswith("HUMAN_REVIEW_REQUIRED") for e in result.errors)


def test_publishable_clean_passes(tmp_path):
    body = """# 课

| 字段 | 内容 |
| --- | --- |
| 数据状态 | 已校对 |
| 发布日期 | 2026-07-01 |
"""
    page = _page(
        tmp_path,
        {
            "lifecycle": "publishable",
            "reviewed": "true",
            "reviewer": "PR-Reviewer",
            "replacement_confirmed": "true",
        },
        body,
    )
    result = GateResult()
    check_page(page, result)
    assert result.errors == []
    assert result.publishable_pages == 1
