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
SECTION_MARKER = "课程内容与考核要求"
SAMPLE_PAPER_HEADING = "参考样卷"
FOCUS_MARKER = "本章重点"
MANUAL_TREE_HEADING = "## 章节知识树"
MANUAL_REFERENCE_ROW = "章节知识树"
MANUAL_ELEMENT_PREFIX = "#### "

# 章标题形态（B6 / KB-1）：章序标签 `导论` / `绪 论` 或 `第N章 …`（N 可用中文数字或阿拉伯数字；
# 抽取件里两种写法混用，见下）。`CHAPTER_RE` 额外捕获标题部分；`CHAPTER_TITLE_RE` 只判形态，
# 供闸门验证模型章标题。
#
# **章序标签内的空白必须容忍**（KB-1）：机器抽取件在数字两侧随机插空格 —— `00898` 实测
# `第1章   JSP 与 Web 技术概论`（L120）与 `第 10 章   Servlet 基础`（L475）同课并存。只认
# `第N章`（无空格）会把双位数的章整批漏掉，于是「漏章」在 `ordinal` 上看起来就像考纲真缺章。
#
# **数字形态**：`00898` / `02333` / `04747` / `04751` 四门考纲全部用**阿拉伯数字**（`第1章`），
# 而 `15040` / `15043` / `15044` 用中文数字（`第一章`）—— 两种都要认（`_chapter_number` 同步处理）。
#
# **分隔符**：`第N章` 的数字形态自证，标题前的分隔空格**可以缺失** —— `00898:523` 实测
# `第 11 章使用 Servlet 过滤器和监听器`（`章` 后直接跟标题，无空格）。若强制 `\s+`，该章会被漏掉，
# 1–16 变成 1–10、12–16，连续性守卫反过来把一门**完整**的考纲判成缺章。
# 反之 `导论` / `绪 论` 没有数字锚点，若也允许无分隔，正文句首的
# `绪论的核心是阐明马克思主义的产生…`（`15044:161` 实测）就会被误判成章标题 —— 故这两个标签
# 后面必须有空白或行尾。
CHAPTER_LABEL = r"(导论|绪\s*论)"
NUMBERED_CHAPTER_LABEL = r"第\s*(?:[一二三四五六七八九十]+|\d+)\s*章"
CHAPTER_TITLE_RE = re.compile(
    rf"^(?:{CHAPTER_LABEL}(?=\s|$)(?:\s+.+)?|{NUMBERED_CHAPTER_LABEL}(?:\s*.+)?)$"
)
CHAPTER_RE = re.compile(
    rf"^(?:{CHAPTER_LABEL}(?=\s|$)(?:\s+(.+))?|{NUMBERED_CHAPTER_LABEL}(?:\s*(.+))?)$"
)
# 章序标签前缀（`_chapter_index` 用）：只取标签段，不要求标签后面还有标题
CHAPTER_LABEL_PREFIX_RE = re.compile(rf"^(?:{CHAPTER_LABEL}|{NUMBERED_CHAPTER_LABEL})")
SECTION_RE = re.compile(r"^(\d+)\.(.*)$")
# 节标题的第二种版式（KB-4）：`（一）标题`。`00898` 的考核要求小节用它编号（实测 53 个节），
# 而 `15040` / `15043` / `15044` 用 `1.标题`（三课实测 0 个 `（N）` 行）—— 两种都要认，
# 否则 `00898` 一个节都切不出来（全章落进 `unmodeled[]`、`coverage.ratio` 退化成 0.0）。
PAREN_SECTION_RE = re.compile(r"^（([一二三四五六七八九十]+)）\s*(.*)$")
NOT_ASSESSED_MARKER = "不作考核要求"
# 抽取件里页码行会粘进考核要求小节（`00898` 实测 3 处），必须先剔除，否则会被当成考核段落
PAGE_MARKER_RE = re.compile(r"^第\s*\d+\s*页\s*共\s*\d+\s*页$")
REQUIREMENT_RE = re.compile(r"^(识记|领会|应用)：(.*)$")
TOP_HEADING_RE = re.compile(r"^[一二三四五六七八九十]+、")
PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")
# 题型声明行有两种版式（15040 `…等题型。` / 15043·15044 `…论述题等。各…`），词表按顿号切分后过滤
QUESTION_TYPE_RE = re.compile(r"主要题型一般有(.+?)等")
QUESTION_TYPE_SUFFIX_RE = re.compile(r"题型$")
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
DENOMINATOR_RULE_CHAPTER_TEMPLATE = "考纲「{heading}」中的章数（该考纲不分子节，章即考核单元）"
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


def _chinese_number(text: str) -> int | None:
    """中文数字 → 整数（`一` → 1 … `十` → 10 … `十七` → 17）；无法识别返回 `None`。"""
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + digits.get(text[1:], 0)
    if "十" in text:
        head, _, tail = text.partition("十")
        return digits.get(head, 0) * 10 + (digits.get(tail, 0) if tail else 0)
    return digits.get(text)


def _chapter_number(label: str) -> int | None:
    """`第N章` 的章号 → 整数（`第一章` / `第 1 章` → 1 … `第十七章` → 17）；非 `第N章` 返回 `None`。

    中文数字与阿拉伯数字两种形态都认（KB-1）：四门缺目录页的考纲（`00898` / `02333` / `04747` /
    `04751`）用阿拉伯数字，三门有目录页的用中文数字。章号两侧的空格一并容忍（`第 10 章`）。
    """
    match = re.fullmatch(r"第\s*([一二三四五六七八九十]+|\d+)\s*章", label)
    if match is None:
        return None
    text = match.group(1)
    return int(text) if text.isdigit() else _chinese_number(text)


def _slug_for(title: str) -> str:
    """章标题 → `slug`：**由章序标签推导**，不由列表位置推导（B6）。

    旧实现 `_slug(位置序号)` 把「没有导论的课程」的第一章标成 `intro`（`15043` 实测：`第一章` →
    `slug: intro`，`ordinal 0`），而 `09` 号章页文件名又跟着错位。按标签推导后 `intro` 只属于
    `导论` / `绪 论`，其余章一律 `ch<NN>`（NN = 实际章号）。
    """
    number = _chapter_number(_chapter_index(title))
    return "intro" if number is None else f"ch{number:02d}"


def _ordinal_for(title: str) -> int:
    """章标题 → `ordinal`：`导论` / `绪 论` = 0，`第N章` = N（plan § Data contracts 3）。

    由**标签**推导而不是列表位置，正是为了让「丢了一章」在 `ordinal` 上直接可见：`15044` 丢掉
    `绪 论` 后若按位置编号，`第一章` 会顶到 0 而没人看得出来。
    """
    number = _chapter_number(_chapter_index(title))
    return 0 if number is None else number


def _chapter_index(title: str) -> str:
    """章序标签（`导论` / `绪论` / `第一章` / `第 1 章`）：取标签段并折叠**内部**空白。

    考纲目录里 `绪 论` 带一个内部空格（`15044`），而 `syllabus.md` 的章序列写 `绪论` —— 标签必须折叠，
    `title` 才保留原文（Data contracts 3：`title` 逐字、`index` 是章序标签）。
    章号两侧的抽取件空格（`第 10 章`）同样折叠：`index` 恒为 `第10章`（KB-1）。
    """
    match = CHAPTER_LABEL_PREFIX_RE.match(title.strip())
    label = match.group(0) if match else title.split(" ", 1)[0]
    return re.sub(r"\s+", "", label)


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


def _section_chapters(lines: list[str]) -> tuple[int, list[str]]:
    """章目回退（KB-2）：从 `Ⅲ 课程内容与考核要求` 节推章目 → 同一返回契约 `(end_index, titles)`。

    **仅当 `_toc_chapters()` 抛 `ValueError` 时调用** —— 有 `大纲目录` 切片的课走原判据，本函数对其
    不可达（AC3 逐字节不变的结构保证）。

    四门 `L1` 课的考纲**天生没有目录页**（`00898` 第 14 行是页码、第 15 行即 `Ⅰ 课程性质与课程目标`），
    但正文里章标题齐全；`Ⅲ` 节是章正文的起点，故 `end_index` 取该节**起点**，使 `_body_slices` 从
    `Ⅲ` 起算（`_body_slices` 仍按「标题在切片后的首次出现」定位章首）。

    失败关闭（不允许无声产出空章目）：找不到 `Ⅲ` 节、或该节之后没有任何章标题 → `ValueError`。
    """
    start = next(
        (index for index, line in enumerate(lines) if SECTION_MARKER in _fold(line)),
        None,
    )
    if start is None:
        raise ValueError(f"考纲缺少「{TOC_MARKER}」切片，也缺少「{SECTION_MARKER}」节，无法确定章目")
    titles: list[str] = []
    for line in lines[start + 1:]:
        text = _fold(line)
        if text and CHAPTER_RE.match(text) and text not in titles:
            titles.append(text)
    if not titles:
        raise ValueError(f"「{SECTION_MARKER}」节之后没有章标题行，无法确定章目")
    return start, titles


def _chapter_titles(lines: list[str]) -> tuple[int, list[str]]:
    """章目判定：**先试 `大纲目录`，失败才回退** 到 `Ⅲ 课程内容与考核要求` 节（KB-2）。

    顺序即回归保证（AC3）：有目录页的课（`15040` / `15043` / `15044`）在原判据上就成功返回，
    回退分支对其**不可达**，故其产物逐字节不变。

    两种失败模式都走回退（缺 `大纲目录` 切片 / 切片内无章标题行）：两者都只是「目录页取不到章目」，
    此时从正文推是同一意图的恢复动作。回退自身失败关闭（找不到 `Ⅲ` 节或其后无章标题 → `ValueError`），
    所以「两边都取不到」时仍然 raise，绝不无声产出空章目。
    """
    try:
        return _toc_chapters(lines)
    except ValueError:
        return _section_chapters(lines)


def _missing_chapters(ordinals: list[int]) -> list[int]:
    """章序标签推出的 `ordinal` 序列 → 缺失章号（升序去重；`0` = 导论，不参与章号）。

    两种缺口都要报（KB-3）：**前部缺口**（首章不是 1，如 `第4章` 打头 → 缺 1–3）与
    **内部缺口**（相邻章号跳号 → 缺中间那些）。
    """
    numbers: set[int] = set()
    if ordinals[0] not in (0, 1):
        numbers.update(range(1, ordinals[0]))
    for left, right in zip(ordinals, ordinals[1:]):
        if right - left > 1:
            numbers.update(range(left + 1, right))
    return sorted(number for number in numbers if number > 0)


def _format_chapter_runs(numbers: list[int]) -> str:
    """章号 → 压缩表述：`[1, 2, 3, 6]` → `第1–3章、第6章`（连续段折叠成一个区间）。"""
    parts: list[str] = []
    start = previous = None
    for number in [*numbers, None]:
        if number is not None and start is None:
            start = previous = number
            continue
        if number is not None and number == previous + 1:
            previous = number
            continue
        if start is not None:
            parts.append(f"第{start}章" if start == previous else f"第{start}–{previous}章")
        start = previous = number
    return "、".join(parts)


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


def _section_label(text: str) -> tuple[str, str] | None:
    """节标题 → `(index, title)`；两种版式：`1.标题` 与 `（一）标题`（KB-4）。"""
    section = SECTION_RE.match(text)
    if section:
        return section.group(1), section.group(2).strip()
    paren = PAREN_SECTION_RE.match(text)
    if paren:
        number = _chinese_number(paren.group(1))
        return (str(number) if number else paren.group(1)), paren.group(2).strip()
    return None


def _parse_requirement_block(
    block: list[dict], code: str, slug: str, chapter_title: str
) -> tuple[list[dict], list[dict], bool]:
    """考核要求小节 → (`sections[]`, `unmodeled[]`, `chapter_level`)。

    **无节边界时整章即考核单元**（KB-4）：`02333` / `04747` / `04751` 的 `二、考核知识点与考核要求`
    直接列 `识记：` / `领会：` / `应用：`，没有任何节号 —— 此时该小节本身就是考核单元（`index` 取 `1`，
    `title` 取章标题），否则整章要求会全部落进 `unmodeled[]`、`coverage.ratio` 退化成 `0.0`。
    有节边界的课（`15040` / `15043` / `15044`）不受影响。

    **明确不考核的单元不进分母**：标题带 `（本节内容不作考核要求）` 的节（`00898` 实测 8 个）
    与带 `（本章内容不作考核要求）` 的章（`02333` 第 14 章）本身就没有考核要求，
    把它们算作「未抽出的节」会把「不考」误报成「抽取失败」；改为只留痕（`reason: not_assessed`）。
    """
    sections: list[dict] = []
    unmodeled: list[dict] = []
    numbered = any(_section_label(item["text"]) for item in block)
    chapter_level = not numbered
    current: dict | None = None
    skip_reason: str | None = None
    if chapter_level and NOT_ASSESSED_MARKER not in chapter_title:
        current = {"index": "1", "title": chapter_title, "points": []}
        sections.append(current)
    prefixed = False
    for item in block:
        text = item["text"]
        if PAGE_MARKER_RE.match(text):
            continue  # 页码行既不是考核内容，也不是缺口
        label = _section_label(text)
        if label is not None:
            index, title = label
            if NOT_ASSESSED_MARKER in title:
                current = None
                skip_reason = "not_assessed"
                unmodeled.append({
                    "locator": f"L{item['line']}",
                    "title": text[:MAX_QUOTE_CHARS].rstrip("。").strip(),
                    "reason": "not_assessed",
                })
                continue
            current = {"index": index, "title": title, "points": []}
            sections.append(current)
            prefixed = False
            skip_reason = None
            continue
        requirement = REQUIREMENT_RE.match(text)
        if requirement is not None and current is not None:
            prefixed = True
            requirement_name, body = requirement.group(1), requirement.group(2)
        elif current is not None and not prefixed:
            requirement_name, body = None, text
        else:
            # `current is None`（本行不属于任何考核单元 —— 含无考核单元的章、明确不考核的节，
            # 以及 `识记：` / `领会：` / `应用：` 行本身）或该单元已出现带前缀要求 → 未编号段落，
            # 只留痕、不生成 point、不编造 index（GC3）。留在「明确不考核」单元内的行沿用该原因，
            # 免得读者把「官方声明不考」误读成「抽取失败」。
            unmodeled.append({
                "locator": f"L{item['line']}",
                "title": text[:MAX_QUOTE_CHARS].rstrip("。").strip(),
                "reason": skip_reason or "unnumbered_section",
            })
            continue
        for phrase in _phrases(body):
            seq = len(current["points"]) + 1
            current["points"].append(
                _point(code, slug, current["index"], seq, requirement_name, phrase, item["line"])
            )
    return sections, unmodeled, chapter_level


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
    """题型 / 样卷锚点（B1 只登记锚点，不转载题文）。

    考纲未声明题型时**不得**留 `question_types: []` 而让下游 `generate` 在运行时抛错（B6 / QC3-005）：
    显式写 `question_types_status: "named_gap"` + `gap_impact` + `next_evidence`，让「该课没有题型依据」
    在产物与闸门里都可见。
    """
    question_types: list[str] = []
    types_line: int | None = None
    sample_line: int | None = None
    for number, raw in enumerate(lines, start=1):
        text = _fold(raw)
        if types_line is None:
            match = QUESTION_TYPE_RE.search(text)
            if match:
                types_line = number
                question_types = [
                    item.strip()
                    for item in match.group(1).split("、")
                    if item.strip() and not QUESTION_TYPE_SUFFIX_RE.search(item.strip())
                ]
        if sample_line is None and text == SAMPLE_PAPER_HEADING:
            sample_line = number
    exam = {
        "question_types": question_types,
        "question_types_provenance": {"doc_id": doc_id, "locator": f"L{types_line}"} if types_line else None,
        # 考纲未声明的字段一律 null + named_gap（GC3）
        "duration_minutes": None,
        "duration_status": "named_gap",
        "sample_paper": {"doc_id": doc_id, "locator": f"L{sample_line}"} if sample_line else None,
    }
    if not question_types:
        # 考纲未声明题型时不得留 `question_types: []` 让下游 `generate` 在运行时才抛错（B6 / QC3-005）：
        # 显式命名缺口，让「该课没有题型依据」在产物与 `evidence` 层闸门里都可见。
        exam["question_types_status"] = "named_gap"
        exam["question_types_gap_impact"] = "考纲未声明题型 → 无法按官方题型生成练习，AI 备考层的 drill 不得产出"
        exam["question_types_next_evidence"] = "官方考纲「考试命题的主要题型」段落（或等效的官方说明）"
    return exam


# ---- 手工知识树比对（AC5：逐条留痕） -------------------------------------------

def _manual_tree(path: Path, label: str) -> tuple[int | None, list[dict], list[str]]:
    """手工页 `## 章节知识树` → (自评行行号, `####` 元素列表, 无法解析的行)。

    返回第三项是为了让「台账被静默清空」不可能发生（C2-012）：旧实现跳过不匹配的 `####` 行、
    且在找不到 `## 章节知识树` 时返回空列表，于是 `diff_vs_manual` 变成 `[]`、`manual_only` 检查失去对象。
    调用方必须对「解析不了的行」与「找不到锚点」都失败关闭。

    **锚点缺失但编号元素仍在 → 直接失败关闭**（W3）：把标题改名为 `## 知识点总览` 而 61 条 `####` 元素
    原地不动，与「本课没有手工参照」在返回值上完全同形，于是 `manual_only` 对这份输入永远空转。
    「有锚点但无元素」仍是诚实的命名缺口（15043 / 15044 的真实形态），不在此列。
    """
    lines = _physical_lines(path)
    start = next((index for index, line in enumerate(lines) if line.strip() == MANUAL_TREE_HEADING), None)
    if start is None:
        orphaned = [
            index + 1
            for index, line in enumerate(lines)
            if line.strip().startswith(MANUAL_ELEMENT_PREFIX)
            and MANUAL_ELEMENT_RE.match(line.strip()[len(MANUAL_ELEMENT_PREFIX):])
        ]
        if orphaned:
            raise ValueError(
                f"{label}: 含 {len(orphaned)} 条编号 `####` 考点行（{orphaned[0]}–{orphaned[-1]}），"
                f"但没有手工知识树锚点 `{MANUAL_TREE_HEADING}`（标题被改名或删除？）"
                "（台账不得静默清空：锚点缺失 + 元素仍在 = 手工参照无法比对）"
            )
        return None, [], []

    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))

    elements: list[dict] = []
    unparsed: list[str] = []
    for index in range(start + 1, end):
        line = lines[index].strip()
        if not line.startswith(MANUAL_ELEMENT_PREFIX):
            continue
        title = line[len(MANUAL_ELEMENT_PREFIX):].strip()
        match = MANUAL_ELEMENT_RE.match(title)
        if match is None:
            unparsed.append(f"{label}:{index + 1}")
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
    return reference_line or start + 1, elements, unparsed


def _manual_reference(root: Path, code: str) -> tuple[dict | None, list[dict]]:
    """手工页 →（`manual_reference`, 元素列表）。三种输入各自失败关闭或如实留痕：

    - 锚点缺失 + 有编号 `####` 元素 → `ValueError`（W3：手工参照无法比对，台账不得静默清空）；
    - 锚点内部有无法解析的行 → `ValueError`（C2-012，带行号）；
    - 有锚点但无 `####` 元素 = 该页显式声明「章节知识树」为命名缺口（15043 / 15044 的真实形态），
      这不是解析失败，`manual_reference` 保持 `null`、`diff_vs_manual` 写 `[]` 是诚实结果；
    - 无手工页 → `(None, [])`。
    """
    path = root / COURSE_PAGES_DIR / code / "index.md"
    if not path.is_file():
        return None, []
    label = _rel(root, path)
    line, elements, unparsed = _manual_tree(path, label)
    if unparsed:
        raise ValueError(
            f"{code}: 手工页 {label} 的 `{MANUAL_TREE_HEADING}` 下有无法解析的考点行 {unparsed}"
            "（台账不得静默清空；编号须为 `N.N 标题` 或改用 manual: 块）"
        )
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
    toc_end, titles = _chapter_titles(lines)
    slices = _body_slices(lines, titles, toc_end)

    # 章身份由章序**标签**推导（B6）：`ordinal` 必须严格递增且步长恒为 1，且首章只能是 0（导论类）
    # 或 1（无导论课程）。任何缺口 = 有章被静默丢弃 —— 旧实现按列表位置编号，丢章后序号整体前移
    # 而无人可见（15044 的 `绪 论` 就是这样消失、且 `第一章` 顶到 `ordinal 0` / `slug intro` 的）。
    # 缺口**指名缺的章号**（KB-3）：读者侧缺口呈现直接复用这句话，不必再去解析裸序号列表。
    identities = [(_ordinal_for(title), _slug_for(title)) for title in titles]
    ordinals = [ordinal for ordinal, _ in identities]
    gaps = [right - left for left, right in zip(ordinals, ordinals[1:])]
    if ordinals[0] not in (0, 1) or any(gap != 1 for gap in gaps):
        missing = _missing_chapters(ordinals)
        detail = f"缺 {_format_chapter_runs(missing)}" if missing else "章序标签无法识别"
        raise ValueError(
            f"{code}: 考纲章目不连续（{detail}，章序标签推出的章号 {ordinals}）："
            f"{'、'.join(titles[:8])}…"
        )

    chapters = []
    chapter_level_model = False
    for position, title in enumerate(titles):
        ordinal, slug = identities[position]
        logical = _logical_lines(slices[position])
        block = _requirement_block(logical, heading)
        sections, unmodeled, chapter_level = _parse_requirement_block(block or [], code, slug, title)
        chapter_level_model = chapter_level_model or chapter_level
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
            "denominator_rule": (
                DENOMINATOR_RULE_CHAPTER_TEMPLATE.format(heading=heading)
                if chapter_level_model
                else DENOMINATOR_RULE_TEMPLATE.format(heading=heading)
            ),
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
