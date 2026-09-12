"""Evidence Gate: validates official facts layer and knowledge model contracts (Issue #55 / Task 6).

失败关闭清单（plan Task 6 Step 1 / design-notes §3）：

- `facts[*].status` 非法；`status == "verified"` 缺 `provenance`；`named_gap` 缺 `gap_impact` / `next_evidence`；
- **非 `verified` 的事实不得携带 `value`** —— 未验证的值一旦渲染就是「官方事实」（C2-003）；
- **`eligibility.level` 必须能由 `syllabus` / `textbook_plan` 重新推导出来**（D8 单一门槛）：
  声明 `L1` 而任一输入不满足 → 失败关闭；非 `L1` 课程存在 `content.json` / `knowledge-model.json` → 失败关闭；
- `quote` > 60 字符（含**缺失**）→ 失败关闭；point `id` 重复 / 格式不符；`coverage.ratio < 0.90`；
  `diff_vs_manual[].kind == "manual_only"`；
- 知识模型章目与 `syllabus.md` 的章目索引**逐行一致**，且 `official_point_count` 与模型自身的节数一致
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
from lib.course_pipeline.knowledge_model import CHAPTER_TITLE_RE
from lib.course_pipeline.official_source import is_official_url

# `facts[*].status` 只允许契约里的两个取值（plan § Data contracts 2）。
# 旧实现接受 `unverified` / `missing-source`，而两者在检查链里没有任何分支 —— 等于给
# 「verified 掉了 provenance」开了一条静默降级通道（C2-003 / QC3-009）。
VALID_STATUSES = {"verified", "named_gap"}
POINT_ID_RE = re.compile(r"^\d{5}-(intro|ch\d{2})-s\d+-p\d+$")
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


def _knowledge_model_problems(root: Path, rel_km: str, code: str | None, km: dict, errors: list[str]) -> None:
    """知识模型：point id / quote / coverage / 章目与 `syllabus.md` 的一致性（B6 的闸门侧闭环）。"""
    if not isinstance(km, dict):
        errors.append(f"{rel_km}: knowledge-model 必须是 JSON 对象")
        return
    chapters = km.get("chapters")
    if not isinstance(chapters, list):
        errors.append(f"{rel_km}: chapters must be list")
        return

    pattern = re.compile(rf"^{code}-(intro|ch\d{{2}})-s\d+-p\d+$") if code else POINT_ID_RE
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
        section_total += len(sections)
        for sec in sections:
            if not isinstance(sec, dict):
                errors.append(f"{rel_km}: chapters[{index}].sections 元素必须为对象")
                continue
            points = sec.get("points")
            if not isinstance(points, list):
                errors.append(f"{rel_km}: 节 {ch.get('index')}-{sec.get('index')} 的 points 必须为列表")
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

        # 分母自洽：`official_point_count` = 模型自身的节数，两者不等即说明有章 / 节被静默丢弃
        official = coverage.get("official_point_count")
        if isinstance(official, bool) or not isinstance(official, int):
            errors.append(f"{rel_km}: coverage.official_point_count 必须是整数，实际 {type(official).__name__}")
        elif official != section_total:
            errors.append(
                f"{rel_km}: coverage.official_point_count {official} 与模型实际节数 {section_total} 不一致"
                "（有章 / 节被静默丢弃）"
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
        if expected_titles is not None and actual_titles != expected_titles:
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
            _knowledge_model_problems(root, rel_km, code, km, errors)

    return errors
