"""15040 syllabus chapter-name index (导论 + 17) and official HTML provenance."""
from __future__ import annotations

from pathlib import Path

from check_source_links import extract_refs

from tests.baseline_contract import assert_page_work_keeps_baseline_intact

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "content" / "jiangsu" / "courses" / "15040"
JSEEA_HTML = (
    "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285134977044320256.html"
)
CHAPTER_NAMES_15040 = (
    "导论",
    "第一章 新时代坚持和发展中国特色社会主义",
    "第二章 以中国式现代化全面推进中华民族伟大复兴",
    "第三章 坚持党的全面领导",
    "第四章 坚持以人民为中心",
    "第五章 全面深化改革开放",
    "第六章 推动高质量发展",
    "第七章 社会主义现代化建设的教育、科技、人才战略",
    "第八章 发展全过程人民民主",
    "第九章 全面依法治国",
    "第十章 建设社会主义文化强国",
    "第十一章 以保障和改善民生为重点加强社会建设",
    "第十二章 建设社会主义生态文明",
    "第十三章 维护和塑造国家安全",
    "第十四章 建设巩固国防和强大人民军队",
    "第十五章 坚持“一国两制”和推进祖国完全统一",
    "第十六章 中国特色大国外交和推动构建人类命运共同体",
    "第十七章 全面从严治党",
)
SECTION_LABELS = (
    ("Ⅰ", "课程性质与课程目标"),
    ("Ⅱ", "考核目标"),
    ("Ⅲ", "课程内容与考核要求"),
    ("Ⅳ", "关于大纲的说明与考核实施要求"),
)
# Distinctive PDF preface / body phrases that must not be pasted onto public pages.
PDF_BODY_SNIPPETS = (
    "高等教育自学考试是个人自学、社会助学和国家考试相结合",
    "课程自学考试大纲是规范自学者学习范围、要求和考试标准的文件",
    "附录：参考样卷",
    "大纲后记",
)


def _read(page: str) -> str:
    return (COURSE / page).read_text(encoding="utf-8")


def _section_after(text: str, heading: str) -> str:
    idx = text.index(heading)
    rest = text[idx:]
    hashes = heading[: heading.index(" ")]
    # Stop at the next heading of the same or higher level (## and ### both appear).
    marker = "\n" + hashes + " "
    nxt = rest.find(marker, 1)
    if nxt == -1 and hashes == "###":
        nxt = rest.find("\n## ", 1)
    return rest if nxt == -1 else rest[:nxt]


def _pipe_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(cells)
    return rows


def _index_names(syllabus: str) -> list[str]:
    block = _section_after(syllabus, "### 章目索引")
    rows = _pipe_rows(block)
    assert rows and rows[0][0] == "章序" and rows[0][1] == "章名"
    return [row[1] for row in rows[1:]]


def _status_rows(text: str, heading: str) -> list[list[str]]:
    return _pipe_rows(_section_after(text, heading))


def test_15040_syllabus_chapter_index_is_daolun_plus_seventeen():
    names = _index_names(_read("syllabus.md"))
    assert names == list(CHAPTER_NAMES_15040)
    assert len(names) == 18
    assert names[0] == "导论"
    assert names[-1] == "第十七章 全面从严治党"


def test_15040_section_labels_are_not_extra_chapters():
    syllabus = _read("syllabus.md")
    names = _index_names(syllabus)
    for mark, title in SECTION_LABELS:
        assert mark not in names
        assert title not in names
        assert f"{mark} {title}" not in names
    section_rows = _pipe_rows(_section_after(syllabus, "### 大纲部次"))
    assert section_rows[0][:2] == ["部次", "名称"]
    body = [(row[0], row[1]) for row in section_rows[1:]]
    assert body == list(SECTION_LABELS)


def test_15040_syllabus_html_and_toc_rows_are_verified_metadata():
    rows = _status_rows(_read("syllabus.md"), "## 资料状态")
    by_item = {row[0]: row for row in rows[1:]}
    html_row = by_item["官方考纲页"]
    assert JSEEA_HTML in html_row[2]
    assert html_row[-1] == "verified-metadata"
    toc_row = by_item["大纲目录（章名）"]
    assert "15040-xi-thought-gaogang-2024/document.extracted.md" in toc_row[2]
    assert toc_row[-1] == "verified-metadata"
    assert by_item["官方考纲 PDF 公开 URL"][-1] == "missing-source"
    assert by_item["章节正文"][-1] == "missing-source"


def test_15040_sources_table_lists_jseea_html_and_named_gaps():
    path = COURSE / "sources.md"
    urls = {ref.url for ref in extract_refs(path)}
    assert JSEEA_HTML in urls
    text = path.read_text(encoding="utf-8")
    rows = _status_rows(text, "## 来源清单")
    statuses = [row[-1] for row in rows[1:]]
    titles = [row[1] for row in rows[1:]]
    assert "verified-metadata" in statuses
    assert any(JSEEA_HTML in row[0] for row in rows[1:])
    assert any("官方考纲 PDF 公开出处" in title for title in titles)
    assert any("章节正文" in title for title in titles)
    assert "missing-source" in statuses
    assert "官方考纲 PDF 公开 URL" in text
    assert "章节正文" in text
    assert "HTML 章目" in text or "章节级大纲（HTML" in text


def test_15040_public_pages_do_not_copy_pdf_body():
    combined = _read("syllabus.md") + "\n" + _read("sources.md")
    for snippet in PDF_BODY_SNIPPETS:
        assert snippet not in combined


def test_15040_source_links_baseline_unchanged():
    """本文件的章目索引工作**不得写** baseline（B2-D4 保留的实质意图）。

    原断言是「baseline 零 git diff」；baseline 可被 `--update-baseline` / `refresh-baseline`
    job 合法刷新，故改为「读这些页面不改 baseline 一个字节」+ 语义契约。
    见 tests/baseline_contract.py。
    """

    def _read_all_pages():
        return [_read(page) for page in ("syllabus.md", "sources.md")]

    assert_page_work_keeps_baseline_intact(_read_all_pages)
