"""04751 计算机网络安全 reader path and syllabus chapter index contract tests.

`04751` 已进入 AI 备考流水线：`plan.md` / `practice.md` / `review.md` / `knowledge/*.md` 由
`scripts/build-course-content.py` 渲染（官方三页 `index` / `syllabus` / `sources` 仍是手写正文 +
派生区块，见 `scripts/lib/course_pages_contract.py` 的 `generated_page_markers`）。本模块断言的是
**读者路径本身** —— 考纲章序逐章可见、非考核章的标注可见、六个顶层页面从课程概览可达 —— 而不是
手写时代的页面形状（`plan.md` 的 `## 建议节奏：按章节顺序执行` 表与六页两两互链）。
"""
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

# `plan.md` 的按章学习序列表：渲染器所有（`render_pages.py::_render_plan`）。无附录课程的表名固定为
# `## 按章学习序列`、首列固定为 `章节` —— 这是既有契约（`tests/test_chapter_index_study_plan.py`
# 与 `tests/test_00023_study_plan.py` 锁定同一形状），只在课程真的有附录时才改名为
# `## 按考核单元学习序列`。
PLAN_SEQUENCE_HEADING = "## 按章学习序列"
PLAN_SEQUENCE_FIRST_HEADER_CELL = "章节"

KNOWLEDGE_LINK_RE = re.compile(r"\]\((knowledge/[^)]+)\)")
INDEX_CHAPTER_LINK_RE = re.compile(r"\[([^\]]+)\]\(knowledge/[^)]+\)")


def _read(page: str) -> str:
    path = COURSE / f"{page}.md"
    assert path.is_file(), f"Missing course page: {path}"
    return path.read_text(encoding="utf-8")


def _without_whitespace(title: str) -> str:
    """章目标题的「去空白视图」——与 `scripts/lib/evidence_gate.py::_without_whitespace` 同规则。

    知识模型逐字照录考纲抽取件（`04747` 抽取件印 `第 6 章`；本课同形，如 `第 3章`），手写
    `syllabus.md` 的章目索引表把章号内部空白归一 —— 两侧的章集合 / 章序 / 章名完全相同，差异
    **只在空白**（W4.5 / Task 0b）。这是本模块比较侧的**唯一**放宽：空白以外（大小写、标点、
    全半角、数字）仍须逐字相同，章数与章序仍由列表比较承担。同一课的 `evidence_gate` 已按此规则
    判定模型与页面一致，本模块不得比它更严。
    """
    return "".join(title.split())


def _h1(text: str) -> str:
    headings = [line[2:].strip() for line in text.splitlines() if line.startswith("# ")]
    assert headings, "page carries no level-1 heading"
    return headings[0]


def _chapter_page(index: int) -> Path:
    """第 `index` 章（1-based）的渲染页 `knowledge/NN-chNN.md`（`render_pages._unit_filename`）。"""
    return COURSE / "knowledge" / f"{index:02d}-ch{index:02d}.md"


def _chapter_page_titles() -> list[str]:
    """13 个章页各自的 H1，按章序排列 —— 每页只取自己的标题，不取章节导航里的邻居标签。"""
    titles = []
    for index in range(1, len(CHAPTER_NAMES_04751) + 1):
        page = _chapter_page(index)
        assert page.is_file(), f"Missing chapter page: {page}"
        titles.append(_h1(page.read_text(encoding="utf-8")))
    return titles


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


def _plan_sequence_rows(plan_text: str) -> list[list[str]]:
    """`plan.md` 的按章学习序列表数据行（去表头）—— 渲染器所有，不是手写正文。"""
    rows = _pipe_rows(_section_after(plan_text, PLAN_SEQUENCE_HEADING))
    header = rows[0] if rows else None
    assert header and header[0] == PLAN_SEQUENCE_FIRST_HEADER_CELL, (
        f"Unexpected sequence table header: {header}"
    )
    return rows[1:]


def _index_chapter_link_names(index_text: str) -> list[str]:
    """`index.md` 章节知识精读区块里逐章链接的可见文本（读者在概览页看到的章名）。"""
    return INDEX_CHAPTER_LINK_RE.findall(index_text)


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
    """计划页的学习序列逐行照录考纲章目索引（章序 + 章名），且每一行都能点进该章的页面。

    手写时代该表名为 `## 建议节奏：按章节顺序执行`、列为 `顺序 / 章节（标题照录）/ 类型`；`04751`
    进入流水线后该页由渲染器重建（plan § PM 更正记录第二条），表名与列形随之变为渲染器契约。
    被保护的性质不变：读者从计划页能按考纲顺序找到**每一章**，且行内链接落在该章自己的页面上。
    """
    plan_text = _read("plan")
    assert "30 天" not in plan_text, "Generic 30-day plan stub must not remain"

    syllabus_names = _syllabus_index_names(_read("syllabus"))
    rows = _plan_sequence_rows(plan_text)
    plan_names = [row[0] for row in rows]

    assert len(rows) == 13
    assert [_without_whitespace(name) for name in plan_names] == [
        _without_whitespace(name) for name in syllabus_names
    ]
    assert [_without_whitespace(name) for name in plan_names] == [
        _without_whitespace(name) for name in CHAPTER_NAMES_04751
    ]

    # 行 k 必须落在第 k 章的页面上：目标页 H1 与该行章名逐字相同（两侧同出知识模型，不放宽空白），
    # 且该页正是按章序命名的第 k 个章页（否则顺序被换过，只是章名恰好还对得上）。
    for order, (row, ordinal_page_title) in enumerate(zip(rows, _chapter_page_titles()), start=1):
        targets = KNOWLEDGE_LINK_RE.findall(row[1])
        assert targets, f"Chapter {order} sequence row carries no chapter page link: {row[1]!r}"
        target = COURSE / targets[0]
        assert target.is_file(), f"Chapter {order} sequence row points at a missing page: {targets[0]}"
        target_title = _h1(target.read_text(encoding="utf-8"))
        assert target_title == row[0], (
            f"Chapter {order} sequence row advertises {row[0]!r} but {targets[0]} "
            f"is titled {target_title!r}"
        )
        assert target_title == ordinal_page_title, (
            f"Chapter {order} sequence row links to {targets[0]} which is not the "
            f"{order}-th chapter page"
        )


def test_04751_chapter_assessed_and_non_assessed_partition():
    """「考核 / 不作考核要求」分区以考纲章目索引为准，四个渲染面必须一致。

    手写时代这张分区表在 `plan.md` 的「建议节奏」表里（`类型` 列 `考核章节` / `参考-only`）；该页
    由渲染器重建后分区不再落在计划表，而由**章页 H1**、计划页学习序列、概览页章节链接三处共同承载。
    读者在任一页面看到的「哪些章不作考核要求」必须与考纲相同 —— 少标一章等于把不考的内容当成考点。
    """
    syllabus_names = _syllabus_index_names(_read("syllabus"))
    by_syllabus = [NON_ASSESSED_QUALIFIER in name for name in syllabus_names]

    assert sum(by_syllabus) == 3
    assert [idx for idx, flagged in enumerate(by_syllabus, start=1) if flagged] == sorted(
        NON_ASSESSED_INDICES
    )
    assert [idx for idx, flagged in enumerate(by_syllabus, start=1) if not flagged] == sorted(
        ASSESSED_INDICES
    )

    chapter_page_titles = _chapter_page_titles()
    assert [_without_whitespace(title) for title in chapter_page_titles] == [
        _without_whitespace(name) for name in syllabus_names
    ]
    assert [NON_ASSESSED_QUALIFIER in title for title in chapter_page_titles] == by_syllabus

    plan_names = [row[0] for row in _plan_sequence_rows(_read("plan"))]
    assert [NON_ASSESSED_QUALIFIER in name for name in plan_names] == by_syllabus

    index_names = _index_chapter_link_names(_read("index"))
    assert len(index_names) == 13, f"Course index advertises {len(index_names)} chapter links"
    assert [NON_ASSESSED_QUALIFIER in name for name in index_names] == by_syllabus


def test_04751_six_pages_reachable_from_course_index():
    """六个顶层页面都从课程概览可达，且每个页面都能回到概览页。

    手写时代六页两两互链（30 条对称导航）。渲染器从未实现该形状 —— `render_pages.py` 给 `plan.md`
    与 `practice.md` 的导航行本就不含 `review.md`（七门课一致，`review.md` 自己在概览页与考纲页可达）。
    因此改为断言真正成立的读者保证：概览页是入口，六页皆可达，其余五页都不是死胡同。
    """
    index_text = _read("index")

    reachable = {"index"} | {page for page in PAGE_NAMES if f"]({page}.md)" in index_text}
    assert reachable == set(PAGE_NAMES), (
        f"Unreachable from index.md: {sorted(set(PAGE_NAMES) - reachable)}"
    )

    for page in PAGE_NAMES:
        if page == "index":
            continue
        assert "](index.md)" in _read(page), f"Page {page}.md is a dead end: no link to index.md"

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
