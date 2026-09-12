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
