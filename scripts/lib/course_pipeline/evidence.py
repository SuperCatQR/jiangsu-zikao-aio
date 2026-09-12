"""取证与放行判定：`sources/jiangsu/courses/<code>/evidence.json`（Data contracts 2）。

**唯一放行判定**（spec `D8` / GC2）：`evaluate_eligibility()` 是唯一判定点，`build_evidence()` 在末尾
调用它写入 `eligibility`；渲染层与闸门层只读该字段，不得各自重判。

三块证据，全部来自**仓内**抽取件与**只读**基线（离线优先，GC14 / GC15）：

1. `syllabus` —— `sources/jiangsu/processed/syllabus/<code>-*/document.extracted.md` 存在**且**能定位
   「考核知识点与考核要求」小节 → `extracted`（写 `path` + `sha256` + 小节标题原文），否则 `missing`。
   小节的章节序号在不同批次的高纲里不一致：`15040` / `15043` / `15044` 用 `三、考核知识点与考核要求`，
   `00898` / `02333` / `04747` / `04751` 用 `二、考核知识点与考核要求`（同一小节，逐行核对四份抽取件）。
   因此判据取小节名的稳定部分（`^[一二三四五六七八九十]+、考核知识点与考核要求$`），并把命中的标题
   **逐字**记入 `requirements_heading`，让口径可复核；「说明书里提到该小节名」不算定位到小节。
2. `textbook_plan` —— **只在教材计划区内**匹配。区起点 = 首个含表头 `教材代号` 的行（表头在每页
   重复出现，因此区内所有分页段一并算），区终点 = 文档末尾；区**之前**是通知正文与附件 1/2 的
   考试日程区，那里的课码出现**一律不算**教材行。区内按行内空白 token 匹配教材代号
   `^<code>\\d{1,3}$`（后缀不限于 `0`/`1`：实测 `130031` / `000151` / `131401` / `131411` …），
   命中行 ±2 行的窗口内必须同时能读到该课码（多行版式的教材行课码会独占一行）与至少一个来源标记
   （`出版社` / `大学出版社` / `高纲` / `考试指导委员会`）；四份文档取**并集**（同一课不必在每份都有行）。
3. `facts` —— 课名 / 学分 / 考试方式取自目录 SSOT `sources/jiangsu/catalog/courses.json`（spec `D10`），
   溯到该课最高优先来源的 `path` + `locator`。`provenance.kind` 必须与所引证据同类，因此这里恒为
   `official_major_plan`（专业计划表课程行）：基线里覆盖该课码的官方 URL 属于**另一份文档**
   （考纲页 / 政策文件页），记在课程级 `course_url`（基线只读，GC14），不进 `provenance` ——
   否则同一对象会拿 `official_major_plan` 去标注一个考纲 URL（Data contracts 2 的 `kind` 语义）。
   取不到值的字段一律 `named_gap` + `gap_impact` + `next_evidence`，不猜。

行号约定与 Task 1 一致：`L<n>` 是 `Path.read_text(encoding="utf-8").split("\\n")` 口径的 1-based
**物理行号**（与 `sed -n '<n>p'` 一致，`\\x0c` 计入所在行）；**不得**用 `str.splitlines()` 算行号。

产物字节确定：`serialize()` 用 `ensure_ascii=False, indent=2` + 末尾换行，字段顺序固定，集合一律
`sorted()`，时间戳只到日期（`generated_at` / 不写抓取时刻），因此同一输入两次序列化字节一致。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from lib.course_pipeline.official_source import is_official_url

SCHEMA_VERSION = 1
CATALOG_PATH = Path("sources") / "jiangsu" / "catalog" / "courses.json"
BASELINE_PATH = Path("ops") / "jiangsu" / "source-links.baseline.json"
SYLLABUS_DIR = Path("sources") / "jiangsu" / "processed" / "syllabus"
TEXTBOOK_DIR = Path("sources") / "jiangsu" / "processed" / "textbooks"
COURSES_DIR = Path("sources") / "jiangsu" / "courses"
COURSE_PAGES_DIR = Path("content") / "jiangsu" / "courses"

TEXTBOOK_HEADER = "教材代号"
# 教材计划区内的分页表头重复出现：窗口 / 行文本里剔除表头行，避免表头里的 `出版社` 充当旁证
REQUIREMENTS_HEADING_RE = re.compile(r"^[一二三四五六七八九十]+、考核知识点与考核要求$")
SAMPLE_PAPER_MARKER = "参考样卷"
CORROBORATION_MARKERS = ("出版社", "大学出版社", "高纲", "考试指导委员会")
ROW_WINDOW_RADIUS = 2
ROW_MAX_CHARS = 200
CODE_DIR_RE = re.compile(r"\d{5}")

FACT_FIELDS = ("name", "credits", "exam_method")
# 命名缺口文案：缺口项 →（对读者的影响, 下一份需要的证据）
FACT_GAPS = {
    "name": ("读者无法确认该课码对应的官方课程名", "官方专业计划表中的课程行"),
    "credits": ("读者无法判断该课的学分权重与备考投入", "官方专业计划表中的课程行"),
    "exam_method": ("读者无法判断该课是笔试、机考还是实践考核", "官方专业计划表中的课程行"),
}
SYLLABUS_GAP = (
    "缺官方考纲 → 无章目 / 考核要求 / 题型依据，AI 备考层一律不生成（放行等级非 L1）",
    "jseea.cn 公开的该课自学考试大纲原件（入库并抽取为 document.extracted.md）",
)
TEXTBOOK_PLAN_GAP = (
    "缺官方教材计划行 → 读者无法核对指定教材，知识点无法与教材章节对齐",
    "官方《开考课程教材计划》抽取件中出现该课码的教材代号行（`<code>\\d{1,3}`）",
)


def _physical_lines(path: Path) -> list[str]:
    """物理行（`sed -n '<n>p'` 口径的 1-based 行号，`\\x0c` 计入所在行）。"""
    return path.read_text(encoding="utf-8").split("\n")


def _fold(text: str) -> str:
    """折行 / 分页符归一：`\\x0c` 与连续空白折叠为单个半角空格。"""
    return re.sub(r"\s+", " ", text.replace("\x0c", " ")).strip()


def _truncate_row(text: str) -> tuple[str, bool]:
    if len(text) <= ROW_MAX_CHARS:
        return text, False
    return text[:ROW_MAX_CHARS], True


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# ---- 放行判定（唯一） --------------------------------------------------------

def evaluate_eligibility(evidence: dict) -> dict:
    """`syllabus.status == "extracted"` 且 `textbook_plan.status == "matched"` → `L1`，否则 `blocked`。

    `reasons` 是固定的有序列表（`syllabus:*` → `textbook_plan:*`），`blocked` 时至少一条 `*:missing`。
    """
    syllabus_ok = (evidence.get("syllabus") or {}).get("status") == "extracted"
    textbook_ok = (evidence.get("textbook_plan") or {}).get("status") == "matched"
    return {
        "level": "L1" if syllabus_ok and textbook_ok else "blocked",
        "reasons": [
            "syllabus:extracted" if syllabus_ok else "syllabus:missing",
            "textbook_plan:matched" if textbook_ok else "textbook_plan:missing",
        ],
    }


# ---- 考纲证据 ----------------------------------------------------------------

def _syllabus_document(root: Path, code: str) -> Path | None:
    base = root / SYLLABUS_DIR
    if not base.is_dir():
        return None
    matches = sorted(base.glob(f"{code}-*/document.extracted.md"))
    return matches[0] if matches else None


def _requirements_heading(lines: list[str]) -> tuple[int, str] | None:
    """定位「考核知识点与考核要求」小节标题行（1-based 行号 + 标题原文）。"""
    for number, line in enumerate(lines, start=1):
        text = _fold(line)
        if REQUIREMENTS_HEADING_RE.match(text):
            return number, text
    return None


def _syllabus_evidence(root: Path, code: str) -> dict:
    document = _syllabus_document(root, code)
    payload = {
        "status": "missing",
        "doc_id": f"syllabus:{code}",
        "path": None,
        "sha256": None,
        # 抽取件在库但定位不到考核要求小节时，仍记下候选文件，避免静默丢失「已入库」这一事实
        "candidate_path": _rel(root, document) if document is not None else None,
        "has_assessment_requirements": False,
        "has_sample_paper": False,
        "requirements_heading": None,
        "gap_impact": SYLLABUS_GAP[0],
        "next_evidence": SYLLABUS_GAP[1],
    }
    if document is None:
        return payload

    lines = _physical_lines(document)
    heading = _requirements_heading(lines)
    payload["has_sample_paper"] = any(SAMPLE_PAPER_MARKER in line for line in lines)
    if heading is None:
        return payload

    number, title = heading
    return {
        "status": "extracted",
        "doc_id": f"syllabus:{code}",
        "path": _rel(root, document),
        "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
        "has_assessment_requirements": True,
        "has_sample_paper": payload["has_sample_paper"],
        "requirements_heading": title,
        "locator": f"L{number}",
    }


# ---- 教材计划证据 ------------------------------------------------------------

def _textbook_documents(root: Path) -> list[Path]:
    base = root / TEXTBOOK_DIR
    if not base.is_dir():
        return []
    return sorted(base.glob("*/document.raw.txt"))


def _textbook_doc_id(path: Path) -> str:
    name = path.parent.name
    return f"schedule-textbooks:{name.removeprefix('jiangsu-').removesuffix('-schedule-textbooks')}"


def _region_start(lines: list[str]) -> int | None:
    """教材计划区起点 = 首个含表头 `教材代号` 的行（0-based）；找不到即整份文档没有该区。"""
    return next((index for index, line in enumerate(lines) if TEXTBOOK_HEADER in line), None)


def _match_document(root: Path, path: Path, code: str) -> list[dict]:
    """单份文档内的教材行命中（已做跨行归一化 + 旁证 + 课码同窗校验）。"""
    lines = _physical_lines(path)
    start = _region_start(lines)
    if start is None:
        return []

    token_re = re.compile(rf"^{re.escape(code)}\d{{1,3}}$")
    code_re = re.compile(rf"(?<!\d){re.escape(code)}(?!\d)")
    hits = []
    for index in range(start, len(lines)):
        if not any(token_re.match(token) for token in lines[index].split()):
            continue
        low = max(start, index - ROW_WINDOW_RADIUS)
        high = min(len(lines), index + ROW_WINDOW_RADIUS + 1)
        window = [line for number, line in enumerate(lines[low:high], start=low) if TEXTBOOK_HEADER not in line]
        text = _fold(" ".join(window))
        # 多行版式：课码可能独占一行，必须在同一窗口内读到该课码
        if not code_re.search(text):
            continue
        if not any(marker in text for marker in CORROBORATION_MARKERS):
            continue
        row, truncated = _truncate_row(text)
        hits.append(
            {
                "doc_id": _textbook_doc_id(path),
                "path": _rel(root, path),
                "locator": f"L{index + 1}",
                "row": row,
                "row_truncated": truncated,
            }
        )
    return hits


def _textbook_plan_evidence(root: Path, code: str) -> dict:
    matches: list[dict] = []
    for document in _textbook_documents(root):
        matches.extend(_match_document(root, document, code))
    if not matches:
        return {
            "status": "missing",
            "doc_id": None,
            "path": None,
            "locator": None,
            "row": None,
            "matches": [],
            "gap_impact": TEXTBOOK_PLAN_GAP[0],
            "next_evidence": TEXTBOOK_PLAN_GAP[1],
        }

    matches.sort(key=lambda match: (match["doc_id"], int(match["locator"][1:])))
    # 规范行 = **最新**一份命中文档的行（`doc_id` 里的日期标签按字典序即时间序）
    canonical_doc = max(match["doc_id"] for match in matches)
    canonical = [match for match in matches if match["doc_id"] == canonical_doc]
    # 发布行 = 规范文档命中窗口的拼接；`row_truncated` 只描述这一行是否**真的**被截断（Data contracts 2）：
    # ① 任一规范窗口自身超长被截断（`matches[].row` 已按 200 字符截断，再拼一遍不会超长），或 ② 拼接后超长。
    # 非规范文档的截断状态留在各自 `matches[].row_truncated`，不 OR 进来 —— 旧实现 OR 全部匹配，
    # 于是 00023（`len(row)=162`）/ 13015（`len(row)=177`）也报 `row_truncated=true`，与发布行和 `matches[]` 都矛盾。
    row_text = " / ".join(match["row"] for match in canonical)
    return {
        "status": "matched",
        "doc_id": canonical_doc,
        "path": canonical[0]["path"],
        "locator": ",".join(match["locator"] for match in canonical),
        "row": row_text[:ROW_MAX_CHARS],
        "row_truncated": any(match["row_truncated"] for match in canonical) or len(row_text) > ROW_MAX_CHARS,
        "matches": matches,
    }


# ---- 官方事实（目录 SSOT + 只读基线 URL） ------------------------------------

def _catalog_course(root: Path, code: str) -> dict | None:
    path = root / CATALOG_PATH
    if not path.is_file():
        return None
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return next((course for course in catalog.get("courses") or [] if course.get("code") == code), None)


def _official_urls(root: Path) -> dict[str, str]:
    """课程级官方 URL：基线（**只读**）里 `authoritative` 且域名为 `jseea.cn` 的 URL → 课码（同课多 URL 取字典序最小）。

    写进 `course_url`，不写 `facts[*].provenance.url`（那份证据是专业计划表行，见 `_facts`）。
    """
    path = root / BASELINE_PATH
    if not path.is_file():
        return {}
    baseline = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for url, item in sorted((baseline.get("urls") or {}).items()):
        if not item.get("authoritative") or not is_official_url(url):
            continue
        for code in item.get("course_codes") or []:
            mapping.setdefault(code, url)
    return mapping


def _supporting_locator(root: Path, source: dict, value: Any) -> str:
    """`provenance.locator`：引用**能支撑 `value` 的那一行**（C2-015）。

    专业计划表的课名会折到课码行的下一行（实测 `10993` / `12656`），此时课码行只含课码 / 学分 /
    考试方式 —— 引它作 `name` 的凭据是错的。策略：以 `sources[].locator` 为中心在 ±2 行窗口内
    找首个包含该值的行；窗口内找不到就保持原 locator（值可能来自折叠空白，例如全角括号）。
    """
    path = root / source["path"]
    if not path.is_file() or not isinstance(value, str):
        return source["locator"]
    lines = _physical_lines(path)
    center = int(source["locator"][1:])
    order = sorted(range(max(1, center - ROW_WINDOW_RADIUS), min(len(lines), center + ROW_WINDOW_RADIUS) + 1),
                   key=lambda number: (abs(number - center), number))
    for number in order:
        if value in _fold(lines[number - 1]):
            return f"L{number}"
    return source["locator"]


def _facts(root: Path, code: str) -> dict:
    course = _catalog_course(root, code)
    sources = (course or {}).get("sources") or []
    best = sources[0] if sources else None
    facts = {}
    for field in FACT_FIELDS:
        value = (course or {}).get(field)
        gap_impact, next_evidence = FACT_GAPS[field]
        if value in (None, "") or best is None:
            facts[field] = {
                "value": None,
                "status": "named_gap",
                "gap_impact": gap_impact,
                "next_evidence": next_evidence,
            }
            continue
        facts[field] = {
            "value": value,
            "status": "verified",
            "provenance": {
                "doc_id": best["doc_id"],
                "kind": "official_major_plan",
                # 值出自专业计划表课程行（`path` + `locator`）；基线的官方 URL 是另一份文档，
                # 记在课程级 `course_url`，因此这里恒为 `null`（Data contracts 2：`url|path` 只需其一）
                "url": None,
                "path": best["path"],
                "locator": _supporting_locator(root, best, value),
            },
        }
    return facts


# ---- 产物 --------------------------------------------------------------------

def course_codes(root: Path) -> list[str]:
    """现有课程页课码（`content/jiangsu/courses/<5 位课码>/`），`evidence --all` 的输入口径。"""
    base = root / COURSE_PAGES_DIR
    if not base.is_dir():
        return []
    return sorted(path.name for path in base.iterdir() if path.is_dir() and CODE_DIR_RE.fullmatch(path.name))


def validate_code(code: str) -> str:
    """课码必须是 5 位数字（C2-006）。

    课码会直接参与路径拼接（`root / COURSES_DIR / code / …`）。旧实现只由 CLI 的 `resolve` 阶段
    间接约束，于是 `build <crafted-query> --stages evidence` 可写出仓根之外（实测 exit 0）。
    校验放在**写入者**这一层：所有调用点自动受保护，不依赖调用方记得先校验，也不依赖阶段开关。
    """
    if not isinstance(code, str) or not CODE_DIR_RE.fullmatch(code):
        raise ValueError(f"课码必须是 5 位数字：{code!r}")
    return code


def build_evidence(root: Path, code: str, *, offline: bool = True) -> dict:
    """课码 → 取证文档（Data contracts 2）；`eligibility` 由 `evaluate_eligibility()` 写入。

    `offline=True`（默认）只读仓内抽取件与只读基线。B1 不落盘官方快照（GC15），因此 `offline=False`
    显式失败而不是静默联网入库；联网取证在 B2 首次真实取证时接入（spec `D7` / § Roadmap B2 门槛③）。
    """
    validate_code(code)
    if not offline:
        raise RuntimeError("offline: build_evidence 只支持离线取证（B1 不落盘官方快照，见 GC15）")

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "course_code": code,
        "generated_at": date.today().isoformat(),
        # 课程级官方页面（只读基线；该课码在基线里没有权威官方 URL 时为 `null`）。不是任何字段的
        # `provenance`：事实值出自专业计划表行，混在 provenance 里会让 `kind` 与所引证据不符（F-203）。
        "course_url": _official_urls(root).get(code),
        "facts": _facts(root, code),
        "syllabus": _syllabus_evidence(root, code),
        "textbook_plan": _textbook_plan_evidence(root, code),
        "source_snapshot": None,
    }
    evidence["eligibility"] = evaluate_eligibility(evidence)
    return evidence


def serialize(doc: dict) -> str:
    """确定性 JSON 文本（`--check` / 幂等复跑依赖此点）。"""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def evidence_path(root: Path, code: str) -> Path:
    return root / COURSES_DIR / validate_code(code) / "evidence.json"


def write_evidence(root: Path, codes: list[str]) -> tuple[list[Path], list[dict]]:
    """逐课写 `evidence.json`，返回（写入路径, 对应文档）。"""
    paths = []
    documents = []
    for code in codes:
        doc = build_evidence(root, code)
        path = evidence_path(root, code)
        # 双保险：解析后的路径必须仍在仓根内（符号链接 / 平台路径差异都挡在这里，C2-006）
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"课码 {code!r} 解析出的路径逃出仓根：{path.resolve()}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialize(doc), encoding="utf-8")
        paths.append(path)
        documents.append(doc)
    return paths, documents
