"""Public maturity projection: schema, drift check, ops-only default write."""
from __future__ import annotations

from pathlib import Path

import compute_page_maturity as cpm

REPO = Path(__file__).resolve().parents[1]

LEGACY_PUBLIC_TABLE = """# 页面成熟度报告

    来源：`ops/jiangsu/page-maturity.report.md`。本页用于站点展示。


|课程|status|成熟度|原因|
|-|-|-|-|
|00023|yellow|yellow|status:yellow|
|00898|unknown|yellow|status:unknown|
|15043|draft|yellow|status:draft|
|15044|draft|yellow|status:draft|

合计：red=0 yellow=18 green=0
"""


def _symlink_courses(tmp_root: Path) -> Path:
    courses = tmp_root / "content" / "jiangsu" / "courses"
    gaps = tmp_root / "content" / "jiangsu" / "gaps"
    gaps.mkdir(parents=True)
    courses.parent.mkdir(parents=True, exist_ok=True)
    courses.symlink_to(REPO / "content" / "jiangsu" / "courses")
    return gaps


def test_render_headers_are_lifecycle_completeness_not_status():
    md = cpm.render_public_markdown(cpm.compute_rows(REPO))
    header = next(line for line in md.splitlines() if line.startswith("|课程|"))
    assert "lifecycle" in header
    assert "completeness" in header
    assert "|status|" not in header
    assert "status" not in header.split("|")


def test_legacy_fixture_fails_check(tmp_path: Path):
    gaps = _symlink_courses(tmp_path)
    (gaps / "page-maturity.md").write_text(LEGACY_PUBLIC_TABLE, encoding="utf-8")
    errors = cpm.check_public_projection(tmp_path)
    assert errors
    joined = "\n".join(errors)
    assert "content/jiangsu/gaps/page-maturity.md" in joined
    assert "--write-public" in joined
    assert "--check" in joined


def test_check_empty_after_rendering_current_rows(tmp_path: Path):
    gaps = _symlink_courses(tmp_path)
    rows = cpm.compute_rows(tmp_path)
    (gaps / "page-maturity.md").write_text(cpm.render_public_markdown(rows), encoding="utf-8")
    assert cpm.check_public_projection(tmp_path) == []


def test_main_without_check_writes_ops_only_not_public(tmp_path: Path, monkeypatch):
    gaps = _symlink_courses(tmp_path)
    public = gaps / "page-maturity.md"
    public.write_text("UNCHANGED\n", encoding="utf-8")
    ops = tmp_path / "ops" / "jiangsu"
    ops.mkdir(parents=True)
    monkeypatch.setattr(cpm, "ROOT", tmp_path)
    monkeypatch.setattr(cpm, "COURSES", tmp_path / "content" / "jiangsu" / "courses")
    monkeypatch.setattr(cpm, "OUT_JSON", ops / "page-maturity.json")
    monkeypatch.setattr(cpm, "OUT_MD", ops / "page-maturity.report.md")
    assert cpm.main([]) == 0
    assert public.read_text(encoding="utf-8") == "UNCHANGED\n"
    assert (ops / "page-maturity.json").is_file()
    assert (ops / "page-maturity.report.md").is_file()
    assert cpm.main(["--write-public"]) == 0
    assert public.read_text(encoding="utf-8") != "UNCHANGED\n"
    assert "|lifecycle|" in public.read_text(encoding="utf-8")


def test_check_ops_empty_after_write(tmp_path: Path, monkeypatch):
    gaps = _symlink_courses(tmp_path)
    public = gaps / "page-maturity.md"
    public.write_text(cpm.render_public_markdown(cpm.compute_rows(tmp_path)), encoding="utf-8")
    ops = tmp_path / "ops" / "jiangsu"
    ops.mkdir(parents=True)
    monkeypatch.setattr(cpm, "ROOT", tmp_path)
    monkeypatch.setattr(cpm, "COURSES", tmp_path / "content" / "jiangsu" / "courses")
    monkeypatch.setattr(cpm, "OUT_JSON", ops / "page-maturity.json")
    monkeypatch.setattr(cpm, "OUT_MD", ops / "page-maturity.report.md")
    cpm.main([])  # writes ops JSON + report
    assert cpm.check_ops_projection(tmp_path) == []
    assert cpm.check_projection(tmp_path) == []


def test_check_ops_catches_stale_json(tmp_path: Path, monkeypatch):
    gaps = _symlink_courses(tmp_path)
    public = gaps / "page-maturity.md"
    public.write_text(cpm.render_public_markdown(cpm.compute_rows(tmp_path)), encoding="utf-8")
    ops = tmp_path / "ops" / "jiangsu"
    ops.mkdir(parents=True)
    monkeypatch.setattr(cpm, "ROOT", tmp_path)
    monkeypatch.setattr(cpm, "COURSES", tmp_path / "content" / "jiangsu" / "courses")
    monkeypatch.setattr(cpm, "OUT_JSON", ops / "page-maturity.json")
    monkeypatch.setattr(cpm, "OUT_MD", ops / "page-maturity.report.md")
    cpm.main([])  # correct ops files
    # stale the JSON
    rows = cpm.compute_rows(tmp_path)
    for r in rows:
        if r["code"] == "15043":
            r["lifecycle"] = "draft"
    ops.joinpath("page-maturity.json").write_text(
        cpm.json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    errors = cpm.check_ops_projection(tmp_path)
    assert errors
    joined = "\n".join(errors)
    assert "page-maturity.json" in joined
    assert "python scripts/compute-page-maturity.py" in joined
    # combined check also fails
    assert cpm.check_projection(tmp_path) != []
