"""AI 备考层生成：`sources/jiangsu/courses/<code>/content.json`（Data contracts 4 / spec `D1`）。

生成内容：

- 每个考核点：`explain`（要点梳理 + 易错点）、`memorize`（记忆法 / 口诀 / 对比）、`drill`
  （按考纲声明的题型出题；B1 只出 AI 自编题，`source_kind == "ai_generated"`，不转载题文 —— GC4 / spec `O2`）；
- 课程级：`stage_plan`（恰五阶段）+ `exam_strategy`（`point_id: null` + `scope: "course"`），
  由 `stage_plan` 提示词**一次**调用产出；
- `review_schedule`：由知识模型 + `weekly_hours` **确定性**推导（不调 LLM）。输入齐备 → 30 / 14 / 7 三档
  （`end_date` = 考期，`start_date` = 考期 − (horizon − 1) 天，`daily_minutes = round(weekly_hours * 60 / 7)`）；
  缺任一输入 → `named_gap`（`plans: []` + 非空 `gap_impact` / `next_evidence`，**不编造日期** —— GC3）。

排程输入取 `model["exam"]` 的 `exam_date` / `weekly_hours`：`exam` 块本就是知识模型里承载考期事实的地方，
输入放在这里可以保持接口签名 `generate_course_content(root, model, *, backend)` 不变（逐字对齐
plan § Target-state module map）。15040 的知识模型没有这两个键 → B1 产物即命名缺口。

标注契约（GC1 / `D1`）：`blocks[]`、`stage_plan[]`、`review_schedule` 及其 `plans[]` 每一项都必须带
`ai_generated: true` + `generator`（`backend` / `model` / `prompt_id` / `prompt_version` / `generated_at`）
+ 非空 `evidence_refs` + `review_state: "machine_draft"`；`validate_content_doc()` 是本层的失败关闭自检
（Task 6 的 `ai-content` 层复用同一函数）。

确定性：块序 = 章 → 节 → 点 → explain / memorize / drill（`order_blocks()` 的唯一规范序，合并路径同序），
课程级块在末尾；提示词 payload 不含时间戳，
因此 fixture 哈希稳定；`generated_at` 来自 `llm_client.generator_metadata()`（`replay` 回放录制时的来源），
`--backend replay` 复跑与首次产物逐字段一致（AC9）。

分批：`--merge` 的语义见 `merge_content_docs()`（课程级块整块替换 / 考点级块按 `block_id` 合并 /
合并后按同一规范序重排）；`out_of_scope_prompts()` 是「课程无提示词包」的失败关闭判据（F-401）。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from lib.course_pipeline import llm_client

EXPLAIN_PROMPT = ("explain_point", "v1")
MEMORIZE_PROMPT = ("memorize_point", "v1")
DRILL_PROMPT = ("drill_point", "v1")
STAGE_PLAN_PROMPT = ("stage_plan", "v1")
POINT_PROMPTS = (("explain", EXPLAIN_PROMPT), ("memorize", MEMORIZE_PROMPT), ("drill", DRILL_PROMPT))

BLOCK_KINDS = ("explain", "memorize", "drill", "exam_strategy")
SOURCE_KINDS = ("ai_generated", "official_sample")
SCHEDULE_ITEM_KINDS = ("read", "drill", "review")
STAGES = ("入门", "精读", "刷题", "冲刺", "复盘")
HORIZONS = (30, 14, 7)
SPACED_REPETITION_OFFSETS = (1, 3, 7)
# 按考纲要求层级选题型：识记考再认、领会考说明、应用考材料分析；未声明该题型时回落第一个声明题型。
REQUIREMENT_QUESTION_TYPES = {"识记": "单项选择题", "领会": "简答题", "应用": "材料题"}
EXPLAIN_SUMMARY_HEADING = "### 要点梳理"
EXPLAIN_PITFALL_HEADING = "### 易错点"
MEMORY_MARKERS = ("记忆", "口诀", "对比", "联想", "串联", "谐音", "关键词", "顺口溜")
MIN_EXPLAIN_CHARS = 120
MIN_MEMORIZE_CHARS = 80
MIN_DRILL_CHARS = 40
# `official_sample` 转载上限（C2-009）：公开仓只允许有界引文，不得整段转载官方题文（GC4 / spec `O2`）
MAX_OFFICIAL_SAMPLE_CHARS = 200
NGRAM_SIZE = 8
PLAGIARISM_THRESHOLD = 0.2
COURSES_DIR = Path("sources") / "jiangsu" / "courses"
CONTENT_FILENAME = "content.json"
REVIEW_GAP_IMPACT_TEMPLATE = "缺少 {missing}，无法推导 30 / 14 / 7 天排程"
REVIEW_GAP_NEXT_EVIDENCE = "用户或官方考期公告提供 exam_date 与 weekly_hours（写入 knowledge-model.json 的 exam 块）"


def _point_ids(model: dict) -> list[str]:
    return [point["id"] for chapter in model["chapters"] for section in chapter["sections"] for point in section["points"]]


def declared_question_types(model: dict) -> list[str]:
    types = list(((model.get("exam") or {}).get("question_types")) or [])
    if not types:
        raise RuntimeError(f"知识模型未声明题型，无法生成 drill（course_code={model.get('course_code')}）")
    return types


def out_of_scope_prompts(course_code: str) -> list[str]:
    """该课程缺哪些提示词包（模板 frontmatter 的 `course_scope`）；空列表 = 在作用域内。

    plan § Data contracts 4「提示词课程作用域」（F-401）：作用域外的课程必须 fail closed —— 四个 v1
    提示词只服务 15040，用别人的模板生成会静默产出错课内容，且所有自检都看不出来。
    """
    return [
        f"{prompt_id}.{prompt_version}"
        for prompt_id, prompt_version in (*[prompt for _, prompt in POINT_PROMPTS], STAGE_PLAN_PROMPT)
        if course_code not in llm_client.prompt_course_scope(prompt_id, prompt_version)
    ]


def select_chapters(model: dict, selectors) -> dict:
    """按章 `slug` / 章序标签 / `ordinal` 选章（分批生成用），保持知识模型内的章序。"""
    wanted = [str(item).strip() for item in selectors if str(item).strip()]
    if not wanted:
        raise ValueError("select_chapters 需要至少一个章选择器（slug / 章序标签 / ordinal）")
    known = {chapter["slug"]: chapter for chapter in model["chapters"]}
    names = {
        chapter["slug"]: {chapter["slug"], chapter["index"], str(chapter["ordinal"])}
        for chapter in model["chapters"]
    }
    unknown = [item for item in wanted if not any(item in names[slug] for slug in known)]
    if unknown:
        raise ValueError(f"未知的章选择器: {'、'.join(unknown)}")
    chapters = [chapter for slug, chapter in known.items() if names[slug] & set(wanted)]
    return {**model, "chapters": chapters}


def _question_types(model: dict, chapter: dict) -> dict[str, str]:
    """章内题型分配：先按要求层级映射，再保证本章覆盖考纲声明的全部题型（确定性、可复算）。"""
    types = declared_question_types(model)
    points = [point for section in chapter["sections"] for point in section["points"]]
    assignment: dict[str, str] = {}
    for point in points:
        preferred = REQUIREMENT_QUESTION_TYPES.get(point.get("requirement"))
        assignment[point["id"]] = preferred if preferred in types else types[0]
    for question_type in [item for item in types if item not in set(assignment.values())]:
        for point in reversed(points):
            if list(assignment.values()).count(assignment[point["id"]]) > 1:
                assignment[point["id"]] = question_type
                break
    return assignment


def _point_payload(model: dict, chapter: dict, section: dict, point: dict, *, kind: str, question_type: str | None) -> dict:
    payload = {
        "course_code": model["course_code"],
        "chapter": {"ordinal": chapter["ordinal"], "index": chapter["index"], "title": chapter["title"]},
        "section": {"index": section["index"], "title": section["title"]},
        "point": {
            "id": point["id"],
            "title": point["title"],
            "requirement": point["requirement"],
            "quote": point["quote"],
            "locator": point["locator"],
        },
        "section_points": [
            {"id": item["id"], "title": item["title"], "requirement": item["requirement"]}
            for item in section["points"]
        ],
        "chapter_focus": [item["text"] for item in chapter.get("chapter_focus") or []],
    }
    if kind == "drill":
        payload["question_type"] = question_type
    return payload


def _stage_plan_payload(model: dict) -> dict:
    """课程级 payload：只放官方已声明的事实（题型 / 样卷锚点 / 章节目录），不放排程输入。

    排程输入（`exam_date` / `weekly_hours`）不进 payload —— 否则同一课程的 stage_plan payload 哈希会随
    用户输入变化，破坏 fixture 回放；排程由 `_review_schedule()` 确定性推导。
    """
    exam = model.get("exam") or {}
    return {
        "course_code": model["course_code"],
        "exam": {
            "question_types": list(exam.get("question_types") or []),
            "duration_minutes": exam.get("duration_minutes"),
            "duration_status": exam.get("duration_status"),
            "sample_paper": exam.get("sample_paper"),
        },
        "chapters": [
            {
                "ordinal": chapter["ordinal"],
                "index": chapter["index"],
                "title": chapter["title"],
                "sections": [
                    {"index": section["index"], "title": section["title"], "point_count": len(section["points"])}
                    for section in chapter["sections"]
                ],
            }
            for chapter in model["chapters"]
        ],
        "point_total": len(_point_ids(model)),
    }


def _jobs(model: dict) -> list[dict]:
    jobs: list[dict] = []
    assignments: dict[str, str] = {}
    for chapter in model["chapters"]:
        assignments.update(_question_types(model, chapter))
    for chapter in model["chapters"]:
        for section in chapter["sections"]:
            for point in section["points"]:
                for kind, (prompt_id, prompt_version) in POINT_PROMPTS:
                    jobs.append(
                        {
                            "kind": kind,
                            "prompt_id": prompt_id,
                            "prompt_version": prompt_version,
                            "payload": _point_payload(
                                model, chapter, section, point, kind=kind, question_type=assignments[point["id"]]
                            ),
                            "chapter": chapter,
                            "section": section,
                            "point": point,
                        }
                    )
    jobs.append(
        {
            "kind": "stage_plan",
            "prompt_id": STAGE_PLAN_PROMPT[0],
            "prompt_version": STAGE_PLAN_PROMPT[1],
            "payload": _stage_plan_payload(model),
        }
    )
    return jobs


def call_plan(model: dict) -> list[tuple[str, str, dict]]:
    """本次生成会发出的全部 prompt 调用（确定性顺序）。agent 后端据此一次性写出全部任务包。"""
    return [(job["prompt_id"], job["prompt_version"], job["payload"]) for job in _jobs(model)]


def _generator(job: dict) -> dict:
    generator = job["generator"]
    return {
        "backend": generator["backend"],
        "model": generator["model"],
        "prompt_id": job["prompt_id"],
        "prompt_version": job["prompt_version"],
        "generated_at": generator["generated_at"],
    }


def _point_block(model: dict, job: dict) -> dict:
    point = job["point"]
    block = {
        "block_id": f"{point['id']}/{job['kind']}",
        "kind": job["kind"],
        "point_id": point["id"],
        "ai_generated": True,
        "review_state": "machine_draft",
        "generator": _generator(job),
        "evidence_refs": [f"syllabus:{model['course_code']}#{point['locator']}"],
        "text_md": job["response"]["text_md"],
    }
    if job["kind"] == "drill":
        block["question_type"] = job["response"]["question_type"]
        block["answer_md"] = job["response"]["answer_md"]
        block["source_kind"] = "ai_generated"
    return block


def _stage_entry(stage: dict, job: dict) -> dict:
    return {
        "stage": stage["stage"],
        "goal": stage["goal"],
        "inputs": list(stage["inputs"]),
        "how": list(stage["how"]),
        "outputs": list(stage["outputs"]),
        "done_when": stage["done_when"],
        "ai_generated": True,
        "review_state": "machine_draft",
        "generator": _generator(job),
        "evidence_refs": ["knowledge-model:chapters"],
    }


def _exam_strategy_block(job: dict) -> dict:
    return {
        "block_id": "course/exam_strategy",
        "kind": "exam_strategy",
        "point_id": None,
        "scope": "course",
        "ai_generated": True,
        "review_state": "machine_draft",
        "generator": _generator(job),
        "evidence_refs": ["knowledge-model:exam"],
        "text_md": job["response"]["exam_strategy"]["text_md"],
    }


def _exam_inputs(model: dict) -> tuple[date | None, float | None, list[str]]:
    exam = model.get("exam") or {}
    raw_date = exam.get("exam_date")
    weekly_hours = exam.get("weekly_hours")
    missing: list[str] = []
    exam_date: date | None = None
    if raw_date in (None, ""):
        missing.append("exam_date")
    elif not isinstance(raw_date, str):
        raise ValueError("exam.exam_date 必须是 YYYY-MM-DD 字符串")
    else:
        try:
            exam_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(f"exam.exam_date 不是合法日期: {raw_date}") from exc
    hours: float | None = None
    if (
        weekly_hours in (None, "")
        or isinstance(weekly_hours, bool)
        or not isinstance(weekly_hours, (int, float))
        or weekly_hours <= 0
    ):
        missing.append("weekly_hours")
    else:
        hours = float(weekly_hours)
    return exam_date, hours, missing


def _day_kind(day: int, days: int) -> str:
    """前 1/2 天通读、随后 1/4 天刷题、其余复盘（确定性，三档同规则）。"""
    read_days = -(-days // 2)
    drill_until = read_days + -(-days // 4)
    if day <= read_days:
        return "read"
    return "drill" if day <= drill_until else "review"


def _tier(model: dict, horizon_days: int, exam_date: date, weekly_hours: float, generator: dict) -> dict:
    entries = [
        (chapter, section, point)
        for chapter in model["chapters"]
        for section in chapter["sections"]
        for point in section["points"]
    ]
    start = exam_date - timedelta(days=horizon_days - 1)
    plan = {
        "tier": f"{horizon_days}d",
        "horizon_days": horizon_days,
        "start_date": start.isoformat(),
        "end_date": exam_date.isoformat(),
        "daily_minutes": round(weekly_hours * 60 / 7),
        "items": [],
        "spaced_repetition": [
            {"point_id": point["id"], "offsets_days": list(SPACED_REPETITION_OFFSETS)} for _, _, point in entries
        ],
        "ai_generated": True,
        "review_state": "machine_draft",
        "generator": generator,
        "evidence_refs": ["knowledge-model:chapters"],
    }
    total = len(entries)
    for day in range(1, horizon_days + 1):
        chunk = entries[(day - 1) * total // horizon_days : day * total // horizon_days]
        if not chunk:
            continue
        # 天数多于考核点时只写有内容的日，日号仍从 1 连续编号（契约只要求连续性，不要求等于 horizon）
        index = len(plan["items"])
        plan["items"].append(
            {
                "day": index + 1,
                "date": (start + timedelta(days=index)).isoformat(),
                "focus": f"{chunk[0][0]['index']}·{chunk[0][1]['title']}",
                "point_ids": [point["id"] for _, _, point in chunk],
                "kind": _day_kind(day, horizon_days),
            }
        )
    return plan


def _review_schedule(model: dict, generator: dict) -> dict:
    exam_date, weekly_hours, missing = _exam_inputs(model)
    schedule = {
        "exam_date": exam_date.isoformat() if exam_date else None,
        "weekly_hours": weekly_hours,
        "status": "named_gap",
        "plans": [],
        "ai_generated": True,
        "review_state": "machine_draft",
        "generator": generator,
        "evidence_refs": ["knowledge-model:exam"],
    }
    if missing:
        schedule["gap_impact"] = REVIEW_GAP_IMPACT_TEMPLATE.format(missing="、".join(missing))
        schedule["next_evidence"] = REVIEW_GAP_NEXT_EVIDENCE
        return schedule
    schedule["status"] = "planned"
    schedule["plans"] = [_tier(model, horizon, exam_date, weekly_hours, generator) for horizon in HORIZONS]
    return schedule


def generate_course_content(root: Path, model: dict, *, backend: str = "cli") -> dict:
    """生成 AI 备考层文档；任何自检失败都抛 `RuntimeError`（不产出半成品）。"""
    source_path = (model.get("source") or {}).get("path")
    if source_path and not (root / source_path).is_file():
        raise RuntimeError(f"知识模型引用的考纲抽取件不存在: {source_path}（先跑 model 阶段）")
    jobs = _jobs(model)
    if backend == "agent":
        missing = llm_client.prepare_agent_tasks(
            model["course_code"], [(job["prompt_id"], job["prompt_version"], job["payload"]) for job in jobs]
        )
        if missing:
            raise llm_client.AgentTasksPendingError(missing)
    for job in jobs:
        job["generator"] = llm_client.generator_metadata(
            job["prompt_id"], job["prompt_version"], job["payload"], backend=backend
        )
        job["response"] = llm_client.complete_json(
            job["prompt_id"], job["prompt_version"], job["payload"], backend=backend
        )
    course_job = jobs[-1]
    blocks = [_point_block(model, job) for job in jobs[:-1]] + [_exam_strategy_block(course_job)]
    doc = {
        "schema_version": 1,
        "course_code": model["course_code"],
        "generated_at": course_job["generator"]["generated_at"],
        "generator": {
            "backend": course_job["generator"]["backend"],
            "model": course_job["generator"]["model"],
            "prompt_versions": {job["prompt_id"]: job["prompt_version"] for job in jobs},
        },
        "stage_plan": [_stage_entry(stage, course_job) for stage in course_job["response"]["stages"]],
        "blocks": order_blocks(blocks, model),
        "review_schedule": _review_schedule(model, _generator(course_job)),
    }
    problems = validate_content_doc(doc, model)
    if problems:
        raise RuntimeError("content 自检失败（不写半成品）: " + "; ".join(problems))
    return doc


def content_path(root: Path, code: str) -> Path:
    return root / COURSES_DIR / code / CONTENT_FILENAME


def _point_level_blocks(doc: dict, *, source: str) -> dict[str, dict]:
    """考点级块（`point_id` 非空）按 `block_id` 索引；缺 `block_id` 即失败关闭（不猜、不静默丢块）。"""
    blocks: dict[str, dict] = {}
    for block in doc.get("blocks") or []:
        if block.get("point_id") is None:
            continue
        block_id = block.get("block_id")
        if not isinstance(block_id, str) or not block_id:
            raise RuntimeError(f"{source} 的考点级块缺 block_id，拒绝合并")
        blocks[block_id] = block
    return blocks


# 块序契约（plan § Data contracts 4「唯一规范序」）：考点级块按 章序 → 节序 → 点序 → kind 排序，
# kind 用生成序 explain → memorize → drill（与知识模型的阅读序一致），课程级块排在末尾。
KIND_ORDER = {kind: index for index, kind in enumerate([kind for kind, _ in POINT_PROMPTS] + ["exam_strategy"])}


def _point_order(model: dict) -> dict[str, tuple[int, int, int]]:
    """`point_id` → 规范序前缀（知识模型的章序 → 节序 → 点序）。"""
    return {
        point["id"]: (chapter["ordinal"], section_index, point_index)
        for chapter in model["chapters"]
        for section_index, section in enumerate(chapter["sections"])
        for point_index, point in enumerate(section["points"])
    }


def order_blocks(blocks: list[dict], model: dict) -> list[dict]:
    """按唯一规范序重排块（PM 2026-09-11 二次裁决，F-405 收口）。

    逐批 `--merge` 与一次性全量生成都调用本函数：只有两条路径落在同一个序上，它们对同一内容集合
    才可能逐字节一致（plan § Data contracts 4；`tests/test_generate_content.py` 的字节相等用例锁住这一点）。
    考点级块按知识模型的章序 → 节序 → 点序 → `kind`；课程级块（`point_id: null`）一律排在末尾。
    """
    order = _point_order(model)

    def _key(block: dict) -> tuple[int, int, int, int, int]:
        kind = block.get("kind")
        if kind not in KIND_ORDER:
            raise RuntimeError(f"块的 kind 不在标注契约内，无法按规范序重排: {block.get('block_id')}（{kind!r}）")
        point_id = block.get("point_id")
        if point_id is None:
            return (1, 0, 0, 0, KIND_ORDER[kind])
        position = order.get(point_id)
        if position is None:
            raise RuntimeError(f"考点级块不在知识模型内，无法按规范序重排: {block.get('block_id')}")
        return (0, *position, KIND_ORDER[kind])

    return sorted(blocks, key=_key)


def merge_content_docs(existing: dict, new: dict, model: dict) -> dict:
    """逐批合并（plan § Data contracts 4「逐批合并语义」，PM 2026-09-11 裁决 F-405）。

    - 课程级块（`stage_plan[]` / `exam_strategy` / `review_schedule`）**整块替换**为本次生成结果
      —— 它们的 payload 每批都变，保留旧值会产生自相矛盾的阶段目标；
    - 考点级块（`blocks[]`）按 `block_id` 合并：同 id 替换、其余保留（批次间不丢已通过闸门的内容）；
    - 合并后 `blocks[]` 按唯一规范序重排（`order_blocks()`），保证字节确定性，且与非合并的全量生成路径
      同序（plan § Data contracts 4 二次裁决）；`model` 传**全课**知识模型：既有产物里历史批次的块
      不在本批 `--chapters` 的范围内，只有全课模型才能给它们定位章序。
    """
    if existing.get("course_code") != new.get("course_code"):
        raise RuntimeError(f"不能合并不同课程的产物: {existing.get('course_code')} ← {new.get('course_code')}")
    blocks = _point_level_blocks(existing, source="既有产物")
    blocks.update(_point_level_blocks(new, source="本次生成"))
    course_blocks = [block for block in new.get("blocks") or [] if block.get("point_id") is None]
    return {**new, "blocks": order_blocks([*blocks.values(), *course_blocks], model)}


def merge_content_file(path: Path, doc: dict, model: dict) -> dict:
    """`--merge` 的落盘口径：既有产物存在即合并（不存在 = 首批，直接返回本次产物）；损坏即失败关闭。"""
    if not path.is_file():
        return doc
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RuntimeError(f"既有产物不是合法 JSON，拒绝合并: {path.name}") from exc
    if not isinstance(existing, dict):
        raise RuntimeError(f"既有产物不是 JSON 对象，拒绝合并: {path.name}")
    return merge_content_docs(existing, doc, model)


def serialize(doc: dict) -> str:
    """确定性 JSON 文本（幂等复跑依赖此点）。"""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# --------------------------------------------------------------------------------------
# 失败关闭自检（Task 6 的 `ai-content` 层复用）
# --------------------------------------------------------------------------------------

def _check_label(entry: dict, where: str, problems: list[str]) -> None:
    if entry.get("ai_generated") is not True:
        problems.append(f"{where}: 缺 ai_generated: true")
    generator = entry.get("generator")
    if not isinstance(generator, dict):
        problems.append(f"{where}: 缺 generator")
    else:
        for key in ("backend", "model", "prompt_id", "prompt_version", "generated_at"):
            if not generator.get(key):
                problems.append(f"{where}: generator.{key} 为空")
    refs = entry.get("evidence_refs")
    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref for ref in refs):
        problems.append(f"{where}: evidence_refs 必须是非空字符串列表")
    if entry.get("review_state") != "machine_draft":
        problems.append(f"{where}: review_state 必须是 machine_draft")


def _review_schedule_problems(schedule, point_ids: set[str]) -> list[str]:
    problems: list[str] = []
    if not isinstance(schedule, dict):
        return ["缺 review_schedule"]
    _check_label(schedule, "review_schedule", problems)
    status = schedule.get("status")
    plans = schedule.get("plans")
    if status == "named_gap":
        if plans != []:
            problems.append("review_schedule: named_gap 时 plans 必须为空")
        for key in ("gap_impact", "next_evidence"):
            if not isinstance(schedule.get(key), str) or not schedule[key].strip():
                problems.append(f"review_schedule: named_gap 必须写非空 {key}")
        return problems
    if status != "planned":
        problems.append("review_schedule: status 必须是 planned 或 named_gap")
        return problems
    if not isinstance(plans, list) or len(plans) != len(HORIZONS):
        problems.append(f"review_schedule: planned 时 plans 必须恰 {len(HORIZONS)} 条")
        return problems
    exam_date = schedule.get("exam_date")
    weekly_hours = schedule.get("weekly_hours")
    if not isinstance(weekly_hours, (int, float)) or isinstance(weekly_hours, bool) or weekly_hours <= 0:
        problems.append("review_schedule: planned 时 weekly_hours 必须 > 0")
    if [plan.get("horizon_days") for plan in plans] != list(HORIZONS):
        problems.append(f"review_schedule: horizon_days 必须依次为 {list(HORIZONS)}")
    for plan in plans:
        where = f"review_schedule.plans[{plan.get('tier')}]"
        _check_label(plan, where, problems)
        if plan.get("end_date") != exam_date:
            problems.append(f"{where}: end_date 必须等于 exam_date")
        if isinstance(weekly_hours, (int, float)) and not isinstance(weekly_hours, bool):
            if plan.get("daily_minutes") != round(weekly_hours * 60 / 7):
                problems.append(f"{where}: daily_minutes 必须等于 round(weekly_hours * 60 / 7)")
        horizon = plan.get("horizon_days")
        if isinstance(exam_date, str) and isinstance(plan.get("start_date"), str) and isinstance(horizon, int):
            try:
                expected = (date.fromisoformat(exam_date) - timedelta(days=horizon - 1)).isoformat()
            except ValueError:
                problems.append(f"{where}: exam_date 不是合法日期")
                continue
            if plan["start_date"] != expected:
                problems.append(f"{where}: start_date 必须是 exam_date − (horizon_days − 1) 天")
        items = plan.get("items") or []
        if [item.get("day") for item in items] != list(range(1, len(items) + 1)):
            problems.append(f"{where}: items[].day 必须从 1 连续编号")
        dates = [item.get("date") for item in items]
        if not all(isinstance(value, str) for value in dates) or dates != sorted(dates) or len(set(dates)) != len(dates):
            problems.append(f"{where}: items[].date 必须单调递增")
        for item in items:
            if item.get("kind") not in SCHEDULE_ITEM_KINDS:
                problems.append(f"{where}: items[].kind 必须是 {SCHEDULE_ITEM_KINDS} 之一")
            for point_id in item.get("point_ids") or []:
                if point_id not in point_ids:
                    problems.append(f"{where}: items[].point_ids 含知识模型外的考核点 {point_id}")
        for repetition in plan.get("spaced_repetition") or []:
            if repetition.get("point_id") not in point_ids:
                problems.append(f"{where}: spaced_repetition 含知识模型外的考核点 {repetition.get('point_id')}")
            if list(repetition.get("offsets_days") or []) != list(SPACED_REPETITION_OFFSETS):
                problems.append(f"{where}: spaced_repetition.offsets_days 必须是 {list(SPACED_REPETITION_OFFSETS)}")
    return problems


def _official_sample_problems(block: dict, where: str) -> list[str]:
    """`official_sample` 块（唯一允许转载官方题文的分支）的凭据与长度校验（C2-009）。

    B1 产物不含此类块（`O2` 未收敛）；本函数服务于「未来产物不得靠自声明豁免抄袭守卫」：
    `provenance` 必须给出 `doc_id` + `locator` + `kind`，且转载长度必须在上限内。
    """
    problems: list[str] = []
    provenance = block.get("provenance")
    if not isinstance(provenance, dict):
        problems.append(f"{where}: official_sample 块必须带 provenance")
        return problems
    for key in ("doc_id", "locator", "kind"):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            problems.append(f"{where}: official_sample 的 provenance 缺少可核验字段 {key}")
    source = f"{block.get('text_md') or ''}\n{block.get('answer_md') or ''}"
    if len(source) > MAX_OFFICIAL_SAMPLE_CHARS:
        problems.append(
            f"{where}: official_sample 转载长度 {len(source)} 超过上限 {MAX_OFFICIAL_SAMPLE_CHARS}"
            "（公开仓不得整段转载官方题文）"
        )
    return problems


def validate_content_doc(doc: dict, model: dict) -> list[str]:
    """AI 备考层失败关闭自检：返回违规列表（空 = 通过）。"""
    problems: list[str] = []
    point_ids = set(_point_ids(model))
    declared = list(((model.get("exam") or {}).get("question_types")) or [])

    stages = doc.get("stage_plan")
    if not isinstance(stages, list) or [stage.get("stage") for stage in stages] != list(STAGES):
        problems.append(f"stage_plan 必须恰为五阶段且顺序为 {'/'.join(STAGES)}")
    for index, stage in enumerate(stages if isinstance(stages, list) else []):
        where = f"stage_plan[{index}]"
        _check_label(stage, where, problems)
        for key in ("goal", "done_when"):
            if not isinstance(stage.get(key), str) or not stage[key].strip():
                problems.append(f"{where}: {key} 为空")
        for key in ("inputs", "how", "outputs"):
            value = stage.get(key)
            if not isinstance(value, list) or not [item for item in value if isinstance(item, str) and item.strip()]:
                problems.append(f"{where}: {key} 必须是非空字符串列表")

    covered: dict[str, set[str]] = defaultdict(set)
    seen_ids: set[str] = set()
    exam_strategy_count = 0
    for block in doc.get("blocks") or []:
        block_id = block.get("block_id")
        where = f"block {block_id}"
        _check_label(block, where, problems)
        if not isinstance(block_id, str) or not block_id:
            problems.append(f"{where}: block_id 必须是非空字符串")
        elif block_id in seen_ids:
            problems.append(f"{where}: block_id 重复")
        seen_ids.add(block_id)
        kind = block.get("kind")
        if kind not in BLOCK_KINDS:
            problems.append(f"{where}: kind 必须是 {BLOCK_KINDS} 之一")
            continue
        if kind == "exam_strategy":
            if block.get("point_id") is not None or block.get("scope") != "course":
                problems.append(f"{where}: 课程级块必须是 point_id: null + scope: course")
            exam_strategy_count += 1
            text = block.get("text_md")
            if not isinstance(text, str) or len(text.strip()) < MIN_DRILL_CHARS:
                problems.append(f"{where}: text_md 为空或过短")
            continue
        point_id = block.get("point_id")
        if point_id not in point_ids:
            problems.append(f"{where}: point_id 不在知识模型（{point_id}）")
            continue
        covered[kind].add(point_id)
        text = block.get("text_md")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where}: text_md 为空")
            continue
        if kind == "explain":
            if EXPLAIN_SUMMARY_HEADING not in text or EXPLAIN_PITFALL_HEADING not in text:
                problems.append(f"{where}: explain 必须含 {EXPLAIN_SUMMARY_HEADING} 与 {EXPLAIN_PITFALL_HEADING}")
            if len(text) < MIN_EXPLAIN_CHARS:
                problems.append(f"{where}: explain 内容过短")
        elif kind == "memorize":
            if len(text) < MIN_MEMORIZE_CHARS or not any(marker in text for marker in MEMORY_MARKERS):
                problems.append(f"{where}: memorize 必须有记忆抓手且内容足够长")
        else:
            if not isinstance(block.get("answer_md"), str) or not block["answer_md"].strip():
                problems.append(f"{where}: drill 缺 answer_md")
            source_kind = block.get("source_kind")
            if source_kind not in SOURCE_KINDS:
                problems.append(f"{where}: drill 的 source_kind 必须是 {SOURCE_KINDS} 之一")
            if source_kind == "official_sample":
                # C2-009：豁免必须建立在**可核验的**凭据上，而不是「有个真值 dict」。
                # 旧实现 `not block.get("provenance")` 让 `{"doc_id": "x"}` 就能豁免 600 字逐字官方正文。
                problems.extend(_official_sample_problems(block, where))
            if declared and block.get("question_type") not in declared:
                problems.append(f"{where}: question_type 不在考纲声明的题型内（{block.get('question_type')}）")

    for point_id in _point_ids(model):
        for kind in ("explain", "memorize"):
            if point_id not in covered[kind]:
                problems.append(f"point {point_id}: 缺 {kind} 块")
    # W1：课程级 `exam_strategy` 块必须存在且唯一 —— 旧实现只在它**存在时**校验字段，
    # 于是整块删除（1180 → 1179）后两层闸门全绿，248 字的应试策略无声消失。
    if exam_strategy_count != 1:
        problems.append(
            f"blocks: 必须恰有 1 个 exam_strategy 课程级块（point_id: null + scope: course），实际 {exam_strategy_count} 个"
        )
    problems.extend(_review_schedule_problems(doc.get("review_schedule"), point_ids))
    return problems


# --------------------------------------------------------------------------------------
# 抄袭守卫输入（Task 6 的 `ai-content` 层复用）：8-gram 重合率
# --------------------------------------------------------------------------------------

def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _ngrams(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(len(text) - size + 1)]


def ngram_overlap_ratio(text: str, source_text: str, *, size: int = NGRAM_SIZE) -> float:
    """`text` 的字符级 n-gram 中，有多大比例也出现在 `source_text`（去空白后比对）。"""
    grams = _ngrams(_squeeze(text), size)
    if not grams:
        return 0.0
    source_grams = set(_ngrams(_squeeze(source_text), size))
    return sum(1 for gram in grams if gram in source_grams) / len(grams)


def _block_text(block: dict) -> str:
    return "\n".join(str(block[key]) for key in ("text_md", "answer_md") if isinstance(block.get(key), str))


def _stage_text(stage: dict) -> str:
    parts = [str(stage.get(key)) for key in ("stage", "goal", "done_when") if stage.get(key)]
    for key in ("inputs", "how", "outputs"):
        parts.extend(str(item) for item in stage.get(key) or [])
    return "\n".join(parts)


def emitted_texts(doc: dict) -> list[tuple[str, str]]:
    """AI 产物中**全部**会印到页面上的自然语言 → `(定位标签, 文本)`（C2-007）。

    旧实现只测 `blocks[]`，于是 `stage_plan[]` 与 `review_schedule` 的文本从不被测。
    8-gram 守卫的作用域 = 全部 AI 生成的自然语言，而不是 `blocks[]` 一个子集。
    """
    emitted: list[tuple[str, str]] = [
        (f"block {block.get('block_id')}", _block_text(block)) for block in doc.get("blocks") or []
    ]
    emitted += [
        (f"stage_plan[{index}]·{stage.get('stage')}", _stage_text(stage))
        for index, stage in enumerate(doc.get("stage_plan") or [])
    ]
    schedule = doc.get("review_schedule") or {}
    emitted += [
        (f"review_schedule.{key}", str(schedule[key]))
        for key in ("gap_impact", "next_evidence")
        if schedule.get(key)
    ]
    for plan in schedule.get("plans") or []:
        # `items[].focus` 是**确定性派生标签**（章序标签 + 考纲节标题逐字拼接），不是 LLM 正文：
        # 它与考纲必然高度重合（实测 85%），按契约豁免并只在 content-standard 记录口径（C2-007）。
        # 排程里真正由生成器产出的部分（日期 / 天数 / 每日时长）是无文案的结构值。
        emitted.append((f"review_schedule.plans[{plan.get('tier')}].spaced_repetition",
                       json.dumps(plan.get("spaced_repetition") or [], ensure_ascii=False, sort_keys=True)))
    return emitted



def plagiarism_violations(
    doc: dict, syllabus_text: str, *, threshold: float = PLAGIARISM_THRESHOLD, size: int = NGRAM_SIZE
) -> list[str]:
    """AI 产出与考纲抽取件的 n-gram 重合率超阈值即失败；`official_sample` 转载块豁免。

    作用域 = **全部 AI 生成的自然语言**（`emitted_texts()`），不只是 `blocks[]`（C2-007）；
    豁免只给 `official_sample` 转载块，且该块必须带**结构完整的** `provenance`（见 C2-009：
    旧实现只看真值，`{"doc_id": "x"}` 就能豁免 600 字逐字官方正文）。
    """
    problems: list[str] = []
    exempt: set[str] = set()
    for block in doc.get("blocks") or []:
        if block.get("source_kind") == "official_sample":
            exempt.add(f"block {block.get('block_id')}")
    for label, text in emitted_texts(doc):
        if label in exempt:
            continue
        ratio = ngram_overlap_ratio(text, syllabus_text, size=size)
        if ratio > threshold:
            problems.append(
                f"{label}: {size}-gram 重合率 {ratio:.1%} 超过阈值 {threshold:.0%}"
                "（改写后重试，不得调高阈值）"
            )
    return problems
