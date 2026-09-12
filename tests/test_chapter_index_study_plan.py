"""Chapter-name index on syllabus.md must match plan.md sequences (official TOC names)."""
from pathlib import Path
import re

from tests.baseline_contract import assert_page_work_keeps_baseline_intact

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"

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


def test_15040_plan_sequence_matches_syllabus_index_order():
    expected = _index_names(_read("15040", "syllabus.md"))
    plan_names = _plan_names(_read("15040", "plan.md"))
    assert expected == list(CHAPTER_NAMES_15040)
    assert plan_names == expected
    assert len(plan_names) == 18
    assert plan_names[0] == "导论"
    assert plan_names[-1] == "第十七章 全面从严治党"
    assert "绪论" not in plan_names


def test_15040_plan_table_has_required_columns():
    rows = _pipe_rows(_section_after(_read("15040", "plan.md"), "## 按章学习序列"))
    assert rows[0] == ["章节", "学习任务", "自检方式", "完成标记"]
    assert len(rows) == 19  # header + 导论 + 17


def test_15040_plan_keeps_named_gaps_and_rejects_invented_schedule():
    plan = _read("15040", "plan.md")
    for marker in ("教材空态", "真题空态", "适用考期"):
        assert marker in plan
    assert "D1-" not in plan
    assert "30 天" not in plan
    assert not re.search(r"\d{13}", plan)
    assert "978-" not in plan
    # B2-D4：原断言是「baseline 零 git diff」。实质意图 = 读页面这条路**不得写** baseline。
    # 保留该意图（写自由 + 语义契约），去掉与合法刷新冲突的形式约束。见 tests/baseline_contract.py。
    assert_page_work_keeps_baseline_intact(lambda: _read("15040", "plan.md"))
