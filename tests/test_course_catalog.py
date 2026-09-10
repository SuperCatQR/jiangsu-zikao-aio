"""课程目录：`content/jiangsu/majors/*` 来源 → `sources/jiangsu/catalog/*.json`。

来源优先级（逐专业取实际命中档位）：现行课程表 `index.md` > 官方计划定宽表
`sources/plan.raw.txt` > 机器抽取件 `sources/jiangsu/processed/major-source/*/document.extracted.md`。
"""
from __future__ import annotations

import json
import re
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
    (major / "index.md").write_text(body, encoding="utf-8")
    if plan_rows is not None:
        (major / "sources" / "plan.raw.txt").write_text(plan_rows, encoding="utf-8")
    return major


def test_catalog_from_major_raw_txt():
    rows = cc.parse_plan_rows(RAW_PLAN)
    assert len(rows) >= 20, "080901 定宽表含 21 门课（含名称折行行）"
    by_code = {row["code"]: row for row in rows}

    java = by_code["04747"]
    assert _fold(java["name"]) == _fold("Java 语言程序设计（一）")
    assert java["credits"] == 3
    assert java["exam_method"] == "笔试"

    # 序号独占一行的版式（`13013 高级语言程序设计 4 笔试`，序号在下一行）——漏掉它是回归
    advanced = by_code["13013"]
    assert advanced["credits"] == 4
    assert advanced["exam_method"] == "笔试"
    assert advanced["name"].startswith("高级语言程序设计")

    # 名称折行的行同样入目录，locator 指回真实行号
    raw_lines = RAW_PLAN.read_text(encoding="utf-8").splitlines()
    assert _fold(by_code["00899"]["name"]) == _fold("互联网软件应用与开发（实践）")
    assert _fold(by_code["14976"]["name"]) == _fold("计算机科学与技术（本科）毕业设计")
    assert by_code["14976"]["credits"] is None  # 官方「不计学分」，不得猜
    for code in ("04747", "13013", "00899", "14976"):
        locator = by_code[code]["locator"]
        assert re.fullmatch(r"L\d+", locator), locator
        assert code in raw_lines[int(locator[1:]) - 1]


def test_catalog_from_current_major_table():
    page = (MAJOR_DIR / "index.md").read_text(encoding="utf-8")
    page_codes = cc.scan_course_codes(page)
    assert page_codes == sorted(set(page_codes))
    assert len(page_codes) == 25, "现行课程表页边界感知 5 位课码去重 25 门"
    assert "08090" not in page_codes, "`080901` / `X2080901` 的子串不是课码"
    assert "08090" in re.findall(r"\d{5}", page), "整页 naive 扫描确实会注入伪课码"

    majors = {m["code"]: m for m in cc.build_majors(ROOT)["majors"]}
    major = majors["080901"]
    assert major["course_table_source"] == "index.md"
    assert major["course_codes"] == CURRENT_TABLE_CODES

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
    assert majors_doc["schema_version"] == 1
    assert len(majors_doc["majors"]) == 54
    for major in majors_doc["majors"]:
        assert major["course_codes"], major["slug"]
        assert major["course_table_source"] in {"index.md", "plan.raw.txt", "major-source"}
        assert (ROOT / major["page"]).is_file()
        assert len(set(major["course_codes"])) == len(major["course_codes"])
    assert len(cc.build_catalog(ROOT)["courses"]) >= 60  # AC2 前半：唯一课码 ≥ 60


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
    course = next(c for c in cc.build_catalog(tmp_path)["courses"] if c["code"] == "13013")
    assert course["sources"][0]["path"].endswith("major-source/25/document.extracted.md")


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
