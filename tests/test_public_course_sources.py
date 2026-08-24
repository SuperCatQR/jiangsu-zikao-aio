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


CHAPTER_NAMES_15043 = (
    "第一章 反对外国侵略的斗争",
    "第二章 对国家出路的早期探索",
    "第三章 辛亥革命",
    "第四章 开天辟地的大事变",
    "第五章 中国革命的新道路",
    "第六章 中华民族的抗日战争",
    "第七章 为创建新中国而奋斗",
    "第八章 完成社会主义革命和推进社会主义建设",
    "第九章 中国特色社会主义的开创与接续发展",
    "第十章 中国特色社会主义进入新时代",
)

CHAPTER_NAMES_15044 = (
    "绪 论",
    "第一章 物质世界及其发展规律",
    "第二章 认识的本质及规律",
    "第三章 人类社会及其发展规律",
    "第四章 资本主义制度的形成及本质",
    "第五章 资本主义的发展及其趋势",
    "第六章 社会主义的发展及其规律",
    "第七章 共产主义社会是人类最崇高的社会理想",
)


def _syllabus_text(code: str) -> str:
    return (ROOT / "content" / "jiangsu" / "courses" / code / "syllabus.md").read_text(
        encoding="utf-8"
    )


def test_15043_syllabus_lists_toc_chapter_names():
    text = _syllabus_text("15043")
    for name in CHAPTER_NAMES_15043:
        assert name in text
    assert "课程性质与课程目标" in text
    assert "关于大纲的说明与考核实施要求" in text
    assert "2024 年 8 月" in text
    assert "15043-modern-chinese-history-gaogang-2024/document.extracted.md" in text


def test_15044_syllabus_lists_toc_chapter_names():
    text = _syllabus_text("15044")
    for name in CHAPTER_NAMES_15044:
        assert name in text
    assert "绪 论" in text
    assert "2024 年 8 月" in text
    assert "15044-marxism-principles-gaogang-2024/document.extracted.md" in text
