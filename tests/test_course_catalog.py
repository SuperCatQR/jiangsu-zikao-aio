"""课程目录：`content/jiangsu/majors/*` 来源 → `sources/jiangsu/catalog/*.json`。

来源优先级（逐专业取实际命中档位）：现行课程表 `index.md` > 官方计划定宽表
`sources/plan.raw.txt` > 机器抽取件 `sources/jiangsu/processed/major-source/*/document.extracted.md`。

本文件的校验探针（`_physical_lines` / `_candidate_lines` / `_boundary_codes`）**自备**：
自己按 `\\n` 切物理行、自己写正则，不调用生产函数的读取 / 匹配 / 定位逻辑——否则校验与被校验
共用同一套约定，回归（如 `locator` 偏 1–3 行、静默丢行）永远测不出来。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from lib.course_pipeline import course_catalog as cc

ROOT = Path(__file__).resolve().parents[1]
MAJOR_DIR = ROOT / "content" / "jiangsu" / "majors" / "080901-computer-science-and-technology"
RAW_PLAN = MAJOR_DIR / "sources" / "plan.raw.txt"

# `080901/index.md` 现行课程表（7 列）主表 23 门
CURRENT_TABLE_CODES = [
    "00023", "00898", "00899", "02324", "02333", "02334", "04735", "04736",
    "04747", "04748", "04751", "13000", "13003", "13004", "13013", "13014",
    "13015", "13017", "13180", "14976", "15040", "15043", "15044",
]
# `content/jiangsu/courses/*/` 现有 18 个课码目录
EXISTING_COURSE_CODES = [
    "00023", "00898", "02324", "02333", "03708", "03709", "04735", "04747",
    "04751", "13000", "13003", "13013", "13015", "13017", "13180", "15040",
    "15043", "15044",
]
# 首轮解析器静默丢弃的课码（F-001 回归锚点，逐条来自评审的审计清单）
PREVIOUSLY_DROPPED_CODES = ["03006", "04487", "05418", "13594", "14795", "18914"]

# ---- 独立校验探针（不使用生产函数） -----------------------------------------
# 物理行 = `sed` / `grep` 口径：只按 `\n` 切；PDF 分页的 `\x0c` 计入其所在行
_PHYSICAL_CODE_HEAD = re.compile(r"^\s*(?:\d{1,3}\s+)?\d{5}(?:\s|$)")
_PHYSICAL_TABLE_ROW = re.compile(r"^\|\s*\d+\s*\|\s*\d{5}\s*\|")
_BOUNDARY_CODE_RE = re.compile(r"(?<!\d)\d{5}(?!\d)")


def _physical_lines(path: Path) -> list[str]:
    """独立读取：1-based 下标即 `sed -n '<n>p'` 显示的行。"""
    return path.read_text(encoding="utf-8").split("\n")


def _candidate_lines(path: Path, pattern: re.Pattern) -> list[int]:
    """独立枚举候选课程行的物理行号（来源区内的行首课码行 / 现行表行）。"""
    return [index for index, line in enumerate(_physical_lines(path), start=1) if pattern.match(line)]


def _boundary_codes(text: str) -> list[str]:
    """边界感知扫描 5 位课码（测试侧自备；生产模块不导出该工具）。"""
    return sorted(set(_BOUNDARY_CODE_RE.findall(text)))


def _fold(text: str) -> str:
    """统一全/半角与空白差异，便于逐字比对官方原文。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text.replace("\u3000", " "))).strip()


def _write_major(
    root: Path,
    slug: str,
    *,
    code: str,
    name: str,
    level: str = "专升本",
    course_table: bool = False,
    extra_page: str = "",
    plan_rows: str | None = None,
) -> Path:
    major = root / "content" / "jiangsu" / "majors" / slug
    (major / "sources").mkdir(parents=True)
    body = (
        f"# {name}（{level}）\n\n"
        "| 字段 | 内容 |\n| --- | --- |\n"
        f"| 省份 | 江苏 |\n| 专业代码 | {code} |\n| 专业名称 | {name} |\n| 层次 | {level} |\n"
    )
    if course_table:
        body += (
            "\n## 现行课程清单\n\n"
            "| 序号 | 课程代码 | 课程名称 | 学分 | 考试方式 | 课程页 | 建设优先级 |\n"
            "| ---: | --- | --- | ---: | --- | --- | --- |\n"
            "| 1 | 04747 | Java 语言程序设计（一） | 3 | 笔试 | [04747](../../courses/04747/index.md) | P1 |\n"
        )
    (major / "index.md").write_text(body + extra_page, encoding="utf-8")
    if plan_rows is not None:
        (major / "sources" / "plan.raw.txt").write_text(plan_rows, encoding="utf-8")
    return major


# ---- 行形态（逐条取自真实来源文件，逐字节照录） -----------------------------

def test_catalog_from_major_raw_txt():
    rows, dropped = cc.parse_plan_rows(RAW_PLAN)
    assert dropped == []
    assert len(rows) >= 20, "080901 定宽表含 21 门课（含名称折行行）"
    by_code = {row["code"]: row for row in rows}
    assert len(by_code) == len(rows), "同一专业页内不得重复课码"

    java = by_code["04747"]
    assert _fold(java["name"]) == _fold("Java 语言程序设计（一）")
    assert java["credits"] == 3
    assert java["exam_method"] == "笔试"

    # 序号独占一行的版式（`13013 高级语言程序设计 4 笔试`，序号在下一行）——漏掉它是回归
    advanced = by_code["13013"]
    assert advanced["credits"] == 4
    assert advanced["exam_method"] == "笔试"
    assert advanced["name"].startswith("高级语言程序设计")

    # 名称折行的行同样入目录，locator 指回**物理**行号（`sed -n '75p'` 即这一行）
    assert _fold(by_code["00899"]["name"]) == _fold("互联网软件应用与开发（实践）")
    assert _fold(by_code["14976"]["name"]) == _fold("计算机科学与技术（本科）毕业设计")
    assert by_code["14976"]["credits"] is None  # 官方「不计学分」，不得猜
    assert by_code["13013"]["locator"] == "L75", "序号独占一行的课程行位于物理行 75"
    assert "13013" in _physical_lines(RAW_PLAN)[74]
    assert "13013" not in _physical_lines(RAW_PLAN)[76], "旧实现的 splitlines 行号（L77）指向 13014 行"
    for code in ("04747", "13013", "00899", "14976"):
        locator = by_code[code]["locator"]
        assert re.fullmatch(r"L\d+", locator), locator
        assert code in _physical_lines(RAW_PLAN)[int(locator[1:]) - 1]


def test_parser_reads_row_with_trailing_note(tmp_path: Path):
    """带尾随 `备注` 单元格的行（41 个专业页有此形态）必须入目录，备注不得顶掉课程行。"""
    raw = tmp_path / "plan.raw.txt"
    raw.write_text(
        " 13   13594   高层建筑结构施工                 4    笔试   不 少 于 21\n"
        " 11   03954   现代公文写作                  5   笔试   考外语者，\n",
        encoding="utf-8",
    )
    rows, dropped = cc.parse_plan_rows(raw)
    assert dropped == []
    assert [(r["code"], r["name"], r["credits"], r["exam_method"]) for r in rows] == [
        ("13594", "高层建筑结构施工", 4, "笔试"),
        ("03954", "现代公文写作", 5, "笔试"),
    ]


def test_parser_reads_practice_row_without_credits_cell(tmp_path: Path):
    """`… 实践` 且来源确实未给学分的行必须入目录，`credits` 为 `null`（不得猜）。"""
    raw = tmp_path / "plan.raw.txt"
    raw.write_text(
        " 15   14817   金融学（本科）毕业论文                       实践\n"
        " 17   10331   视觉传达设计毕业论文                  实践\n",
        encoding="utf-8",
    )
    rows, dropped = cc.parse_plan_rows(raw)
    assert dropped == []
    assert [(r["code"], r["name"], r["credits"], r["exam_method"]) for r in rows] == [
        ("14817", "金融学（本科）毕业论文", None, "实践"),
        ("10331", "视觉传达设计毕业论文", None, "实践"),
    ]


def test_parser_reads_wrapped_name_rows(tmp_path: Path):
    """课名单元格为空、名称折到相邻行的行必须入目录并拼回完整课名。"""
    raw = tmp_path / "plan.raw.txt"
    raw.write_text(
        "        00898   互联网软件应用与开发               3   笔试\n"
        " 11             互联网软件应用与开发\n"
        "        00899                            3   实践\n"
        "                （实践）\n",
        encoding="utf-8",
    )
    rows, dropped = cc.parse_plan_rows(raw)
    assert dropped == []
    assert [(r["code"], r["name"], r["credits"], r["exam_method"], r["locator"]) for r in rows] == [
        ("00898", "互联网软件应用与开发", 3, "笔试", "L1"),
        ("00899", "互联网软件应用与开发（实践）", 3, "实践", "L3"),
    ]


def test_parser_reads_code_and_method_only_row(tmp_path: Path):
    """`课码 + 考试方式` 极简形态（毕业环节）：课名从相邻行拼回，学分单元格折行 → `null`。"""
    raw = tmp_path / "plan.raw.txt"
    raw.write_text(
        " 14     13017   计算机网络与信息安全               6   笔试\n"
        "                计算机科学与技术（本科）毕        不计\n"
        " 15     14976                                实践\n"
        "                业设计                  学分\n",
        encoding="utf-8",
    )
    rows, dropped = cc.parse_plan_rows(raw)
    assert dropped == []
    assert rows[1] == {
        "code": "14976",
        "name": "计算机科学与技术（本科）毕业设计",
        "credits": None,
        "exam_method": "实践",
        "locator": "L3",
    }


def test_parser_ignores_non_course_lines(tmp_path: Path):
    """非课程文本（表头 / 学分合计 / 页码 / 说明段 / 6 位专业代码）不得产出课程行。"""
    raw = tmp_path / "plan.raw.txt"
    raw.write_text(
        "     四、考试课程与学分\n"
        " 序    课程                                     考试\n"
        "                   课程名称                 学分         备注\n"
        " 号    代码                                     方式\n"
        " 1    03708   中国近现代史纲要                  2    笔试\n"
        "  学分合计                          73 学分\n"
        "                           -3-\n"
        "  1.含实践的课程及实践所占学分：高级语言程序设计（2）。\n"
        "080901   计算机科学与技术（专升本）考试计划\n"
        "  五、实践性环节学习考核要求\n",
        encoding="utf-8",
    )
    rows, dropped = cc.parse_plan_rows(raw)
    assert dropped == []
    assert [(r["code"], r["locator"]) for r in rows] == [("03708", "L5")]


def test_parser_records_unparseable_candidate_row(tmp_path: Path):
    """行首有课码但读不出考试方式的候选行必须写进 `dropped_rows`，不得静默丢弃。"""
    raw = tmp_path / "plan.raw.txt"
    raw.write_text(
        " 1    03708   中国近现代史纲要                  2    笔试\n"
        "      99999   只有课码和说明文字的候选行\n",
        encoding="utf-8",
    )
    rows, dropped = cc.parse_plan_rows(raw)
    assert [r["code"] for r in rows] == ["03708"]
    assert len(dropped) == 1
    assert dropped[0]["locator"] == "L2"
    assert dropped[0]["raw"] == "99999   只有课码和说明文字的候选行"
    assert set(dropped[0]) == {"locator", "raw", "reason"}
    assert dropped[0]["reason"]


def test_every_major_parses_every_candidate_course_row():
    """载荷化覆盖断言（F-001）：每个专业「候选课程行数 == parsed_rows」且 `dropped_rows` 为空。

    候选行由本文件独立枚举（自备物理行读取与正则）。首轮解析器只要求「整行匹配某一种形态」，
    静默丢弃 81 行 / 78 个课码而该断言不存在，因此本测试是该缺陷的回归门。
    """
    majors_doc = cc.build_majors(ROOT)
    total_candidates = 0
    for major in majors_doc["majors"]:
        page = ROOT / major["page"]
        if major["course_table_source"] == "index.md":
            source, pattern = page, _PHYSICAL_TABLE_ROW
        else:
            assert major["course_table_source"] == "plan.raw.txt", major["slug"]
            source, pattern = page.parent / "sources" / "plan.raw.txt", _PHYSICAL_CODE_HEAD
        candidates = _candidate_lines(source, pattern)
        assert major["parsed_rows"] == len(candidates), major["slug"]
        assert major["parsed_rows"] > 0, major["slug"]
        assert major["dropped_rows"] == [], major["slug"]
        assert len(major["course_codes"]) > 0, major["slug"]
        total_candidates += len(candidates)

    assert total_candidates == sum(m["parsed_rows"] for m in majors_doc["majors"])
    assert total_candidates > 1000, "54 个专业页的课程表合计逾千行；数量骤降即解析器漏行"

    # 首轮被丢弃的课码（评审 F-001 清单）现在必须全部在目录里
    catalog = cc.build_catalog(ROOT)
    codes = {course["code"] for course in catalog["courses"]}
    assert set(PREVIOUSLY_DROPPED_CODES) <= codes
    assert len(catalog["courses"]) > 644, "首轮 644 门；丢弃的 78 个课码必须全部补齐"
    assert sum(len(course["sources"]) for course in catalog["courses"]) == total_candidates


def test_locators_point_at_physical_source_lines():
    """`sources[].locator` 必须是物理行号：`L<n>` 行内出现该课码（独立于生产读取器计算）。"""
    catalog = cc.build_catalog(ROOT)
    checked = 0
    for course in catalog["courses"]:
        for source in course["sources"]:
            matched = re.fullmatch(r"L(\d+)", source["locator"])
            assert matched, (course["code"], source["locator"])
            lines = _physical_lines(ROOT / source["path"])
            number = int(matched.group(1))
            assert 1 <= number <= len(lines), (course["code"], source)
            assert course["code"] in lines[number - 1], (course["code"], source["path"], source["locator"])
            checked += 1
    assert checked == sum(len(course["sources"]) for course in catalog["courses"])
    assert checked > 1000


def test_committed_artifacts_match_a_fresh_build():
    """提交的产物必须与当前来源一致（catalog 是 T2+ 的 SSOT，不得停在旧解析器上）。"""
    assert cc.check_catalog(ROOT) == []


def test_catalog_shape_invariants():
    """Data contracts 1 / 1b 的形状不变量，对全量元素断言（不只抽样）。"""
    catalog = json.loads(cc.serialize(cc.build_catalog(ROOT)))
    assert set(catalog) == {"schema_version", "generated_at", "courses"}
    assert catalog["schema_version"] == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", catalog["generated_at"])
    for course in catalog["courses"]:
        assert set(course) == {
            "code", "name", "aliases", "credits", "exam_method", "majors", "sources", "conflicts",
        }, course["code"]
        assert re.fullmatch(r"\d{5}", course["code"]), course["code"]
        assert isinstance(course["name"], str) and course["name"].strip(), course["code"]
        assert course["credits"] is None or isinstance(course["credits"], int), course["code"]
        assert course["exam_method"] in {"笔试", "实践", "机考", None}, course["code"]
        assert course["aliases"] == sorted(set(course["aliases"])), course["code"]
        assert course["sources"], course["code"]
        for source in course["sources"]:
            assert set(source) == {"doc_id", "path", "locator"}, source
            assert source["doc_id"].strip() and source["path"].strip(), source
            assert re.fullmatch(r"L\d+", source["locator"]), source
            assert (ROOT / source["path"]).is_file(), source["path"]
        for major in course["majors"]:
            assert set(major) == {"code", "name", "level"}, major
            assert major["level"] in {"专科", "专升本", None}, major
        for conflict in course["conflicts"]:
            assert set(conflict) == {"field", "values"}, conflict
            assert conflict["field"] in {"name", "credits", "exam_method"}, conflict
            assert len(conflict["values"]) > 1, conflict

    majors_doc = json.loads(cc.serialize(cc.build_majors(ROOT)))
    assert set(majors_doc) == {"schema_version", "generated_at", "majors"}
    for major in majors_doc["majors"]:
        assert set(major) == {
            "code", "slug", "name", "level", "page", "course_table_source",
            "parsed_rows", "dropped_rows", "course_codes", "practice_codes",
        }, major["slug"]
        assert re.fullmatch(r"\d{6}[A-Z]?", major["code"]), major["code"]
        assert major["course_table_source"] in {"index.md", "plan.raw.txt", "major-source"}, major["slug"]
        assert isinstance(major["parsed_rows"], int) and major["parsed_rows"] > 0, major["slug"]
        assert isinstance(major["dropped_rows"], list) and major["dropped_rows"] == [], major["slug"]
        assert major["course_codes"] == sorted(set(major["course_codes"])), major["slug"]
        assert set(major["practice_codes"]) <= set(major["course_codes"]), major["slug"]
        assert (ROOT / major["page"]).is_file(), major["page"]

    # AC2 第二半：54 个专业页课程表所涉课码 == catalog 课码（无遗漏、无凭空多出）
    union = {code for major in majors_doc["majors"] for code in major["course_codes"]}
    assert union == {course["code"] for course in catalog["courses"]}


def test_catalog_from_current_major_table():
    page = (MAJOR_DIR / "index.md").read_text(encoding="utf-8")
    page_codes = _boundary_codes(page)
    assert page_codes == sorted(set(page_codes))
    assert len(page_codes) == 25, "现行课程表页边界感知 5 位课码去重 25 门"
    assert "08090" not in page_codes, "`080901` / `X2080901` 的子串不是课码"
    assert "08090" in re.findall(r"\d{5}", page), "整页 naive 扫描确实会注入伪课码"

    majors = {m["code"]: m for m in cc.build_majors(ROOT)["majors"]}
    major = majors["080901"]
    assert major["course_table_source"] == "index.md"
    assert major["course_codes"] == CURRENT_TABLE_CODES
    assert major["parsed_rows"] == len(CURRENT_TABLE_CODES)
    assert major["dropped_rows"] == []

    courses = {c["code"]: c for c in cc.build_catalog(ROOT)["courses"]}
    assert set(CURRENT_TABLE_CODES) <= set(courses)
    assert courses["15040"]["name"] == "习近平新时代中国特色社会主义思想概论"
    assert courses["15040"]["credits"] == 3
    assert courses["15040"]["exam_method"] == "笔试"
    assert courses["14976"]["credits"] is None  # 「不计学分」→ null
    assert courses["14976"]["exam_method"] == "实践"


def test_catalog_covers_existing_pages():
    codes = {c["code"] for c in cc.build_catalog(ROOT)["courses"]}
    pages = sorted(
        p.name
        for p in (ROOT / "content" / "jiangsu" / "courses").iterdir()
        if p.is_dir() and re.fullmatch(r"\d{5}", p.name)
    )
    assert len(pages) == 18
    assert set(pages) <= codes
    assert set(EXISTING_COURSE_CODES) == set(pages)


def test_catalog_covers_all_54_majors():
    majors_doc = cc.build_majors(ROOT)
    catalog = cc.build_catalog(ROOT)
    assert majors_doc["schema_version"] == 1
    assert len(majors_doc["majors"]) == 54
    codes = {course["code"] for course in catalog["courses"]}
    for major in majors_doc["majors"]:
        assert major["course_codes"], major["slug"]
        assert major["course_table_source"] in {"index.md", "plan.raw.txt", "major-source"}
        assert (ROOT / major["page"]).is_file()
        assert len(set(major["course_codes"])) == len(major["course_codes"])
        assert set(major["course_codes"]) <= codes, major["slug"]  # 每个专业的课码都必须可解析
    assert len(catalog["courses"]) >= 60  # AC2 前半：唯一课码 ≥ 60


def test_resolve_by_code_and_name():
    catalog = cc.build_catalog(ROOT)

    by_code = cc.resolve_course(catalog, "15040")
    assert (by_code["status"], by_code["code"], by_code["matched_by"]) == ("resolved", "15040", "code")
    assert by_code["name"] == "习近平新时代中国特色社会主义思想概论"

    # 同名课（旧码 03708 / 现行码 15043）按来源档位定序：现行课程表来源胜出
    legacy = next(c for c in catalog["courses"] if c["code"] == "03708")
    assert legacy["name"] == "中国近现代史纲要"
    assert all(s["path"].endswith("plan.raw.txt") for s in legacy["sources"])
    by_name = cc.resolve_course(catalog, "中国近现代史纲要")
    assert (by_name["status"], by_name["code"], by_name["matched_by"]) == ("resolved", "15043", "name")

    # 大小写 / 空格 / 全半角归一
    for query in ("java 语言程序设计（一）", "JAVA　语言程序设计(一)", "Java语言程序设计（一）"):
        result = cc.resolve_course(catalog, query)
        assert result["status"] == "resolved", query
        assert result["code"] == "04747", query


def test_resolve_ambiguous_returns_candidates():
    catalog = {
        "schema_version": 1,
        "generated_at": "2026-09-11",
        "courses": [
            {"code": "00002", "name": "示例课程(一)", "aliases": [], "credits": None,
             "exam_method": "笔试", "majors": [], "sources": [], "conflicts": []},
            {"code": "00001", "name": "示例课程（一）", "aliases": ["示例课程二"], "credits": None,
             "exam_method": "笔试", "majors": [], "sources": [], "conflicts": []},
        ],
    }
    result = cc.resolve_course(catalog, "示例课程（一）")
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
    assert [c["code"] for c in result["candidates"]] == ["00001", "00002"]

    by_alias = cc.resolve_course(catalog, "示例课程二")
    assert (by_alias["status"], by_alias["code"], by_alias["matched_by"]) == ("resolved", "00001", "alias")

    assert cc.resolve_course(catalog, "不存在的课程")["status"] == "not_found"
    assert cc.resolve_course(catalog, "99999")["status"] == "not_found"


def test_conflict_recorded_not_guessed(tmp_path: Path):
    _write_major(tmp_path, "080901-demo-a", code="080901", name="示例专业甲", course_table=True)
    _write_major(
        tmp_path,
        "080903-demo-b",
        code="080903",
        name="示例专业乙",
        plan_rows=" 1    04747   Java语言程序设计(二)                 4   笔试\n",
    )

    catalog = cc.build_catalog(tmp_path)
    assert [c["code"] for c in catalog["courses"]] == ["04747"]
    course = catalog["courses"][0]

    # 名称取优先级高者（现行课程表），不自动合并、不编造第三值
    assert course["name"] == "Java 语言程序设计（一）"
    assert course["credits"] == 3

    conflicts = {c["field"]: c for c in course["conflicts"]}
    assert set(conflicts) == {"name", "credits"}
    name_values = {v["value"] for v in conflicts["name"]["values"]}
    assert name_values == {"Java 语言程序设计（一）", "Java语言程序设计(二)"}
    assert course["name"] in name_values
    assert {v["value"] for v in conflicts["credits"]["values"]} == {3, 4}
    for conflict in course["conflicts"]:
        assert set(conflict) == {"field", "values"}
        for value in conflict["values"]:
            assert set(value) == {"value", "doc_id", "locator"}  # Data contracts 1 的元素形状
            assert value["doc_id"] and value["locator"]
    assert len(course["sources"]) == 2
    assert [s["doc_id"] for s in course["sources"]] == ["major-plan:080901", "major-plan:080903"]


def test_catalog_falls_back_to_major_source(tmp_path: Path):
    """现行课程表与官方计划表都未命中时，回落到机器抽取件（来源优先级第 3 档）。"""
    _write_major(tmp_path, "080703-demo-c", code="080703", name="示例专业丙")
    doc = tmp_path / "sources" / "jiangsu" / "processed" / "major-source" / "25" / "document.extracted.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# 25.示例专业丙（专升本）考试计划\n\n（专业代码：080703）\n\n"
        " 1    03708   中国近现代史纲要                 2   笔试\n"
        "        13013   高级语言程序设计                 4   笔试\n",
        encoding="utf-8",
    )

    major = {m["code"]: m for m in cc.build_majors(tmp_path)["majors"]}["080703"]
    assert major["course_table_source"] == "major-source"
    assert major["course_codes"] == ["03708", "13013"]
    assert major["parsed_rows"] == 2
    assert major["dropped_rows"] == []
    course = next(c for c in cc.build_catalog(tmp_path)["courses"] if c["code"] == "13013")
    assert course["sources"][0]["path"].endswith("major-source/25/document.extracted.md")
    assert course["sources"][0]["locator"] == "L6"


def test_zero_row_tier_with_candidates_is_not_silently_skipped(tmp_path: Path):
    """G-001：某档位「0 解析行但有候选行」时，不得静默回落而丢掉它的 `dropped_rows`。

    档位命中判据是**产出候选行**（解析行**或**丢弃行），因此回落只发生在「本档位无候选行」时——
    无候选即无可丢弃，回落不可能丢行；有候选的档位成为被选中档位，`dropped_rows` 只覆盖它。
    把命中判据改回「解析行非空」（`if table_rows:` / `if plan_rows:`），tier-1 的候选行就会凭空
    消失、目录改用它本不该用的下一档。
    """
    # 档位 1（现行课程表）0 解析行 + 1 候选行；档位 2（计划定宽表）可解析 → 不得改用档位 2
    root = tmp_path / "zero-row-index-tier"
    major = _write_major(
        root,
        "080901-demo-a",
        code="080901",
        name="示例专业甲",
        extra_page=(
            "\n## 现行课程清单\n\n"
            "| 序号 | 课程代码 | 课程名称 | 学分 | 考试方式 | 课程页 | 建设优先级 |\n"
            "| ---: | --- | --- | ---: | --- | --- | --- |\n"
            "| 1 | 04747 |\n"
        ),
        plan_rows=" 1    03708   中国近现代史纲要                 2   笔试\n",
    )
    broken = next(
        number
        for number, line in enumerate(_physical_lines(major / "index.md"), start=1)
        if line.startswith("| 1 | 04747 |")
    )
    selected = cc.build_majors(root)["majors"][0]
    assert selected["course_table_source"] == "index.md", "有候选行的档位即被选中档位，不回落"
    assert selected["parsed_rows"] == 0
    assert selected["course_codes"] == [], "档位 2 的行不得冒充被选中档位的课程表"
    assert len(selected["dropped_rows"]) == 1
    assert set(selected["dropped_rows"][0]) == {"locator", "raw", "reason"}
    assert selected["dropped_rows"][0]["locator"] == f"L{broken}"
    assert selected["dropped_rows"][0]["raw"] == "| 1 | 04747 |"
    assert selected["dropped_rows"][0]["reason"]

    # 档位 2（计划定宽表）0 解析行 + 1 候选行；档位 3（抽取件）可解析 → 同样不得改用档位 3
    root = tmp_path / "zero-row-plan-tier"
    _write_major(
        root,
        "080703-demo-b",
        code="080703",
        name="示例专业乙",
        plan_rows="99999   只有课码和说明文字的候选行\n",
    )
    doc = root / "sources" / "jiangsu" / "processed" / "major-source" / "25" / "document.extracted.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# 25.示例专业乙（专升本）考试计划\n\n（专业代码：080703）\n\n"
        " 1    03708   中国近现代史纲要                 2   笔试\n",
        encoding="utf-8",
    )
    selected = cc.build_majors(root)["majors"][0]
    assert selected["course_table_source"] == "plan.raw.txt"
    assert selected["parsed_rows"] == 0
    assert selected["course_codes"] == [], "档位 3 的行不得冒充被选中档位的课程表"
    assert [row["locator"] for row in selected["dropped_rows"]] == ["L1"]
    assert selected["dropped_rows"][0]["raw"] == "99999   只有课码和说明文字的候选行"
    assert selected["dropped_rows"][0]["reason"]


def test_catalog_is_byte_stable(tmp_path: Path):
    first = cc.serialize(cc.build_catalog(ROOT))
    second = cc.serialize(cc.build_catalog(ROOT))
    assert first == second

    catalog = json.loads(first)
    codes = [c["code"] for c in catalog["courses"]]
    assert codes == sorted(codes)
    for course in catalog["courses"]:
        assert course["aliases"] == sorted(set(course["aliases"]))
        assert course["majors"] == sorted(course["majors"], key=lambda m: m["code"])

    root = tmp_path / "repo"
    _write_major(root, "080901-demo-a", code="080901", name="示例专业甲", course_table=True)
    _write_major(
        root,
        "080903-demo-b",
        code="080903",
        name="示例专业乙",
        plan_rows=" 1    04747   Java 语言程序设计（一）           3   笔试\n",
    )
    paths, documents = cc.write_catalog(root)
    assert [p.name for p in paths] == ["courses.json", "majors.json"]
    assert [doc["schema_version"] for doc in documents] == [1, 1]
    assert all(p.read_text(encoding="utf-8").endswith("\n") for p in paths)
    first_bytes = [p.read_bytes() for p in paths]
    paths_again, _ = cc.write_catalog(root)
    assert paths_again == paths and [p.read_bytes() for p in paths] == first_bytes
    assert cc.check_catalog(root) == []

    # `generated_at` 是构建日期：--check 只比对内容字节，跨天不误报
    courses_path = paths[0]
    doc = json.loads(courses_path.read_text(encoding="utf-8"))
    doc["generated_at"] = "1999-01-01"
    courses_path.write_text(cc.serialize(doc), encoding="utf-8")
    assert cc.check_catalog(root) == []

    doc["courses"][0]["credits"] = 99
    courses_path.write_text(cc.serialize(doc), encoding="utf-8")
    assert cc.check_catalog(root) == [f"stale: {courses_path}"]


def test_catalog_is_deterministic_across_processes():
    """字节确定性要跨进程成立（`--check` 在 CI 的新进程里比对；集合迭代序会被哈希种子影响）。"""
    probe = (
        "import hashlib, sys;"
        "sys.path.insert(0, 'scripts');"
        "from pathlib import Path;"
        "from lib.course_pipeline import course_catalog as cc;"
        "root = Path.cwd();"
        "text = cc.serialize(cc.build_catalog(root)) + cc.serialize(cc.build_majors(root));"
        "print(hashlib.sha256(text.encode('utf-8')).hexdigest())"
    )
    digests = set()
    for seed in ("0", "1", "42"):
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        digests.add(result.stdout.strip())

    expected = hashlib.sha256(
        (cc.serialize(cc.build_catalog(ROOT)) + cc.serialize(cc.build_majors(ROOT))).encode("utf-8")
    ).hexdigest()
    assert digests == {expected}
