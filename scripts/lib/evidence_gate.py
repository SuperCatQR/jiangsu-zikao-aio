"""Evidence Gate: validates official facts layer and knowledge model contracts (Issue #55 / Task 6).

失败关闭清单（plan Task 6 Step 1 / design-notes §3）：

- `facts[*].status` 非法；`status == "verified"` 缺 `provenance`；`named_gap` 缺 `gap_impact` / `next_evidence`；
- **非 `verified` 的事实不得携带 `value`** —— 未验证的值一旦渲染就是「官方事实」（C2-003）；
- **`eligibility.level` 必须能由 `syllabus` / `textbook_plan` 重新推导出来**（D8 单一门槛）：
  声明 `L1` 而任一输入不满足 → 失败关闭；非 `L1` 课程存在 `content.json` / `knowledge-model.json` → 失败关闭；
- `quote` > 60 字符（含**缺失**）→ 失败关闭；point `id` 重复 / 格式不符；`coverage.ratio < 0.90`；
  `diff_vs_manual[].kind == "manual_only"`；
- 知识模型章目与 `syllabus.md` 的章目索引**逐行一致（空白不敏感，见 `_without_whitespace`）**，
  且 `official_point_count` 与模型自身的节数一致
  （防止静默丢章：`15044` 的 `绪 论` 曾因 `CHAPTER_RE` 只认 `导论` 而整章消失，见 B6）。

诊断纪律（C2-013）：本层对任何**类型**错误的产物都必须返回定位到文件与字段的错误字符串，
不允许抛 `TypeError` 中断整层 —— 否则一个坏文件会掩盖其余课码的问题。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lib.course_pipeline.evidence import evaluate_eligibility
from lib.course_pipeline.knowledge_model import (
    APPENDIX_RE,
    CHAPTER_TITLE_RE,
    normalized_source_lines,
    source_assessment_unit_count,
)
from lib.course_pipeline.official_source import is_official_url

# `facts[*].status` 只允许契约里的两个取值（plan § Data contracts 2）。
# 旧实现接受 `unverified` / `missing-source`，而两者在检查链里没有任何分支 —— 等于给
# 「verified 掉了 provenance」开了一条静默降级通道（C2-003 / QC3-009）。
VALID_STATUSES = {"verified", "named_gap"}
# point id 形态的唯一真源（W7 / QC1 F-10）：`POINT_ID_BODY` 只写一遍，通用形态与课码专属形态都从它派生。
# 旧实现除了 `POINT_ID_RE`，还在 `_knowledge_model_problems()` 里第二次 `re.compile(...)` 同一规则，
# 改一处不会改另一处。
# `ap\d{2}` 是**附录单元**（R41）：`附录N` 是 `Ⅲ` 部之下的独立考核单元，其 point 不得借用章 slug。
POINT_ID_BODY = r"(intro|ch\d{2}|ap\d{2})-s\d+-p\d+"
POINT_ID_RE = re.compile(rf"^\d{{5}}-{POINT_ID_BODY}$")


def point_id_pattern(code: str | None):
    """课码专属的 point id 正则；`code` 为空时返回通用形态（两者共用 `POINT_ID_BODY`）。"""
    if not code:
        return POINT_ID_RE
    return re.compile(rf"^{re.escape(code)}-{POINT_ID_BODY}$")
SYLLABUS_STATUSES = {"extracted", "missing"}
TEXTBOOK_STATUSES = {"matched", "missing"}
CHAPTER_INDEX_HEADING = "### 章目索引"
MAX_QUOTE_CHARS = 60
MIN_COVERAGE_RATIO = 0.90


def _strip_generated_at(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_generated_at(v) for k, v in obj.items() if k != "generated_at"}
    if isinstance(obj, list):
        return [_strip_generated_at(x) for x in obj]
    return obj


def is_fresh(obj1: Any, obj2: Any) -> bool:
    """Compare two data objects ignoring generated_at timestamps."""
    return _strip_generated_at(obj1) == _strip_generated_at(obj2)


def _chapter_titles_from_syllabus(root: Path, code: str) -> list[str] | None:
    """`content/jiangsu/courses/<code>/syllabus.md` 的章目索引第二列（逐字章名）；无该页返回 `None`。"""
    path = root / "content" / "jiangsu" / "courses" / code / "syllabus.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    idx = text.find(CHAPTER_INDEX_HEADING)
    if idx == -1:
        return None
    rows: list[str] = []
    for line in text[idx:].splitlines()[1:]:
        if line.startswith("## ") or line.startswith("### "):
            break
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", ":"}:
            continue
        if cells[0] == "章序":
            continue
        rows.append(cells[1])
    return rows or None


def _without_whitespace(title: Any) -> Any:
    """章目标题的「去空白视图」：删掉全部空白字符（首尾与内部），其余字符一律不动。

    W4.5 / plan Task 0b：模型逐字照录抽取件（`04747` 抽取件印 `第 6 章`），手写 `syllabus.md`
    表把章号内部空白归一掉了（`第6章`）—— 两侧章集合 / 章序 / 章名完全相同，差异**只在空白**。
    这是**比较**侧的唯一放宽：空白以外（大小写、标点、全半角、数字）仍须逐字相同，章数与章序
    仍由列表比较承担。非字符串原样返回：`title` 缺失时 `None` 与页面表字符串不等 ⇒ 仍失败关闭
    （且不得抛 `TypeError` 中断整层，见模块头 C2-013 诊断纪律）。

    与 `knowledge_model._fold` 的分工：`_fold` 是「空白串折叠为单个半角空格」（`第1章   X` → `第1章 X`），
    实测**不**能让 `第 6 章` 与 `第6章` 判等 —— 本条要的是「删掉空白」，故不复用 `_fold`。
    """
    return "".join(title.split()) if isinstance(title, str) else title


def _facts_problems(rel: str, facts: Any, errors: list[str]) -> None:
    if not isinstance(facts, dict):
        errors.append(f"{rel}: facts must be dict")
        return
    for key, fact in facts.items():
        if not isinstance(fact, dict):
            errors.append(f"{rel}: facts.{key} must be dict")
            continue
        status = fact.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{rel}: facts.{key}.status has invalid value: {status!r}（只允许 {sorted(VALID_STATUSES)}）")
            continue
        if status == "verified":
            prov = fact.get("provenance")
            if not prov or not isinstance(prov, dict):
                errors.append(f"{rel}: facts.{key} has status 'verified' but missing provenance")
        else:  # named_gap
            if not fact.get("gap_impact") or not fact.get("next_evidence"):
                errors.append(f"{rel}: facts.{key} has status 'named_gap' but missing gap_impact or next_evidence")
        # 非 verified 的事实不得带 value：渲染层会把 value 当官方事实印到 official_only 页面（C2-003）
        if status != "verified" and fact.get("value") not in (None, ""):
            errors.append(
                f"{rel}: facts.{key} has status {status!r} but carries a value"
                "（未验证的值不得渲染为官方事实，须置 null）"
            )


def _eligibility_problems(root: Path, rel: str, ev: dict, errors: list[str]) -> None:
    """`eligibility` 必须能由 `syllabus` / `textbook_plan` 重新推导（D8 / C2-002 / B3）。"""
    eligibility = ev.get("eligibility")
    if not isinstance(eligibility, dict):
        errors.append(f"{rel}: eligibility must be dict")
        return
    level = eligibility.get("level")
    expected = evaluate_eligibility(ev)
    if level != expected["level"]:
        errors.append(
            f"{rel}: eligibility.level {level!r} 无法由 syllabus/textbook_plan 推导"
            f"（应为 {expected['level']!r}，reasons={expected['reasons']}）"
        )
    reasons = eligibility.get("reasons")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(item, str) and item for item in reasons):
        errors.append(f"{rel}: eligibility.reasons 必须是非空字符串列表")

    syllabus = ev.get("syllabus")
    if not isinstance(syllabus, dict):
        errors.append(f"{rel}: syllabus must be dict")
    else:
        status = syllabus.get("status")
        if status not in SYLLABUS_STATUSES:
            errors.append(f"{rel}: syllabus.status has invalid value: {status!r}")
        elif status == "extracted":
            for key in ("path", "sha256", "requirements_heading"):
                if not syllabus.get(key):
                    errors.append(f"{rel}: syllabus.status 'extracted' 但缺少 {key}")
            rel_path = syllabus.get("path")
            sha = syllabus.get("sha256")
            if isinstance(rel_path, str) and isinstance(sha, str):
                document = root / rel_path
                if not document.is_file():
                    errors.append(f"{rel}: syllabus.path 指向的抽取件不存在: {rel_path}")
                elif hashlib.sha256(document.read_bytes()).hexdigest() != sha:
                    errors.append(f"{rel}: syllabus.sha256 与 {rel_path} 实际内容不一致")
        elif status == "missing":
            for key in ("gap_impact", "next_evidence"):
                if not syllabus.get(key):
                    errors.append(f"{rel}: syllabus.status 'missing' 但缺少 {key}")

    textbook = ev.get("textbook_plan")
    if not isinstance(textbook, dict):
        errors.append(f"{rel}: textbook_plan must be dict")
    else:
        status = textbook.get("status")
        if status not in TEXTBOOK_STATUSES:
            errors.append(f"{rel}: textbook_plan.status has invalid value: {status!r}")
        elif status == "matched":
            for key in ("doc_id", "path", "locator", "row"):
                if not textbook.get(key):
                    errors.append(f"{rel}: textbook_plan.status 'matched' 但缺少 {key}")
        elif status == "missing":
            for key in ("gap_impact", "next_evidence"):
                if not textbook.get(key):
                    errors.append(f"{rel}: textbook_plan.status 'missing' 但缺少 {key}")


def _course_url_problems(rel: str, code: str | None, url: Any, baseline_urls: dict, errors: list[str]) -> None:
    if url is None:
        return
    if not isinstance(url, str):
        errors.append(f"{rel}: course_url must be string or null")
        return
    if not baseline_urls:
        return
    if url not in baseline_urls:
        errors.append(f"{rel}: course_url {url!r} not found in source-links baseline")
        return
    entry = baseline_urls[url]
    if not entry.get("authoritative"):
        errors.append(f"{rel}: course_url {url!r} is not authoritative")
    if not is_official_url(url):
        errors.append(f"{rel}: course_url {url!r} host {(urlparse(url).hostname or '')!r} is not jseea.cn")
    if code and code not in entry.get("course_codes", []):
        errors.append(f"{rel}: course_url {url!r} course_codes does not include {code}")


def _declared_unit_count(root: Path, syllabus: Any, rel_km: str, errors: list[str]) -> int | None:
    """考纲原文声明的考核单元数（R43 的独立分母）；取不到时返回 `None`（不判定）。

    独立性是这条检查的全部价值：它读**抽取件原文**（`evidence.syllabus.path`）并按源文重数一遍，
    而 `official_point_count` 是切片解析的产物。旧实现的「分母自洽」两侧同源，恒真。
    读不到抽取件时不臆造判定（`syllabus.sha256` 漂移 / 路径缺失已由 `_eligibility_problems` 报出）。

    **三态（R54），不得压成 `raw or normalized`**：

    | 原文直读 | 规范化渲染 | 返回 | 含义 |
    |---|---|---|---|
    | `None` | — | `None` | 前置不可用 → **不判定**（既有行为） |
    | `>0` | — | 该值 | 原读可用（既有 5 门课全在此态：分母不移动） |
    | `0` | `>0` | 规范化值 | 版式噪声（`\\x0c` 等分隔符）把整篇读成一行 → 回退 |
    | `0` | `0` | `None` **+ 记一条 `errors`** | `status == "extracted"` 却两侧都数不出 = 源侧损坏的**矛盾态** → 失败关闭 |

    末态必须失败关闭，且不能静默跳过：`status == "extracted"` 的判据恰是「能定位到该小节」，
    两侧都为 0 与该状态矛盾。按 `declared = 0` 去比对则**方向反了** —— 真实语义是**多**出
    `official` 个未计入单元（源侧标记损坏），不是「源文声明了 0 个单元」。
    """
    if not isinstance(syllabus, dict) or syllabus.get("status") != "extracted":
        return None
    rel_path = syllabus.get("path")
    heading = syllabus.get("requirements_heading")
    if not isinstance(rel_path, str) or not isinstance(heading, str) or not heading:
        return None
    document = root / rel_path
    if not document.is_file():
        return None
    text = document.read_text(encoding="utf-8")
    declared = source_assessment_unit_count(text.split("\n"), heading)
    if declared > 0:
        return declared
    declared = source_assessment_unit_count(normalized_source_lines(text), heading)
    if declared > 0:
        return declared
    errors.append(
        f"{rel_km}: 考纲原文声明的考核单元数两侧都解出 0（原文直读与规范化渲染都定位不到"
        f"「课程内容与考核要求」分部标记 /「{heading}」小节）—— `syllabus.status` 为 `extracted` "
        "却数不出考核单元，是源侧损坏的矛盾态，不得当作『源文声明 0 个单元』通过"
    )
    return None


def _sections_problems(
    unit: dict, where: str, rel_km: str, pattern, seen_point_ids: set[str], errors: list[str]
) -> int:
    """单元（章 / 附录）的 `sections[]` 与 `points[]` 校验 → 产出的节数。

    章与附录的节 / point 契约**完全相同**（id 形如 `<code>-<slug>-s<n>-p<n>`、`quote` 必填且 ≤ 60），
    故两侧共用本函数：附录单元若不校验，一个坏 point 就能从附录侧绕过闸门。
    """
    sections = unit.get("sections")
    if not isinstance(sections, list):
        errors.append(f"{rel_km}: {where}.sections must be list")
        return 0
    for sec in sections:
        if not isinstance(sec, dict):
            errors.append(f"{rel_km}: {where}.sections 元素必须为对象")
            continue
        points = sec.get("points")
        if not isinstance(points, list):
            errors.append(f"{rel_km}: 节 {unit.get('index')}-{sec.get('index')} 的 points 必须为列表")
            continue
        for pt in points:
            if not isinstance(pt, dict):
                errors.append(f"{rel_km}: point 元素必须为对象")
                continue
            pid = pt.get("id")
            if not pid or not isinstance(pid, str) or not pattern.fullmatch(pid):
                errors.append(f"{rel_km}: invalid point id format: {pid!r}")
            elif pid in seen_point_ids:
                errors.append(f"{rel_km}: duplicate point id: {pid!r}")
            else:
                seen_point_ids.add(pid)

            quote = pt.get("quote")
            # 缺失与超长都必须失败关闭：旧实现 `pt.get("quote") or ""` 让「没有 quote」等同于合规
            if not isinstance(quote, str) or not quote.strip():
                errors.append(f"{rel_km}: point {pid} 缺 quote（考纲原文短语必填）")
            elif len(quote) > MAX_QUOTE_CHARS:
                errors.append(
                    f"{rel_km}: point {pid} quote exceeds {MAX_QUOTE_CHARS} chars ({len(quote)}): {quote[:40]}..."
                )
    return len(sections)


def _knowledge_model_problems(
    root: Path, rel_km: str, code: str | None, km: dict, syllabus: Any, errors: list[str]
) -> None:
    """知识模型：point id / quote / coverage / 章目与 `syllabus.md` 的一致性（B6 的闸门侧闭环）。"""
    if not isinstance(km, dict):
        errors.append(f"{rel_km}: knowledge-model 必须是 JSON 对象")
        return
    chapters = km.get("chapters")
    if not isinstance(chapters, list):
        errors.append(f"{rel_km}: chapters must be list")
        return

    pattern = point_id_pattern(code)
    seen_point_ids: set[str] = set()
    section_total = 0
    for index, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            errors.append(f"{rel_km}: chapters[{index}] must be dict")
            continue
        title = ch.get("title")
        # 章标题必须与考纲目录的章序标签形态一致：`导论` / `绪 论` / `第N章 …`（B6 的静默丢章根因）
        if not isinstance(title, str) or not CHAPTER_TITLE_RE.match(title.strip()):
            errors.append(f"{rel_km}: chapters[{index}].title 不是可识别的章标题: {title!r}")
        ordinal = ch.get("ordinal")
        # `ordinal` 由章序标签推导（`导论`/`绪 论` = 0，`第N章` = N）：必须严格递增且步长 1。
        # 首章允许是 0（有导论）或 1（无导论课程，如 15043）—— 两者之外都是丢章信号（B6）。
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            errors.append(f"{rel_km}: chapters[{index}].ordinal 必须是整数，实际 {ordinal!r}")
        elif index == 0 and ordinal not in (0, 1):
            errors.append(f"{rel_km}: chapters[0].ordinal 必须是 0（导论类）或 1（无导论课程），实际 {ordinal}")
        elif index > 0:
            previous = chapters[index - 1].get("ordinal") if isinstance(chapters[index - 1], dict) else None
            if isinstance(previous, int) and not isinstance(previous, bool) and ordinal != previous + 1:
                errors.append(
                    f"{rel_km}: chapters[{index}].ordinal {ordinal} 与上一章 {previous} 不连续"
                    "（章序缺口 = 有章被静默丢弃）"
                )
        sections = ch.get("sections")
        if not isinstance(sections, list):
            errors.append(f"{rel_km}: chapters[{index}].sections must be list")
            continue
        section_total += _sections_problems(ch, f"chapters[{index}]", rel_km, pattern, seen_point_ids, errors)

    # 附录单元（R41）：`附录N` 是 `Ⅲ` 部之下的独立考核单元，其 point 与章同契约、同样进分母。
    # 结构守卫与章同源：`ordinal` 必须 1..N 连续（缺口 = 有附录被静默吞掉），标题必须是 `附录N 标题`。
    appendices = km.get("appendices", [])
    if not isinstance(appendices, list):
        errors.append(f"{rel_km}: appendices must be list")
    else:
        for index, ap in enumerate(appendices):
            if not isinstance(ap, dict):
                errors.append(f"{rel_km}: appendices[{index}] must be dict")
                continue
            title = ap.get("title")
            # 形态判据与抽取器**共用同一个正则**（F-3）：两个各自维护的 `附录N` 判据曾漂移成
            # 「都接受裸 `附录一`」，于是无标题条目在抽取侧与闸门侧同时被放行。
            if not isinstance(title, str) or not APPENDIX_RE.match(title.strip()):
                errors.append(f"{rel_km}: appendices[{index}].title 不是可识别的附录标题: {title!r}")
            ordinal = ap.get("ordinal")
            if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal != index + 1:
                errors.append(
                    f"{rel_km}: appendices[{index}].ordinal 必须是 {index + 1}（附录序连续），实际 {ordinal!r}"
                    "（附录缺口 = 有附录单元被静默丢弃）"
                )
            section_total += _sections_problems(ap, f"appendices[{index}]", rel_km, pattern, seen_point_ids, errors)

    coverage = km.get("coverage")
    if not isinstance(coverage, dict):
        errors.append(f"{rel_km}: coverage must be dict")
    else:
        ratio = coverage.get("ratio", 0.0)
        # 类型守卫：`ratio: null` / `"1.0"` 曾让闸门抛 TypeError 中断整层（C2-013）
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            errors.append(f"{rel_km}: coverage.ratio 必须是数字，实际 {type(ratio).__name__}")
        elif ratio < MIN_COVERAGE_RATIO:
            errors.append(f"{rel_km}: coverage ratio {ratio:.2f} is under {MIN_COVERAGE_RATIO:.2f}")

        # 分母自洽：`official_point_count` = 模型自身产出的单元数（章节 + 附录节）。
        # 这一条**不是** R43 的修法 —— 两侧同源自同一次解析，恒真，只能抓「产物被手改坏了」。
        official = coverage.get("official_point_count")
        if isinstance(official, bool) or not isinstance(official, int):
            errors.append(f"{rel_km}: coverage.official_point_count 必须是整数，实际 {type(official).__name__}")
        elif official != section_total:
            errors.append(
                f"{rel_km}: coverage.official_point_count {official} 与模型实际单元数 {section_total} 不一致"
                "（有章 / 节被静默丢弃）"
            )

        # R43：分母必须**独立于产出**数出来 —— 源侧声明的考核单元数来自考纲原文
        # （`source_assessment_unit_count()`），与模型的切片 / 要求块解析是两条独立路径。
        # 旧实现只做上面那条同源核对：解析丢掉一整个单元时，`official` 与 `section_total`
        # **同时变小**、比值仍 `1.0`，于是 `02333` 带着 7 个被吞掉的附录单元全绿出厂。
        if isinstance(official, int) and not isinstance(official, bool):
            declared = _declared_unit_count(root, syllabus, rel_km, errors)
            if declared is not None and declared != official:
                errors.append(
                    f"{rel_km}: coverage.official_point_count {official} 与考纲原文声明的考核单元数 "
                    f"{declared} 不一致（{declared - official} 个单元被静默丢弃；分母必须独立于产出）"
                )

        diff = coverage.get("diff_vs_manual", [])
        if not isinstance(diff, list):
            errors.append(f"{rel_km}: coverage.diff_vs_manual 必须是列表")
        else:
            for item in diff:
                if not isinstance(item, dict):
                    errors.append(f"{rel_km}: diff_vs_manual 元素必须为对象")
                    continue
                if item.get("kind") == "manual_only":
                    errors.append(f"{rel_km}: diff_vs_manual contains manual_only entry: {item}")

    if code:
        expected_titles = _chapter_titles_from_syllabus(root, code)
        actual_titles = [ch.get("title") for ch in chapters if isinstance(ch, dict)]
        # 逐项比较两侧的「去空白视图」（W4.5 / Task 0b）：条数、顺序、空白以外的一切字符仍须完全一致。
        if expected_titles is not None and [_without_whitespace(t) for t in actual_titles] != [
            _without_whitespace(t) for t in expected_titles
        ]:
            errors.append(
                f"{rel_km}: chapters 与 content/jiangsu/courses/{code}/syllabus.md 章目索引不一致"
                f"（模型 {len(actual_titles)} 章 / 页面 {len(expected_titles)} 章）"
            )


def run_evidence_gate(root: Path) -> list[str]:
    """Validate 18 evidence.json and knowledge-model.json files."""
    errors: list[str] = []
    courses_dir = root / "sources" / "jiangsu" / "courses"
    if not courses_dir.is_dir():
        return errors

    baseline_file = root / "ops" / "jiangsu" / "source-links.baseline.json"
    baseline_urls: dict[str, Any] = {}
    if baseline_file.is_file():
        baseline_data = json.loads(baseline_file.read_text(encoding="utf-8"))
        baseline_urls = baseline_data.get("urls", {})

    for ev_file in sorted(courses_dir.glob("*/evidence.json")):
        rel = ev_file.relative_to(root).as_posix()
        try:
            ev = json.loads(ev_file.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{rel}: JSON decode error: {exc}")
            continue
        if not isinstance(ev, dict):
            errors.append(f"{rel}: evidence.json 必须是 JSON 对象")
            continue

        code = ev.get("course_code")
        if not code or not isinstance(code, str) or not re.fullmatch(r"\d{5}", code):
            errors.append(f"{rel}: invalid course_code: {code!r}")

        _facts_problems(rel, ev.get("facts"), errors)
        _eligibility_problems(root, rel, ev, errors)
        _course_url_problems(rel, code, ev.get("course_url"), baseline_urls, errors)

        level = (ev.get("eligibility") or {}).get("level") if isinstance(ev.get("eligibility"), dict) else None
        km_file = ev_file.parent / "knowledge-model.json"
        content_file = ev_file.parent / "content.json"
        # 零 AI 产物规则（spec AC4 / D8）：非 `L1` 课程不得有任何下游产物
        for artifact, label in ((content_file, "content.json"), (km_file, "knowledge-model.json")):
            if level != "L1" and artifact.is_file():
                errors.append(
                    f"{rel}: eligibility level is {level!r} (not L1), but {label} exists at "
                    f"{artifact.relative_to(root).as_posix()}"
                )

        if km_file.is_file():
            rel_km = km_file.relative_to(root).as_posix()
            try:
                km = json.loads(km_file.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{rel_km}: JSON decode error: {exc}")
                continue
            _knowledge_model_problems(root, rel_km, code, km, ev.get("syllabus"), errors)

    return errors
