"""取证与放行判定：`sources/jiangsu/courses/<code>/evidence.json`（Data contracts 2）。

放行判定唯一（spec `D8` / GC2）：`syllabus.status == "extracted"` 且 `textbook_plan.status == "matched"`
→ `eligibility.level == "L1"`，否则 `blocked`。所有证据来自**仓内**抽取件 + 只读基线 URL（GC14 / GC15）。

本文件的校验探针（`_physical_lines` / `_textbook_region_start` / `_token_lines`）**自备**：
自己按 `\\n` 切物理行、自己写正则，绝不调用生产函数的读取 / 匹配 / 定位逻辑——否则校验与被校验
共用同一套约定，行号偏移、跨行归一化退化、日程区误判都测不出来（对齐 `tests/test_course_catalog.py` 的做法）。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest
import shutil

from lib.course_pipeline import evidence as ev

ROOT = Path(__file__).resolve().parents[1]
COURSES_DIR = Path("sources/jiangsu/courses")
SYLLABUS_ROOT = Path("sources/jiangsu/processed/syllabus")
TEXTBOOK_ROOT = Path("sources/jiangsu/processed/textbooks")
BASELINE = Path("ops/jiangsu/source-links.baseline.json")
OFFICIAL_TREE = "sources/jiangsu/public-official"

# `content/jiangsu/courses/*/` 现有 18 个课码目录（spec AC4）
EXISTING_COURSE_CODES = [
    "00023", "00898", "02324", "02333", "03708", "03709", "04735", "04747",
    "04751", "13000", "13003", "13013", "13015", "13017", "13180", "15040",
    "15043", "15044",
]
# spec AC4 / plan Task 2 Step 5 的**预期**集合（硬编码：不得由产物反推，否则测试自我循环）
EXPECTED_L1 = ["00898", "02333", "04747", "04751", "15040", "15043", "15044"]
EXPECTED_BLOCKED = [
    "00023", "02324", "03708", "03709", "04735", "13000", "13003",
    "13013", "13015", "13017", "13180",
]
# 基线（只读）里覆盖该课码的权威 jseea URL → 产物 `course_url`（同课多 URL 取字典序最小）；
# 未列出的课码必须为 null。硬编码来自基线实测，不由产物反推。
EXPECTED_COURSE_URLS = {
    "00898": "https://www.jseea.cn/webfile/selflearning_jcdg/2024-07-05/7214792761239670784.html",
    "02333": "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285132780508286976.html",
    "04747": "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285133106820943872.html",
    "04751": "https://www.jseea.cn/webfile/index/index_zcwj/2025-11-20/7397162260776357888.html",
    "13017": "https://www.jseea.cn/webfile/index/index_zcwj/2025-11-20/7397162260776357888.html",
    "15040": "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285134977044320256.html",
    "15043": "https://www.jseea.cn/webfile/selflearning_jcdg/2025-02-25/7300038163492245504.html",
    "15044": "https://www.jseea.cn/webfile/selflearning_jcdg/2025-02-25/7300038247357353984.html",
}
# 四份官方「考试日程与教材」抽取件（教材计划区 = 首个 `教材代号` 表头之后）
TEXTBOOK_DOCS = [
    "jiangsu-2025-04-07-schedule-textbooks",
    "jiangsu-2025-10-2026-01-schedule-textbooks",
    "jiangsu-2026-04-07-schedule-textbooks",
    "jiangsu-2026-10-2027-01-schedule-textbooks",
]
MULTILINE_DOC = "jiangsu-2026-10-2027-01-schedule-textbooks"
TEXTBOOK_HEADER = "教材代号"
CORROBORATION = ("出版社", "大学出版社", "高纲", "考试指导委员会")

# ---- 独立校验探针（不使用生产函数） -----------------------------------------
_SAMPLE_TOKENS = {
    "15040": ("150400", "150401"),
    "04747": ("047470", "047471"),
    "13003": ("130031",),
    "13140": ("131401",),
    "13141": ("131411",),
}


def _physical_lines(path: Path) -> list[str]:
    """独立读取：1-based 下标即 `sed -n '<n>p'` 显示的行。"""
    return path.read_text(encoding="utf-8").split("\n")


def _textbook_doc(name: str, filename: str = "document.raw.txt") -> Path:
    return ROOT / TEXTBOOK_ROOT / name / filename


def _textbook_region_start(lines: list[str]) -> int:
    """教材计划区起点 = 首个含表头 `教材代号` 的行（1-based）。"""
    for number, line in enumerate(lines, start=1):
        if TEXTBOOK_HEADER in line:
            return number
    raise AssertionError("文档内找不到教材计划区表头")


def _token_lines(lines: list[str], code: str) -> list[int]:
    """本文件独立的教材代号探针：行内空白分隔 token 匹配 `^<code>\\d{1,3}$`。"""
    pattern = re.compile(rf"^{re.escape(code)}\d{{1,3}}$")
    return [number for number, line in enumerate(lines, start=1) if any(pattern.match(token) for token in line.split())]


def _code_lines(lines: list[str], code: str) -> list[int]:
    """边界感知的课码出现行（独立正则，只用于日程区分布统计，不参与教材行判定）。"""
    pattern = re.compile(rf"(?<!\d){re.escape(code)}(?!\d)")
    return [number for number, line in enumerate(lines, start=1) if pattern.search(line)]


def _write_syllabus(root: Path, code: str, body: str) -> Path:
    doc = root / SYLLABUS_ROOT / f"{code}-demo-gaogang-2024" / "document.extracted.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(body, encoding="utf-8")
    return doc


def _write_textbook_doc(root: Path, name: str, body: str) -> Path:
    doc = root / TEXTBOOK_ROOT / name / "document.raw.txt"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(body, encoding="utf-8")
    return doc


def _walk_status(node, status: str) -> list[dict]:
    """递归收集所有 `status == <status>` 的字段。"""
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get("status") == status:
            found.append(node)
        for value in node.values():
            found.extend(_walk_status(value, status))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_status(item, status))
    return found


class _FrozenDate:
    """`date` 的替身：把 `build_evidence` 的构建日期冻结到指定值（F-201 跨天验证）。"""

    def __init__(self, iso: str) -> None:
        self._iso = iso

    def today(self) -> "_FrozenDate":
        return self

    def isoformat(self) -> str:
        return self._iso


def _freeze_build_date(monkeypatch: pytest.MonkeyPatch, iso: str) -> None:
    monkeypatch.setattr(ev, "date", _FrozenDate(iso))


def _is_fresh(root: Path, code: str) -> bool:
    """产物新鲜度：`generated_at` 是构建日期（T1 `check_catalog()` 口径，沿用磁盘值），其余逐字节比对。"""
    path = root / COURSES_DIR / code / "evidence.json"
    on_disk = path.read_text(encoding="utf-8")
    fresh = ev.build_evidence(root, code)
    fresh["generated_at"] = json.loads(on_disk)["generated_at"]
    return ev.serialize(fresh) == on_disk


# ---- 放行判定与 15040 试点 ---------------------------------------------------

def test_15040_is_l1():
    """15040 双齐：考纲抽取件可定位考核要求 + 教材计划区命中 `150400`/`150401`。"""
    doc = ev.build_evidence(ROOT, "15040")

    assert doc["schema_version"] == 1
    assert doc["course_code"] == "15040"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["generated_at"])
    assert doc["eligibility"] == {"level": "L1", "reasons": ["syllabus:extracted", "textbook_plan:matched"]}

    syllabus = doc["syllabus"]
    assert syllabus["status"] == "extracted"
    assert syllabus["doc_id"] == "syllabus:15040"
    assert syllabus["path"] == "sources/jiangsu/processed/syllabus/15040-xi-thought-gaogang-2024/document.extracted.md"
    assert syllabus["sha256"] == hashlib.sha256((ROOT / syllabus["path"]).read_bytes()).hexdigest()
    assert syllabus["has_assessment_requirements"] is True
    assert syllabus["has_sample_paper"] is True

    textbook = doc["textbook_plan"]
    assert textbook["status"] == "matched"
    assert textbook["doc_id"] == "schedule-textbooks:2026-10-2027-01"
    assert textbook["path"] == (
        "sources/jiangsu/processed/textbooks/jiangsu-2026-10-2027-01-schedule-textbooks/document.raw.txt"
    )
    assert textbook["locator"] == "L1958,L1962"
    assert textbook["row"].strip()
    assert textbook["row_truncated"] is False
    assert doc["source_snapshot"] is None

    # 事实层：课名 / 学分 / 考试方式来自目录 SSOT，且可回溯到官方课程表行
    assert doc["facts"]["name"]["value"] == "习近平新时代中国特色社会主义思想概论"
    assert doc["facts"]["credits"]["value"] == 3
    assert doc["facts"]["exam_method"]["value"] == "笔试"
    # 官方考纲 URL 是**课程级**信息（`course_url`）；三个字段的出处是专业计划表行（见 F-203 回归测试）
    assert doc["course_url"] == "https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285134977044320256.html"
    for fact in doc["facts"].values():
        assert fact["status"] == "verified"
        assert fact["provenance"]["kind"] == "official_major_plan"
        assert fact["provenance"]["url"] is None


def test_evaluate_eligibility_is_the_single_decision_point():
    """GC2 / spec `D8`：放行判定只此一处，两种证据的组合结果逐条固定。"""
    assert ev.evaluate_eligibility(
        {"syllabus": {"status": "extracted"}, "textbook_plan": {"status": "matched"}}
    ) == {"level": "L1", "reasons": ["syllabus:extracted", "textbook_plan:matched"]}

    expectations = {
        ("extracted", "missing"): ["syllabus:extracted", "textbook_plan:missing"],
        ("missing", "matched"): ["syllabus:missing", "textbook_plan:matched"],
        ("missing", "missing"): ["syllabus:missing", "textbook_plan:missing"],
    }
    for (syllabus_status, textbook_status), reasons in expectations.items():
        result = ev.evaluate_eligibility(
            {"syllabus": {"status": syllabus_status}, "textbook_plan": {"status": textbook_status}}
        )
        assert result == {"level": "blocked", "reasons": reasons}

    # 产物里的 `eligibility` 必须是该函数的结果（不得是渲染层 / 闸门层各自重判）
    for code in EXISTING_COURSE_CODES:
        path = ROOT / COURSES_DIR / code / "evidence.json"
        if not path.is_file():
            continue
        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert ev.evaluate_eligibility(persisted) == persisted["eligibility"], code


def test_textbook_row_multiline_layout():
    """多行版式：15040 的课码独占一行（`:1960`），教材代号在相邻行（`:1958` / `:1962`）。

    这是编写期实测踩中的真实假阴性：只按「行首课码 + 同行教材代号」匹配会漏判 15040。
    """
    lines = _physical_lines(_textbook_doc(MULTILINE_DOC))
    assert lines[1959].strip() == "15040"  # L1960：课码独占一行
    assert "150400" in lines[1957]  # L1958：大纲行
    assert "150401" in lines[1961]  # L1962：教材行
    assert "15040" not in lines[1957].split() and "15040" not in lines[1961].split(), "课码与教材代号确实不在同一行"

    textbook = ev.build_evidence(ROOT, "15040")["textbook_plan"]
    assert textbook["status"] == "matched"
    assert textbook["locator"] == "L1958,L1962"
    assert "150400" in textbook["row"] and "150401" in textbook["row"]
    # 上报的行号必须落在教材计划区内（首个表头之后），日程区的同名课码行不算
    start = _textbook_region_start(lines)
    assert all(int(locator[1:]) > start for locator in textbook["locator"].split(","))


def test_textbook_token_pattern():
    """教材代号 = 课码 + 1–3 位序号：`^<code>\\d{1,3}$` 的形态都要能命中。"""
    doc_lines = {name: _physical_lines(_textbook_doc(name)) for name in TEXTBOOK_DOCS}
    for code, tokens in _SAMPLE_TOKENS.items():
        textbook = ev.build_evidence(ROOT, code)["textbook_plan"]
        assert textbook["status"] == "matched", code
        lines = _physical_lines(ROOT / textbook["path"])
        token_lines = {name: _token_lines(doc_lines[name], code) for name in TEXTBOOK_DOCS}
        for token in tokens:
            holders = [
                name
                for name in TEXTBOOK_DOCS
                if any(token in doc_lines[name][number - 1].split() for number in token_lines[name])
            ]
            assert holders, f"{code}: 样本 token {token} 未被独立探针认定为教材代号"
        for locator in textbook["locator"].split(","):
            number = int(locator[1:])
            assert number in _token_lines(lines, code), (code, locator)
            assert any(re.fullmatch(rf"{code}\d{{1,3}}", token) for token in lines[number - 1].split()), (code, locator)


def test_13000_textbook_token_is_not_matched():
    """F3 反例：`13000` 不得被 `000151` / `000159`（属课码 `00015`）判为 matched。"""
    lines = _physical_lines(_textbook_doc("jiangsu-2026-04-07-schedule-textbooks", "document.extracted.md"))
    assert lines[1435].split()[0] == "000151"  # L1436
    assert lines[1436].strip() == "13000   英语(专升本)"  # L1437
    assert lines[1437].split()[0] == "000159"  # L1438
    # 那两个 token 的前缀是 `00015`，不满足 `^13000\d{1,3}$`
    assert not re.fullmatch(r"13000\d{1,3}", "000151")
    assert not re.fullmatch(r"13000\d{1,3}", "000159")
    assert _token_lines(lines, "13000") == []
    assert {1436, 1438} <= set(_token_lines(lines, "00015"))  # 同文档另有 00015 的行（:811/:813），此处只锁 F3 两行

    textbook = ev.build_evidence(ROOT, "13000")["textbook_plan"]
    assert textbook["status"] == "missing"
    assert textbook["locator"] is None
    assert ev.build_evidence(ROOT, "13000")["eligibility"]["level"] == "blocked"
    # 同样的两行属于课码 `00015`：它才是命中方（证明反例不是「匹配整体失效」）
    assert ev.build_evidence(ROOT, "00015")["textbook_plan"]["status"] == "matched"


def test_textbook_matching_unions_documents():
    """逐文档覆盖不同 → 匹配必须跨四份文档取并集。"""
    tokens_04751 = {name: _token_lines(_physical_lines(_textbook_doc(name)), "04751") for name in TEXTBOOK_DOCS}
    assert tokens_04751["jiangsu-2025-04-07-schedule-textbooks"] == []
    assert tokens_04751["jiangsu-2026-04-07-schedule-textbooks"] == []
    assert len(tokens_04751["jiangsu-2025-10-2026-01-schedule-textbooks"]) == 2
    assert len(tokens_04751["jiangsu-2026-10-2027-01-schedule-textbooks"]) == 2

    textbook = ev.build_evidence(ROOT, "04751")["textbook_plan"]
    assert textbook["status"] == "matched"
    assert {match["doc_id"] for match in textbook["matches"]} == {
        "schedule-textbooks:2025-10-2026-01",
        "schedule-textbooks:2026-10-2027-01",
    }
    for match in textbook["matches"]:
        assert (ROOT / match["path"]).is_file()
        assert _token_lines(_physical_lines(ROOT / match["path"]), "04751"), match

    # `047470` 的相反分布：2025-04-07 / 2026-04-07 有，另两份没有
    tokens_04747 = {name: _token_lines(_physical_lines(_textbook_doc(name)), "04747") for name in TEXTBOOK_DOCS}
    assert tokens_04747["jiangsu-2025-10-2026-01-schedule-textbooks"] == []
    assert tokens_04747["jiangsu-2026-10-2027-01-schedule-textbooks"] == []
    textbook_04747 = ev.build_evidence(ROOT, "04747")["textbook_plan"]
    assert textbook_04747["status"] == "matched"
    assert {match["doc_id"] for match in textbook_04747["matches"]} == {
        "schedule-textbooks:2025-04-07",
        "schedule-textbooks:2026-04-07",
    }


def test_row_truncated_reflects_the_published_row_only(tmp_path: Path):
    """F-202：`row_truncated` 只描述**发布行**（Data contracts 2：「> 200 字符时截断并置 true，仅在实际截断时为 true」）。

    `00023`（`len(row) == 162`）与 `13015`（`len(row) == 177`）的发布行都没超 200 字符，但**非规范**
    文档（较旧的那份）的命中窗口被截断过：旧实现把 `matches[].row_truncated` OR 进发布标志，于是给出
    `row_truncated == true`，既与同行文本矛盾，也与同一对象的 `matches[]` 矛盾。
    """
    for code, width in (("00023", 162), ("13015", 177)):
        path = ROOT / COURSES_DIR / code / "evidence.json"
        textbook = json.loads(path.read_text(encoding="utf-8"))["textbook_plan"]
        assert textbook["status"] == "matched", code
        assert len(textbook["row"]) == width and width <= 200, code
        assert textbook["row_truncated"] is False, code
        assert any(match["row_truncated"] for match in textbook["matches"]), (
            f"{code}: 非规范文档确实截断过，只是不该体现在发布行的标志上"
        )

    # 读者 / T6 闸门会用的不变量：置了 true 的发布行必须真是被截断的那一行（200 字符上限）
    for code in EXISTING_COURSE_CODES:
        textbook = json.loads((ROOT / COURSES_DIR / code / "evidence.json").read_text(encoding="utf-8"))["textbook_plan"]
        if textbook["status"] == "matched" and textbook["row_truncated"]:
            assert len(textbook["row"]) == 200, code

    # 发布行自身超长 → 必须为 true（标志不是被一次性关掉）
    root = tmp_path / "published-row-truncation"
    _write_textbook_doc(
        root,
        "jiangsu-demo-schedule-textbooks",
        "附件 3\n课程代号  课程名称  教材代号  教材名称  作者  出版社  版次\n"
        "15040   " + "长" * 250 + "   150401   示例教材   本书编写组   高等教育出版社   2023 年\n",
    )
    textbook = ev.build_evidence(root, "15040")["textbook_plan"]
    assert textbook["status"] == "matched"
    assert len(textbook["row"]) == 200 and textbook["row_truncated"] is True


def test_schedule_occurrence_is_not_textbook_row(tmp_path: Path):
    """只在考试日程区出现的课码不得判 matched（日程区锚点：extracted.md:70-168，15040 出现 10 次）。"""
    # 真实语料：四份文档的日程区都含 15040，而命中的教材行必须在教材计划区内
    for name in TEXTBOOK_DOCS:
        lines = _physical_lines(_textbook_doc(name, "document.extracted.md"))
        start = _textbook_region_start(lines)
        schedule = [number for number in _code_lines(lines, "15040") if number < start]
        assert len(schedule) >= 10, (name, len(schedule))
        assert schedule[-1] < start, name
    assert len([n for n in _code_lines(_physical_lines(_textbook_doc(MULTILINE_DOC, "document.extracted.md")), "15040") if 70 <= n <= 168]) == 10

    for match in ev.build_evidence(ROOT, "15040")["textbook_plan"]["matches"]:
        lines = _physical_lines(ROOT / match["path"])
        start = _textbook_region_start(lines)
        for locator in match["locator"].split(","):
            assert int(locator[1:]) > start, (match["path"], locator)

    # 合成语料（决定性）：课码只在日程区出现、教材区没有它的行 → 不得 matched
    root = tmp_path / "schedule-only"
    _write_textbook_doc(
        root,
        "jiangsu-demo-schedule-textbooks",
        "附件 1\n江苏省高等教育自学考试 2026 年 10 月考试日程\n"
        "专业代码及名称      上午 9:00-11:30\n"
        "X2080901  15040 习近平新时代中国特色社会主义思想概论  00022 高等数学(工专)\n"
        "附件 3\n"
        "课程代号  课程名称  教材代号  教材名称  作者  出版社  版次\n"
        "00022   高等数学(工专)   000221   高等数学(工专)(附大纲)   吴纪桃、漆毅   北京大学出版社   2023 年\n",
    )
    assert ev.build_evidence(root, "15040")["textbook_plan"]["status"] == "missing"
    assert ev.build_evidence(root, "00022")["textbook_plan"]["status"] == "matched"


# ---- 命名缺口 / 零 AI 产物 ---------------------------------------------------

def test_00023_blocked_without_syllabus():
    """00023 的教材行已存在，`blocked` 只因官方考纲未入库。"""
    page = (ROOT / "content" / "jiangsu" / "courses" / "00023" / "plan.md").read_text(encoding="utf-8")
    assert "考纲空态（missing-source）" in page  # `plan.md:13` 的页面自述
    assert not list((ROOT / SYLLABUS_ROOT).glob("00023-*"))

    doc = ev.build_evidence(ROOT, "00023")
    assert doc["syllabus"]["status"] == "missing"
    assert doc["syllabus"]["path"] is None
    assert doc["textbook_plan"]["status"] == "matched"
    assert doc["eligibility"]["level"] == "blocked"
    assert doc["eligibility"]["reasons"] == ["syllabus:missing", "textbook_plan:matched"]


def test_blocked_course_has_no_generated_artifacts():
    """非 `L1` 课程零 AI 产物：`sources/jiangsu/courses/<code>/content.json` 不存在（spec AC4）。"""
    checked = []
    for path in sorted((ROOT / COURSES_DIR).glob("*/evidence.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["eligibility"]["level"] == "L1":
            continue
        assert not (path.parent / "content.json").exists(), path.parent.name
        checked.append(path.parent.name)
    assert checked == EXPECTED_BLOCKED
    assert not (ROOT / COURSES_DIR / "00023" / "content.json").exists()


def test_gap_fields_carry_impact_and_next_evidence():
    """每个 `named_gap` 字段都必须写明缺口影响与下一份需要的证据。"""
    # 14976 官方标「不计学分」→ 真实命名缺口（不是合成数据）
    real_gap = ev.build_evidence(ROOT, "14976")
    credits = real_gap["facts"]["credits"]
    assert credits["status"] == "named_gap" and credits["value"] is None
    assert credits["gap_impact"].strip() and credits["next_evidence"].strip()

    docs = [real_gap]
    docs += [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / COURSES_DIR).glob("*/evidence.json"))
    ]
    assert len(docs) == 1 + len(EXISTING_COURSE_CODES)

    gaps = 0
    for doc in docs:
        for gap in _walk_status(doc, "named_gap"):
            assert gap["gap_impact"].strip(), (doc["course_code"], gap)
            assert gap["next_evidence"].strip(), (doc["course_code"], gap)
            assert gap["value"] is None, (doc["course_code"], gap)
            gaps += 1
        # 命名缺口不止 `facts`：`syllabus` / `textbook_plan` 空态同样要给出影响与下一步
        for block in ("syllabus", "textbook_plan"):
            if doc[block]["status"] == "missing":
                assert doc[block]["gap_impact"].strip(), (doc["course_code"], block)
                assert doc[block]["next_evidence"].strip(), (doc["course_code"], block)
    assert gaps >= 1


# ---- 离线 / 字节稳定 / 基线只读 ----------------------------------------------

def test_offline_never_network(monkeypatch):
    """`offline=True`（默认）只用仓内抽取件与只读基线 URL，绝不触网。"""

    def _boom(*args, **kwargs):
        raise AssertionError("offline 路径不得调用 urllib.request.urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    for code in EXPECTED_L1:
        doc = ev.build_evidence(ROOT, code)
        assert doc["eligibility"]["level"] == "L1", code
        assert doc["source_snapshot"] is None


def test_build_evidence_refuses_online_path_in_b1():
    """B1 不落盘官方快照（GC15）：`offline=False` 必须显式失败，不得静默退化成联网入库。"""
    with pytest.raises(RuntimeError, match="offline"):
        ev.build_evidence(ROOT, "15040", offline=False)


def test_build_evidence_is_byte_stable():
    """同一输入两次序列化字节一致；sha256 现算，抓取时间戳不进可比字段。"""
    first = ev.serialize(ev.build_evidence(ROOT, "15040"))
    second = ev.serialize(ev.build_evidence(ROOT, "15040"))
    assert first == second
    assert hashlib.sha256(first.encode("utf-8")).hexdigest() == hashlib.sha256(second.encode("utf-8")).hexdigest()
    assert "fetched_at" not in first
    assert json.loads(first)["source_snapshot"] is None

    # 跨进程（PYTHONHASHSEED 变化）也要一致：集合迭代序不得进入产物
    probe = (
        "import hashlib, sys;"
        "sys.path.insert(0, 'scripts');"
        "from pathlib import Path;"
        "from lib.course_pipeline import evidence as ev;"
        "text = ev.serialize(ev.build_evidence(Path.cwd(), '15040'));"
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
    assert digests == {hashlib.sha256(first.encode("utf-8")).hexdigest()}


def test_baseline_and_official_tree_untouched():
    """GC14 / GC15：跑完取证后基线与官方原件树的 `git diff` 必须为空。"""
    baseline = ROOT / BASELINE
    before = hashlib.sha256(baseline.read_bytes()).hexdigest()
    for code in EXISTING_COURSE_CODES:
        ev.build_evidence(ROOT, code)
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == before

    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(BASELINE), OFFICIAL_TREE],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---- 产物集合（AC4 的实测锁定） ----------------------------------------------

def test_evidence_artifacts_lock_the_measured_l1_set():
    """18 份产物齐备，`L1` 集合与 AC4 预期逐元素相等，其余 11 门 `blocked` 且 `reasons` 非空。

    与预期不符时**不得**放宽判定：这是 STOP 条件的可运行形式（plan Task 2 Step 5 / spec AC4）。
    """
    paths = sorted((ROOT / COURSES_DIR).glob("*/evidence.json"))
    assert [path.parent.name for path in paths] == EXISTING_COURSE_CODES, "18 份产物必须与现有课码目录一一对应"

    docs = {path.parent.name: json.loads(path.read_text(encoding="utf-8")) for path in paths}
    l1 = sorted(code for code, doc in docs.items() if doc["eligibility"]["level"] == "L1")
    blocked = sorted(set(docs) - set(l1))
    assert l1 == EXPECTED_L1
    assert blocked == EXPECTED_BLOCKED
    for code in blocked:
        assert docs[code]["eligibility"]["reasons"], code
        assert any(reason.endswith(":missing") for reason in docs[code]["eligibility"]["reasons"]), code

    # `L1` = 有考纲抽取件的课码 ∩ 教材计划匹配的课码（两条件都必要）
    syllabus_codes = sorted(path.name.split("-")[0] for path in (ROOT / SYLLABUS_ROOT).iterdir())
    with_syllabus = sorted(code for code in EXISTING_COURSE_CODES if code in syllabus_codes)
    assert with_syllabus == EXPECTED_L1
    with_textbook = sorted(
        code for code in EXISTING_COURSE_CODES if docs[code]["textbook_plan"]["status"] == "matched"
    )
    assert set(EXPECTED_L1) <= set(with_textbook)
    assert sorted(set(with_syllabus) & set(with_textbook)) == EXPECTED_L1


def test_evidence_shape_invariants():
    """Data contracts 2 的形状不变量：键集合 / 枚举 / sha256 / 可回溯来源。"""
    for code in EXISTING_COURSE_CODES:
        path = ROOT / COURSES_DIR / code / "evidence.json"
        assert path.is_file(), path
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert set(doc) == {
            "schema_version", "course_code", "generated_at", "course_url", "facts",
            "syllabus", "textbook_plan", "eligibility", "source_snapshot",
        }, code
        assert doc["schema_version"] == 1 and doc["course_code"] == code
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["generated_at"])
        assert doc["course_url"] is None or doc["course_url"].startswith("https://www.jseea.cn/"), code
        assert doc["source_snapshot"] is None  # 离线路径（GC15）
        assert set(doc["eligibility"]) == {"level", "reasons"}
        assert doc["eligibility"]["level"] in {"L1", "blocked"}
        assert isinstance(doc["eligibility"]["reasons"], list) and doc["eligibility"]["reasons"]
        assert doc["syllabus"]["status"] in {"extracted", "missing"}
        assert doc["textbook_plan"]["status"] in {"matched", "missing"}

        for name, fact in doc["facts"].items():
            assert fact["status"] in {"verified", "named_gap"}, (code, name)
            if fact["status"] == "named_gap":
                assert fact["value"] is None and fact["gap_impact"] and fact["next_evidence"]
                continue
            provenance = fact["provenance"]
            assert set(provenance) == {"doc_id", "kind", "url", "path", "locator"}, (code, name)
            assert provenance["doc_id"] and provenance["kind"] and provenance["locator"]
            assert provenance["url"] or provenance["path"]
            assert provenance["url"] is None or provenance["url"].startswith("https://www.jseea.cn/")
            lines = _physical_lines(ROOT / provenance["path"])
            number = int(provenance["locator"][1:])
            assert code in lines[number - 1], (code, name, provenance)

        if doc["syllabus"]["status"] == "extracted":
            assert re.fullmatch(r"[0-9a-f]{64}", doc["syllabus"]["sha256"])
            assert doc["syllabus"]["has_assessment_requirements"] is True
        else:
            assert doc["syllabus"]["path"] is None and doc["syllabus"]["sha256"] is None

        if doc["textbook_plan"]["status"] == "matched":
            assert (ROOT / doc["textbook_plan"]["path"]).is_file()
            assert re.fullmatch(r"L\d+(,L\d+)*", doc["textbook_plan"]["locator"])
            assert doc["textbook_plan"]["row"].strip()
            assert doc["textbook_plan"]["matches"]
        else:
            assert doc["textbook_plan"]["locator"] is None and doc["textbook_plan"]["row"] is None


def test_fact_provenance_kind_matches_the_cited_evidence():
    """F-203：`facts[*].provenance` 的 `kind` 必须与**所引证据**同类（Data contracts 2）。

    课名 / 学分 / 考试方式取自专业计划表课程行（`path` + `locator`）→ `kind == "official_major_plan"`；
    基线里的官方 URL 是另一份文档（考纲页 / 政策文件页），只作为课程级 `course_url`。旧实现把这个
    考纲 URL 与 `official_major_plan` 配对，而 plan § Data contracts 2 对同一个 URL 标的是
    `official_syllabus` —— 于是同一个 provenance 对象里 `kind` 描述的是 `path`，`url` 却是别的文档。
    """
    for code in EXISTING_COURSE_CODES:
        path = ROOT / COURSES_DIR / code / "evidence.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["course_url"] == EXPECTED_COURSE_URLS.get(code), code
        for name, fact in doc["facts"].items():
            if fact["status"] != "verified":
                continue
            provenance = fact["provenance"]
            assert provenance["kind"] == "official_major_plan", (code, name)
            assert provenance["url"] is None, (code, name)
            assert provenance["path"] and provenance["locator"], (code, name)

    # 15040：考纲 URL 是课程级来源，不是三个字段的出处
    doc = json.loads((ROOT / COURSES_DIR / "15040" / "evidence.json").read_text(encoding="utf-8"))
    assert doc["course_url"] == EXPECTED_COURSE_URLS["15040"]
    assert all(fact["provenance"]["url"] != doc["course_url"] for fact in doc["facts"].values())


def test_syllabus_requires_locatable_assessment_requirements(tmp_path: Path):
    """`extracted` 的判据是**能定位考核要求小节**，不是「目录里有文件」。

    四份既有高纲抽取件的章节序号并不一致：15040 / 15043 / 15044 用 `三、考核知识点与考核要求`，
    00898 / 02333 / 04747 / 04751 用 `二、考核知识点与考核要求`（同一小节，页码页眉换行后逐行核对）。
    因此判据取小节名的稳定部分；标题原文逐字记入 `requirements_heading` 供复核。
    """
    root = tmp_path / "syllabus-shape"
    _write_syllabus(root, "15040", "# 大纲\n\n一、课程内容\n\n二、本章重点\n")
    missing = ev.build_evidence(root, "15040")["syllabus"]
    assert missing["status"] == "missing" and missing["has_assessment_requirements"] is False

    doc = _write_syllabus(root, "15040", "# 大纲\n\n二、考核知识点与考核要求\n\n识记：示例\n\n参考样卷\n")
    extracted = ev.build_evidence(root, "15040")["syllabus"]
    assert extracted["status"] == "extracted"
    assert extracted["has_assessment_requirements"] is True
    assert extracted["requirements_heading"] == "二、考核知识点与考核要求"
    assert extracted["has_sample_paper"] is True
    assert extracted["sha256"] == hashlib.sha256(doc.read_bytes()).hexdigest()

    # 只是「说明书里提到过该小节名」不算定位到小节
    _write_syllabus(root, "15041", "# 大纲\n\n了解各节的学习目的与要求、考核知识点与考核要求\n")
    assert ev.build_evidence(root, "15041")["syllabus"]["status"] == "missing"

    # 真语料：7 份抽取件都能定位到该小节，且 7 个课码正是 `L1` 集合
    located = {
        path.name.split("-")[0]: ev.build_evidence(ROOT, path.name.split("-")[0])["syllabus"]
        for path in sorted((ROOT / SYLLABUS_ROOT).iterdir())
    }
    assert sorted(located) == EXPECTED_L1
    for code, syllabus in located.items():
        assert syllabus["status"] == "extracted", code
        assert syllabus["has_assessment_requirements"] is True, code
        assert re.fullmatch(r"[一二三四五六七八九十]+、考核知识点与考核要求", syllabus["requirements_heading"]), code


def test_supporting_locator_resolves_folded_course_names(tmp_path: Path):
    """W4：±2 行窗口把「折行课名」也解析到位，且不改动任何既有 locator。

    真形态（`10993` / `12656` 等 8 门）：课名折行、**课码行夹在两段中间** ——

    ```text
    L71                工程数学（线性代数、概率论
    L72  5      10993                            6   笔试
    L73                与数理统计）
    ```

    逐行包含判定永远不可能命中（没有单行含全名），把窗口直连同样不行（课码行插在中间）。
    本用例用**合成**抽取件锁住语义（不依赖某门课的版式），再对全量 722 门课复算双侧计数。
    """
    root = tmp_path / "locator-root"
    doc = root / "majors" / "plan.raw.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        " 4      00023   高等数学（工本）              10     笔试\n"
        "                工程数学（线性代数、概率论\n"
        " 5      10993                            6   笔试\n"
        "                与数理统计）\n"
        "        13013   高级语言程序设计                 4   笔试\n",
        encoding="utf-8",
    )
    source = {"doc_id": "major-plan:99999", "path": "majors/plan.raw.txt", "locator": "L3"}

    # ① 跨行折名：前段在 L2、后段在 L4 → 引折名起始行 L2（不再回落课码行 L3）
    assert ev._supporting_locator(root, source, "工程数学（线性代数、概率论与数理统计）") == "L2"
    # ② 整行命中优先（原行为不变）：值完整落在中心行
    assert ev._supporting_locator(root, source, "10993") == "L3"
    # ③ 都命中不了 → 保持原 locator（不臆造行号）
    assert ev._supporting_locator(root, source, "不存在的课名") == "L3"
    # ④ 非字符串值（credits 是 int）→ 保持原 locator，不做字符串化匹配
    assert ev._supporting_locator(root, source, 6) == "L3"

    # ⑤ C2-015：前段同时出现在**邻课**的折名行上时必须**就近取行**，不得指到更远的那一行。
    #    `02208 电气传动与可编程控制器（PLC）（实践）` 的前段正是 `02207` 的完整课名 ——
    #    旧实现取窗口内最远的命中行，把引用指到了邻课行上（跨课误引）。
    neighbor = root / "majors" / "neighbor.raw.txt"
    neighbor.write_text(
        "      02207   电气传动与可编程控制器（PLC）      3   笔试\n"
        " 10             电气传动与可编程控制器（PLC）\n"
        "      02208                             1   实践\n"
        "                 （实践）\n",
        encoding="utf-8",
    )
    neighbor_source = {"doc_id": "major-plan:99998", "path": "majors/neighbor.raw.txt", "locator": "L3"}
    assert ev._supporting_locator(root, neighbor_source, "电气传动与可编程控制器（PLC）（实践）") == "L2", (
        "折名起点取到了更远的邻课行（L1）而不是最近的前段行（L2）"
    )

    # ⑥ 诚实谓词必须**可伪**：错误行号 / 不存在的值都不得判为「支撑」
    neighbor_lines = _physical_lines(neighbor)
    assert _citation_supports_value(neighbor_lines, "L2", "电气传动与可编程控制器（PLC）（实践）")
    assert not _citation_supports_value(neighbor_lines, "L4", "电气传动与可编程控制器（PLC）（实践）")
    assert not _citation_supports_value(neighbor_lines, "L2", "完全不存在的课名ZZZ")

    # 全量复算：722 门课 / 2123 个 (course, field) 对的「所引行是否支撑该值」
    catalog = json.loads((ROOT / "sources" / "jiangsu" / "catalog" / "courses.json").read_text(encoding="utf-8"))
    cache: dict[str, list[str]] = {}
    worsened: list[tuple] = []
    unresolved: list[tuple] = []
    pairs = 0
    for course in catalog["courses"]:
        for field in ev.FACT_FIELDS:
            value = course.get(field)
            if value in (None, ""):
                continue
            source_entry = (course.get("sources") or [None])[0]
            if not source_entry:
                continue
            pairs += 1
            path = source_entry["path"]
            if path not in cache:
                cache[path] = _physical_lines(ROOT / path)
            lines = cache[path]
            center = int(source_entry["locator"][1:])
            text = str(value)
            line_ok = text in " ".join(lines[center - 1].split())

            resolved = ev._supporting_locator(ROOT, source_entry, value)

            if not _citation_supports_value(lines, resolved, text):
                unresolved.append((course["code"], field, text, resolved))
            elif line_ok and resolved != source_entry["locator"]:
                worsened.append((course["code"], field, text, resolved))

    assert pairs == 2123, f"722 课程目录的 (course, field) 对数变了：{pairs}"
    assert not unresolved, f"解析后的 locator 仍不支撑该值：{unresolved}"
    assert not worsened, f"fix 不得把原本正确的 locator 改坏：{worsened}"
    assert len(cache) > 0


def _citation_supports_value(lines: list[str], locator: str, value: str) -> bool:
    """引用是否**支撑**该值（C2-015 的诚实口径，替代旧的「含前半段」弱谓词）。

    两个必要条件，都对着**读者能不能从所引行读出来源**这个性质，而不是「生成器当初怎么选的」：
    ① **起点**：所引行含该值的某个非空前缀（引用必须指向值**开始**出现的行）；
    ② **可读全**：从所引行起、在 ±`ROW_WINDOW_RADIUS` 行内按序拼得出**完整**值
    （折名场景：前段在所引行，后段在紧随的续行）。

    旧谓词 `text in line or (moved and text[: len(text) // 2] in line)` 对移动过的 locator 只要求
    「行内含值的前半段」，于是「引用指到**邻课**的行」也算通过 —— 指标因此不可伪。
    本谓词可伪：对不存在的值、对远离值所在处的错误行号，都返回 `False`。
    """
    start = int(locator[1:]) - 1
    if not any(value[:end] in ev._fold(lines[start]) for end in range(1, len(value) + 1)):
        return False
    remaining = value
    for index in range(start, min(len(lines), start + ev.ROW_WINDOW_RADIUS + 1)):
        folded = ev._fold(lines[index])
        for end in range(len(remaining), 0, -1):
            if remaining[:end] in folded:
                remaining = remaining[end:]
                break
    return not remaining


def test_committed_artifacts_match_a_fresh_build():
    """磁盘上的 18 份产物必须与当前来源一致：不得停在旧判定逻辑上（离线，只读）。

    `generated_at` 是**构建日期**，比对时沿用磁盘值再逐字节比内容（T1 `check_catalog()` 的
    「跨天不误报」口径，`tests/test_course_catalog.py:589-594`）；其它字段一律逐字节比对。
    """
    for code in EXISTING_COURSE_CODES:
        path = ROOT / COURSES_DIR / code / "evidence.json"
        assert path.is_file(), path
        assert _is_fresh(ROOT, code), code


def test_freshness_comparison_ignores_build_date_but_catches_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """F-201：跨天不得误报（两个不同构建日期都判 fresh），内容漂移必须判 stale。

    ① 真实 18 份产物：磁盘构建日期下 fresh，构建日期冻结到**磁盘日期 + 3 天**后仍 fresh；
    ② 冻结日期确实进入构建结果，且与磁盘产物只差 `generated_at` 一行（日期从产物读取，不硬编码）；
    ③ 篡改一个内容值（合成根，不动仓库产物）→ 必须判 stale，证明比对不是空转。
    """
    path = ROOT / COURSES_DIR / "15040" / "evidence.json"
    disk_date = json.loads(path.read_text(encoding="utf-8"))["generated_at"]
    assert all(_is_fresh(ROOT, code) for code in EXISTING_COURSE_CODES)

    other_date = (datetime.date.fromisoformat(disk_date) + datetime.timedelta(days=3)).isoformat()
    _freeze_build_date(monkeypatch, other_date)
    assert all(_is_fresh(ROOT, code) for code in EXISTING_COURSE_CODES)

    on_disk = path.read_text(encoding="utf-8")
    fresh = ev.serialize(ev.build_evidence(ROOT, "15040"))
    assert fresh != on_disk, "冻结日期必须真的进入构建结果，否则本条断言空转"
    assert fresh.replace(f'"generated_at": "{other_date}"', f'"generated_at": "{disk_date}"') == on_disk

    root = tmp_path / "freshness-drift"
    _write_syllabus(root, "15040", "# 大纲\n\n三、考核知识点与考核要求\n\n识记：示例\n")
    _write_textbook_doc(
        root,
        "jiangsu-demo-schedule-textbooks",
        "附件 3\n课程代号  课程名称  教材代号  教材名称  作者  出版社  版次\n"
        "15040   习近平新时代中国特色社会主义思想概论   150401   习近平新时代中国特色社会主义思想概论   "
        "本书编写组   高等教育出版社   2023 年\n",
    )
    paths, _ = ev.write_evidence(root, ["15040"])
    assert _is_fresh(root, "15040"), "刚写完的产物必须判 fresh"

    drifted = json.loads(paths[0].read_text(encoding="utf-8"))
    drifted["facts"]["name"]["value"] = "被篡改的课名"
    paths[0].write_text(ev.serialize(drifted), encoding="utf-8")
    assert not _is_fresh(root, "15040"), "内容漂移必须判 stale（比对不得空转）"


def test_write_evidence_lands_on_disk_byte_identically(tmp_path: Path):
    """`write_evidence` 落盘路径 = `sources/jiangsu/courses/<code>/evidence.json`，且逐字节等于现算结果。"""
    root = tmp_path / "repo"
    _write_syllabus(root, "15040", "# 大纲\n\n三、考核知识点与考核要求\n\n1.示例节\n识记：示例\n")
    _write_textbook_doc(
        root,
        "jiangsu-demo-schedule-textbooks",
        "附件 3\n课程代号  课程名称  教材代号  教材名称  作者  出版社  版次\n"
        "15040   习近平新时代中国特色社会主义思想概论   150401   习近平新时代中国特色社会主义思想概论   "
        "本书编写组   高等教育出版社   2023 年\n",
    )

    paths, documents = ev.write_evidence(root, ["15040"])
    assert [path.relative_to(root).as_posix() for path in paths] == [
        "sources/jiangsu/courses/15040/evidence.json"
    ]
    body = paths[0].read_text(encoding="utf-8")
    assert body.endswith("\n")
    assert body == ev.serialize(ev.build_evidence(root, "15040"))
    assert documents[0]["eligibility"]["level"] == "L1"

    # `course_codes()` = 现有课程页目录（`--all` 的输入口径）
    assert ev.course_codes(ROOT) == EXISTING_COURSE_CODES


# ---- C2-006：课码必须在**写入者**这一层校验 --------------------------------------------

def test_evidence_path_rejects_non_code_and_never_escapes_root(tmp_path: Path):
    """C2-006：`--stages evidence` 曾让 crafted query 逃出仓根并写盘（exit 0）。

    校验放在 `evidence_path()` / `build_evidence()` / `write_evidence()` 三处 —— 调用点无法绕过，
    也不依赖调用方记得先跑 `resolve` 阶段。
    """
    from lib.course_pipeline import evidence as ev_mod

    root = tmp_path / "repo"
    (root / "sources").mkdir(parents=True)

    for crafted in ("../../../../escaped", "1504", "150400", "abcde", "", "15040/../..", None, 15040):
        with pytest.raises(ValueError):
            ev_mod.evidence_path(root, crafted)

    with pytest.raises(ValueError):
        ev_mod.write_evidence(root, ["../../../../escaped"])

    # 逃逸路径确实没有产生任何文件
    assert not (tmp_path / "escaped").exists()


def test_build_evidence_rejects_non_code(tmp_path: Path):
    """`build_evidence()` 同样拒绝非课码（唯一入口的守卫，不靠 CLI 阶段开关）。"""
    from lib.course_pipeline import evidence as ev_mod

    root = tmp_path / "repo"
    (root / "sources").mkdir(parents=True)
    with pytest.raises(ValueError):
        ev_mod.build_evidence(root, "../../escape")


def test_cli_build_rejects_crafted_query_even_without_resolve_stage(tmp_path: Path):
    """C2-006 的入口侧：`build <crafted> --stages evidence` 必须 exit ≠ 0，且仓根外零写入。"""
    import importlib.util

    fake_root = tmp_path / "repo"
    (fake_root / "scripts").mkdir(parents=True)
    (fake_root / "scripts" / "lib").symlink_to(ROOT / "scripts" / "lib", target_is_directory=True)
    (fake_root / "ops" / "jiangsu").mkdir(parents=True)
    shutil.copy(ROOT / "ops" / "jiangsu" / "source-links.baseline.json",
                fake_root / "ops" / "jiangsu" / "source-links.baseline.json")
    (fake_root / "sources").mkdir()
    shutil.copy(ROOT / "scripts" / "build-course-content.py", fake_root / "scripts" / "build-course-content.py")

    spec = importlib.util.spec_from_file_location("bce", fake_root / "scripts" / "build-course-content.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.ROOT = fake_root

    rc = cli.run_build("../../../../escaped", backend="replay", stages=["evidence"], dry_run=False, record_fixtures=False)

    assert rc != 0, "crafted query 必须被拒绝"
    assert not (fake_root.parent / "escaped").exists(), "不得写出仓根之外"
    assert not (fake_root.parent.parent / "escaped").exists()
    # 也确认没有落进 fake_root 内的非课码目录
    assert not (fake_root / "sources" / "jiangsu" / "courses").exists() or not any(
        p.name == "escaped" for p in (fake_root / "sources" / "jiangsu" / "courses").iterdir()
    )
