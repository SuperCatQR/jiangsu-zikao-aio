"""知识模型抽取：`sources/jiangsu/courses/<code>/knowledge-model.json`（Data contracts 3）。

**确定性、无 LLM**：产物 `generator.kind == "deterministic"`，`model` / `prompt_id` / `prompt_version`
一律 `null`；本模块只读仓内考纲抽取件与只读课程页（不联网、不调用模型，GC8 / GC12）。

抽取链路（全部来自 Task 2 的 `evidence.json`：`syllabus.path` + `requirements_heading`）：

1. **章目**：`大纲目录` 切片里的章标题行（`导论` / `第N章 …`），折叠内部连续空白为单个半角空格 →
   与 `content/jiangsu/courses/15040/syllabus.md` 的章目索引逐字一致（TOC 用多空格、正文标题用单空格）。
   `Ⅰ–Ⅳ` 是部次标签、`附录：参考样卷` / `大纲后记` 是后附件，都不算章（GC3：不发明章号）。
   `ordinal` = 切片中的 0 基序号；`index` = 标题里的章序标签；`slug` = `intro`（ordinal 0）/ `ch<NN>`
   ——纯函数推导，不查表、不做拼音转写。
2. **归一化前置（必须）**：先按物理行合并折行续行、丢弃独占一行的页码与空行，再切节。
   抽取件版式实测：`识记：` 内容续行到下一行（`document.extracted.md:222-224`），页码独占一行且插在
   要求块中间（`:240` 的 `7` 把第 4 节 `识记` 与 `领会` 隔开）。不归一化会让三级要求整体错位。
   合并规则（逐条可核对）：节标题（`^\\d+\\.`）与顶层小节标题（`^[一二三四五六七八九十]+、`）恒为独立逻辑行、
   也不吸收续行；`识记：` / `领会：` / `应用：` 行与普通段落在其文本尚未以 `。！？` 收尾时吸收后续物理行。
   实测 15040：102 条续行全部归属考核要求行，0 条归属节标题 —— 故「节标题不吸收续行」在本课纲上无副作用。
3. **节与考核点**：考核要求小节内 `^\\d+\\.` 为节边界；节内 `识记：` / `领会：` / `应用：` 行按 `；`
   拆成 point，`requirement` 取该行前缀。**编号节内没有前缀的考核内容** → `requirement: null`（考纲未分级）；
   **不属于任何编号节的段落**（该段之前没有编号节 —— 含要求行本身，或该节已出现带前缀的要求）→ 只进
   `chapters[].unmodeled[]`（`reason: "unnumbered_section"`），不生成 point、不编造 index / 章号（GC3）。
4. **`quote` ≤ 60 字符且逐字来自考纲**：短语本身超长时取最后一个分句边界（`，、：,;`）之内的前缀
   ——不拼接、不改写、不加省略号，`title` 仍保留完整原文（GC4；长短语只截 `quote`、不拆 point，
   因此 point id 用节内 `p<seq>` 而不是 requirement 后缀）。
5. **覆盖率**：分母 = 考核要求小节内带编号的节数（15040 实测 **61**，与 `index.md:549` 手工自评吻合）；
   分子 = 至少抽出 1 个 point 的节数；`diff_vs_manual` 与手工页 `## 章节知识树` 的每条 `####` 元素
   逐条比对留痕（`manual_only` = 手工页有、模型未抽出，必须逐条可见；无手工参照的课程写 `[]`）。

产物字节确定：`serialize()` 用 `ensure_ascii=False, indent=2` + 末尾换行，字段顺序固定，时间戳只到日期
（`generated_at`），同一输入两次序列化字节一致（与 `evidence.py` 同约定）。
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from lib.course_pipeline.evidence import evidence_path

SCHEMA_VERSION = 1
MODEL_VERSION = "v1"
COURSES_DIR = Path("sources") / "jiangsu" / "courses"
COURSE_PAGES_DIR = Path("content") / "jiangsu" / "courses"
MODEL_FILENAME = "knowledge-model.json"

TOC_MARKER = "大纲目录"
SAMPLE_PAPER_HEADING = "参考样卷"
FOCUS_MARKER = "本章重点"
MANUAL_TREE_HEADING = "## 章节知识树"
MANUAL_REFERENCE_ROW = "章节知识树"
MANUAL_ELEMENT_PREFIX = "#### "

CHAPTER_RE = re.compile(r"^(导论|第[一二三四五六七八九十]+章)(?:\s+(.+))?$")
SECTION_RE = re.compile(r"^(\d+)\.(.*)$")
REQUIREMENT_RE = re.compile(r"^(识记|领会|应用)：(.*)$")
TOP_HEADING_RE = re.compile(r"^[一二三四五六七八九十]+、")
PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")
QUESTION_TYPE_RE = re.compile(r"主要题型一般有(.+?)等题型")
MANUAL_ELEMENT_RE = re.compile(r"^(\d+)\.(\d+)\s+(.*)$")
MANUAL_MARKER_SUFFIX_RE = re.compile(r"\s*—\s*[🟢🟡🔴\s]+$")
MANUAL_INDEX_RE = re.compile(r"^\d+\.\d+\s+")
# 部次标签（Ⅰ–Ⅳ）：末章切片不得越过 `Ⅳ 关于大纲的说明与考核实施要求`，否则部次标签 / 附录 / 样卷会混进本章重点
PART_LABEL_RE = re.compile(r"^[ⅠⅡⅢⅣ]\s*\S")

MAX_QUOTE_CHARS = 60
SENTENCE_END = ("。", "！", "？")
CLAUSE_END = "，、：,;"
QUOTE_STYLE = str.maketrans({"「": "“", "」": "”", "『": "‘", "』": "’"})
DENOMINATOR_RULE_TEMPLATE = "考纲「{heading}」中带编号的节数"
MANUAL_MARKERS = {"🟢": "识记", "🟡": "领会", "🔴": "应用"}
REQUIREMENT_ORDER = ("识记", "领会", "应用")


def _physical_lines(path: Path) -> list[str]:
    """物理行（1-based 行号 = `sed -n '<n>p'` 口径；`\\x0c` 计入所在行）。"""
    return path.read_text(encoding="utf-8").split("\n")


def _fold(text: str) -> str:
    """折行 / 分页符归一：`\\x0c` 与连续空白折叠为单个半角空格（列位不受版式影响）。"""
    return re.sub(r"\s+", " ", text.replace("\x0c", " ")).strip()


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _slug(ordinal: int) -> str:
    return "intro" if ordinal == 0 else f"ch{ordinal:02d}"


def _chapter_index(title: str) -> str:
    return title.split(" ", 1)[0]


# ---- 章目切片 ------------------------------------------------------------------

def _toc_chapters(lines: list[str]) -> tuple[int, list[str]]:
    """`大纲目录` 切片 → (切片结束下标, 章标题列表)。Ⅰ–Ⅳ / 附录 / 大纲后记 都不算章。"""
    start = next((index for index, line in enumerate(lines) if _fold(line) == TOC_MARKER), None)
    if start is None:
        raise ValueError(f"考纲缺少「{TOC_MARKER}」切片，无法确定章目")
    end = len(lines)
    titles: list[str] = []
    for index in range(start + 1, len(lines)):
        text = _fold(lines[index])
        if not text or PAGE_NUMBER_RE.fullmatch(text):
            continue
        if CHAPTER_RE.match(text):
            titles.append(text)
            continue
        if titles:
            end = index
            break
    if not titles:
        raise ValueError(f"「{TOC_MARKER}」切片内没有章标题行")
    return end, titles


def _body_slices(lines: list[str], titles: list[str], start: int) -> list[list[tuple[int, str]]]:
    """章正文切片：章首 = 章标题在目录切片之后的**首次**出现；章末 = 下一个章首 / 下一个部次标签。"""
    anchors: list[int | None] = []
    cursor = start
    for title in titles:
        found = next((index for index in range(cursor, len(lines)) if _fold(lines[index]) == title), None)
        anchors.append(found)
        if found is not None:
            cursor = found + 1

    slices: list[list[tuple[int, str]]] = []
    for position, anchor in enumerate(anchors):
        if anchor is None:
            slices.append([])
            continue
        end = next((item for item in anchors[position + 1:] if item is not None), len(lines))
        part_end = next(
            (index for index in range(anchor, end) if PART_LABEL_RE.match(_fold(lines[index]))),
            None,
        )
        if part_end is not None:
            end = part_end
        slices.append([(index + 1, lines[index]) for index in range(anchor, end)])
    return slices


# ---- 折行 / 页码归一化 ---------------------------------------------------------

def _logical_lines(raw_lines: list[tuple[int, str]]) -> list[dict]:
    """物理行 → 逻辑行：丢弃页码与空行，折行续行并入上一条逻辑行。"""
    logical: list[dict] = []
    for number, raw in raw_lines:
        text = _fold(raw)
        if not text or PAGE_NUMBER_RE.fullmatch(text):
            continue
        if TOP_HEADING_RE.match(text):
            kind = "heading"
        elif SECTION_RE.match(text):
            kind = "section"
        elif REQUIREMENT_RE.match(text):
            kind = "requirement"
        else:
            kind = "passage"
        previous = logical[-1] if logical else None
        joins = (
            previous is not None
            and kind == "passage"
            and previous["kind"] not in ("heading", "section")
            and not previous["text"].endswith(SENTENCE_END)
        )
        if joins:
            previous["text"] += text
            continue
        logical.append({"line": number, "text": text, "kind": kind})
    return logical


def _requirement_block(logical: list[dict], heading: str) -> list[dict] | None:
    """考核要求小节正文：小节标题之后、下一个顶层小节标题（如 `四、本章重点`）之前。"""
    for index, item in enumerate(logical):
        if item["text"] != heading:
            continue
        end = index + 1
        while end < len(logical) and not TOP_HEADING_RE.match(logical[end]["text"]):
            end += 1
        return logical[index + 1:end]
    return None


def _phrases(text: str) -> list[str]:
    """`；` 分句 → 短语（去首尾空白与句末句号；空片段丢弃）。"""
    phrases = []
    for part in text.split("；"):
        phrase = _fold(part).rstrip("。").strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def _quote(text: str) -> str:
    """`quote` ≤ 60 字符：超长时取最后一个分句边界内的**逐字**前缀（GC4）。"""
    if len(text) <= MAX_QUOTE_CHARS:
        return text
    cut = max((index for index, char in enumerate(text[:MAX_QUOTE_CHARS]) if char in CLAUSE_END), default=-1)
    if cut <= 0:
        return text[:MAX_QUOTE_CHARS]
    return text[:cut].rstrip(CLAUSE_END)


def _point(code: str, slug: str, section_index: str, seq: int, requirement: str | None, text: str,
           line: int) -> dict:
    return {
        "id": f"{code}-{slug}-s{section_index}-p{seq}",
        "title": text,
        "requirement": requirement,
        "quote": _quote(text),
        "locator": f"L{line}",
    }


def _parse_requirement_block(block: list[dict], code: str, slug: str) -> tuple[list[dict], list[dict]]:
    """考核要求小节 → (`sections[]`, `unmodeled[]`)。"""
    sections: list[dict] = []
    unmodeled: list[dict] = []
    current: dict | None = None
    prefixed = False
    for item in block:
        text = item["text"]
        section = SECTION_RE.match(text)
        if section:
            current = {"index": section.group(1), "title": section.group(2).strip(), "points": []}
            sections.append(current)
            prefixed = False
            continue
        requirement = REQUIREMENT_RE.match(text)
        if requirement is not None and current is not None:
            prefixed = True
            requirement_name, body = requirement.group(1), requirement.group(2)
        elif current is not None and not prefixed:
            requirement_name, body = None, text
        else:
            # `current is None`（本行不属于任何编号节，含 `识记：` / `领会：` / `应用：` 行本身）
            # 或该节已出现带前缀要求 → 未编号考核段落，只留痕、不生成 point、不编造 index（GC3）
            unmodeled.append({
                "locator": f"L{item['line']}",
                "title": text[:MAX_QUOTE_CHARS].rstrip("。").strip(),
                "reason": "unnumbered_section",
            })
            continue
        for phrase in _phrases(body):
            seq = len(current["points"]) + 1
            current["points"].append(
                _point(code, slug, current["index"], seq, requirement_name, phrase, item["line"])
            )
    return sections, unmodeled


def _chapter_focus(logical: list[dict]) -> list[dict]:
    """`四、本章重点` → `chapter_focus[]`（考纲未声明即空列表）。"""
    for index, item in enumerate(logical):
        if item["kind"] == "heading" and FOCUS_MARKER in item["text"]:
            focus = []
            for entry in logical[index + 1:]:
                if entry["kind"] == "heading":
                    break
                focus.extend({"text": phrase, "locator": f"L{entry['line']}"} for phrase in _phrases(entry["text"]))
            return focus
    return []


# ---- 题型 / 样卷锚点（B1 只登记锚点，不转载题文） -------------------------------

def _exam(lines: list[str], doc_id: str) -> dict:
    question_types: list[str] = []
    types_line: int | None = None
    sample_line: int | None = None
    for number, raw in enumerate(lines, start=1):
        text = _fold(raw)
        if types_line is None:
            match = QUESTION_TYPE_RE.search(text)
            if match:
                types_line = number
                question_types = [item.strip() for item in match.group(1).split("、") if item.strip()]
        if sample_line is None and text == SAMPLE_PAPER_HEADING:
            sample_line = number
    return {
        "question_types": question_types,
        "question_types_provenance": {"doc_id": doc_id, "locator": f"L{types_line}"} if types_line else None,
        # 考纲未声明的字段一律 null + named_gap（GC3）
        "duration_minutes": None,
        "duration_status": "named_gap",
        "sample_paper": {"doc_id": doc_id, "locator": f"L{sample_line}"} if sample_line else None,
    }


# ---- 手工知识树比对（AC5：逐条留痕） -------------------------------------------

def _manual_tree(path: Path, label: str) -> tuple[int | None, list[dict]]:
    """手工页 `## 章节知识树` → (自评行行号, `####` 元素列表)。元素为节级（识记/领会/应用三层合并）。"""
    lines = _physical_lines(path)
    start = next((index for index, line in enumerate(lines) if line.strip() == MANUAL_TREE_HEADING), None)
    if start is None:
        return None, []
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))

    elements: list[dict] = []
    for index in range(start + 1, end):
        line = lines[index].strip()
        if not line.startswith(MANUAL_ELEMENT_PREFIX):
            continue
        title = line[len(MANUAL_ELEMENT_PREFIX):].strip()
        match = MANUAL_ELEMENT_RE.match(title)
        if match is None:
            continue
        elements.append({
            "locator": f"{label}:{index + 1}",
            "title": title,
            "ordinal": int(match.group(1)),
            "section": match.group(2),
            "body": MANUAL_INDEX_RE.sub("", MANUAL_MARKER_SUFFIX_RE.sub("", title)).strip(),
            "markers": {name for mark, name in MANUAL_MARKERS.items() if mark in title},
        })

    reference_line = next(
        (
            index + 1
            for index, line in enumerate(lines)
            if line.startswith("|") and len(line.strip().strip("|").split("|")) >= 2
            and line.strip().strip("|").split("|")[1].strip() == MANUAL_REFERENCE_ROW
        ),
        None,
    )
    return reference_line or start + 1, elements


def _manual_reference(root: Path, code: str) -> tuple[dict | None, list[dict]]:
    path = root / COURSE_PAGES_DIR / code / "index.md"
    if not path.is_file():
        return None, []
    label = _rel(root, path)
    line, elements = _manual_tree(path, label)
    if not elements:
        return None, []
    return {"path": label, "locator": f"L{line}", "point_count": len(elements)}, elements


def _layers(points: list[dict]) -> str:
    counts = {name: 0 for name in REQUIREMENT_ORDER}
    unclassified = 0
    for point in points:
        if point["requirement"] in counts:
            counts[point["requirement"]] += 1
        else:
            unclassified += 1
    parts = [f"{name} {counts[name]}" for name in REQUIREMENT_ORDER if counts[name]]
    if unclassified:
        parts.append(f"未分级 {unclassified}")
    return "、".join(parts)


def _diff_vs_manual(elements: list[dict], chapters: list[dict]) -> list[dict]:
    """手工页节级元素 ↔ 模型节：**逐条**写台账（`matched` / `model_only` / `manual_only`）。"""
    diff: list[dict] = []
    matched_keys: set[tuple[int, str]] = set()
    for element in elements:
        ordinal, section_index = element["ordinal"], element["section"]
        chapter = chapters[ordinal] if 0 <= ordinal < len(chapters) else None
        section = None
        if chapter is not None:
            section = next((item for item in chapter["sections"] if item["index"] == section_index), None)
        points = section["points"] if section else []
        if not points:
            # 手工页有、模型未抽出：逐条留痕，禁止静默丢弃（T6 闸门据此失败关闭）
            diff.append({
                "manual_locator": element["locator"],
                "manual_title": element["title"],
                "model_point_id": None,
                "kind": "manual_only",
                "note": "手工页有该节，模型未抽出对应 point（考纲该节缺失或未编号）：named_gap",
            })
            continue
        matched_keys.add((ordinal, section_index))
        note = (
            "手工页把识记/领会/应用三层合并写在节标题行（🟢🟡🔴）；"
            f"模型同节拆为 {len(points)} 个 point（{_layers(points)}）"
        )
        if element["markers"] != {point["requirement"] for point in points}:
            manual_levels = "、".join(name for name in REQUIREMENT_ORDER if name in element["markers"])
            note += f"；手工页层级标记（{manual_levels}）与模型 requirement 集合不一致（人工复核项）"
        if element["body"] == section["title"]:
            pass
        elif element["body"].translate(QUOTE_STYLE) == section["title"].translate(QUOTE_STYLE):
            note += "；节标题与考纲仅引号样式不同（手工「」/ 考纲 “”）"
        else:
            note += f"；节标题与考纲不同：手工「{element['body']}」/ 考纲「{section['title']}」"
        diff.append({
            "manual_locator": element["locator"],
            "manual_title": element["title"],
            "model_point_id": points[0]["id"],
            "kind": "matched",
            "note": note,
        })

    for ordinal, chapter in enumerate(chapters):
        for section in chapter["sections"]:
            if not section["points"] or (ordinal, section["index"]) in matched_keys:
                continue
            diff.append({
                "manual_locator": None,
                "manual_title": None,
                "model_point_id": section["points"][0]["id"],
                "kind": "model_only",
                "note": f"模型抽出该节（{len(section['points'])} 个 point），手工页章知识树无对应元素",
            })
    return diff


# ---- 产物 ---------------------------------------------------------------------

def extract_knowledge_model(root: Path, evidence: dict) -> dict:
    """课码取证 → 知识模型（Data contracts 3）；放行等级非 `L1` 时显式失败（不编造章目）。"""
    code = evidence.get("course_code")
    syllabus = evidence.get("syllabus") or {}
    heading = syllabus.get("requirements_heading")
    if not code:
        raise ValueError("evidence 缺少 course_code")
    if syllabus.get("status") != "extracted" or not syllabus.get("path") or not heading:
        raise ValueError(f"考纲未抽取或未记录考核要求小节：{code} 不生成知识模型（放行等级非 L1）")

    lines = _physical_lines(root / syllabus["path"])
    toc_end, titles = _toc_chapters(lines)
    slices = _body_slices(lines, titles, toc_end)

    chapters = []
    for ordinal, title in enumerate(titles):
        slug = _slug(ordinal)
        logical = _logical_lines(slices[ordinal])
        block = _requirement_block(logical, heading)
        sections, unmodeled = _parse_requirement_block(block or [], code, slug)
        chapters.append({
            "ordinal": ordinal,
            "index": _chapter_index(title),
            "slug": slug,
            "title": title,
            "sections": sections,
            "chapter_focus": _chapter_focus(logical),
            "unmodeled": unmodeled,
        })

    official = sum(len(chapter["sections"]) for chapter in chapters)
    modeled = sum(1 for chapter in chapters for section in chapter["sections"] if section["points"])
    manual_reference, manual_elements = _manual_reference(root, code)
    return {
        "schema_version": SCHEMA_VERSION,
        "course_code": code,
        "model_version": MODEL_VERSION,
        "generated_at": date.today().isoformat(),
        "generator": {"kind": "deterministic", "model": None, "prompt_id": None, "prompt_version": None},
        "source": {"doc_id": syllabus["doc_id"], "path": syllabus["path"], "sha256": syllabus.get("sha256")},
        "chapters": chapters,
        "exam": _exam(lines, syllabus["doc_id"]),
        "coverage": {
            "official_point_count": official,
            "modeled_point_count": modeled,
            "ratio": round(modeled / official, 4) if official else 0.0,
            "denominator_rule": DENOMINATOR_RULE_TEMPLATE.format(heading=heading),
            "manual_reference": manual_reference,
            # 每次生成都写：无手工参照写 []；有手工参照则逐条留痕（无差异时全为 matched）
            "diff_vs_manual": _diff_vs_manual(manual_elements, chapters) if manual_reference else [],
        },
    }


def knowledge_model_path(root: Path, code: str) -> Path:
    return root / COURSES_DIR / code / MODEL_FILENAME


def build_knowledge_model(root: Path, code: str) -> dict:
    """读 `evidence.json` → 知识模型（放行判定由 `evidence.evaluate_eligibility()` 负责，本函数不重判）。"""
    evidence = json.loads(evidence_path(root, code).read_text(encoding="utf-8"))
    return extract_knowledge_model(root, evidence)


def serialize(doc: dict) -> str:
    """确定性 JSON 文本（幂等复跑依赖此点）。"""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def write_knowledge_model(root: Path, code: str) -> tuple[Path, dict]:
    doc = build_knowledge_model(root, code)
    path = knowledge_model_path(root, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize(doc), encoding="utf-8")
    return path, doc
