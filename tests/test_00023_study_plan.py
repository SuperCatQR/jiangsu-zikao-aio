"""00023 plan.md is a textbook-metadata stage sequence, not an invented outline."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "content" / "jiangsu" / "courses" / "00023" / "plan.md"

STAGE_LABELS = (
    "核对教材计划元数据",
    "通读教材对应章节",
    "公式与例题练习",
    "自检与错题",
    "真题待补",
)

NAMED_GAP_MARKERS = (
    "考纲空态",
    "真题空态",
    "适用考期空态",
    "ISBN",
)


def _plan_text() -> str:
    assert PLAN.is_file(), f"missing {PLAN.relative_to(ROOT)}"
    return PLAN.read_text(encoding="utf-8")


def test_00023_plan_exists_and_cites_verified_textbook_metadata():
    text = _plan_text()
    assert "高等数学(工本)" in text
    assert "陈兆斗" in text
    assert "马鹏" in text
    assert "北京大学出版社" in text
    assert "2023" in text
    assert "verified-metadata" in text


def test_00023_plan_has_stage_sequence_not_invented_chapters():
    text = _plan_text()
    for label in STAGE_LABELS:
        assert label in text, f"missing stage {label!r}"
    assert "## 可执行学习序列" in text
    assert "第一章" not in text
    assert "第二章" not in text
    assert "按章学习序列" not in text
    assert "不是自拟「章节地图」" in text
    assert not re.search(r"^## .*章节地图", text, re.M)


def test_00023_plan_keeps_named_gaps_and_rejects_invented_calendar():
    text = _plan_text()
    for marker in NAMED_GAP_MARKERS:
        assert marker in text
    assert "missing-source" in text
    assert "D1-" not in text
    assert not re.search(r"\| *D\d+", text)
    assert not re.search(r"\d{13}", text)
    assert "978-" not in text
    result = subprocess.run(
        ["git", "diff", "--", "ops/jiangsu/source-links.baseline.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    assert result.stderr == ""
