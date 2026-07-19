"""Publish-gate checks extracted from the former build-course-pages SSG.

Blocking errors fire only when lifecycle == publishable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lib.course_status import parse_course_status
from lib.mdutil import (
    code_for_source,
    git_head_commit,
    parse_exam_index_from_frontmatter,
    parse_meta_table,
    split_frontmatter,
)

PENDING_VALUES = {"待补充", "待统计", "待收集", "待校对", "待确认", "待核验"}
V2_CODES = {"15040", "15043", "15044", "13000", "00023", "04735"}


@dataclass
class CoursePage:
    code: str
    source: Path
    meta: dict[str, str]
    frontmatter: dict[str, str]
    body: str


@dataclass
class GateResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_revision: str = ""
    pages_checked: int = 0
    publishable_pages: int = 0


def load_course(path: Path) -> CoursePage:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    return CoursePage(
        code=code_for_source(path),
        source=path,
        meta=parse_meta_table(body),
        frontmatter=frontmatter,
        body=body,
    )


def _check_replacement_free_text_bypass(page: CoursePage, result: GateResult) -> None:
    in_replacement_section = False
    has_4field_table = False
    has_free_text = False
    for line in page.body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## 新旧课程顶替"):
            in_replacement_section = True
            continue
        if in_replacement_section and stripped.startswith("## ") and "新旧课程顶替" not in stripped:
            break
        if not in_replacement_section:
            continue
        if stripped == "| 字段 | 内容 |":
            has_4field_table = True
            continue
        if stripped.startswith("> ") and "替代" in stripped:
            has_free_text = True
            continue
    if has_free_text and has_4field_table:
        result.errors.append(
            f"REPLACEMENT_FREE_TEXT_BYPASS: {page.source}: "
            "新旧课程顶替区块同时存在 4 字段结构化表和自由文本 blockquote。"
        )


def _check_publish_pending(page: CoursePage, result: GateResult) -> None:
    for key in ("数据状态", "发布日期"):
        val = page.meta.get(key, "")
        if any(pv in val for pv in PENDING_VALUES):
            result.errors.append(
                f"PUBLISH_PENDING_REQUIRED_DATA: {page.source}: "
                f"元信息字段「{key}」仍处于待定状态（值：{val}），"
                "不得标记为 publishable。"
            )
    replacement_confirmed = page.frontmatter.get("replacement_confirmed", "")
    if replacement_confirmed and replacement_confirmed.lower() not in ("true", "yes", "confirmed", "not_applicable"):
        result.errors.append(
            f"PUBLISH_PENDING_REQUIRED_DATA: {page.source}: "
            "顶替关系确认状态仍为 pending，不得标记为 publishable。"
        )
    for key in ("exam_source_status", "exam_analysis_status"):
        val = page.frontmatter.get(key, "")
        if any(pv in val for pv in PENDING_VALUES):
            result.errors.append(
                f"PUBLISH_PENDING_REQUIRED_DATA: {page.source}: "
                f"真题数据字段「{key}」仍处于待定状态（值：{val}），"
                "不得标记为 publishable。"
            )


def _check_human_review(page: CoursePage, result: GateResult) -> None:
    reviewed = page.frontmatter.get("reviewed", "")
    reviewer = page.frontmatter.get("reviewer", "")
    if str(reviewed).lower() not in ("true", "yes"):
        result.errors.append(
            f"HUMAN_REVIEW_REQUIRED: {page.source}: "
            "lifecycle=publishable 但缺少人工校对签名。"
            "请设置 reviewed: true 和 reviewer: <姓名>。"
        )
    elif not reviewer or reviewer.lower() in ("null", "none", '""', "''"):
        result.errors.append(
            f"HUMAN_REVIEW_REQUIRED: {page.source}: "
            "reviewed=true 但 reviewer 为空，签名不可追溯。"
        )


def _check_exam_index_scope(page: CoursePage, result: GateResult) -> None:
    in_exam_index = False
    for line in page.body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## 考期索引"):
            in_exam_index = True
            continue
        if in_exam_index and stripped.startswith("## ") and "考期索引" not in stripped:
            break
        if not in_exam_index:
            continue
        if stripped.startswith("|") and not stripped.startswith("|---") and not stripped.startswith("| 考期"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            row_text = " ".join(cells)
            has_new = any(code in row_text for code in ("15043", "15044"))
            has_old = any(code in row_text for code in ("03708", "03709"))
            if has_new and has_old:
                result.errors.append(
                    f"EXAM_INDEX_SCOPE_MIXED: {page.source}: "
                    f"考期索引行混排新旧代码（{row_text[:60]}），"
                    "请拆分为 current_exam_periods 与 legacy_comparison_periods。"
                )
    current, legacy = parse_exam_index_from_frontmatter(page.frontmatter)
    if current and legacy:
        overlap = set(current) & set(legacy)
        if overlap:
            result.errors.append(
                f"EXAM_INDEX_DUPLICATED_SCOPE: {page.source}: "
                f"考期 {sorted(overlap)} 同时出现在 current 与 legacy 列表。"
            )


def _check_content_revision(page: CoursePage, result: GateResult) -> None:
    page_rev = page.frontmatter.get("content_revision", "")
    if not page_rev:
        return
    build_rev = result.content_revision
    if not build_rev:
        return
    if page_rev != build_rev:
        result.errors.append(
            f"CONTENT_REVISION_MISMATCH: {page.source}: "
            f"content_revision={page_rev[:8]} 与 HEAD={build_rev[:8]} 不一致。"
        )


def check_page(page: CoursePage, result: GateResult) -> None:
    status = parse_course_status(page.frontmatter, page.meta)
    result.pages_checked += 1
    if not status.is_publishable():
        return
    result.publishable_pages += 1
    if page.code in V2_CODES:
        _check_replacement_free_text_bypass(page, result)
    _check_publish_pending(page, result)
    _check_human_review(page, result)
    _check_exam_index_scope(page, result)
    _check_content_revision(page, result)


def iter_course_index_pages(courses_dir: Path) -> list[Path]:
    pages: list[Path] = []
    for path in sorted(courses_dir.glob("*/index.md")):
        if re.fullmatch(r"\d{5}", path.parent.name):
            pages.append(path)
    for path in sorted(courses_dir.glob("*.md")):
        if path.stem != "index" and re.fullmatch(r"\d{5}", path.stem):
            pages.append(path)
    return pages


def run_publish_gate(root: Path, courses_dir: Path | None = None) -> GateResult:
    courses = courses_dir or (root / "content" / "jiangsu" / "courses")
    result = GateResult(content_revision=git_head_commit(root))
    for path in iter_course_index_pages(courses):
        page = load_course(path)
        check_page(page, result)
    return result
