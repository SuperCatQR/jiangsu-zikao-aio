"""Chapter-name index on syllabus.md must match plan.md sequences (official TOC names)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"

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


def _read(code: str, page: str) -> str:
    return (COURSES / code / page).read_text(encoding="utf-8")


def _section_after(text: str, heading: str) -> str:
    idx = text.index(heading)
    rest = text[idx:]
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


def _plan_names(plan: str) -> list[str]:
    block = _section_after(plan, "## 按章学习序列")
    rows = _pipe_rows(block)
    assert rows and rows[0][0] == "章节"
    return [row[0] for row in rows[1:]]


def test_15043_syllabus_chapter_index_is_exactly_ten_toc_names():
    names = _index_names(_read("15043", "syllabus.md"))
    assert names == list(CHAPTER_NAMES_15043)
    assert len(names) == 10


def test_15044_syllabus_chapter_index_is_preface_plus_seven():
    names = _index_names(_read("15044", "syllabus.md"))
    assert names == list(CHAPTER_NAMES_15044)
    assert len(names) == 8
    assert names[0] == "绪 论"
    assert "绪论" not in names


def test_15043_plan_sequence_matches_syllabus_index_order():
    expected = _index_names(_read("15043", "syllabus.md"))
    assert _plan_names(_read("15043", "plan.md")) == expected


def test_15044_plan_sequence_matches_syllabus_index_order():
    expected = _index_names(_read("15044", "syllabus.md"))
    plan_names = _plan_names(_read("15044", "plan.md"))
    assert plan_names == expected
    assert plan_names[0] == "绪 论"
    assert "绪论" not in plan_names
