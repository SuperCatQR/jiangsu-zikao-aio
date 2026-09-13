"""04751 计算机网络安全 reader path and syllabus chapter index contract tests."""
from __future__ import annotations

import re
from pathlib import Path

from tests.baseline_contract import assert_page_work_keeps_baseline_intact

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "content" / "jiangsu" / "courses" / "04751"
EXTRACTION = (
    ROOT
    / "sources"
    / "jiangsu"
    / "processed"
    / "syllabus"
    / "04751-computer-network-security-gaogang-4389"
    / "document.extracted.md"
)

OFFICIAL_JSEEA_URLS = {
    "https://www.jseea.cn/webfile/index/index_zcwj/2025-11-20/7397162260776357888.html",
    "https://www.jseea.cn/webfile/upload/2025/06-19/14-59-1607281034810553.pdf",
}

CHAPTER_NAMES_04751 = (
    "第1章 网络安全概述",
    "第2章 网络安全技术基础",
    "第3章 网络安全体系与管理",
    "第4章 黑客攻防与检测防御",
    "第5章 密码与加密技术",
    "第6章 身份认证与访问控制",
    "第7章 计算机及手机病毒防范",
    "第8章 防火墙技术及应用",
    "第9章 操作系统及站点安全",
    "第10章 数据库及数据库安全",
    "第11章 电子商务安全（本章内容不作考核要求）",
    "第12章 网络安全新技术及解决方案（本章内容不作考核要求）",
    "第13章 网络安全课程设计指导（本章内容不作考核要求）",
)

NON_ASSESSED_QUALIFIER = "（本章内容不作考核要求）"
NON_ASSESSED_INDICES = {11, 12, 13}
ASSESSED_INDICES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
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


def test_04751_syllabus_chapter_index_has_thirteen_ordered_names():
    syllabus = _read("syllabus")
    names = _syllabus_index_names(syllabus)
    assert names == list(CHAPTER_NAMES_04751)
    assert len(names) == 13
    assert names[0] == "第1章 网络安全概述"
    assert names[-1] == "第13章 网络安全课程设计指导（本章内容不作考核要求）"


def test_04751_syllabus_non_assessed_qualifiers_preserved():
    syllabus = _read("syllabus")
    names = _syllabus_index_names(syllabus)
    qualifier_count = sum(1 for name in names if NON_ASSESSED_QUALIFIER in name)
    assert qualifier_count == 3

    for idx, name in enumerate(names, start=1):
        if idx in NON_ASSESSED_INDICES:
            assert NON_ASSESSED_QUALIFIER in name, f"Chapter {idx} missing qualifier: {name}"
        else:
            assert NON_ASSESSED_QUALIFIER not in name, f"Chapter {idx} should not have qualifier: {name}"


def test_04751_plan_sequence_matches_syllabus_index_order():
    syllabus_names = _syllabus_index_names(_read("syllabus"))
    plan_rows = _plan_index_rows(_read("plan"))
    plan_names = [row[1] for row in plan_rows]
    assert plan_names == syllabus_names
    assert plan_names == list(CHAPTER_NAMES_04751)
    assert len(plan_rows) == 13


def test_04751_plan_assessed_and_non_assessed_partition():
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


def test_04751_six_pages_symmetric_navigation():
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


def test_04751_lifecycle_ceiling_and_forbidden_fields():
    for page in PAGE_NAMES:
        text = _read(page)
        assert "reviewed: true" not in text, f"Forbidden 'reviewed: true' found in {page}.md"
        assert "publishable" not in text, f"Forbidden 'publishable' found in {page}.md"

    index_text = _read("index")
    assert "status: draft" in index_text
    assert "lifecycle: draft" in index_text
    assert "completeness: metadata-only" in index_text


def test_04751_official_url_boundary():
    url_pattern = re.compile(r"https?://[^\s)\]<>`\"'；]+")
    official_jseea_pattern = re.compile(r"https?://(?:www\.)?jseea\.cn[^\s)\]<>`\"'；]*", re.IGNORECASE)

    for page in PAGE_NAMES:
        text = _read(page)
        all_urls = url_pattern.findall(text)
        jseea_urls = [u for u in all_urls if official_jseea_pattern.match(u)]
        for u in jseea_urls:
            assert u in OFFICIAL_JSEEA_URLS, f"Unexpected official JSEEA URL in {page}.md: {u}"

    sources_text = _read("sources")
    for u in OFFICIAL_JSEEA_URLS:
        assert u in sources_text


def test_04751_source_extraction_artifact_identity_and_drift():
    assert EXTRACTION.is_file(), f"Missing extraction artifact: {EXTRACTION}"
    content = EXTRACTION.read_text(encoding="utf-8")

    assert "高纲4389" in content or "高纲 4389" in content
    assert "04751" in content
    assert "计算机网络安全" in content
    assert "南京航空航天大学编（2025 年）" in content

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
    normalized_headings = [re.sub(r"第\s*([0-9]+)\s*章", r"第\1章", h) for h in headings]

    assert normalized_headings == list(CHAPTER_NAMES_04751)
    assert len(normalized_headings) == 13


def test_04751_source_links_baseline_unchanged():
    """本文件的 reader-path 工作**不得写** baseline（B2-D4 保留的实质意图）。

    原断言是「baseline 零 git diff」；baseline 可被 `--update-baseline` / `refresh-baseline`
    job 合法刷新，故改为「读这些页面不改 baseline 一个字节」+ 语义契约。
    见 tests/baseline_contract.py。
    """

    def _read_all_pages():
        return [_read(page) for page in PAGE_NAMES]

    assert_page_work_keeps_baseline_intact(_read_all_pages)
