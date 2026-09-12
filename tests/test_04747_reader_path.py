"""04747 Java 语言程序设计（一） reader path and syllabus chapter index contract tests."""
from __future__ import annotations

import re
from pathlib import Path

from tests.baseline_contract import assert_page_work_keeps_baseline_intact

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "content" / "jiangsu" / "courses" / "04747"
EXTRACTION = (
    ROOT
    / "sources"
    / "jiangsu"
    / "processed"
    / "syllabus"
    / "04747-java-programming-1-gaogang-4067"
    / "document.extracted.md"
)

OFFICIAL_JSEEA_URL = (
    "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285133106820943872.html"
)

CHAPTER_NAMES_04747 = (
    "第1章 概述",
    "第2章 标识符和数据类型",
    "第3章 表达式和流程控制语句",
    "第4章 数组、向量和字符串",
    "第5章 进一步讨论对象和类",
    "第6章 Java 语言中的异常",
    "第7章 Java 语言的高级特性（本章内容不作考核要求）",
    "第8章 Java 的图形用户界面设计",
    "第9章 Swing 组件",
    "第10章 Java Applet",
    "第11章 Java 数据流（本章内容不作考核要求）",
    "第12章 线程（本章内容不作考核要求）",
    "第13章 Java 的网络功能（本章内容不作考核要求）",
)

NON_ASSESSED_QUALIFIER = "（本章内容不作考核要求）"
NON_ASSESSED_INDICES = {7, 11, 12, 13}
ASSESSED_INDICES = {1, 2, 3, 4, 5, 6, 8, 9, 10}
PAGE_NAMES = ("index", "syllabus", "plan", "review", "practice", "sources")


def _read(page: str) -> str:
    path = COURSE / f"{page}.md"
    assert path.is_file(), f"Missing course page: {path}"
    return path.read_text(encoding="utf-8")


def _section_after(text: str, heading: str) -> str:
    assert heading in text, f"Heading {heading!r} not found in text"
    idx = text.index(heading)
    rest = text[idx:]
    marker = "\n## "
    nxt = rest.find(marker, 1)
    return rest if nxt == -1 else rest[:nxt]


def _pipe_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(cells)
    return rows


def _syllabus_index_names(syllabus_text: str) -> list[str]:
    block = _section_after(syllabus_text, "### 章目索引")
    rows = _pipe_rows(block)
    assert rows and rows[0][:2] == ["章序", "章名"]
    return [row[1] for row in rows[1:]]


def _plan_index_rows(plan_text: str) -> list[list[str]]:
    block = _section_after(plan_text, "## 建议节奏：按章节顺序执行")
    rows = _pipe_rows(block)
    assert rows and rows[0][:3] == ["顺序", "章节（标题照录）", "类型"]
    return rows[1:]


def test_04747_syllabus_chapter_index_has_thirteen_ordered_names():
    syllabus = _read("syllabus")
    names = _syllabus_index_names(syllabus)
    assert names == list(CHAPTER_NAMES_04747)
    assert len(names) == 13
    assert names[0] == "第1章 概述"
    assert names[-1] == "第13章 Java 的网络功能（本章内容不作考核要求）"


def test_04747_syllabus_non_assessed_qualifiers_preserved():
    syllabus = _read("syllabus")
    names = _syllabus_index_names(syllabus)
    qualifier_count = sum(1 for name in names if NON_ASSESSED_QUALIFIER in name)
    assert qualifier_count == 4

    for idx, name in enumerate(names, start=1):
        if idx in NON_ASSESSED_INDICES:
            assert NON_ASSESSED_QUALIFIER in name, f"Chapter {idx} missing qualifier: {name}"
        else:
            assert NON_ASSESSED_QUALIFIER not in name, f"Chapter {idx} should not have qualifier: {name}"


def test_04747_plan_sequence_matches_syllabus_index_order():
    syllabus_names = _syllabus_index_names(_read("syllabus"))
    plan_rows = _plan_index_rows(_read("plan"))
    plan_names = [row[1] for row in plan_rows]
    assert plan_names == syllabus_names
    assert plan_names == list(CHAPTER_NAMES_04747)
    assert len(plan_rows) == 13


def test_04747_plan_assessed_and_non_assessed_partition():
    plan_text = _read("plan")
    assert "30 天" not in plan_text, "Generic 30-day plan stub must not remain"
    plan_rows = _plan_index_rows(plan_text)

    for row in plan_rows:
        order = int(row[0])
        chapter_name = row[1]
        category = row[2]
        action = row[4]

        if order in ASSESSED_INDICES:
            assert category == "考核章节", f"Chapter {order} expected '考核章节', got {category}"
            assert "读 → 记 → 查" in action, f"Chapter {order} missing standard read->note->check action: {action}"
            assert NON_ASSESSED_QUALIFIER not in chapter_name
        elif order in NON_ASSESSED_INDICES:
            assert "参考-only" in category, f"Chapter {order} expected '参考-only', got {category}"
            assert NON_ASSESSED_QUALIFIER in category
            assert NON_ASSESSED_QUALIFIER in chapter_name
            assert "仅参考阅读" in action, f"Chapter {order} non-assessed action expected reference-only: {action}"


def test_04747_six_pages_symmetric_navigation():
    for page in PAGE_NAMES:
        text = _read(page)
        for target in PAGE_NAMES:
            if target == page:
                continue
            target_link = f"{target}.md"
            assert target_link in text, f"Page {page}.md missing navigation link to {target_link}"

    index_text = _read("index")
    assert "## 开始学习" in index_text
    assert "1. 考纲范围" in index_text
    assert "2. 学习计划" in index_text
    assert "3. 练习与真题" in index_text
    assert "4. 来源核验" in index_text


def test_04747_lifecycle_ceiling_and_forbidden_fields():
    for page in PAGE_NAMES:
        text = _read(page)
        assert "reviewed: true" not in text, f"Forbidden 'reviewed: true' found in {page}.md"
        assert "publishable" not in text, f"Forbidden 'publishable' found in {page}.md"

    index_text = _read("index")
    assert "status: draft" in index_text
    assert "lifecycle: draft" in index_text
    assert "completeness: metadata-only" in index_text
    assert "reviewer: null" in index_text


def test_04747_official_url_boundary():
    url_pattern = re.compile(r"https?://[^\s)\]<>`\"']+")
    official_jseea_pattern = re.compile(r"https?://(?:www\.)?jseea\.cn[^\s)\]<>`\"']*", re.IGNORECASE)

    for page in PAGE_NAMES:
        text = _read(page)
        all_urls = url_pattern.findall(text)
        jseea_urls = [u for u in all_urls if official_jseea_pattern.match(u)]
        for u in jseea_urls:
            assert u == OFFICIAL_JSEEA_URL, f"Unexpected official JSEEA URL in {page}.md: {u}"

    sources_text = _read("sources")
    assert OFFICIAL_JSEEA_URL in sources_text


def test_04747_source_extraction_artifact_identity_and_drift():
    assert EXTRACTION.is_file(), f"Missing extraction artifact: {EXTRACTION}"
    content = EXTRACTION.read_text(encoding="utf-8")

    assert "高纲 4067" in content
    assert "04747" in content
    assert "Java 语言程序设计（一）" in content
    assert "南京航空航天大学编（2024 年）" in content

    # Find section III window and extract chapter headings
    idx_iii = content.find("Ⅲ 课程内容与考核要求")
    idx_iv = content.find("Ⅳ 关于大纲的说明与考核实施要求")
    assert idx_iii != -1 and idx_iv != -1 and idx_iii < idx_iv
    sec_iii = content[idx_iii:idx_iv]

    headings = [
        re.sub(r"\s+", " ", line.strip())
        for line in sec_iii.splitlines()
        if re.search(r"第\s*[0-9]+\s*章", line)
    ]
    # Normalize Chinese number spacing if any (e.g. '第 6 章' -> '第6章')
    normalized_headings = [re.sub(r"第\s*([0-9]+)\s*章", r"第\1章", h) for h in headings]

    assert normalized_headings == list(CHAPTER_NAMES_04747)
    assert len(normalized_headings) == 13


def test_04747_source_links_baseline_unchanged():
    """本文件的 reader-path 工作**不得写** baseline（B2-D4 保留的实质意图）。

    原断言是「baseline 零 git diff」；baseline 可被 `--update-baseline` / `refresh-baseline`
    job 合法刷新，故改为「读这些页面不改 baseline 一个字节」+ 语义契约。
    见 tests/baseline_contract.py。
    """

    def _read_all_pages():
        return [_read(page) for page in PAGE_NAMES]

    assert_page_work_keeps_baseline_intact(_read_all_pages)
