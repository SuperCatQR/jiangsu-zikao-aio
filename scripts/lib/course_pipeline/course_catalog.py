"""课程目录：课码 / 课名 / 学分 / 考试方式的单一真源。

来源优先级（逐专业取**实际命中**档位，写入 `majors[].course_table_source`）：

1. `content/jiangsu/majors/<slug>/index.md` 现行课程表（7 列 Markdown 表）
2. `content/jiangsu/majors/<slug>/sources/plan.raw.txt` 官方计划定宽表
3. `sources/jiangsu/processed/major-source/<NN>/document.extracted.md` 机器抽取件

**行覆盖（入场判据 + 形态）**：某行只要**行首**（序号单元格之后）出现**边界感知**的 5 位
课码 token 就是候选课程行——不要求整行匹配某一种形态；随后按结构读出行内**唯一**的考试方式
单元格，其左侧若以整数单元格收尾即为学分，余下为课名。必须覆盖的真实形态：

1. `课码 + 课名 + 学分 + 考试方式`
2. 同上但带尾随 `备注` 单元格（41 个专业页有此形态）
3. `课码 + 课名 + 考试方式`（毕业环节等来源确实未给学分的行 → `credits: null`，不猜）
4. 课名单元格为空、课名折到相邻行（`00899` + 下一行 `（实践）`、`12656` 上下两行
   `毛泽东思想…` / `理论体系概论`），按**紧邻上下两行同列片段**拼回
5. `课码 + 考试方式` 极简形态（`14875` / `14976`，学分单元格也折行 → `credits: null`）

非课程文本（`学分合计 73 学分`、表头、说明段、页码、6 位专业代码）不满足入场判据，不会
产出课程行；**行首有课码却读不出唯一考试方式**的候选行写进 `majors[].dropped_rows[]`
（`{locator, raw, reason}`），不静默丢弃。`majors[].parsed_rows` = 该专业来源区的解析行数，
与候选行数相等即覆盖完整。**`dropped_rows[]` 只覆盖 `course_table_source` 命中的那一档**
（不合并其它档位）：档位链以「产出候选行」（解析行**或**丢弃行）为命中判据，只有在本档位既无
解析行也无候选行时才回落——无候选即无可丢弃，因此回落不会丢行（T1 复审 G-001）。

**`locator` 约定**：`L<n>` 是 `Path.read_text(encoding="utf-8").split("\\n")` 口径的 1-based
**物理行号**（与 `sed -n '<n>p'` / `grep -n` 显示的行号一致）；PDF 分页产生的 `\\x0c` 落在
行内，计入其所在行。注意 `str.splitlines()` 会把 `\\x0c` 当换行、凭空多出行来，**不得**用它
算行号（T1 评审 F-002）。

同名课（如旧代码 `03708 中国近现代史纲要` 与现行代码 `15043 中国近现代史纲要`）
按**来源档位**定序：现行课程表来源的课优先于旧计划定宽表来源的课；档位仍相同才报
`ambiguous`，不猜测。

产物（`sources/jiangsu/catalog/{courses,majors}.json`）字节确定：`courses[]` 按 `code`
升序、`aliases[]` 去重排序、`majors[]` / `course_codes` 去重升序；`serialize()` 用
`ensure_ascii=False, indent=2` + 末尾换行。`majors[].code` 照录专业页 `专业代码` 字段
（格式对齐 `scripts/lib/content_gate.py:15` 的专业页契约），`majors[].slug` = 目录名。
`generated_at` 是构建日期，`check_catalog()` 只比对内容字节（沿用磁盘上的
`generated_at`），因此跨天 `--check` 不会误报。
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lib.mdutil import parse_meta_table

SCHEMA_VERSION = 1
EXAM_METHODS = ("笔试", "实践", "机考")
COURSE_TABLE_SOURCES = ("index.md", "plan.raw.txt", "major-source")
CATALOG_DIR = Path("sources") / "jiangsu" / "catalog"
CATALOG_FILES = ("courses.json", "majors.json")

# 候选课程行入场判据：行首（序号单元格之后）是**边界感知**的 5 位课码 token。
# `080901` / `X2080901` 的子串（`08090` / `20809`）与 6 位专业代码都不算课码。
_ROW_HEAD_RE = re.compile(r"^\s*(?:\d{1,3}\s+)?(\d{5})(?=\s|$)")
# 行内考试方式单元格：空白分隔的独立 token（课程名里的 `（实践）` 不算）
_METHOD_RE = re.compile(rf"(?:(?<=\s)|^)({'|'.join(EXAM_METHODS)})(?=\s|$)")
# 考试方式左侧的「课名 + 学分」：左侧以整数单元格收尾时该整数即学分
_NAME_CREDITS_RE = re.compile(r"^(?P<name>.*?)\s*(?P<credits>\d+)$")
# `index.md` 现行课程表行：`| 序号 | 课程代码 | 课程名称 | 学分 | 考试方式 | … |`
_TABLE_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(\d{5})\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*(笔试|实践|机考)\s*\|"
)
# 候选现行课程表行：列位不足时必须登记为丢弃行，不得静默跳过
_TABLE_CANDIDATE_RE = re.compile(r"^\|\s*\d+\s*\|\s*\d{5}\s*\|")
_SEQUENCE_RE = re.compile(r"^\s*\d+\s*$")
_CREDIT_TAIL_RE = re.compile(r"\s+(?:不计学分|不计|学分)$")
# 边界感知的 5 位课码（`080901` / `X2080901` 的子串 `08090` / `20809` 不算）：折行片段识别与课码查询复用
_CODE_TOKEN_RE = re.compile(r"(?<!\d)\d{5}(?!\d)")
_HALFWIDTH_PARENS = str.maketrans({"（": "(", "）": ")"})
_MAJOR_SOURCE_CODE_RE = r"专业代码[：:]\s*{}(?!\d)"
_UNKNOWN_PRIORITY = len(COURSE_TABLE_SOURCES) + 1
_DROPPED_NO_METHOD = "行内未找到唯一的考试方式单元格"


@dataclass(frozen=True)
class _Source:
    """某个专业页给出的某门课的一条来源记录。"""

    doc_id: str
    path: str
    locator: str
    priority: int
    code: str
    name: str | None
    credits: int | None
    exam_method: str
    major_code: str
    major_name: str | None
    major_level: str | None

    @property
    def line(self) -> int:
        return int(self.locator[1:])


def _fold_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def source_priority(path: str) -> int:
    """来源路径 → 档位（越小越权威）；未知来源排在最后。"""
    for priority, name in enumerate(COURSE_TABLE_SOURCES, start=1):
        if path.endswith(name) or f"/{name}/" in path:
            return priority
    return _UNKNOWN_PRIORITY


def name_key(text: str) -> str:
    """课名比较键：全/半角等价（NFKC）、空白折叠为单个空格、大小写归一。"""
    return _fold_space(unicodedata.normalize("NFKC", text)).casefold()


def aliases_for(name: str | None) -> list[str]:
    """课名别名：去空白版本 + 半角括号版本，去重排序（不含原名）。"""
    if not name:
        return []
    variants = {re.sub(r"\s+", "", name), name.translate(_HALFWIDTH_PARENS)}
    return sorted(variant for variant in variants if variant and variant != name)


def _row(code: str, name: str | None, credits: int | None, exam_method: str, locator: str) -> dict:
    return {
        "code": code,
        "name": name,
        "credits": credits,
        "exam_method": exam_method,
        "locator": locator,
    }


def _dropped(line: str, locator: str, reason: str) -> dict:
    return {"locator": locator, "raw": line.strip(), "reason": reason}


def _split_name_credits(left: str) -> tuple[str | None, int | None]:
    """考试方式单元格左侧内容 →（课名, 学分）；以整数单元格收尾时该整数是学分。"""
    matched = _NAME_CREDITS_RE.match(left)
    if matched is None:
        return _fold_space(left) or None, None
    return _fold_space(matched.group("name")) or None, int(matched.group("credits"))


def _parse_row_line(line: str) -> tuple[dict | None, str]:
    """单行 →（课程行不含 locator, 丢弃原因）；非候选行返回 `(None, "")`。"""
    head = _ROW_HEAD_RE.match(line)
    if head is None:
        return None, ""
    rest = line[head.end():]
    methods = list(_METHOD_RE.finditer(rest))
    if len(methods) != 1:
        return None, _DROPPED_NO_METHOD
    method = methods[0]
    name, credits = _split_name_credits(rest[: method.start()].strip())
    return _row(head.group(1), name, credits, method.group(1), ""), ""


def parse_plan_rows(path: Path) -> tuple[list[dict], list[dict]]:
    """解析官方计划定宽表 / 机器抽取件 →（课程行, 被丢弃的候选行）。

    行号与折行片段都按**物理行**（`split("\\n")`，`\\x0c` 计入所在行）计算，与 `sed -n '<n>p'`
    显示的行号一致。课名为空的行按紧邻上下两行的同列片段拼回。
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    rows: list[dict] = []
    dropped: list[dict] = []
    for index, line in enumerate(lines):
        row, reason = _parse_row_line(line)
        locator = f"L{index + 1}"
        if row is None:
            if reason:
                dropped.append(_dropped(line, locator, reason))
            continue
        if row["name"] is None:
            row["name"] = _wrapped_name(lines, index)
        row["locator"] = locator
        rows.append(row)
    return rows, dropped


def _table_rows(page_text: str) -> tuple[list[dict], list[dict]]:
    """现行课程表行（`| 序号 | 课程代码 | 课程名称 | 学分 | 考试方式 | … |`）→（课程行, 丢弃行）。"""
    rows: list[dict] = []
    dropped: list[dict] = []
    for index, line in enumerate(page_text.split("\n"), start=1):
        matched = _TABLE_ROW_RE.match(line)
        if matched is None:
            if _expected_table_row(line):
                dropped.append(_dropped(line, f"L{index}", "现行课程表行列位不足"))
            continue
        credits = matched.group(3).strip()
        rows.append(
            _row(
                matched.group(1),
                _fold_space(matched.group(2)) or None,
                int(credits) if credits.isdigit() else None,
                matched.group(4),
                f"L{index}",
            )
        )
    return rows, dropped


def _expected_table_row(line: str) -> bool:
    """候选现行课程表行：`| 序号 | 5 位课码 | …`（列位不足时须登记为丢弃行）。"""
    return _TABLE_CANDIDATE_RE.match(line) is not None


def _fragment(line: str) -> str:
    """折行名称片段：取名称列首段，丢掉行首序号与学分列碎片。"""
    stripped = line.strip()
    if not stripped or _CODE_TOKEN_RE.search(stripped):
        return ""
    cells = [cell for cell in re.split(r"\s{2,}", stripped) if cell]
    while cells and _SEQUENCE_RE.match(cells[0]):
        cells.pop(0)
    if not cells:
        return ""
    return _CREDIT_TAIL_RE.sub("", cells[0])


def _wrapped_name(lines: list[str], index: int) -> str | None:
    parts = []
    if index > 0:
        parts.append(_fragment(lines[index - 1]))
    if index + 1 < len(lines):
        parts.append(_fragment(lines[index + 1]))
    return _fold_space("".join(parts)) or None


def _major_source_doc(root: Path, code: str) -> Path | None:
    """第三档来源：正文声明该专业代码的机器抽取件。"""
    base = root / "sources" / "jiangsu" / "processed" / "major-source"
    if not base.is_dir():
        return None
    pattern = re.compile(_MAJOR_SOURCE_CODE_RE.format(re.escape(code)))
    for doc in sorted(base.glob("*/document.extracted.md")):
        if pattern.search(doc.read_text(encoding="utf-8")):
            return doc
    return None


def _major_sources(root: Path, major_dir: Path) -> tuple[list[_Source], dict]:
    """按优先级取该专业实际命中的来源，返回（来源记录, `majors.json` 行）。"""
    page = major_dir / "index.md"
    page_text = page.read_text(encoding="utf-8") if page.is_file() else ""
    meta = parse_meta_table(page_text) if page_text else {}
    code = (meta.get("专业代码") or "").strip() or major_dir.name.split("-", 1)[0]
    rel = major_dir.relative_to(root).as_posix()
    doc_id = f"major-plan:{code}"

    rows: list[dict] = []
    dropped: list[dict] = []
    path = f"{rel}/index.md"
    source = None
    # 档位命中判据 = 产出候选行（解析行**或**丢弃行）：只要本档位有候选行就被选中，回落只发生在本
    # 档位无候选行时——无候选即无可丢弃，回落不会丢掉上一档的 `dropped_rows`（T1 复审 G-001）。
    table_rows, table_dropped = _table_rows(page_text)
    if table_rows or table_dropped:
        rows, dropped, source = table_rows, table_dropped, "index.md"
    else:
        plan = major_dir / "sources" / "plan.raw.txt"
        plan_rows, plan_dropped = parse_plan_rows(plan) if plan.is_file() else ([], [])
        if plan_rows or plan_dropped:
            rows, dropped = plan_rows, plan_dropped
            path, source = f"{rel}/sources/plan.raw.txt", "plan.raw.txt"
        elif (extracted := _major_source_doc(root, code)) is not None:
            rows, dropped = parse_plan_rows(extracted)
            path, source = extracted.relative_to(root).as_posix(), "major-source"

    major = {
        "code": code,
        "slug": major_dir.name,
        "name": (meta.get("专业名称") or "").strip() or None,
        "level": (meta.get("层次") or "").strip() or None,
        "page": f"{rel}/index.md",
        "course_table_source": source,
        "parsed_rows": len(rows),
        "dropped_rows": dropped,
        "course_codes": sorted({row["code"] for row in rows}),
        "practice_codes": sorted({row["code"] for row in rows if row["exam_method"] == "实践"}),
    }
    sources = [
        _Source(
            doc_id=doc_id,
            path=path,
            locator=row["locator"],
            priority=source_priority(path),
            code=row["code"],
            name=row["name"],
            credits=row["credits"],
            exam_method=row["exam_method"],
            major_code=code,
            major_name=major["name"],
            major_level=major["level"],
        )
        for row in rows
    ]
    return sources, major


def _scan_majors(root: Path) -> tuple[list[_Source], list[dict]]:
    majors_root = root / "content" / "jiangsu" / "majors"
    sources: list[_Source] = []
    majors: list[dict] = []
    for major_dir in sorted(path for path in majors_root.iterdir() if path.is_dir()):
        major_sources, major = _major_sources(root, major_dir)
        sources.extend(major_sources)
        majors.append(major)
    return sources, sorted(majors, key=lambda major: major["code"])


def _ordered(records: list[_Source]) -> list[_Source]:
    return sorted(records, key=lambda record: (record.priority, record.path, record.line))


def _first_value(records: list[_Source], field: str):
    for record in records:
        value = getattr(record, field)
        if value is not None:
            return value
    return None


def _conflicts(records: list[_Source]) -> list[dict]:
    """两份来源名称 / 学分 / 考试方式不一致时逐字段登记两侧值，不自动取舍。"""
    conflicts = []
    for field in ("name", "credits", "exam_method"):
        values: list[dict] = []
        seen: set = set()
        for record in records:
            value = getattr(record, field)
            if value is None:
                continue
            key = name_key(value) if field == "name" else value
            if key in seen:
                continue
            seen.add(key)
            values.append({"value": value, "doc_id": record.doc_id, "locator": record.locator})
        if len(values) > 1:
            conflicts.append({"field": field, "values": values})
    return conflicts


def _course(code: str, records: list[_Source]) -> dict:
    ordered = _ordered(records)
    name = _first_value(ordered, "name")
    major_list = sorted({(record.major_code, record.major_name, record.major_level) for record in ordered})
    return {
        "code": code,
        "name": name,
        "aliases": aliases_for(name),
        "credits": _first_value(ordered, "credits"),
        "exam_method": _first_value(ordered, "exam_method"),
        "majors": [{"code": major_code, "name": major_name, "level": level} for major_code, major_name, level in major_list],
        "sources": [
            {"doc_id": record.doc_id, "path": record.path, "locator": record.locator}
            for record in ordered
        ],
        "conflicts": _conflicts(ordered),
    }


def build_catalog(root: Path) -> dict:
    """扫全部专业页 → `courses.json` 文档（Data contracts 1）。"""
    sources, _ = _scan_majors(root)
    grouped: dict[str, list[_Source]] = {}
    for record in sources:
        grouped.setdefault(record.code, []).append(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": date.today().isoformat(),
        "courses": [_course(code, grouped[code]) for code in sorted(grouped)],
    }


def build_majors(root: Path) -> dict:
    """扫全部专业页 → `majors.json` 文档（Data contracts 1b）。"""
    _, majors = _scan_majors(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": date.today().isoformat(),
        "majors": majors,
    }


def _course_priority(course: dict) -> int:
    """该课最高优先来源的档位（越小越权威）；无来源时最不优先。"""
    return min(
        (source_priority(source.get("path", "")) for source in course.get("sources") or []),
        default=_UNKNOWN_PRIORITY,
    )


def resolve_course(catalog: dict, query: str) -> dict:
    """课码 / 课名 / 别名 → 课程。

    同名课按来源档位定序（现行课程表 > 旧计划定宽表 > 机器抽取件）：档位最高的唯一一课
    直接命中；档位仍并列才返回 `ambiguous` + 全部并列候选，不猜测。
    """
    raw = (query or "").strip()
    courses = catalog.get("courses") or []
    if _CODE_TOKEN_RE.fullmatch(raw):
        for course in courses:
            if course["code"] == raw:
                return {"status": "resolved", "code": raw, "name": course["name"], "matched_by": "code"}
        return {"status": "not_found", "query": query}
    if not raw:
        return {"status": "not_found", "query": query}
    key = name_key(raw)
    matched: list[tuple[dict, str]] = []
    for course in courses:
        if course["name"] and name_key(course["name"]) == key:
            matched.append((course, "name"))
        elif any(name_key(alias) == key for alias in course.get("aliases") or []):
            matched.append((course, "alias"))
    if not matched:
        return {"status": "not_found", "query": query}
    if len(matched) > 1:
        best = min(_course_priority(course) for course, _ in matched)
        matched = [entry for entry in matched if _course_priority(entry[0]) == best]
    candidates = [
        {"code": course["code"], "name": course["name"], "matched_by": matched_by}
        for course, matched_by in sorted(matched, key=lambda entry: entry[0]["code"])
    ]
    if len(candidates) == 1:
        return {"status": "resolved", **candidates[0]}
    return {"status": "ambiguous", "candidates": candidates}


def serialize(doc: dict) -> str:
    """确定性 JSON 文本（`--check` 的字节比对依赖此点）。"""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def catalog_paths(root: Path) -> list[Path]:
    base = root / CATALOG_DIR
    return [base / name for name in CATALOG_FILES]


def _documents(root: Path) -> list[dict]:
    return [build_catalog(root), build_majors(root)]


def write_catalog(root: Path) -> tuple[list[Path], list[dict]]:
    """写 `courses.json` + `majors.json`，返回（写入路径, 对应文档）。"""
    paths = catalog_paths(root)
    documents = _documents(root)
    for path, doc in zip(paths, documents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialize(doc), encoding="utf-8")
    return paths, documents


def check_catalog(root: Path) -> list[str]:
    """重新生成并与磁盘逐字节比对（`generated_at` 沿用磁盘值）；返回差异描述。"""
    problems = []
    for path, doc in zip(catalog_paths(root), _documents(root)):
        if not path.is_file():
            problems.append(f"missing: {path}")
            continue
        on_disk = path.read_text(encoding="utf-8")
        expected = dict(doc, generated_at=json.loads(on_disk).get("generated_at"))
        if serialize(expected) != on_disk:
            problems.append(f"stale: {path}")
    return problems
