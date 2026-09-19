"""知识模型抽取与覆盖率（Data contracts 3 / spec AC5）。

被校验对象：产物 `sources/jiangsu/courses/15040/knowledge-model.json` 与生产函数
`extract_knowledge_model()`。源侧探针（`_toc_titles` / `_index_names` / `_doc_lines` / `_fold`）
本文件**自备**——自己切物理行、自己写正则，不调用生产函数的读取 / 归一化 / 切分逻辑，
否则折行合并、页码丢弃、章目切片会共用同一套约定而测不出来（对齐 `tests/test_course_evidence.py`）。

硬约束（plan Global Constraints / Data contracts 3）：确定性无 LLM、章标题与 `syllabus.md` 章目逐字一致、
`quote` ≤ 60 字符且逐字来自考纲、点 id 唯一且匹配 `^15040-(intro|ch\\d{2})-s\\d+-p\\d+$`、
未编号段落只进 `unmodeled[]`、覆盖率分母 = 考纲带编号节数 **61**、模型内无 > 200 字符连续官方正文串。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import tempfile

from lib.course_pipeline import knowledge_model as km
from tests.test_chapter_index_study_plan import CHAPTER_NAMES_15040

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path("sources/jiangsu/courses/15040/knowledge-model.json")
SYLLABUS_MD = Path("content/jiangsu/courses/15040/syllabus.md")
MANUAL_INDEX = Path("content/jiangsu/courses/15040/index.md")
SYLLABUS_DOC = Path("sources/jiangsu/processed/syllabus/15040-xi-thought-gaogang-2024/document.extracted.md")

# 导论第 1 节（源 `document.extracted.md:221-226`）的 5 条识记短语，逐字来自考纲
INTRO_MEMORIZE = (
    "世界百年未有之大变局加速演进",
    "中华民族伟大复兴进入关键时期",
    "中国式现代化全面推进拓展",
    "科学社会主义在 21 世纪的中国焕发新的蓬勃生机",
    "中国共产党自我革命开辟新的境界",
)
# 导论第 4 节的 3 条识记短语：源 `:238` 与页码行 `:240` 之间夹着换页，末条不得被页码污染
INTRO_4_MEMORIZE = ("党的指导思想", "国家的指导思想", "“四个伟大”")

# 合成考纲片段（未编号考核段落 + 无识记/领会/应用前缀的编号节）
FRAGMENT = """大纲目录

导论

第一章 示例章

Ⅳ 关于大纲的说明与考核实施要求
附录：参考样卷
大纲后记

导论
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.示例节
三、考核知识点与考核要求
这是一段没有编号的考核说明，考纲未给出节号。
1.示例节
识记：甲；乙。
领会：丙。
四、本章重点
甲；丙。

第一章 示例章
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.无前缀节
三、考核知识点与考核要求
1.无前缀节
本节考核内容没有识记领会应用前缀；第二句也没有。
四、本章重点
无。
"""

# 合成考纲片段（F-301：`识记：` 行出现在任何编号节之前 → `current is None`。
# 15040 的 18 个要求块首行全部是编号节，故本片段是这条守卫唯一的复现路径；B2–B4 复用抽取器时会遇到）
ORPHAN_LINE = "识记：考纲在第一个编号节之前先给了一段总述性识记要求；第二句。"
ORPHAN_FRAGMENT = f"""大纲目录

导论

Ⅳ 关于大纲的说明与考核实施要求
附录：参考样卷
大纲后记

导论
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.示例节
三、考核知识点与考核要求
{ORPHAN_LINE}
1.示例节
识记：甲；乙。
领会：丙。
四、本章重点
甲；丙。
"""

# 合成手工页（F-303）：`1.1` 与模型 ch01 第 1 节匹配；`1.2` 手工页有、模型没有；
# 模型导论第 1 节手工页没有 → 三条分支各命中一次
MANUAL_PAGE = """# 99999 示例课程

## 章节知识树

#### 1.1 无前缀节 — 🟢🟡
#### 1.2 考纲缺失的节 — 🟢
"""


# ---- 自备探针（不使用生产函数） ---------------------------------------------

def _fold(text: str) -> str:
    """折行 / 分页符归一：`\\x0c` 与连续空白折叠为单个半角空格（与抽取件版式一致）。"""
    return re.sub(r"\s+", " ", text.replace("\x0c", " ")).strip()


def _model() -> dict:
    return json.loads((ROOT / MODEL_PATH).read_text(encoding="utf-8"))


def _doc_lines() -> list[str]:
    return (ROOT / SYLLABUS_DOC).read_text(encoding="utf-8").split("\n")


def _folded_source() -> str:
    """源文去噪文本：丢弃独占一行的页码与空行、折叠全部空白（折行合并**不插空格**）。

    与生产合并同口径但**独立实现**——用于逐字复核（折行跨页、页码插在要求块中间时仍可对照）。
    """
    kept = [
        line
        for line in _doc_lines()
        if line.strip() and not re.fullmatch(r"\d{1,3}", line.strip())
    ]
    return re.sub(r"\s+", "", "".join(kept))


def _toc_titles() -> list[str]:
    """独立探针：`大纲目录` 切片中的章标题（折叠内部空白；Ⅰ–Ⅳ / 附录 / 大纲后记不算章）。"""
    lines = _doc_lines()
    start = next(index for index, line in enumerate(lines) if _fold(line) == "大纲目录")
    titles: list[str] = []
    for line in lines[start + 1:]:
        text = _fold(line)
        if not text or re.fullmatch(r"\d{1,3}", text):
            continue
        if text == "导论" or re.match(r"^第[一二三四五六七八九十]+章\s+\S", text):
            titles.append(text)
            continue
        if titles:
            break
    return titles


def _index_names() -> list[str]:
    """独立探针：`syllabus.md` 的 `### 章目索引` 表格第二列（章名）。"""
    text = (ROOT / SYLLABUS_MD).read_text(encoding="utf-8")
    block = text[text.index("### 章目索引"):]
    end = block.find("\n## ", 1)
    if end != -1:
        block = block[:end]
    names: list[str] = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "章序" or set(cells[0]) <= {"-", ":"}:
            continue
        names.append(cells[1])
    return names


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _fragment_root(tmp_path: Path, text: str = FRAGMENT) -> tuple[Path, dict]:
    """合成考纲片段 + 对应 evidence（`syllabus.path` 指向 tmp 抽取件）。"""
    doc = tmp_path / "sources" / "jiangsu" / "processed" / "syllabus" / "99999-demo" / "document.extracted.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(text, encoding="utf-8")
    evidence = {
        "schema_version": 1,
        "course_code": "99999",
        "syllabus": {
            "status": "extracted",
            "doc_id": "syllabus:99999",
            "path": doc.relative_to(tmp_path).as_posix(),
            "sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
            "has_assessment_requirements": True,
            "has_sample_paper": False,
            "requirements_heading": "三、考核知识点与考核要求",
            "locator": "L16",
        },
        "eligibility": {"level": "L1", "reasons": ["syllabus:extracted", "textbook_plan:matched"]},
    }
    return tmp_path, evidence


def _write_evidence(root: Path, evidence: dict) -> Path:
    """落盘 `sources/jiangsu/courses/<code>/evidence.json`（`build_knowledge_model()` 的唯一输入）。"""
    path = root / "sources" / "jiangsu" / "courses" / evidence["course_code"] / "evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    return path


def _cli_scaffold(root: Path) -> Path:
    """tmp 根上的 CLI 装置：复制入口脚本 + 软链 `scripts/lib`。

    入口脚本用 `Path(__file__).resolve().parents[1]` 推导 `ROOT`（不是 cwd），故只能把脚本放进 tmp 根；
    生产库通过软链复用，测试不碰真实仓（真实产物必须字节不变）。
    """
    (root / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/build-course-content.py", root / "scripts/build-course-content.py")
    (root / "scripts/lib").symlink_to(ROOT / "scripts/lib", target_is_directory=True)
    return root


def _leak_windows(value, source: str) -> list[str]:
    """模型内所有长度 201 的字符串窗口（逐字符串切片）；落在 `source`（去噪官方正文）内的即正文倾倒。"""
    return [
        text[start:start + 201]
        for text in _strings(value)
        for start in range(len(text) - 200)
        if text[start:start + 201] in source
    ]


# ---- Step 1 的 8 个必测项 ----------------------------------------------------

def test_chapter_names_verbatim():
    """18 个章标题与 `syllabus.md` 章目索引、`CHAPTER_NAMES_15040` 三方逐字一致。"""
    titles = [chapter["title"] for chapter in _model()["chapters"]]
    assert len(titles) == 18
    assert titles == _index_names() == list(CHAPTER_NAMES_15040)
    assert titles[0] == "导论"
    assert titles[-1] == "第十七章 全面从严治党"
    assert "第十一章 以保障和改善民生为重点加强社会建设" in titles
    assert all("Ⅰ" not in title and "Ⅳ" not in title for title in titles)
    assert not any(title.startswith(("附录", "大纲后记")) for title in titles)

    # 源侧独立复核：折叠空白后的 TOC 切片行 = 模型章标题（TOC 用多空格、正文用单空格）
    toc = _toc_titles()
    assert toc == titles
    toc_lines = [index + 1 for index, line in enumerate(_doc_lines()) if _fold(line) in toc]
    assert toc_lines[:18] == list(range(64, 98, 2)) + [99]  # 导论 `:64` … 第十七章 `:99`（页码 `:98` 在中间）


def test_chapter_slug_and_filenames():
    """`ordinal` 0…17、`slug` `intro`/`ch01`…`ch17`、`index` `导论`/`第一章`…，渲染文件名一一对应。"""
    chapters = _model()["chapters"]
    assert [chapter["ordinal"] for chapter in chapters] == list(range(18))
    assert [chapter["slug"] for chapter in chapters] == ["intro"] + [f"ch{number:02d}" for number in range(1, 18)]
    assert [chapter["index"] for chapter in chapters] == ["导论"] + [
        title.split(" ", 1)[0] for title in CHAPTER_NAMES_15040[1:]
    ]
    filenames = [f"knowledge/{chapter['ordinal']:02d}-{chapter['slug']}.md" for chapter in chapters]
    assert filenames[0] == "knowledge/00-intro.md"
    assert filenames[-1] == "knowledge/17-ch17.md"
    assert len(set(filenames)) == 18


def test_requirement_levels_parsed():
    """识记 / 领会 / 应用三级都被解析；导论第 1 节恰好 7 个 point（5 + 1 + 1）。"""
    chapters = _model()["chapters"]
    intro = chapters[0]
    assert intro["index"] == "导论" and intro["slug"] == "intro"
    first = intro["sections"][0]
    assert first["index"] == "1"
    assert first["title"] == "习近平新时代中国特色社会主义思想创立的时代背景"
    assert _fold(_doc_lines()[220]) == f"1.{first['title']}"  # 源 `:221`

    points = first["points"]
    assert [point["requirement"] for point in points] == ["识记"] * 5 + ["领会", "应用"]
    assert [point["title"] for point in points[:5]] == list(INTRO_MEMORIZE)
    assert points[0]["locator"] == "L222"
    assert points[5]["quote"] == "中华民族迎来从站起来、富起来到强起来的伟大飞跃"
    assert points[6]["quote"] == "中华民族伟大复兴进入不可逆转的历史进程"
    assert points[5]["requirement"] == "领会" and points[6]["requirement"] == "应用"

    levels = {point["requirement"] for chapter in chapters for section in chapter["sections"] for point in section["points"]}
    assert levels == {"识记", "领会", "应用"}


def test_wrapped_lines_and_page_numbers_normalized():
    """源文折行（`:222-224`）与独占一行的页码（`:240`）先归一化，第 4 节的 `领会` 仍归属第 4 节。"""
    lines = _doc_lines()
    assert lines[239].strip() == "7", "`:240` 必须是独占一行的页码（折行 + 页码的实测锚点）"
    assert lines[221].strip().endswith("中华民族伟大复兴进入关键时期；")
    assert "中国式现代化全面推进拓展" in lines[222]

    sections = _model()["chapters"][0]["sections"]
    fourth = sections[3]
    assert fourth["index"] == "4" and fourth["title"] == "习近平新时代中国特色社会主义思想的历史地位"
    assert [point["requirement"] for point in fourth["points"]] == ["识记"] * 3 + ["领会", "应用"]
    assert [point["title"] for point in fourth["points"][:3]] == list(INTRO_4_MEMORIZE)
    comprehend = fourth["points"][3]
    assert comprehend["requirement"] == "领会"
    assert comprehend["locator"] == "L241"
    assert comprehend["quote"] == (
        "习近平新时代中国特色社会主义思想是当代中国马克思主义、二十一世纪马克思主义，"
        "是中华文化和中国精神的时代精华"
    )
    # 页码不得成为独立 point，也不得粘到相邻短语上
    all_titles = [point["title"] for chapter in _model()["chapters"] for section in chapter["sections"] for point in section["points"]]
    assert not any(re.fullmatch(r"\d{1,3}", title) for title in all_titles)
    assert "“四个伟大”7" not in all_titles


def test_quote_within_60_chars():
    """每个 `quote` ≤ 60 字符、非空、逐字来自考纲，且不使用 `>` 引用块形式。

    `title` 保留完整短语原文（长短语只截 `quote`、不拆 point），故 `title` 只受防正文倾倒上限（200）约束。
    """
    source = _folded_source()
    quotes = 0
    longest_title = 0
    for chapter in _model()["chapters"]:
        for section in chapter["sections"]:
            for point in section["points"]:
                assert point["quote"] and len(point["quote"]) <= 60, (point["id"], len(point["quote"]))
                assert point["title"] and len(point["title"]) <= 200, (point["id"], len(point["title"]))
                for field in ("quote", "title"):
                    text = point[field]
                    assert not text.startswith(">") and "\n>" not in text
                    assert re.sub(r"\s+", "", text) in source, (point["id"], field, text)
                assert point["quote"] in point["title"]
                quotes += 1
                longest_title = max(longest_title, len(point["title"]))
        for focus in chapter["chapter_focus"]:
            assert focus["text"] and len(focus["text"]) <= 60
            assert re.sub(r"\s+", "", focus["text"]) in source
    assert quotes > 0
    assert longest_title < 200


def test_point_ids_unique():
    """点 id 唯一、匹配 `^15040-(intro|ch\\d{2})-s\\d+-p\\d+$`，且与所在章 / 节 / 序号一致。"""
    pattern = re.compile(r"^15040-(intro|ch\d{2})-s\d+-p\d+$")
    ids: list[str] = []
    for chapter in _model()["chapters"]:
        for section in chapter["sections"]:
            for seq, point in enumerate(section["points"], start=1):
                expected = f"15040-{chapter['slug']}-s{section['index']}-p{seq}"
                assert point["id"] == expected
                assert pattern.fullmatch(point["id"]), point["id"]
                ids.append(point["id"])
    assert len(ids) == len(set(ids))
    # 实测总数：每条 `；` 短语一个 point（长短语只截 `quote`、不拆 point）
    assert len(ids) == 393


def test_coverage_ratio_and_diff():
    """分母 = 考纲带编号节数 61（AC5 对照值），`diff_vs_manual` 为逐条比对台账。"""
    doc = _model()
    coverage = doc["coverage"]
    assert coverage["official_point_count"] == 61
    assert coverage["modeled_point_count"] == 61
    assert coverage["ratio"] == 1.0 and coverage["ratio"] >= 0.9
    assert coverage["manual_reference"] == {
        "path": "content/jiangsu/courses/15040/index.md",
        "locator": "L549",
        "point_count": 61,
    }

    # 手工侧独立探针：`index.md:549` 的自评行 + 章知识树的 61 条 `####` 元素
    manual = (ROOT / MANUAL_INDEX).read_text(encoding="utf-8").split("\n")
    assert manual[548].startswith("| B7 | 章节知识树 |") and "61 个节级知识点" in manual[548]
    manual_elements = [line for line in manual if line.startswith("#### ")]
    assert len(manual_elements) == 61

    diff = coverage["diff_vs_manual"]
    keys = {"manual_locator", "manual_title", "model_point_id", "kind", "note"}
    assert isinstance(diff, list) and diff
    assert len(diff) == coverage["manual_reference"]["point_count"], "手工侧每条元素一条比对记录"
    for item in diff:
        assert set(item) == keys
        assert item["kind"] in {"matched", "model_only", "manual_only"}
        assert item["note"]
        assert item["manual_locator"].startswith("content/jiangsu/courses/15040/index.md:")
    kinds = Counter(item["kind"] for item in diff)
    assert kinds["manual_only"] == 0, "存在手工页有、模型未抽出的节（T6 闸门会因此失败）"
    assert kinds["model_only"] == 0
    assert kinds["matched"] == 61


def test_diff_vs_manual_records_manual_only_and_model_only(tmp_path: Path):
    """F-303：`manual_only` / `model_only` 两条分支在合成根上各命中一次（产物里两者都是 0）。

    `manual_only` 正是 T6 `evidence` 层闸门的失败关闭条件，必须有可运行检查而非「读过代码」。
    """
    root, evidence = _fragment_root(tmp_path)
    page = root / "content" / "jiangsu" / "courses" / "99999" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_text(MANUAL_PAGE, encoding="utf-8")

    coverage = km.extract_knowledge_model(root, evidence)["coverage"]
    assert coverage["manual_reference"] == {
        "path": "content/jiangsu/courses/99999/index.md",
        "locator": "L3",
        "point_count": 2,
    }

    diff = coverage["diff_vs_manual"]
    kinds = Counter(item["kind"] for item in diff)
    assert (kinds["matched"], kinds["manual_only"], kinds["model_only"]) == (1, 1, 1)

    manual_only = next(item for item in diff if item["kind"] == "manual_only")
    assert manual_only["manual_locator"] == "content/jiangsu/courses/99999/index.md:6"
    assert manual_only["manual_title"] == "1.2 考纲缺失的节 — 🟢"
    assert manual_only["model_point_id"] is None, "手工页有、模型未抽出：不得编造模型侧 point"
    assert "named_gap" in manual_only["note"]

    model_only = next(item for item in diff if item["kind"] == "model_only")
    assert model_only["manual_locator"] is None and model_only["manual_title"] is None
    assert model_only["model_point_id"] == "99999-intro-s1-p1"
    assert "无对应元素" in model_only["note"]

    matched = next(item for item in diff if item["kind"] == "matched")
    assert matched["manual_locator"] == "content/jiangsu/courses/99999/index.md:5"
    assert matched["model_point_id"] == "99999-ch01-s1-p1"


def test_named_gap_when_unnumbered(tmp_path: Path):
    """未编号考核段落不生成 point、不编造 index，写入 `chapters[].unmodeled[]`。"""
    root, evidence = _fragment_root(tmp_path)
    doc = km.extract_knowledge_model(root, evidence)
    assert [chapter["title"] for chapter in doc["chapters"]] == ["导论", "第一章 示例章"]

    intro = doc["chapters"][0]
    assert [section["title"] for section in intro["sections"]] == ["示例节"]
    assert [point["title"] for point in intro["sections"][0]["points"]] == ["甲", "乙", "丙"]

    passage = "这是一段没有编号的考核说明，考纲未给出节号"
    assert FRAGMENT.split("\n")[16].strip() == f"{passage}。"  # 片段 `L17`
    assert intro["unmodeled"] == [
        {"locator": "L17", "title": passage, "reason": "unnumbered_section"},
    ]
    assert not any(
        passage in point["title"] for section in intro["sections"] for point in section["points"]
    )
    for element in intro["unmodeled"]:
        assert set(element) == {"locator", "title", "reason"}
        assert "index" not in element


def test_orphan_requirement_before_any_section_is_recorded(tmp_path: Path):
    """F-301 回归：编号节之前的 `识记：` 行不得抛 `TypeError`，而是按契约进 `unmodeled[]`（GC3）。

    守卫前行为 = `TypeError: 'NoneType' object is not subscriptable`（`current is None` 仍进 point 循环）；
    守卫后 = 该行只留痕、不生成 point、不凭空造节（`sections` 仍只有考纲真有的 1 节）。
    """
    root, evidence = _fragment_root(tmp_path, ORPHAN_FRAGMENT)
    assert ORPHAN_FRAGMENT.split("\n")[14] == ORPHAN_LINE, "片段 `L15` 必须是孤儿要求行"

    doc = km.extract_knowledge_model(root, evidence)  # 守卫前：TypeError
    intro = doc["chapters"][0]
    assert intro["unmodeled"] == [
        {"locator": "L15", "title": ORPHAN_LINE.rstrip("。"), "reason": "unnumbered_section"},
    ]
    assert set(intro["unmodeled"][0]) == {"locator", "title", "reason"}
    # 不发明结构：孤儿行既不生成 point，也不创建节
    assert [section["index"] for section in intro["sections"]] == ["1"]
    assert [point["title"] for point in intro["sections"][0]["points"]] == ["甲", "乙", "丙"]
    assert not any(
        "总述性识记要求" in point["title"]
        for section in intro["sections"]
        for point in section["points"]
    )
    assert doc["coverage"]["official_point_count"] == 1


def test_section_without_requirement_prefix_gets_null(tmp_path: Path):
    """编号节内没有 `识记：`/`领会：`/`应用：` 前缀 → requirement 为 `null`，不得编造层级。"""
    root, evidence = _fragment_root(tmp_path)
    doc = km.extract_knowledge_model(root, evidence)
    chapter = doc["chapters"][1]
    assert chapter["slug"] == "ch01"
    section = chapter["sections"][0]
    assert section["index"] == "1" and section["title"] == "无前缀节"
    assert [point["requirement"] for point in section["points"]] == [None, None]
    assert [point["title"] for point in section["points"]] == [
        "本节考核内容没有识记领会应用前缀",
        "第二句也没有",
    ]
    assert [point["id"] for point in section["points"]] == ["99999-ch01-s1-p1", "99999-ch01-s1-p2"]
    assert chapter["unmodeled"] == []


def test_chapter_focus_excludes_part_labels_and_appendix():
    """末章切片不得越过 `Ⅳ 关于大纲的说明与考核实施要求`：部次标签 / 附录 / 样卷不得混进本章重点。"""
    chapters = _model()["chapters"]
    assert [len(chapter["chapter_focus"]) for chapter in chapters] == [
        4, 5, 4, 7, 4, 7, 7, 5, 5, 6, 6, 5, 5, 5, 6, 4, 5, 5,
    ]
    for chapter in chapters:
        for focus in chapter["chapter_focus"]:
            assert not re.match(r"^[ⅠⅡⅢⅣⅤⅥ]", focus["text"]), focus
            assert "关于大纲的说明" not in focus["text"]
            assert "参考样卷" not in focus["text"]
    last = chapters[-1]
    assert last["index"] == "第十七章"
    assert [focus["text"] for focus in last["chapter_focus"]][-1] == "以伟大自我革命引领伟大社会革命"


def test_no_body_text_leak():
    """防正文倾倒：模型内不得存在长度 > 200 的连续官方正文串。

    该不变式在真实产物上**空真**（最长字符串 87 字符 → 0 个可扫窗口），故本测试自带阳性对照：
    把 ≥ 201 字符的官方正文塞进模型时必须被报出。删掉窗口循环（检测器退化）→ 阳性对照失败。
    """
    source = _folded_source()
    artifact = _model()
    # 真实产物：字段上界 200 成立（这正是窗口数为 0、必须加阳性对照的原因，不用它冒充测试强度）
    scanned = sum(max(0, len(text) - 200) for text in _strings(artifact))
    assert scanned == 0, "产物出现 > 200 字符字符串：先人工核对是否正文倾倒"
    assert _leak_windows(artifact, source) == []

    # 阳性对照：400 字符官方正文 → 200 个窗口全部命中（检测器必须报出）
    body = source[1000:1400]
    assert len(body) == 400
    assert len(_leak_windows({"body": body}, source)) == 200
    # 阈值语义 `> 200`：200 字符不触发，201 字符触发 1 个窗口
    assert _leak_windows({"body": source[1000:1200]}, source) == []
    assert len(_leak_windows({"body": source[1000:1201]}, source)) == 1


# ---- 产物 / CLI 契约 ---------------------------------------------------------

def test_artifact_matches_fresh_build_and_is_hash_seed_independent():
    """产物 = 现算结果（仅 `generated_at` 为生成日），序列化跨进程 / 跨 hash seed 字节一致。"""
    artifact = _model()
    fresh = km.build_knowledge_model(ROOT, "15040")
    assert {**fresh, "generated_at": artifact["generated_at"]} == artifact
    assert artifact["generator"] == {
        "kind": "deterministic",
        "model": None,
        "prompt_id": None,
        "prompt_version": None,
    }
    assert artifact["source"]["path"] == SYLLABUS_DOC.as_posix()
    assert re.fullmatch(r"[0-9a-f]{64}", artifact["source"]["sha256"])
    assert artifact["exam"] == {
        "question_types": ["单项选择题", "简答题", "材料题"],
        "question_types_provenance": {"doc_id": "syllabus:15040", "locator": "L903"},
        "duration_minutes": None,
        "duration_status": "named_gap",
        "sample_paper": {"doc_id": "syllabus:15040", "locator": "L912"},
    }
    assert _doc_lines()[902].strip().startswith("4.本课程考试命题的主要题型一般有单项选择题")
    assert _fold(_doc_lines()[911]) == "参考样卷"

    first = km.serialize(fresh)
    assert first == km.serialize(km.build_knowledge_model(ROOT, "15040"))
    probe = (
        "import hashlib, sys;"
        "sys.path.insert(0, 'scripts');"
        "from pathlib import Path;"
        "from lib.course_pipeline import knowledge_model as km;"
        "text = km.serialize(km.build_knowledge_model(Path.cwd(), '15040'));"
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


def test_cli_model_skips_blocked_course_and_writes_nothing():
    """非 L1 课码：`model` 子命令跳过且不视为失败（exit 0），零 AI 产物。"""
    blocked = ROOT / "sources/jiangsu/courses/00023/knowledge-model.json"
    assert not blocked.exists()
    result = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "model", "00023"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "blocked" in result.stdout and "跳过" in result.stdout
    assert not blocked.exists()


def test_write_knowledge_model_round_trip_in_tmp_root(tmp_path: Path):
    """F-304：写盘成功路径（`knowledge_model_path` / `write_knowledge_model`）在 tmp 根上往返一次。"""
    root, evidence = _fragment_root(tmp_path)
    _write_evidence(root, evidence)

    path, doc = km.write_knowledge_model(root, "99999")
    assert path == km.knowledge_model_path(root, "99999")
    assert path == root / "sources/jiangsu/courses/99999/knowledge-model.json"
    assert path.read_text(encoding="utf-8") == km.serialize(doc)
    assert json.loads(path.read_text(encoding="utf-8")) == doc

    first = path.read_bytes()  # 复跑幂等：同输入两次落盘字节一致
    assert km.write_knowledge_model(root, "99999")[0] == path
    assert path.read_bytes() == first


def test_cli_model_writes_l1_course_in_tmp_root(tmp_path: Path):
    """F-304：CLI `model <code>` 的 L1 成功路径（另一个 CLI 测试只覆盖 blocked 跳过路径）。"""
    root, evidence = _fragment_root(tmp_path)
    _write_evidence(root, evidence)
    _cli_scaffold(root)

    result = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "model", "99999"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == (
        "99999: chapters=2 ratio=1.0 -> sources/jiangsu/courses/99999/knowledge-model.json"
    )

    written = json.loads(
        (root / "sources/jiangsu/courses/99999/knowledge-model.json").read_text(encoding="utf-8")
    )
    assert written == km.build_knowledge_model(root, "99999")
    assert written["coverage"]["ratio"] == 1.0 and len(written["chapters"]) == 2


def test_l1_course_model_requires_extracted_syllabus(tmp_path: Path):
    """库函数层：考纲未抽取 → 显式失败（不产出编造的章目），CLI 已在上层拦截。"""
    root, evidence = _fragment_root(tmp_path)
    evidence["syllabus"] = {"status": "missing", "path": None, "doc_id": "syllabus:99999"}
    with pytest.raises(ValueError):
        km.extract_knowledge_model(root, evidence)


# ---- B6：章序标签（`导论` / `绪 论`）与题目类型声明 ---------------------------------------

NO_INTRO_FRAGMENT = """大纲目录

第一章 反对外国侵略的斗争

第二章 对国家出路的早期探索

Ⅳ 关于大纲的说明与考核实施要求
附录：参考样卷
大纲后记

第一章 反对外国侵略的斗争
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.鸦片战争前的中国与世界
三、考核知识点与考核要求
1.鸦片战争前的中国与世界
识记：鸦片战争前的中国是独立的封建国家。
四、本章重点
鸦片战争前的中国。

第二章 对国家出路的早期探索
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.太平天国农民战争
三、考核知识点与考核要求
1.太平天国农民战争
识记：太平天国农民战争爆发于 1851 年。
四、本章重点
太平天国农民战争。
"""

XU_LUN_FRAGMENT = """大纲目录

绪 论

第一章 物质世界及其发展规律

第二章 认识的本质及规律

Ⅳ 关于大纲的说明与考核实施要求
附录：参考样卷
大纲后记

绪 论
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.马克思主义的基本立场
三、考核知识点与考核要求
1.马克思主义的基本立场
识记：马克思主义的基本立场是人民大众的立场。
四、本章重点
马克思主义的基本立场。

第一章 物质世界及其发展规律
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.物质及其存在形态
三、考核知识点与考核要求
1.物质及其存在形态
识记：物质是不依赖于意识而存在的客观实在。
四、本章重点
物质及其存在形态。

第二章 认识的本质及规律
一、学习目的与要求
通过本章学习，能说出示例。
二、课程内容
1.实践是认识的基础
三、考核知识点与考核要求
1.实践是认识的基础
识记：实践是认识的基础。
四、本章重点
实践是认识的基础。
"""



def test_xu_lun_label_is_not_silently_dropped():
    """B6：`绪 论`（内部带空格）必须被识别为章，且 `ordinal 0` / `slug intro` / `index 绪论`。

    旧 `CHAPTER_RE` 只认 `导论`，于是 `15044` 的 `绪 论` 被静默丢弃：整章消失、后续章序整体前移
    （`第一章` 顶到 `ordinal 0` 且 `slug intro`），而 `coverage.ratio` 仍是 `1.0`（被丢的章连分母一起带走）。
    """
    doc = km.extract_knowledge_model(*_fragment_root(tmp_path=Path(tempfile.mkdtemp()), text=XU_LUN_FRAGMENT))
    titles = [chapter["title"] for chapter in doc["chapters"]]
    assert titles == ["绪 论", "第一章 物质世界及其发展规律", "第二章 认识的本质及规律"], titles

    intro = doc["chapters"][0]
    assert (intro["ordinal"], intro["slug"], intro["index"]) == (0, "intro", "绪论")
    # 后续章按实际章号定序（不再因为丢章而前移）
    assert [(c["ordinal"], c["slug"]) for c in doc["chapters"][1:]] == [(1, "ch01"), (2, "ch02")]
    # 分母必须含 `绪 论` 的节
    assert doc["coverage"]["official_point_count"] == sum(len(c["sections"]) for c in doc["chapters"]) == 3


def test_no_intro_course_does_not_get_an_intro_slug():
    """B6：没有导论的课程不得把第一章标成 `intro`（`15043` 实测缺陷）。"""
    doc = km.extract_knowledge_model(
        *_fragment_root(tmp_path=Path(tempfile.mkdtemp()), text=NO_INTRO_FRAGMENT)
    )
    assert doc["chapters"][0]["index"] == "第一章"
    assert doc["chapters"][0]["slug"] == "ch01", "没有导论的课程，第一章的 slug 必须是 ch01"
    assert doc["chapters"][0]["ordinal"] == 1
    assert all(chapter["slug"] != "intro" for chapter in doc["chapters"])


def test_question_types_extracted_from_both_syllabus_wordings():
    """B6/QC3-005：题型声明的两种版式都要抽到（15040 用「…等题型。」，15043/15044 用「…论述题等。各」）。"""
    assert km.QUESTION_TYPE_RE.search("4.本课程考试命题的主要题型一般有单项选择题、简答题、材料题等题型。")
    assert km.QUESTION_TYPE_RE.search("4. 本课程考试命题的主要题型一般有单项选择题、简答题、论述题等。各")
    for fragment in (XU_LUN_FRAGMENT, NO_INTRO_FRAGMENT):
        doc = km.extract_knowledge_model(*_fragment_root(tmp_path=Path(tempfile.mkdtemp()), text=fragment))
        # 片段里没有题型声明 → 必须显式命名缺口，而不是留空数组让 generate 在运行时才抛错
        assert doc["exam"]["question_types"] == []
        assert doc["exam"]["question_types_status"] == "named_gap"
        assert doc["exam"]["question_types_gap_impact"] and doc["exam"]["question_types_next_evidence"]


def test_manual_ledger_fails_closed_on_unparseable_elements(tmp_path: Path):
    """C2-012：手册台账出现无法解析的考点行时必须失败关闭（旧实现静默 `continue`，台账被清空而无人知）。"""
    root, evidence = _fragment_root(tmp_path)
    page = root / "content" / "jiangsu" / "courses" / "99999" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "## 章节知识树\n\n#### 1.1 正常考点\n#### 一、非数字编号的考点\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as err:
        km.extract_knowledge_model(root, evidence)
    assert "无法解析" in str(err.value)
    assert ":4" in str(err.value), "错误必须点名行号"


def test_manual_ledger_fails_closed_when_the_anchor_heading_is_renamed(tmp_path: Path):
    """W3 变异证明：锚点标题被改名而编号 `####` 元素仍在 → 必须失败关闭，不得静默返回空台账。

    这是 C2-012 的另一半：旧实现只在**元素解析**这一侧失败关闭；把 `## 章节知识树` 改名成
    `## 知识点总览`、61 条 `####` 原地不动，`_manual_tree()` 返回 `(None, [], [])`，
    与「本课没有手工参照」完全同形 —— 于是 `manual_reference: null` + `diff_vs_manual: []`，
    `evidence` 层的 `manual_only` 检查对这份输入永远空转（PM 实测：两层闸门全绿）。

    真跑 15040 的真实页面（61 条元素）做变异，而不是合成小页：缺口正是「61 条元素在页上」时出现的。
    """
    real_page = ROOT / MANUAL_INDEX
    real_text = real_page.read_text(encoding="utf-8")
    assert "## 章节知识树" in real_text, "对照前提：真实手工页含锚点标题"
    element_lines = [ln for ln in real_text.splitlines() if ln.startswith("#### ")]
    assert len(element_lines) == 61, f"对照前提：15040 手工页有 61 条 `####` 元素，实际 {len(element_lines)}"

    root, evidence = _fragment_root(tmp_path)
    page = root / "content" / "jiangsu" / "courses" / "99999" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_text(real_text.replace("## 章节知识树", "## 知识点总览", 1), encoding="utf-8")

    with pytest.raises(ValueError) as err:
        km.extract_knowledge_model(root, evidence)
    message = str(err.value)
    assert "61" in message, f"错误必须点名元素条数：{message}"
    assert "章节知识树" in message, f"错误必须点名缺失的锚点标题：{message}"

    # 对照组：锚点改回去（同一份文件、同一批元素）→ 台账照常写出，证明上面的失败不是别的原因
    page.write_text(real_text, encoding="utf-8")
    coverage = km.extract_knowledge_model(root, evidence)["coverage"]
    assert coverage["manual_reference"] is not None, "对照前提：锚点存在时台账必须写出"
    assert coverage["manual_reference"]["point_count"] == 61
    assert len(coverage["diff_vs_manual"]) == 61


def test_manual_ledger_still_treats_anchored_empty_tree_as_a_named_gap(tmp_path: Path):
    """15043 / 15044 的真实形态：**有**锚点但 0 条元素 = 诚实的命名缺口，不是解析失败。"""
    root, evidence = _fragment_root(tmp_path)
    page = root / "content" / "jiangsu" / "courses" / "99999" / "index.md"
    page.parent.mkdir(parents=True)
    page.write_text("# demo\n\n## 章节知识树\n\n（本章节暂无编号考点，待人工补齐。）\n", encoding="utf-8")

    coverage = km.extract_knowledge_model(root, evidence)["coverage"]
    assert coverage["manual_reference"] is None
    assert coverage["diff_vs_manual"] == []


# ---- B3a / KB-1…KB-4：章目回退、章号标签与考核单元 ------------------------------------------
#
# 背景（可复现的缺陷类）：`00898` / `02333` / `04747` / `04751` 四门 L1 课的考纲**天生没有
# `大纲目录` 页**（实测 `00898` 第 14 行是页码、第 15 行即 `Ⅰ 课程性质与课程目标`），
# 原判据直接 ValueError，四门课产不出知识模型。规划期探针只认 `第6章`（数字两侧无空格），
# 而抽取件两种写法混用，于是「漏章」看起来像考纲缺章 —— 实测 4 门课**页码齐全、章号 1–N 连续**，
# 缺口是探针缺陷而非考纲事实。这批用例把该缺陷类钉死。

FALLBACK_HEADING = "三、考核知识点与考核要求"  # 与 `_fragment_root()` 的 `requirements_heading` 同值


def _fallback_fragment(titles: list[str], *, paren: bool = False) -> str:
    """合成无目录页考纲：Ⅰ/Ⅱ/Ⅲ 部次齐全、**无** `大纲目录`，`Ⅲ` 之下列 `第N章` + 考核要求。

    `paren=True` 用 `（一）` 节版式（`00898` 的形态）；否则章级直接列要求（`02333` 的形态）。
    """
    body = []
    for title in titles:
        lines = [title, "一、学习目的与要求", "通过本章学习，能说出示例。", FALLBACK_HEADING]
        if paren:
            lines += ["（一）示例节", "识记：示例识记内容。", "（二）第二示例节", "领会：示例领会内容。"]
        else:
            lines += ["识记：示例识记内容。", "领会：示例领会内容。"]
        lines += ["四、本章重点", "示例。"]
        body.append("\n".join(lines))
    return (
        "Ⅰ 课程性质与课程目标\n示例。\n\nⅡ 考核目标\n示例。\n\nⅢ 课程内容与考核要求\n\n"
        + "\n\n".join(body)
        + "\n\nⅣ 关于大纲的说明与考核实施要求\n示例。\n"
    )


def test_chapter_predicate_tolerates_spacing_and_arabic_numerals():
    """KB-1 回归（PM 规划期探针缺陷）：`第 6 章 X` 与 `第6章 X` 必须**同样**被识别为章标题。

    探针只认 `第6章`（数字两侧无空格），而抽取件两种写法混用（`00898:120` `第1章   …` 与
    `:475` `第 10 章   …` 同课并存）—— 只认一种会把双位数的章整批漏掉，于是「漏章」在
    `ordinal` 上看起来就像考纲真缺章（`04747` 的 `第 6 章` 就是这样被漏掉、误报缺第 6 章）。
    """
    for loose, tight in (
        ("第 6 章 Java 语言中的异常", "第6章 Java 语言中的异常"),
        ("第 10 章 面向对象实现", "第10章 面向对象实现"),
        ("第 1 章 网络安全概述", "第1章 网络安全概述"),
    ):
        assert km.CHAPTER_RE.match(loose) and km.CHAPTER_RE.match(tight), (loose, tight)
        # 章号与标签必须一致：两种写法推出同一个 `ordinal` / `slug` / `index`
        assert km._ordinal_for(loose) == km._ordinal_for(tight)
        assert km._slug_for(loose) == km._slug_for(tight)
        assert km._chapter_index(loose) == km._chapter_index(tight)

    # `50` 之上的中文数字与阿拉伯数字都要能算章号
    assert km._ordinal_for("第 16 章 Web 应用开发实践") == 16
    assert km._ordinal_for("第十七章 全面从严治党") == 17
    # `章` 后直接跟标题（`00898:523` 实测 `第 11 章使用 Servlet 过滤器和监听器`）也算章标题
    assert km._ordinal_for("第 11 章使用 Servlet 过滤器和监听器") == 11


def test_intro_label_without_separator_is_not_a_chapter():
    """KB-1 反向守卫：`导论` / `绪 论` 没有数字锚点，正文句首的 `绪论的核心是…` 不得被当成章标题。

    `15044:161` 实测该行 —— 若放开标签后的分隔要求，它会被误判成章，`绪 论` 就会出现两次。
    """
    assert not km.CHAPTER_RE.match("绪论的核心是阐明马克思主义的产生、发展及基本特征。")
    assert not km.CHAPTER_TITLE_RE.match("绪论的核心是阐明马克思主义的产生、发展及基本特征。")
    assert not km.CHAPTER_RE.match("导论部分说明了本课程的性质。")
    # 合法形态仍必须认
    assert km.CHAPTER_RE.match("绪 论") and km.CHAPTER_RE.match("导论")


def test_fallback_from_iii_section_when_toc_missing(tmp_path: Path):
    """KB-2：无 `大纲目录` 时从 `Ⅲ 课程内容与考核要求` 推章目，返回同一契约 `(end_index, titles)`。"""
    text = _fallback_fragment(["第1章 甲", "第2章 乙", "第 3 章 丙"])
    root, evidence = _fragment_root(tmp_path, text)
    lines = text.split("\n")

    start, titles = km._chapter_titles(lines)
    assert [title for title in titles] == ["第1章 甲", "第2章 乙", "第 3 章 丙"]
    assert lines[start].strip().endswith("Ⅲ 课程内容与考核要求"), "`end_index` 必须取 Ⅲ 节起点"

    doc = km.extract_knowledge_model(root, evidence)
    assert [c["ordinal"] for c in doc["chapters"]] == [1, 2, 3]
    assert [c["slug"] for c in doc["chapters"]] == ["ch01", "ch02", "ch03"]
    assert doc["coverage"]["ratio"] == 1.0
    assert doc["generator"]["kind"] == "deterministic"


def test_fallback_is_unreachable_when_toc_exists(tmp_path: Path):
    """KB-2 / AC3 的结构保证：有 `大纲目录` 时走原判据，回退分支不可达（产物逐字节不变的理由）。

    变异证明：把回退函数换成「只返回空章目」，有 TOC 的片段必须**不受影响**；无 TOC 的片段才变。
    """
    root, evidence = _fragment_root(tmp_path, FRAGMENT)  # FRAGMENT 含 `大纲目录`
    original = km._section_chapters
    try:
        km._section_chapters = lambda lines: (_ for _ in ()).throw(AssertionError("回退不得被调用"))
        doc = km.extract_knowledge_model(root, evidence)
    finally:
        km._section_chapters = original
    assert [c["title"] for c in doc["chapters"]] == ["导论", "第一章 示例章"]

    # 对照组：同一批章、但**去掉** `大纲目录`（改由 `Ⅲ` 节推）→ 必须能产出，
    # 证明上面的断言不是因为回退坏了才「没被调用」。
    fb_root, fb_evidence = _fragment_root(
        tmp_path / "second", _fallback_fragment(["导论", "第一章 示例章"])
    )
    doc2 = km.extract_knowledge_model(fb_root, fb_evidence)
    assert [c["title"] for c in doc2["chapters"]] == ["导论", "第一章 示例章"]
    assert not any(line == km.TOC_MARKER for line in (fb_root / fb_evidence["syllabus"]["path"]).read_text(encoding="utf-8").split("\n"))


def test_fallback_fails_closed_without_iii_section_or_chapters(tmp_path: Path):
    """KB-2 失败关闭：既无 `大纲目录`、又无 `Ⅲ` 节（或 `Ⅲ` 后无章标题）→ 仍 raise，绝不产出空章目。"""
    root, evidence = _fragment_root(tmp_path, "Ⅰ 课程性质与课程目标\n示例。\n\nⅣ 关于大纲的说明\n示例。\n")
    with pytest.raises(ValueError) as err:
        km.extract_knowledge_model(root, evidence)
    assert "无法确定章目" in str(err.value)

    # `Ⅲ` 节在、但它后面一个章标题都没有
    root2, evidence2 = _fragment_root(tmp_path / "second", "Ⅲ 课程内容与考核要求\n本大纲不列章。\n")
    with pytest.raises(ValueError) as err2:
        km.extract_knowledge_model(root2, evidence2)
    assert "没有章标题行" in str(err2.value)


def test_missing_gap_is_named_with_runs():
    """KB-3：缺失章号必须**指名**并压缩成区间；前部缺口与内部缺口两种形态都要报。"""
    cases = (
        ((1, 2, 3, 4, 5, 7, 8, 9), [6], "第6章"),              # 内部缺口（04747 规划期误报的形态）
        ((4, 5, 6, 7, 8, 9), [1, 2, 3], "第1–3章"),             # 前部缺口（04751 规划期误报的形态）
        ((0, 1, 3, 4), [2], "第2章"),                           # 导论 + 内部缺口：导论不计章号
        ((1, 4, 5, 9), [2, 3, 6, 7, 8], "第2–3章、第6–8章"),     # 多段缺口
        (tuple(range(1, 17)), [], ""),                          # 连续：无缺口
        ((0, 1, 2, 3), [], ""),
    )
    for ordinals, expected, rendered in cases:
        numbers = km._missing_chapters(list(ordinals))
        assert numbers == expected, ordinals
        assert km._format_chapter_runs(numbers) == rendered, ordinals


def test_continuity_guard_still_fails_closed_and_names_the_gap(tmp_path: Path):
    """KB-3 / GC2：章序连续性守卫**不放宽** —— 非连续章目必须失败关闭，且错误点名缺的章号。

    两条分支各命中一次：内部缺口（`第1,2,4章`）与前部缺口（首章为 `第4章`）。
    """
    for labels, fragment_ordinals, rendered in (
        (["第一章 甲", "第二章 乙", "第四章 丁"], [1, 2, 4], "第3章"),
        (["第四章 丁", "第五章 戊", "第六章 己"], [4, 5, 6], "第1–3章"),
    ):
        # 有 TOC 的路径（原判据）
        toc_text = "大纲目录\n\n" + "\n\n".join(labels) + "\n\nⅣ 关于大纲的说明\n\n" + "\n\n".join(
            f"{label}\n一、学习目的与要求\n示例。\n{FALLBACK_HEADING}\n1.示例节\n识记：示例。" for label in labels
        )
        root, evidence = _fragment_root(tmp_path / rendered, toc_text)
        with pytest.raises(ValueError) as err:
            km.extract_knowledge_model(root, evidence)
        message = str(err.value)
        assert rendered in message, f"错误必须点名缺失章号：{message}"
        assert "不连续" in message
        assert str(fragment_ordinals) in message

        # 无 TOC 的回退路径：同一守卫也必须生效（守卫在章目判定**之后**，两条路径共用）
        fb_root, fb_evidence = _fragment_root(
            tmp_path / f"fb-{rendered}", _fallback_fragment(labels)
        )
        with pytest.raises(ValueError) as fb_err:
            km.extract_knowledge_model(fb_root, fb_evidence)
        assert rendered in str(fb_err.value), str(fb_err.value)


def test_named_gap_error_message_has_no_artifact(tmp_path: Path):
    """KB-3：失败关闭时不得落盘任何产物（`write_knowledge_model` 先算后写）。"""
    root, evidence = _fragment_root(
        tmp_path, _fallback_fragment(["第1章 甲", "第2章 乙", "第4章 丁"])
    )
    _write_evidence(root, evidence)
    with pytest.raises(ValueError):
        km.write_knowledge_model(root, "99999")
    assert not (root / "sources/jiangsu/courses/99999/knowledge-model.json").exists()


def test_paren_sections_and_chapter_level_units(tmp_path: Path):
    """KB-4：`（一）` 节版式与「整章即考核单元」两种形态都要产出正确的 `sections[]` 与分母。"""
    # （一）版式：两个节各自成单元
    root, evidence = _fragment_root(tmp_path, _fallback_fragment(["第1章 甲"], paren=True))
    doc = km.extract_knowledge_model(root, evidence)
    sections = doc["chapters"][0]["sections"]
    assert [s["index"] for s in sections] == ["1", "2"], sections
    assert [s["title"] for s in sections] == ["示例节", "第二示例节"]
    assert doc["coverage"]["official_point_count"] == 2
    assert doc["coverage"]["ratio"] == 1.0

    # 章级形态：无任何节号 → 章本身是唯一考核单元（否则整章要求会全落进 unmodeled）
    root2, evidence2 = _fragment_root(tmp_path / "chapter-level", _fallback_fragment(["第1章 甲", "第2章 乙"]))
    doc2 = km.extract_knowledge_model(root2, evidence2)
    assert [len(c["sections"]) for c in doc2["chapters"]] == [1, 1]
    assert [c["sections"][0]["title"] for c in doc2["chapters"]] == ["第1章 甲", "第2章 乙"]
    assert doc2["coverage"]["official_point_count"] == 2
    assert doc2["coverage"]["ratio"] == 1.0
    assert "章即考核单元" in doc2["coverage"]["denominator_rule"]


def test_not_assessed_units_are_left_out_of_the_denominator():
    """KB-4：标题带 `不作考核要求` 的单元只留痕，不进分母 —— 「不考」不等于「抽取失败」。

    真实形态：`02333` 第 14 章与 `04747` 第 7/11/12/13 章标题都带 `（本章内容不作考核要求）`，
    这些章没有考核要求小节。把它们算作「未抽出的节」会把「官方声明不考」误报成抽取失败。
    """
    text = _fallback_fragment(["第1章 甲（本章内容不作考核要求）", "第2章 乙"])
    root, evidence = _fragment_root(Path(tempfile.mkdtemp()), text)
    doc = km.extract_knowledge_model(root, evidence)
    first = doc["chapters"][0]
    assert first["sections"] == [], "官方声明不考核的章不得造出考核单元"
    assert doc["chapters"][1]["sections"], "对照：正常章必须有考核单元"
    assert doc["coverage"]["official_point_count"] == 1, "分母只算参与考核的章"
    assert doc["coverage"]["ratio"] == 1.0, "分母只含参与考核的单元时不得出现假缺口"

    # 节级限定语（`00898` 的形态）：该节不进分母，但同章其他节照常计入
    paren_text = _fallback_fragment(["第1章 甲"], paren=True).replace(
        "（二）第二示例节", "（二）第二示例节（本节内容不作考核要求）"
    )
    root2, evidence2 = _fragment_root(Path(tempfile.mkdtemp()), paren_text)
    doc2 = km.extract_knowledge_model(root2, evidence2)
    chapter = doc2["chapters"][0]
    assert [s["title"] for s in chapter["sections"]] == ["示例节"], chapter["sections"]
    # 该节标题行与其下 `领会：` 行都归入「明确不考核」，不得被读成抽取失败
    assert {u["reason"] for u in chapter["unmodeled"]} == {"not_assessed"}, chapter["unmodeled"]
    assert doc2["coverage"]["official_point_count"] == 1
    assert doc2["coverage"]["ratio"] == 1.0


def test_artifact_matches_fresh_build_for_fallback_courses():
    """KB-1…KB-4 产物契约：`00898` / `02333` 的模型 = 现算结果，章号 1–N 连续、分母自洽。

    这两门课是「无目录页」的真实回归样本（各有 16 / 14 章）；`ratio == 1.0` 表示考纲每个考核单元
    都抽出了 point。测试直接读真实仓产物，故章数变化会在这里失败而不是静默漂移。
    """
    for code, expected in (("00898", 16), ("02333", 14)):
        doc = km.build_knowledge_model(ROOT, code)
        artifact = json.loads((ROOT / f"sources/jiangsu/courses/{code}/knowledge-model.json").read_text(encoding="utf-8"))
        assert {**doc, "generated_at": artifact["generated_at"]} == artifact, code

        assert len(doc["chapters"]) == expected, code
        assert [c["ordinal"] for c in doc["chapters"]] == list(range(1, expected + 1)), code
        assert [c["slug"] for c in doc["chapters"]] == [f"ch{n:02d}" for n in range(1, expected + 1)], code
        coverage = doc["coverage"]
        assert coverage["ratio"] == 1.0, code
        # 分母 = 章产出单元 + 附录产出单元（R41：`02333` 的 7 个 `附录N` 是独立考核单元，进分母）。
        units = sum(len(c["sections"]) for c in doc["chapters"])
        units += sum(len(a["sections"]) for a in doc.get("appendices", []))
        assert coverage["official_point_count"] == units, code
        assert coverage["modeled_point_count"] == coverage["official_point_count"], code
        assert doc["generator"] == {
            "kind": "deterministic", "model": None, "prompt_id": None, "prompt_version": None,
        }, code
        # 章标题必须与已发布 `syllabus.md` 的章名索引逐字一致（折叠空白后）。这两课的索引标题列
        # 是 `## 章节名称索引` / `## 章名索引（标题照录，机器抽取件）`，**不是**闸门认的
        # `### 章目索引`，故 evidence 层不做这项交叉核对 —— 这里独立读表比对，防止模型与读者页漂移。
        # 索引列照录抽取件的原始多空格（`第1章   JSP 与 Web 技术概论`），模型按契约折叠为单空格，
        # 故比对前两边都折叠（与 `tests/test_knowledge_model.py::test_chapter_names_verbatim` 同口径）。
        page = (ROOT / f"content/jiangsu/courses/{code}/syllabus.md").read_text(encoding="utf-8")
        published = [
            cells[1]
            for line in page[page.index("## 章") :].splitlines()
            for cells in [[cell.strip() for cell in line.strip().strip("|").split("|")]]
            if line.startswith("|") and len(cells) >= 2 and cells[0].startswith("第") and cells[0].endswith("章")
        ]
        assert len(published) == expected, (code, published)
        assert [km._fold(title) for title in published] == [c["title"] for c in doc["chapters"]], code
        # 每个 point 的 quote 都非空且 ≤ 60 字符（闸门失败关闭条件）
        for chapter in doc["chapters"]:
            for section in chapter["sections"]:
                for point in section["points"]:
                    assert point["quote"].strip() and len(point["quote"]) <= 60, point["id"]


# ---- 修复轮 F-1…F-4：真实版式（页码粘连 / 一行多标签 / 节级守卫） ---------------------------
#
# 上一轮的用例全部用**规整**片段（一行恰好一个标签、页码独占行、无粘连），所以 335 条全绿
# 而 `00898` 的产物仍丢了 5 个真考核节。本批用例直接照抄 `00898` 抽取件的**真实形态**
# （行号即 `document.extracted.md` 的行号），让缺陷可证伪。

SAMPLE_898_DOC = (
    "sources/jiangsu/processed/syllabus/00898-internet-software-development-gaogang-4295/"
    "document.extracted.md"
)


def _paren_label_count(text: str) -> int:
    """文本里 `（N）` 标签的个数（测试自备判据，不调用生产正则）。"""
    return len(re.findall(r"（[一二三四五六七八九十]+）", text))


def _sample_898_lines() -> list[str]:
    """`00898` 抽取件的物理行（F-1 的真实形态来源）。"""
    return (ROOT / SAMPLE_898_DOC).read_text(encoding="utf-8").split("\n")


def test_page_marker_glued_to_a_section_label_does_not_swallow_it():
    """F-1 形态 A：页码行把下一行的节标题并走 —— `00898` L167/L168、L367/L368 实测。

    真实版式是「页码独占一行、标签在**下一行**」；旧实现只丢**整行都是页码**的行（`^...$` 锚定），
    于是页码行留在逻辑流里；它不以 `。` 收尾，下一行的 `（七）企业应用开发架构` 被并进它，
    而 `_section_label` 又锚 `^`，嵌入的 `（N）` 看不见 —— 整节消失、其 5 条短语被并进**上一节**
    （`ch01` 只有 6 节而非 7 节，`软件编程体系简介` 拿到 9 个 point 而不是 4 个）。

    断言直接取自真实物理行：这一形态就是缺陷本体，不靠合成片段。
    """
    lines = _sample_898_lines()
    # 前提：源里确实是「页码独占一行 + 下一行是标签」（考纲换版会让这条前提先失败）
    assert km.PAGE_MARKER_RE.fullmatch(km._fold(lines[166])), repr(lines[166])
    assert km._section_label(km._fold(lines[167])) == ("7", "企业应用开发架构"), repr(lines[167])

    raw = [(number, lines[number - 1]) for number in range(167, 172)]
    logical = km._logical_lines(raw)
    assert [item["text"] for item in logical][0] == "（七）企业应用开发架构", logical
    assert all(not km.PAGE_MARKER_RE.search(item["text"]) for item in logical), logical

    sections, unmodeled, _ = km._parse_requirement_block(
        logical, "00898", "ch01", "第1章 JSP 与 Web 技术概论"
    )
    assert [s["index"] for s in sections] == ["7"], sections
    assert sections[0]["title"] == "企业应用开发架构"
    # （七）自己的 5 条短语全在本节内（旧缺陷：它们落在上一节 s6）
    assert [p["title"] for p in sections[0]["points"]] == [
        "①两层、三层、N 层架构的组成",
        "②J2EE 的版本、组成（基础）、特点、本质、相关产品",
        "③J2EE 的分布",
        "①开发架构之间的比较",
        "②J2EE 典型的 4 层架构",
    ], sections[0]["points"]
    assert unmodeled == [], unmodeled
    # 页码既不是考核点，也不是命名缺口
    assert all(km.PAGE_MARKER_RE.search(p["title"]) is None for s in sections for p in s["points"])


def test_two_labels_on_one_logical_line_are_both_kept():
    """F-1 形态 B：相邻的 `（三）`/`（四）` 必须各成一节 —— `00898` L195/L196 实测。

    真实版式是**两个标签各占一行**，但 `（三）…（本节内容不作考核要求）` 不以 `。` 收尾，
    旧实现把 `（四）其他 JSP 开发环境。` 当 `passage` 并进上一行 —— 结果只认到第一个标签，
    B 节整节消失、其 `识记：` 行还被冠上 `reason: "not_assessed"`（把官方**考核**内容说成
    官方**不考**）。把 `（N）` 行认成行边界后，两节都在场，限定语只作用于自己那一节。
    """
    lines = _sample_898_lines()
    first, second = km._fold(lines[194]), km._fold(lines[195])  # L195 / L196
    assert _paren_label_count(first) == 1 and km.NOT_ASSESSED_MARKER in first, first
    assert _paren_label_count(second) == 1, second
    assert not first.endswith("。"), "对照前提：限定语行不以句号收尾，旧实现因此会吞掉下一行"

    logical = km._logical_lines([(195, lines[194]), (196, lines[195]), (197, lines[196])])
    assert [item["text"] for item in logical] == [first, second, km._fold(lines[196])], logical

    sections, unmodeled, _ = km._parse_requirement_block(
        logical, "00898", "ch02", "第2章 JSP 的开发和运行环境"
    )
    assert [s["index"] for s in sections] == ["4"], sections
    assert sections[0]["title"] == "其他 JSP 开发环境。"
    # B 节的 `识记：` 行必须成为该节的 point，绝不记成 not_assessed
    assert [p["requirement"] for p in sections[0]["points"]] == ["识记"]
    assert [u["reason"] for u in unmodeled] == ["not_assessed"]
    assert "不作考核要求" in unmodeled[0]["title"]


def test_requirement_line_is_never_stamped_not_assessed():
    """AC2：`识记/领会/应用：` 行自证该单元参与考核 —— 任何情况下都不得记为 `not_assessed`。

    旧实现把 `skip_reason` 保留到下一个**有效且不带限定语**的标签为止，于是限定语之后的非标签行
    全部继承 `not_assessed`（`00898` L197/L458/L502 三条真要求行中招）。这里遍历七个真实考纲的
    产物：只要出现 `not_assessed`，其标题就必须真含 `不作考核要求`，且带考核前缀的行绝不在其中。
    """
    for code in ("00898", "02333", "04747", "04751", "15040", "15043", "15044"):
        doc = km.build_knowledge_model(ROOT, code)
        for chapter in doc["chapters"]:
            for item in chapter["unmodeled"]:
                if item["reason"] == "not_assessed":
                    assert km.NOT_ASSESSED_MARKER in item["title"], (code, item)
                if km.REQUIREMENT_RE.match(item["title"]):
                    assert item["reason"] != "not_assessed", (code, chapter["slug"], item)


def test_section_continuity_guard_fails_closed_and_names_the_missing_section():
    """F-3：节级守卫必须失败关闭，并**指名**缺哪一节（章级守卫看不见丢节）。

    变异证明：把声明里的 `（二）` 那一节从产出里去掉（`sections` 只给 1、3），守卫必须报第2节。
    对照：声明与产出一致时守卫静默（不得把正常输入判成缺口）。
    """
    problems = km._section_continuity_problems(
        "99999", "ch01", "第1章 甲", ["1", "2", "3"], [{"index": "1"}, {"index": "3"}], []
    )
    assert len(problems) == 1, problems
    message = problems[0]
    assert "缺第2节" in message, message
    assert "99999" in message and "ch01" in message, message

    assert km._section_continuity_problems(
        "99999", "ch01", "第1章 甲", ["1", "2"], [{"index": "1"}, {"index": "2"}], []
    ) == []
    # 明确不考核的节不进分母，但已留痕 → 不算缺节（否则「不考」会被误报成「抽取失败」）
    assert km._section_continuity_problems(
        "99999", "ch01", "第1章 甲",
        ["1", "2"],
        [{"index": "1"}],
        [{"locator": "L9", "title": "（二）不考的节（本节内容不作考核要求）", "reason": "not_assessed"}],
    ) == []


def test_model_build_fails_closed_when_a_section_is_dropped(tmp_path: Path):
    """F-3 端到端：**声明了** `（三）` 而产出没有它时，构建必须 raise（不只靠纯函数单测）。

    三个子例覆盖守卫的判别力：
    1. 真实版式（页码独占一行、标签在下一行）→ 3 节全在场；
    2. 整节连页码一起删掉 → 声明 2、产出 2，守卫必须静默（证明不是恒定 raise）；
    3. **历史缺陷形态**：标签被并进页码行（`第 7 页 共 9 页（三）第三节`）→ 标签仍被声明（3），
       但 `sections[]` 只有 2 → 守卫必须失败关闭。第 3 例正是 `00898` 出厂时全绿的那种输入。
    """
    text = (
        "Ⅰ 课程性质与课程目标\n示例。\n\nⅢ 课程内容与考核要求\n\n第1章 甲\n"
        "一、学习目的与要求\n示例。\n" + FALLBACK_HEADING + "\n"
        "（一）第一节\n识记：示例。\n"
        "（二）第二节\n领会：示例。\n"
        "第 7 页 共 9 页\n（三）第三节\n应用：示例。\n"
        "四、本章重点\n示例。\n"
    )
    root, evidence = _fragment_root(tmp_path, text)
    doc = km.extract_knowledge_model(root, evidence)
    assert [s["index"] for s in doc["chapters"][0]["sections"]] == ["1", "2", "3"], doc["chapters"][0]["sections"]

    # 子例 2：声明数与产出数一致时守卫静默
    narrowed = text.replace("（三）第三节\n应用：示例。\n", "").replace("第 7 页 共 9 页\n", "")
    root2, evidence2 = _fragment_root(tmp_path / "narrowed", narrowed)
    doc2 = km.extract_knowledge_model(root2, evidence2)
    assert [s["index"] for s in doc2["chapters"][0]["sections"]] == ["1", "2"]

    # 子例 3：标签被页码粘连 → 声明 3、产出 2 → 失败关闭且指名缺第3节
    glued = text.replace("第 7 页 共 9 页\n（三）第三节", "第 7 页 共 9 页（三）第三节")
    root3, evidence3 = _fragment_root(tmp_path / "glued", glued)
    with pytest.raises(ValueError) as err:
        km.extract_knowledge_model(root3, evidence3)
    assert "缺第3节" in str(err.value), str(err.value)


def test_not_assessed_absolution_is_symmetric_across_both_section_grammars():
    """QC wave-1 F-1：销账侧必须与声明侧认**同一套版式**，否则官方「不考核」的节被误报成丢节。

    改前 `_declared_section_indexes()` 认两种版式（`1.` + `（N）`），而 `_section_continuity_problems()`
    的 `accounted` 只用 `PAREN_LABEL_RE` 扫 `not_assessed` 标题 —— 按 `1.` 版式书写的「明确不考核」节
    **声明了却永不被销账**，守卫对合法输入报假缺口（QC1 `F-1` 的复现：声明 `['1']`、产出 `[]`）。
    真实数据今日未触发（7 份考纲里 `1.` 版式与 `不作考核要求` 不共存），故本用例用纯函数把两个版式
    钉成对称；同时钉住**判别力** —— 修掉假阳性不得把真阳性一起修掉，且销账仍只认 `not_assessed`。
    """
    def problems(declared: list[str], sections: list[dict], unmodeled: list[dict]) -> list[str]:
        return km._section_continuity_problems("99999", "ch01", "第1章 甲", declared, sections, unmodeled)

    # 1. `1.` 与 `（一）` 两种版式的「不考核」节都已交代 → 守卫必须静默（改前 `1.` 版式报假缺口）
    for label in ("1.", "（一）"):
        title = f"{label}乙节（本节内容不作考核要求）"
        declared = km._declared_section_indexes([{"text": title}])
        assert declared == ["1"], (label, declared)
        assert problems(declared, [], [{"locator": "L9", "title": title, "reason": "not_assessed"}]) == [], label

    # 2. 真阳性：声明 2 节、产出 1 节 → **两种版式**都必须失败关闭且指名第2节（判别力不得被削弱）
    for labels in (["1.甲节", "2.乙节"], ["（一）甲节", "（二）乙节"]):
        declared = km._declared_section_indexes([{"text": text} for text in labels])
        assert declared == ["1", "2"], (labels, declared)
        found = problems(declared, [{"index": "1"}], [])
        assert len(found) == 1 and "缺第2节" in found[0], (labels, found)

    # 3. 销账**只**认 `not_assessed`：其它 reason 不得为丢掉的节销账，否则守卫被蒙住
    title = "2.乙节（本节内容不作考核要求）"
    declared = km._declared_section_indexes([{"text": "1.甲节"}, {"text": title}])
    found = problems(declared, [{"index": "1"}], [{"locator": "L9", "title": title, "reason": "unnumbered_section"}])
    assert len(found) == 1 and "缺第2节" in found[0], found


def test_1_dot_not_assessed_section_builds_while_a_dropped_one_still_raises(tmp_path: Path):
    """QC wave-1 F-1 端到端：`1.` 版式的「明确不考核」节必须能建模；同一版式真丢节仍失败关闭。

    上一条只覆盖 `_section_continuity_problems()` 的入参形态。本用例从 `document.extracted.md` 走到
    `extract_knowledge_model()`，证明守卫在真实调用链上不再误报（改前此处 `ValueError`），
    且该版式下被丢掉的节仍被抓住 —— 「不考」与「抽取失败」在产物里各自可辨。
    """
    def extract(name: str, requirements: str) -> dict:
        text = (
            "Ⅰ 课程性质与课程目标\n示例。\n\nⅢ 课程内容与考核要求\n\n第1章 甲\n"
            "一、学习目的与要求\n示例。\n" + FALLBACK_HEADING + "\n" + requirements + "四、本章重点\n示例。\n"
        )
        root, evidence = _fragment_root(tmp_path / name, text)
        return km.extract_knowledge_model(root, evidence)

    # `1.` 版式的不考核节：不进分母、留痕、守卫静默（改前 `缺第1节` 假缺口）
    chapter = extract("not_assessed", "1.乙节（本节内容不作考核要求）\n")["chapters"][0]
    assert chapter["sections"] == [], chapter["sections"]
    assert [(item["reason"], item["title"]) for item in chapter["unmodeled"]] == [
        ("not_assessed", "1.乙节（本节内容不作考核要求）")
    ], chapter["unmodeled"]

    # 真阳性：`（二）` 与 `1.甲节` 同处一逻辑行（解析器一行至多取一个标签）→ 声明 2、产出 1
    with pytest.raises(ValueError) as err:
        extract("dropped", "1.甲节（二）乙节\n识记：示例。\n")
    assert "缺第2节" in str(err.value), str(err.value)


def test_denominator_rule_describes_the_denominator_actually_used():
    """F-2：`denominator_rule` 必须描述**实际用的分母** —— 两门真实课各占一种形状。

    `00898` 是节级考纲（50 个 `（N）` 节 / 16 章），`02333` 是章级考纲 + 7 个附录单元
    （`13` 考核章 + `7` `附录N` = `20`；R41：附录是独立考核单元，不再是第 14 章的正文）。
    旧实现按「任一章是章级」的 OR 选规则，`00898` 只因 6 个不考核章的空要求块就被判成章级，
    产物便自称「该考纲不分子节」—— 分母实为节数，是可被下游当事实读的假话。
    """
    section_level = km.build_knowledge_model(ROOT, "00898")["coverage"]
    assert section_level["official_point_count"] == 50, "分母是节数（50），不是章数（16）"
    assert "章即考核单元" not in section_level["denominator_rule"], section_level["denominator_rule"]
    assert "节数" in section_level["denominator_rule"], section_level["denominator_rule"]

    chapter_level = km.build_knowledge_model(ROOT, "02333")["coverage"]
    assert chapter_level["official_point_count"] == 20, "分母是 13 考核章 + 7 附录单元"
    assert "章即考核单元" in chapter_level["denominator_rule"], chapter_level["denominator_rule"]
    # 规则串必须把附录单元写出来，否则下游读到的是「分母 = 13 章」而实际是 20 个单元
    assert "7 个附录单元" in chapter_level["denominator_rule"], chapter_level["denominator_rule"]


def test_00898_real_artifact_keeps_all_fifty_assessed_sections_and_no_misattribution():
    """AC1：`00898` 的 50 个考核节全部在场，且短语不跨节错位（真实产物断言）。

    旧产物只有 45 节、`ch01` 缺 `（七）`（9 个 point 全挂到 `s6`）、`ch06` 缺 `（二）`。
    这里钉死：50 节、`ch01` 是 7 节且 `s6`/`s7` 各自成节、每个 point id 的节号与所在节一致。
    """
    doc = json.loads((ROOT / "sources/jiangsu/courses/00898/knowledge-model.json").read_text(encoding="utf-8"))
    sections = [section for chapter in doc["chapters"] for section in chapter["sections"]]
    assert len(sections) == 50, f"考核节数应为 50，实际 {len(sections)}"
    assert doc["coverage"]["official_point_count"] == 50
    assert doc["coverage"]["ratio"] == 1.0

    ch01 = next(chapter for chapter in doc["chapters"] if chapter["slug"] == "ch01")
    assert [s["index"] for s in ch01["sections"]] == ["1", "2", "3", "4", "5", "6", "7"], ch01["sections"]
    s6, s7 = ch01["sections"][5], ch01["sections"][6]
    assert s7["title"] == "企业应用开发架构"
    # （七）的 5 条短语必须落在 s7，不得留在 s6（旧缺陷：s6 拿到 9 个 point）
    assert [p["title"] for p in s7["points"]] == [
        "①两层、三层、N 层架构的组成",
        "②J2EE 的版本、组成（基础）、特点、本质、相关产品",
        "③J2EE 的分布",
        "①开发架构之间的比较",
        "②J2EE 典型的 4 层架构",
    ], s7["points"]
    assert all("架构" not in point["title"] or "B/S" in point["title"] for point in s6["points"]), s6["points"]

    # 每个 point 的 id 必须与其所在节的 index 一致（跨节错位的机器可读判据）
    for chapter in doc["chapters"]:
        for section in chapter["sections"]:
            for point in section["points"]:
                assert point["id"] == f"00898-{chapter['slug']}-s{section['index']}-p{point['id'].rsplit('-p', 1)[1]}", point["id"]
                assert point["title"].strip() and point["quote"].strip(), point["id"]



# ---- QC wave-1 F-2：AC3 冻结基线（`15043` / `15044` 逐字节不变） -----------------------------
#
# AC3 是本切片的头号不变量（回退是 fallback、不是替换）：新分支只应影响「无目录页」的课，
# 三门既有课的模型必须与基线 `334d637` 逐字节一致。此前只有 `15040` 有守护
# （`test_artifact_matches_fresh_build_and_is_hash_seed_independent`），`15043`/`15044`
# 的字节一致只是**报告级声明** —— 下一轮改动共享代码或重跑生成都会静默漂移。
# 与本文件 `15040` 的既有口径一致：既比对 committed 字节，也比对「产物 = f(现算)」。

FROZEN_MODEL_SHA256 = {
    # 基线 `334d637`（= 本切片基线，未经 B3a 改动）的原始字节摘要
    "15043": "b6dea4b3c6427511710cb99b9f11d093ad9d3c83ee80d96cdf47974aac786f25",
    "15044": "ccfc9eebf96d1eac321951373eacba826eed31a7eb393f093d9a9d03b8aeb14d",
}


def _frozen_model_path(code: str) -> Path:
    return ROOT / f"sources/jiangsu/courses/{code}/knowledge-model.json"


def _model_digest(path: Path) -> str:
    """产物文件的原始字节摘要（比较口径：路径无关、逐字节，不做任何归一化）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_models_stay_byte_identical_to_the_base_commit():
    """AC3 持久守护：`15043` / `15044` 的模型必须与基线 `334d637` 逐字节一致。

    两半各有不可替代的判别力：
    1. **字节摘要**钉住 committed 文件本身 —— 重跑生成、改序列化、手工编辑都会让它失败
       （这正是 AC3「逐字节不变」的字面含义）；
    2. **现算重建**钉住「产物 = f(源码)」—— 共享抽取代码被改坏、但产物没重生成时，
       文件摘要仍与基线相同，只有重建比对能发现「代码已不再复现冻结模型」。
    `generated_at` 是生成日（`date.today()`），故重建半边按既有 `15040` 口径归一化该字段；
    字节半边不归一化 —— 该字段变化即意味着重新生成过，而 AC3 禁止重新生成。
    """
    for code, expected_sha in FROZEN_MODEL_SHA256.items():
        path = _frozen_model_path(code)
        assert path.is_file(), f"冻结产物缺失: {path.relative_to(ROOT)}"
        actual = _model_digest(path)
        assert actual == expected_sha, (
            f"{code} 的 knowledge-model.json 偏离基线 334d637："
            f"expected={expected_sha} actual={actual}。AC3 要求逐字节不变 —— "
            "请用 `git checkout 334d637 -- "
            f"sources/jiangsu/courses/{code}/knowledge-model.json` 还原，不要重新生成。"
        )

        # 重建半边：现算结果（仅 `generated_at` 归一化）必须仍等于 committed 产物
        artifact = json.loads(path.read_text(encoding="utf-8"))
        fresh = km.build_knowledge_model(ROOT, code)
        assert {**fresh, "generated_at": artifact["generated_at"]} == artifact, (
            f"{code}：现算模型已不再复现冻结产物（共享抽取代码漂移？）"
        )
        assert km.serialize({**fresh, "generated_at": artifact["generated_at"]}) == path.read_text(encoding="utf-8"), code


def test_frozen_model_byte_pin_is_falsifiable(tmp_path: Path):
    """上一条用例的反向验证：产物被扰动**1 字节**时，同一比较口径必须判否。

    不满足于「断言写在那儿」——若摘要比对退化成恒真（比错文件、比了归一化文本、或字典为空），
    上一条用例将永远绿灯。这里在工作副本上做 1 字节替换（长度不变），确认同一套
    `_model_digest()` + 冻结摘要确实**判否**，并确认反向验证没有触碰仓内产物。
    """
    for code, expected_sha in FROZEN_MODEL_SHA256.items():
        source = _frozen_model_path(code)
        committed = source.read_bytes()
        assert _model_digest(source) == expected_sha, f"对照前提：{code} 当前与基线一致"

        work = tmp_path / f"{code}.json"
        work.write_bytes(committed)

        # 选一个**确实存在**的正文串做扰动点（考前提，避免扰动落空导致假验证）
        victim = "马克思主义".encode()
        assert victim in committed, f"对照前提：{code} 含扰动点 `马克思主义`"
        mutated = committed.replace(victim, "马克思主意".encode(), 1)
        assert mutated != committed, "对照前提：1 字节替换必须改变字节"
        assert len(mutated) == len(committed), "对照前提：扰动只改内容、不改长度"
        work.write_bytes(mutated)

        assert _model_digest(work) != expected_sha, (
            f"{code}：1 字节扰动未被冻结摘要判否 —— 上一条用例的断言是恒真的"
        )
        assert _model_digest(work) != _model_digest(source), code

    # 仓内产物未被本次反向验证触碰
    for code, expected_sha in FROZEN_MODEL_SHA256.items():
        assert _model_digest(_frozen_model_path(code)) == expected_sha, f"反向验证不得改动仓内产物：{code}"


# ---- R41 + R43：`02333` 附录单元被静默吞掉（附录不再是第 14 章的正文） ------------------------
#
# 缺陷（QC/QA/PM 三方复现，AST 级确认与基点 `334d637` 相同的既有缺陷）：
# `02333` 无 `大纲目录`，章目走 `Ⅲ` 回退；`_body_slices()` 只把**部次标签**当末章边界，
# 于是第 14 章切片一路吃到 `Ⅳ`（`L306–L375`），把 `L310–L374` 的 7 个 `附录N` 段落全包进来；
# `_requirement_block()` 又只取章锚点后**第一个** `二、考核知识点与考核要求`（`L314`，实属附录一）。
# 后果：7 条受考要求行（`L324`/`L333`/`L342`/`L353`/`L362`/`L371`/`L372`，末条含 `应用` 级）
# 在整个产物里**一个字都没有**，而 `附录二 需求规格说明书`（`L319`）反被当成第 14 章的「本章重点」。
# 全程 `ratio == 1.0`：分母与产出同源，丢单元时两侧同时变小（R43）。

SAMPLE_233_DOC = (
    "sources/jiangsu/processed/syllabus/02333-software-engineering-gaogang-4068/"
    "document.extracted.md"
)
# 修复前**完全不在产物里**的 7 条要求行（行号即 `document.extracted.md` 的物理行号）
R41_DROPPED_LINES = {
    324: "①需求规格说明书的内容和书写格式",
    333: "①总体设计说明书的内容和书写格式",
    342: "①详细设计说明书的内容和书写格式",
    353: "①软件测试的需求规格说明书的内容和书写格式",
    362: "①软件维护手册的内容和书写格式",
    371: "①UML 的五大模型",
    372: "①会根据实际问题应用五大模型来描述，如用例图、类图、时序图等",
}


def _model_233() -> dict:
    return json.loads((ROOT / "sources/jiangsu/courses/02333/knowledge-model.json").read_text(encoding="utf-8"))


def _all_points(doc: dict) -> list[dict]:
    """产物里全部 point（章 + 附录单元）。"""
    units = [*doc["chapters"], *doc.get("appendices", [])]
    return [point for unit in units for section in unit["sections"] for point in section["points"]]


def test_r41_seven_appendix_requirement_lines_are_no_longer_dropped():
    """R41：7 条附录要求行必须**有身份**地进产物 —— 逐条按源文行号核对，不再静默消失。

    修复前：`ch14.sections == []`、`ch14.unmodeled == [L315]`，这 7 条在整个 JSON 里搜不到
    （连子串都不存在）。修复后每条都必须是某个 point 的 `title`，且 `locator` 指向它自己那一行。
    """
    doc = _model_233()
    by_locator: dict[str, list[dict]] = {}
    for point in _all_points(doc):
        by_locator.setdefault(point["locator"], []).append(point)

    for line, phrase in R41_DROPPED_LINES.items():
        points = by_locator.get(f"L{line}")
        assert points, f"L{line} 的要求行没有任何 point（仍在被静默丢弃）"
        titles = [point["title"] for point in points]
        assert phrase in titles, f"L{line} 的短语 {phrase!r} 不在 {titles}"

    # `L372` 的 `应用` 级要求必须保住层级（不得被降级成 `识记` 或被吞）
    applied = [point for point in by_locator["L372"]]
    assert [point["requirement"] for point in applied] == ["应用"], applied
    # `L371` 的两个短语各自成 point（`；` 分句）
    assert [point["title"] for point in by_locator["L371"]] == ["①UML 的五大模型", "②9 种图表示"]


def test_r41_appendix_content_is_never_attributed_to_chapter_14():
    """R41：附录内容**一律不得**挂在第 14 章下（这正是缺陷本身，不是可接受的呈现）。

    第 14 章的标题自证「（本章内容不作考核要求）」，它的 `sections` / `chapter_focus` / `unmodeled`
    都必须为空 —— 修复前 `chapter_focus` 里坐着 `附录二 需求规格说明书`（`L319`）。
    """
    doc = _model_233()
    ch14 = doc["chapters"][13]
    assert ch14["slug"] == "ch14" and "不作考核要求" in ch14["title"], ch14["title"]
    assert ch14["sections"] == [], ch14["sections"]
    assert ch14["chapter_focus"] == [], ch14["chapter_focus"]
    assert ch14["unmodeled"] == [], ch14["unmodeled"]

    blob = json.dumps(ch14, ensure_ascii=False)
    for leaked in ("附录", "需求规格", "总体设计", "详细设计", "软件维护手册", "UML"):
        assert leaked not in blob, f"第 14 章仍含附录内容：{leaked!r}"


def test_r41_appendices_are_their_own_assessment_units():
    """R41：`附录N` 是独立考核单元 —— 7 个、序连续、各自带 point 与自己的「本章重点」。"""
    doc = _model_233()
    appendices = doc["appendices"]
    assert [ap["slug"] for ap in appendices] == [f"ap{n:02d}" for n in range(1, 8)]
    assert [ap["ordinal"] for ap in appendices] == list(range(1, 8))
    assert [ap["index"] for ap in appendices] == [f"附录{name}" for name in "一二三四五六七八九"[:7]]
    for ap in appendices:
        assert ap["sections"], ap["slug"]
        assert all(section["points"] for section in ap["sections"]), ap["slug"]
        # 「本章重点」归附录自己，不是第 14 章的
        assert ap["chapter_focus"], ap["slug"]
        assert all("附录" not in focus["text"] for focus in ap["chapter_focus"]), ap["slug"]
    # point id 用附录自己的 slug，不得借用章 slug
    ids = [point["id"] for ap in appendices for section in ap["sections"] for point in section["points"]]
    assert ids == sorted(ids)
    assert all(re.fullmatch(r"02333-ap\d{2}-s\d+-p\d+", pid) for pid in ids), ids


def test_r41_does_not_touch_courses_without_numbered_appendices():
    """R41 的爆炸半径：只有 `02333` 有 `附录N`；其余六门不得多出 `appendices` 字段 / 单元。

    `附录：参考样卷`（15040/15043/15044）与 `附录 题型示例`（00898/04747/04751）**没有序号**，
    是 `Ⅳ` 之后的样卷区而非考核内容 —— 判据必须把它们挡在考核单元之外。
    """
    for code in ("15040", "15043", "15044", "00898"):
        doc = km.build_knowledge_model(ROOT, code)
        assert "appendices" not in doc, f"{code} 不应有附录单元"
    assert not km.APPENDIX_RE.match("附录：参考样卷")
    assert not km.APPENDIX_RE.match("附录 题型示例")
    assert not km.APPENDIX_RE.match("附录")
    assert km.APPENDIX_RE.match("附录一 可行性研究报告")
    assert km.APPENDIX_RE.match("附录 7 UML 图")


def _appendix_fragment(appendix_blocks: list[str]) -> str:
    """合成考纲：1 章 + 给定附录块（每块自带 `三、考核知识点与考核要求`，故是一整个考核单元）。

    复用 `_fallback_fragment()`（无目录页、`Ⅲ` 部直接列章）；附录块插在末章与 `Ⅳ` 之间 ——
    与真实考纲里 `附录N` 的位置一致（`02333` 的 7 个附录就在 `Ⅲ` 部末尾、`Ⅳ` 之前）。
    """
    blocks = "\n\n".join(
        f"{block}\n{FALLBACK_HEADING}\n识记：附录识记内容。\n领会：附录领会内容。" for block in appendix_blocks
    )
    return _fallback_fragment(["第一章 示例章"]).replace(
        "\n\nⅣ 关于大纲的说明与考核实施要求",
        f"\n\n{blocks}\n\nⅣ 关于大纲的说明与考核实施要求",
    )


def test_appendix_heading_without_a_title_is_not_an_assessment_unit(tmp_path: Path):
    """F-3①：裸 `附录一`（**无标题**）不是考核单元 —— 修前它被接受并占掉 `ap01`。

    修前实测：`km.APPENDIX_RE.match("附录一")` 命中（标题捕获组为空串）、`_appendix_number("附录一") == 1`，
    端到端抽取产出 `appendices[0]`（`slug: ap01`）；同一份文档里 `附录一 可行性研究报告` 也产出
    `ap01` —— 两个单元共用一个 slug。修后前者不构成单元，标题判据与闸门侧共用同一个正则。
    """
    root, evidence = _fragment_root(tmp_path / "bare", _appendix_fragment(["附录一"]))
    doc = km.extract_knowledge_model(root, evidence)

    assert "appendices" not in doc, doc.get("appendices")
    # 判据本身（`evidence_gate` 用的是同一个正则）：无标题不命中、带标题命中
    assert not km.APPENDIX_RE.match("附录一")
    assert not km.APPENDIX_RE.match("附录一 ")
    assert km.APPENDIX_RE.match("附录一 可行性研究报告")


def test_conflicting_appendix_numbers_fail_closed_with_both_locators(tmp_path: Path):
    """F-3②：同号冲突失败关闭，并**指名冲突的两行 locator**（不得静默复用 `ap01`）。

    修前实测：`附录一 甲附录` 与 `附录 1 乙附录` 都映射到 `number=1` / `slug=ap01`，抽取不报错 ——
    两个单元的 slug 与 point id 前缀相同，产物里看不出「有两个附录一」。
    """
    text = _appendix_fragment(["附录一 甲附录", "附录 1 乙附录"])
    root, evidence = _fragment_root(tmp_path / "clash", text)
    lines = text.split("\n")
    first = lines.index("附录一 甲附录") + 1
    second = lines.index("附录 1 乙附录") + 1

    with pytest.raises(ValueError) as excinfo:
        km.extract_knowledge_model(root, evidence)

    message = str(excinfo.value)
    assert "附录序号冲突" in message, message
    assert f"L{first}" in message and f"L{second}" in message, message
    assert "ap01" in message, message


def test_r43_denominator_is_counted_from_the_source_not_from_the_parse():
    """R43：分母必须**独立于产出**数出来 —— 源侧计数能复现全部真实课，且能看穿丢单元。

    反证：修复前的产物 `official_point_count == 13`（只数到 13 个考核章），
    同源核对（`official` vs `sum(len(sections))`）**恒真**、放行；而源侧计数数出 **20**
    （13 章 + 7 附录）。这条差异就是 R41 曾经不可见的原因。
    """
    ev = json.loads((ROOT / "sources/jiangsu/courses/02333/evidence.json").read_text(encoding="utf-8"))
    lines = (ROOT / ev["syllabus"]["path"]).read_text(encoding="utf-8").split("\n")
    declared = km.source_assessment_unit_count(lines, ev["syllabus"]["requirements_heading"])
    assert declared == 20, f"源侧应数出 13 章 + 7 附录 = 20，实际 {declared}"
    assert declared == _model_233()["coverage"]["official_point_count"]

    # 现有 5 份模型的官方分母都必须能被**源侧**独立复现（否则新分母会变成另一套假话）
    for code, expected in (("15040", 61), ("15043", 34), ("15044", 28), ("00898", 50), ("02333", 20)):
        evidence = json.loads((ROOT / f"sources/jiangsu/courses/{code}/evidence.json").read_text(encoding="utf-8"))
        source_lines = (ROOT / evidence["syllabus"]["path"]).read_text(encoding="utf-8").split("\n")
        counted = km.source_assessment_unit_count(source_lines, evidence["syllabus"]["requirements_heading"])
        assert counted == expected, f"{code}: 源侧计数 {counted} ≠ {expected}"


def test_r43_evidence_gate_catches_a_swallowed_appendix_unit(tmp_path: Path):
    """R43 的闸门侧：吞掉一个附录单元后，`run_evidence_gate` 必须报出（旧检查恒真）。

    对照两半都有判别力：删单元（分母变小）必须报；文件本身不动时必须静默。
    """
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "02333" / "knowledge-model.json"
    clean = json.loads(target.read_text(encoding="utf-8"))
    assert not [e for e in run_evidence_gate(fake_root) if "02333" in e], "对照前提：未改动的产物必须静默"

    for dropped in (1, 2, 7):
        data = json.loads(json.dumps(clean, ensure_ascii=False))
        data["appendices"] = data["appendices"][: len(data["appendices"]) - dropped]
        data["coverage"]["official_point_count"] -= dropped
        data["coverage"]["modeled_point_count"] -= dropped
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors = run_evidence_gate(fake_root)
        assert any("考核单元" in e and "静默丢弃" in e for e in errors), (dropped, errors)


def test_f3_evidence_gate_rejects_an_appendix_title_without_a_title(tmp_path: Path):
    """F-3① 的闸门侧：产物里 `appendices[].title` 是裸 `附录一`（**无标题**）时必须报出。

    修前实测：闸门用的是第二个正则（`APPENDIX_TITLE_RE`，标题段写成可选 `(?:\\s*.+)?`），
    故裸 `附录一` 被放行 —— 抽取侧与闸门侧两个判据各自漂移、同时接受无标题条目。
    """
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "02333" / "knowledge-model.json"
    clean = json.loads(target.read_text(encoding="utf-8"))
    assert not [e for e in run_evidence_gate(fake_root) if "02333" in e], "对照前提：未改动的产物必须静默"

    data = json.loads(json.dumps(clean, ensure_ascii=False))
    data["appendices"][0]["title"] = "附录一"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("可识别的附录标题" in e for e in errors), errors


# ---- R54 3b：题型续行合并的行数上界（固定 3 行前瞻 + 越界失败关闭） -----------------------------

def _r54_exam_lines(type_line: str, body: list[str]) -> list[str]:
    """`_exam()` 的物理行输入：L4 是给定的题型声明行，其后跟 `body` 的长正文。"""
    return [
        "大纲目录",
        "第一章 示例章",
        "三、考核知识点与考核要求",
        type_line,
    ] + body


def test_r54_question_type_merge_does_not_fold_the_trailing_body():
    """R54 3b：题型行**自身已收句末句号**时前瞻消耗 0 行 —— 后续正文一律不得折进题型集。

    ⚠️ QC-5 口径更正：本用例原本靠 `merged.count("、") >= 4` 这条早停条件在 L4 行内终止。该条件已按
    QC-5 移除（`、` 个数**不是**句末判据），故构造改为在 L4 结尾补上句末「。」，锁「句子已结束 ⇒
    窗口立即关闭」这条路径；「≥4 个 `、` 但句子未结束」的形状由
    `test_qc5_question_type_merge_does_not_truncate_a_separator_heavy_declaration` 覆盖。
    正文仍是无「等」、无句末句号的长正文：窗口一旦没能关闭，正文就会被正则的 `$` 兜底吞进
    `group(1)`（末项变成 `材料题本课程考核说明第 5 段…`），故 `考核说明` 断言仍是一次真实的对折行检查。
    """
    lines = _r54_exam_lines(
        "4.本课程考试命题的主要题型一般有单项选择题、多项选择题、填空题、简答题、材料题。",
        [f"本课程考核说明第 {index} 段，来源在此处没有给出句末标点" for index in range(5, 17)],
    )

    exam = km._exam(lines, "syllabus:99999")
    assert exam["question_types"] == ["单项选择题", "多项选择题", "填空题", "简答题", "材料题"]
    assert all("考核说明" not in item for item in exam["question_types"]), exam["question_types"]
    assert exam["question_types_provenance"] == {"doc_id": "syllabus:99999", "locator": "L4"}


def test_r54_question_type_merge_fails_closed_when_the_bound_is_exhausted():
    """R54 3b：拼到上界仍未终止 → 失败关闭并**指名行号**，不得按已拼内容静默截断题型集。

    构造：L4 不收句末句号（来源把 `。` 写成 `．` 之类）；L5–L20 的正文长时间没有句末标点 ——
    终止条件只能靠「一路拼到文末」才可能满足。修复前 `lines[number:]` 无上界，
    会把整篇正文折进 `merged` 并按 `$` 兜底产出一个被污染的题型集（静默污染 → drill 题型集偏离考纲）；
    现在必须在**上界处**失败关闭，且错误点名题型声明所在行号。
    """
    lines = _r54_exam_lines(
        "4.本课程考试命题的主要题型一般有单项选择题、简答题、材料题",
        [f"本课程考核说明第 {index} 段，来源此处未给出句末标点" for index in range(5, 21)],
    )

    with pytest.raises(ValueError) as excinfo:
        km._exam(lines, "syllabus:99999")

    message = str(excinfo.value)
    assert "L4" in message, f"错误必须点名题型声明所在行号：{message}"
    assert "上界" in message, message
    assert km.QUESTION_TYPE_LOOKAHEAD == 3, "上界取 3（实测最坏情形需要 1 行续行；见模块常量注释）"


def test_qc5_question_type_merge_does_not_truncate_a_separator_heavy_declaration():
    """QC-5：声明行自身已含 4 个 `、` 但**未收句末句号**时，早停不得把它当作句子终止。

    终止判据只认句末「。」—— `、` 的个数说明词条多，与句子是否结束无关。修复前
    `merged.count("、") >= 4` 使循环在拼接**任何**续行之前就 `break`，正则
    `(.+?)(?:等|。|$)` 的 `$` 兜底把**词中折行**的半截词 `简答` 收进 `question_types`、
    整条 `论述题` 丢失，且因「已终止」而不触发失败关闭 —— 静默截断，正是 B4b 新来源的形状
    （今天 5 门课的声明行只有 2–3 个 `、`，故未暴露）。
    """
    lines = _r54_exam_lines(
        "4.本课程考试命题的主要题型一般有单项选择题、多项选择题、填空题、判断题、简答",
        ["题、论述题等。"]
        + [f"本课程考核说明第 {index} 段，来源在此处没有给出句末标点" for index in range(6, 18)],
    )

    exam = km._exam(lines, "syllabus:99999")

    assert exam["question_types"] == [
        "单项选择题", "多项选择题", "填空题", "判断题", "简答题", "论述题",
    ], exam["question_types"]
    assert "简答" not in exam["question_types"], exam["question_types"]
    assert all("考核说明" not in item for item in exam["question_types"]), exam["question_types"]
    assert exam["question_types_provenance"] == {"doc_id": "syllabus:99999", "locator": "L4"}


def test_qc5_question_type_window_closes_at_the_sentence_end_before_a_layout_note():
    """QC-5：句子在**版式尾注之前**收尾即算终止 —— `00898` 的真实形状，不得误杀。

    `00898` 的声明 = `…简答题、` + `综合应用题。（题型示例见附录）`。只认 `text.endswith("。")`
    会因括号尾注判为「未终止」，继续折进正文、最终在 3 行上界处失败关闭（实测：真实 `00898`
    的 L633 因此抛 `ValueError`，一门已交付课被误杀）。句末「。」是**句子**的终点而非行尾：
    窗口在该句号处关闭，`group(1)` 停在第一个「等 / 。」处，尾注不进题型集。
    """
    lines = _r54_exam_lines(
        "4.本课程考试试题可能采用的题型有：单项选择题、判断改错题、简答题、",
        ["综合应用题。（题型示例见附录）"]
        + [f"本课程考核说明第 {index} 段，来源在此处没有给出句末标点" for index in range(6, 18)],
    )

    exam = km._exam(lines, "syllabus:99999")

    assert exam["question_types"] == ["单项选择题", "判断改错题", "简答题", "综合应用题"], exam["question_types"]
    assert all("附录" not in item for item in exam["question_types"]), exam["question_types"]
    assert exam["question_types_provenance"] == {"doc_id": "syllabus:99999", "locator": "L4"}


def test_r54_question_types_are_reproduced_for_the_five_delivered_courses():
    """R54 3b 的既有产物不变性：5 门课的题型集必须由源文**原地复现**（有界合并不改动任何一门）。

    实测基线 = `15040`/`15043`/`15044` **3** 项、`00898`/`02333` **4** 项（本次实现前复跑核对）。
    其中 `00898`/`02333` **需要跨行拼接**才能取全：`02333` 的 `…简答题、综` + `合应用题等。`
    在**词中间**断开 —— 故上界不得收紧到 1。

    ⚠️ 口径更正：design-notes § 4.2 写的「既有 5 门课实测题型数 6/6/6/4/4（本席以
    `exam.question_types` 长度核对）」与产物不符 —— 5 门课**没有任何一门**是 6 项（也无 6 项的可能：
    `QUESTION_TYPE_RE` 的 `group(1)` 止于第一个「等 / 。」，这两门课的声明在第一个句号前只有 4 个词条）。
    本测试锁**实测值**，避免这个未复核的数字被继续引用。
    """
    measured = {"15040": 3, "15043": 3, "15044": 3, "00898": 4, "02333": 4}
    for code, expected_len in measured.items():
        evidence = json.loads((ROOT / f"sources/jiangsu/courses/{code}/evidence.json").read_text(encoding="utf-8"))
        artifact = json.loads(
            (ROOT / f"sources/jiangsu/courses/{code}/knowledge-model.json").read_text(encoding="utf-8")
        )
        exam = km.extract_knowledge_model(ROOT, evidence)["exam"]
        assert exam["question_types"] == artifact["exam"]["question_types"], code
        assert exam["question_types_provenance"] == artifact["exam"]["question_types_provenance"], code
        assert len(exam["question_types"]) == expected_len, (code, exam["question_types"])
