"""AI 备考层生成：三后端 + 标注契约 + 排程 + 抄袭守卫（Data contracts 4 / spec `D1` / `D2` / `AC9`）。

被校验对象：产物 `sources/jiangsu/courses/15040/content.json`、生产函数
`generate_content.generate_course_content()` 与 `llm_client.complete_json()`。

**源侧探针自备**：本文件自己读知识模型、自己算 8-gram、自己遍历 JSON，不调用生产 helper 回读断言值，
否则标注契约与覆盖率会与生产代码共用同一套约定而测不出来（对齐 `tests/test_knowledge_model.py`）。

分两段：
1. **机制段**（合成知识模型 + 注入传输 + `tmp_path` fixture 目录）：三后端对同一响应逐字段同构、
   重试/退避、schema 校验、密钥不外泄、agent 回填缺失即报错（不伪造）、排程三档确定性。
2. **产物段**（真实 `content.json` + 已录制 fixture）：离线 replay、切片覆盖 导论 + 第一章、
   B1 不转载题文、8-gram 守卫、CLI 复跑字节一致。

硬约束：`blocks[]` / `stage_plan[]` / `review_schedule`（含 `plans[]` 每一项）四件套必填（GC1）；
缺考期即命名缺口、不编造日期（GC3）；密钥只从环境变量读且报错只出现变量名（GC9）；
不联网（GC8）——真实网络路径一律 monkeypatch `urllib.request.urlopen`。
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import pytest

from lib.course_pipeline import generate_content as gc
from lib.course_pipeline import llm_client as llm

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path("sources/jiangsu/courses/15040/knowledge-model.json")
CONTENT_PATH = Path("sources/jiangsu/courses/15040/content.json")
SYLLABUS_DOC = Path(
    "sources/jiangsu/processed/syllabus/15040-xi-thought-gaogang-2024/document.extracted.md"
)
SLICE_SLUGS = ("intro", "ch01")
STAGE_NAMES = ("入门", "精读", "刷题", "冲刺", "复盘")
LABEL_KEYS = ("backend", "model", "prompt_id", "prompt_version", "generated_at")
MEMORY_MARKERS = ("记忆", "口诀", "对比", "联想", "串联", "谐音", "关键词", "顺口溜")
SECRET_SENTINEL = "sk-unit-test-sentinel-2f7c1d"
# 合成文本：只用于机制段，绝不进入仓内产物（产物段全部读真实 content.json）
SYNTHETIC_TEXT = "本行是机制测试用的合成文本，不进入任何仓内产物。" * 6
# 切片已落地（批 1：导论 + 第一章）：产物段断言不再挂 xfail —— 缺切片 / 缺 fixture 一律红灯。
# 重挂标记这条路走不通：pytest 9 默认把 XPASS 判失败，显式 `strict=False` 则由
# `test_suite_has_no_silent_xfail_markers` 兜住（F-402）。


# --------------------------------------------------------------------------------------
# 合成知识模型 + 注入传输（机制段）
# --------------------------------------------------------------------------------------

def _synthetic_model() -> dict:
    """最小知识模型：1 章 1 节 3 个考核点，三级要求各一（覆盖三种声明题型）。"""
    return {
        "schema_version": 1,
        "course_code": "99999",
        "model_version": "v1",
        "generated_at": "2026-01-01",
        "chapters": [
            {
                "ordinal": 0,
                "index": "导论",
                "slug": "intro",
                "title": "导论",
                "sections": [
                    {
                        "index": "1",
                        "title": "合成示例节",
                        "points": [
                            {
                                "id": "99999-intro-s1-p1",
                                "title": "合成识记点",
                                "requirement": "识记",
                                "quote": "合成识记点",
                                "locator": "L1",
                            },
                            {
                                "id": "99999-intro-s1-p2",
                                "title": "合成领会点",
                                "requirement": "领会",
                                "quote": "合成领会点",
                                "locator": "L2",
                            },
                            {
                                "id": "99999-intro-s1-p3",
                                "title": "合成应用点",
                                "requirement": "应用",
                                "quote": "合成应用点",
                                "locator": "L3",
                            },
                        ],
                    }
                ],
                "chapter_focus": [{"text": "合成本章重点", "locator": "L4"}],
            }
        ],
        "exam": {
            "question_types": ["单项选择题", "简答题", "材料题"],
            "question_types_provenance": {"doc_id": "syllabus:99999", "locator": "L5"},
            "duration_minutes": None,
            "duration_status": "named_gap",
            "sample_paper": {"doc_id": "syllabus:99999", "locator": "L6"},
        },
    }


def _two_chapter_model() -> dict:
    """两个章（intro / ch01）各 1 节 3 点：分批生成与 `--merge` 的最小可测模型（机制段用）。"""
    model = _synthetic_model()
    second = json.loads(json.dumps(model["chapters"][0], ensure_ascii=False))
    second.update({"ordinal": 1, "index": "第一章", "slug": "ch01", "title": "第一章 合成章"})
    for section in second["sections"]:
        for point in section["points"]:
            point["id"] = point["id"].replace("-intro-", "-ch01-")
    return {**model, "chapters": [model["chapters"][0], second]}


class _FakeResponse:
    """`urlopen` 替身：上下文管理器 + `read()`（对齐 `tests/test_official_source.py`）。"""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def _synthetic_response(system: str, payload: dict) -> dict:
    if "explain_point" in system:
        return {"text_md": f"### 要点梳理\n{SYNTHETIC_TEXT}\n### 易错点\n{SYNTHETIC_TEXT}"}
    if "memorize_point" in system:
        return {"text_md": f"记忆法（合成）：{SYNTHETIC_TEXT}"}
    if "drill_point" in system:
        question_type = payload["question_type"]
        return {
            "question_type": question_type,
            "text_md": f"（合成 {question_type} 题干）{SYNTHETIC_TEXT}",
            "answer_md": f"（合成答案与解析）{SYNTHETIC_TEXT}",
        }
    if "stage_plan" in system:
        return {
            "stages": [
                {
                    "stage": stage,
                    "goal": f"{stage}阶段的合成目标。",
                    "inputs": [f"{stage}阶段输入"],
                    "how": [f"{stage}阶段做法"],
                    "outputs": [f"{stage}阶段产出"],
                    "done_when": f"{stage}阶段完成判据。",
                }
                for stage in STAGE_NAMES
            ],
            "exam_strategy": {"text_md": f"（合成应试策略）{SYNTHETIC_TEXT}"},
        }
    raise AssertionError(f"未预期的 prompt 文本：{system[:40]!r}")


class _FakeLLM:
    """OpenAI 兼容端点的注入传输：记录请求，按 prompt 返回合成响应。"""

    def __init__(self, responder=_synthetic_response) -> None:
        self.requests: list[dict] = []
        self.responder = responder

    def urlopen(self, request, timeout=None):  # noqa: ANN001, ARG002 - 替身签名对齐 urlopen
        body = json.loads(request.data.decode("utf-8"))
        self.requests.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "headers": dict(request.headers),
                "body": body,
            }
        )
        payload = json.loads(body["messages"][1]["content"])
        response = self.responder(body["messages"][0]["content"], payload)
        envelope = {"choices": [{"message": {"content": json.dumps(response, ensure_ascii=False)}}]}
        return _FakeResponse(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))


def _wire(monkeypatch, tmp_path, *, record: bool, responder=_synthetic_response) -> _FakeLLM:
    """把三个后端都指到 tmp：注入传输 + tmp fixture 目录 + tmp `.agent-task` 根。"""
    fake = _FakeLLM(responder)
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(llm, "FIXTURES_DIR", tmp_path / "fixtures" / "llm")
    monkeypatch.setattr(llm, "COURSES_DIR", tmp_path / "courses")
    monkeypatch.setattr(llm, "RECORD_FIXTURES", record)
    monkeypatch.setenv("ZIKAO_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("ZIKAO_LLM_API_KEY", SECRET_SENTINEL)
    monkeypatch.setenv("ZIKAO_LLM_MODEL", "fake-model")
    return fake


def _probe_payload() -> dict:
    point = _synthetic_model()["chapters"][0]["sections"][0]["points"][0]
    return {"course_code": "99999", "point": dict(point)}


# --------------------------------------------------------------------------------------
# 源侧探针（机制段与产物段共用；不调用生产 helper）
# --------------------------------------------------------------------------------------

def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _model() -> dict:
    return _json(ROOT / MODEL_PATH)


def _artifact() -> dict:
    return _json(ROOT / CONTENT_PATH)


def _point_ids(model: dict) -> list[str]:
    return [p["id"] for c in model["chapters"] for s in c["sections"] for p in s["points"]]


def _quote_by_point(model: dict) -> dict[str, str]:
    return {p["id"]: p["quote"] for c in model["chapters"] for s in c["sections"] for p in s["points"]}


def _artifact_slugs() -> tuple[str, ...]:
    """产物实际覆盖的章 slug（由 `point_id` 反推）——Task 4b 分批扩展后本测试仍成立。"""
    slugs = {b["point_id"].split("-")[1] for b in _artifact()["blocks"] if b.get("point_id")}
    return tuple(c["slug"] for c in _model()["chapters"] if c["slug"] in slugs)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _scoped_model(*slugs: str, exam: dict | None = None) -> dict:
    model = gc.select_chapters(_model(), slugs)
    if exam:
        model = {**model, "exam": {**model["exam"], **exam}}
    return model


def _batch_responder(system: str, payload: dict) -> dict:
    """在合成响应里带上「本批覆盖的章」——真实模型同样按输入产出课程级内容（合并语义才可测）。"""
    response = _synthetic_response(system, payload)
    if "stage_plan" in system:
        label = "、".join(chapter["index"] for chapter in payload["chapters"])
        response["stages"][0]["goal"] = f"{response['stages'][0]['goal']}（{label}）"
        response["exam_strategy"]["text_md"] = f"{response['exam_strategy']['text_md']}（{label}）"
    return response


def _point_blocks(doc: dict) -> dict[str, dict]:
    """考点级块（`point_id` 非空）按 `block_id` 索引 —— 合并语义的比对基。"""
    return {block["block_id"]: block for block in doc["blocks"] if block.get("point_id") is not None}


def _exam_strategy(doc: dict) -> dict:
    return next(block for block in doc["blocks"] if block["kind"] == "exam_strategy")


def _assert_labelled(entry: dict, where: str) -> None:
    assert entry.get("ai_generated") is True, f"{where}: 缺 ai_generated: true"
    generator = entry.get("generator")
    assert isinstance(generator, dict), f"{where}: 缺 generator"
    for key in LABEL_KEYS:
        assert generator.get(key), f"{where}: generator.{key} 为空"
    refs = entry.get("evidence_refs")
    assert isinstance(refs, list) and refs, f"{where}: evidence_refs 必须非空"
    assert all(isinstance(ref, str) and ref for ref in refs), f"{where}: evidence_refs 元素必须是字符串"
    assert entry.get("review_state") == "machine_draft", f"{where}: review_state 必须是 machine_draft"


def _assert_labelled_everywhere(doc: dict) -> None:
    for index, stage in enumerate(doc["stage_plan"]):
        _assert_labelled(stage, f"stage_plan[{index}]")
    for block in doc["blocks"]:
        _assert_labelled(block, f"block {block.get('block_id')}")
    schedule = doc["review_schedule"]
    _assert_labelled(schedule, "review_schedule")
    for plan in schedule["plans"]:
        _assert_labelled(plan, f"review_schedule.plans[{plan.get('tier')}]")


def _normalized(doc: dict) -> dict:
    """把 `generated_at` 归一为常量（AC9 幂等口径）。"""
    if isinstance(doc, dict):
        return {k: ("<generated_at>" if k == "generated_at" else _normalized(v)) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_normalized(v) for v in doc]
    return doc


def _normalized_backend(doc: dict) -> dict:
    """在三后端同构比对时再归一出处后端（`generator.backend` 记录实际执行体，本就该不同）。"""
    if isinstance(doc, dict):
        return {
            k: ("<backend>" if k == "backend" else _normalized_backend(v))
            for k, v in doc.items()
        }
    if isinstance(doc, list):
        return [_normalized_backend(v) for v in doc]
    return doc


def _fixture_entry(prompt_id: str, prompt_version: str, payload: dict) -> dict:
    doc = _json(llm.FIXTURES_DIR / f"{prompt_id}.{prompt_version}.json")
    return doc["responses"][llm.payload_hash(payload)]


# --------------------------------------------------------------------------------------
# 机制段：三后端 / 重试 / schema / 密钥 / agent 回填 / 排程
# --------------------------------------------------------------------------------------

def test_cli_backend_uses_injected_transport(monkeypatch, tmp_path):
    fake = _wire(monkeypatch, tmp_path, record=False)
    payload = _probe_payload()
    response = llm.complete_json("explain_point", "v1", payload, backend="cli")

    assert response["text_md"].startswith("### 要点梳理")
    sent = fake.requests[0]
    assert sent["method"] == "POST"
    assert sent["url"] == "https://llm.invalid/v1/chat/completions"
    assert sent["body"]["model"] == "fake-model"
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert sent["body"]["messages"][0]["role"] == "system"
    assert json.loads(sent["body"]["messages"][1]["content"]) == payload
    assert sent["headers"]["Authorization"] == f"Bearer {SECRET_SENTINEL}"
    generator = llm.generator_metadata("explain_point", "v1", payload, backend="cli")
    assert generator["backend"] == "cli"
    assert generator["model"] == "fake-model"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", generator["generated_at"])


def test_cli_backend_retries_with_backoff_then_raises(monkeypatch, tmp_path):
    delays: list[float] = []

    def _bad_response(system, payload):  # noqa: ARG001 - 替身签名固定
        return {"unexpected": "字段不符 schema"}

    fake = _wire(monkeypatch, tmp_path, record=False, responder=_bad_response)
    monkeypatch.setattr(time, "sleep", delays.append)

    with pytest.raises(RuntimeError) as err:
        llm.complete_json("explain_point", "v1", _probe_payload(), backend="cli")

    assert len(fake.requests) == 3, "3 次尝试 = 1 次调用 + 2 次重试"
    assert delays == [1, 2], "指数退避必须逐次加倍"
    assert "explain_point.v1" in str(err.value)
    assert "不放宽 schema" in str(err.value)


def test_missing_api_key_raises_named_variable(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=False)
    monkeypatch.delenv("ZIKAO_LLM_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as err:
        llm.complete_json("explain_point", "v1", _probe_payload(), backend="cli")

    message = str(err.value)
    assert "ZIKAO_LLM_API_KEY" in message
    assert "ZIKAO_LLM_BASE_URL" not in message
    assert SECRET_SENTINEL not in message


def test_no_secret_in_errors(monkeypatch, tmp_path, capsys):
    def _boom(request, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("connection refused")

    _wire(monkeypatch, tmp_path, record=False)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    with pytest.raises(RuntimeError) as err:
        llm.complete_json("explain_point", "v1", _probe_payload(), backend="cli")

    captured = capsys.readouterr()
    assert SECRET_SENTINEL not in str(err.value)
    assert SECRET_SENTINEL not in captured.out + captured.err


def test_replay_missing_fixture_fails_loudly(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=False)

    with pytest.raises(RuntimeError) as err:
        llm.complete_json("explain_point", "v1", _probe_payload(), backend="replay")

    assert "explain_point.v1.json" in str(err.value), "缺 fixture 必须点名文件，不得回落模板"


def test_record_then_replay_is_field_identical(monkeypatch, tmp_path):
    payload = _probe_payload()
    _wire(monkeypatch, tmp_path, record=True)
    live = llm.complete_json("explain_point", "v1", payload, backend="cli")
    monkeypatch.setattr(llm, "RECORD_FIXTURES", False)
    replayed = llm.complete_json("explain_point", "v1", payload, backend="replay")

    assert replayed == live
    generator = llm.generator_metadata("explain_point", "v1", payload, backend="replay")
    assert generator["backend"] == "cli", "replay 必须回放录制时的来源后端（产物字节可复现）"
    assert generator["model"] == "fake-model"


def test_agent_backend_bundle_round_trip(monkeypatch, tmp_path):
    payload = _probe_payload()
    _wire(monkeypatch, tmp_path, record=True)
    expected = llm.complete_json("explain_point", "v1", payload, backend="cli")
    monkeypatch.setattr(llm, "RECORD_FIXTURES", False)

    with pytest.raises(llm.AgentTasksPendingError) as err:
        llm.complete_json("explain_point", "v1", payload, backend="agent")

    missing = err.value.missing
    assert [path.name for path in missing] == ["explain_point-1.result.json"]
    bundle_path = missing[0].with_name("explain_point-1.json")
    bundle = _json(bundle_path)
    assert bundle["prompt_id"] == "explain_point"
    assert bundle["prompt_version"] == "v1"
    assert bundle["payload"] == payload
    assert "explain_point" in bundle["instructions"]
    assert bundle["payload_hash"] == llm.payload_hash(payload)
    assert str(missing[0].relative_to(tmp_path)) in str(err.value)

    missing[0].write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
    response = llm.complete_json("explain_point", "v1", payload, backend="agent")
    assert response == expected, "三后端对同一响应必须逐字段同构（GC8）"
    # 同一 payload 复跑不得新增第二个 bundle（回填结果跨次运行仍然有效）
    assert llm.prepare_agent_tasks("99999", [("explain_point", "v1", payload)]) == []


def test_agent_backend_lists_every_missing_result(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=False)
    model = _synthetic_model()
    jobs = [
        (prompt_id, version, payload)
        for prompt_id, version, payload in gc.call_plan(model)
        if prompt_id == "drill_point"
    ]
    assert len(jobs) == 3

    missing = llm.prepare_agent_tasks(model["course_code"], jobs)

    assert [path.name for path in missing] == [
        "drill_point-1.result.json",
        "drill_point-2.result.json",
        "drill_point-3.result.json",
    ]
    with pytest.raises(llm.AgentTasksPendingError) as err:
        gc.generate_course_content(ROOT, model, backend="agent")
    assert len(err.value.missing) == len(gc.call_plan(model)), "必须列出全部缺失结果，不是只报第一个"


def test_generate_content_labels_every_block(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=True)
    model = _synthetic_model()
    doc = gc.generate_course_content(ROOT, model, backend="cli")

    assert gc.validate_content_doc(doc, model) == []
    _assert_labelled_everywhere(doc)
    assert doc["course_code"] == "99999"
    assert set(doc["generator"]["prompt_versions"]) == {
        "explain_point",
        "memorize_point",
        "drill_point",
        "stage_plan",
    }


def test_stage_plan_has_five_stages(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=True)
    doc = gc.generate_course_content(ROOT, _synthetic_model(), backend="cli")

    assert [stage["stage"] for stage in doc["stage_plan"]] == list(STAGE_NAMES)
    assert len(doc["stage_plan"]) == 5
    for stage in doc["stage_plan"]:
        for key in ("inputs", "how", "outputs"):
            assert isinstance(stage[key], list) and stage[key], f"{stage['stage']}.{key}"
        assert stage["goal"].strip(), f"{stage['stage']}.goal"
        assert stage["done_when"].strip(), f"{stage['stage']}.done_when"


def test_point_ids_exist_in_model(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=True)
    model = _synthetic_model()
    doc = gc.generate_course_content(ROOT, model, backend="cli")
    known = set(_point_ids(model))

    for block in doc["blocks"]:
        if block.get("point_id") is not None:
            assert block["point_id"] in known, block["block_id"]
    for plan in doc["review_schedule"]["plans"]:
        for item in plan["items"]:
            for point_id in item["point_ids"]:
                assert point_id in known, plan["tier"]
        for repetition in plan["spaced_repetition"]:
            assert repetition["point_id"] in known, plan["tier"]


def test_drill_blocks_carry_answer_and_source_kind(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=True)
    model = _synthetic_model()
    doc = gc.generate_course_content(ROOT, model, backend="cli")

    drills = [block for block in doc["blocks"] if block["kind"] == "drill"]
    assert len(drills) == 3
    for block in drills:
        assert block["answer_md"].strip()
        assert block["source_kind"] in {"ai_generated", "official_sample"}
        assert block["question_type"] in model["exam"]["question_types"]

    template = drills[0]
    official = {
        "block_id": f"{template['point_id']}/drill-official",
        "kind": "drill",
        "point_id": template["point_id"],
        "ai_generated": True,
        "review_state": "machine_draft",
        "generator": dict(template["generator"]),
        "evidence_refs": ["syllabus:99999#L6"],
        "text_md": "（构造）官方样卷题文",
        "answer_md": "（构造）官方样卷答案",
        "source_kind": "official_sample",
        "question_type": template["question_type"],
        "provenance": {"doc_id": "syllabus:99999", "locator": "L6"},
    }
    with_provenance = {**doc, "blocks": [*doc["blocks"], official]}
    assert gc.validate_content_doc(with_provenance, model) == []

    without_provenance = {**doc, "blocks": [*doc["blocks"], {k: v for k, v in official.items() if k != "provenance"}]}
    problems = gc.validate_content_doc(without_provenance, model)
    assert any("provenance" in problem for problem in problems), problems


def test_review_schedule_named_gap_without_exam_date(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=True)
    doc = gc.generate_course_content(ROOT, _synthetic_model(), backend="cli")

    schedule = doc["review_schedule"]
    assert schedule["status"] == "named_gap"
    assert schedule["plans"] == []
    assert schedule["exam_date"] is None and schedule["weekly_hours"] is None
    assert schedule["gap_impact"].strip()
    assert schedule["next_evidence"].strip()
    # 「不得编造日期」只约束排程数据本身：`generator.generated_at` 是生成日期（GC1 必填），不属于考期事实。
    data = {key: value for key, value in schedule.items() if key != "generator"}
    assert not re.search(r"\d{4}-\d{2}-\d{2}", json.dumps(data, ensure_ascii=False)), "不得编造考期日期"
    assert not re.search(r"\d{4}年\d{1,2}月", json.dumps(data, ensure_ascii=False)), "不得编造考期日期"


def test_review_schedule_planned_has_three_tiers(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, record=True)
    model = {**_synthetic_model(), "exam": {**_synthetic_model()["exam"], "exam_date": "2026-10-25", "weekly_hours": 6}}
    doc = gc.generate_course_content(ROOT, model, backend="cli")

    schedule = doc["review_schedule"]
    assert schedule["status"] == "planned"
    assert schedule["exam_date"] == "2026-10-25"
    assert schedule["weekly_hours"] == 6
    assert [plan["horizon_days"] for plan in schedule["plans"]] == [30, 14, 7]
    assert [plan["tier"] for plan in schedule["plans"]] == ["30d", "14d", "7d"]
    for plan in schedule["plans"]:
        assert plan["end_date"] == "2026-10-25"
        assert plan["daily_minutes"] == round(6 * 60 / 7)
        days = [item["day"] for item in plan["items"]]
        assert days == list(range(1, len(days) + 1)), "day 必须从 1 连续编号"
        dates = [item["date"] for item in plan["items"]]
        assert dates == sorted(dates) and len(set(dates)) == len(dates), "items[].date 必须单调递增"
        assert all(item["kind"] in {"read", "drill", "review"} for item in plan["items"])
        assert plan["spaced_repetition"]

    # F-403：`plans[]` 非空时也要逐项满足四件套（GC1）—— 空 plans 会让标注断言空洞通过。
    assert schedule["plans"], "本用例必须构造出非空 plans（否则 plans[] 标注契约测不到）"
    _assert_labelled_everywhere(doc)


def test_select_chapters_rejects_unknown_selector():
    with pytest.raises(ValueError):
        gc.select_chapters(_model(), ("不存在的章",))


def test_prompt_pack_declares_course_scope():
    """F-401：四个提示词模板声明 `course_scope`；作用域外的课程没有提示词包。"""
    prompts = ("explain_point", "memorize_point", "drill_point", "stage_plan")

    for prompt_id in prompts:
        assert llm.prompt_course_scope(prompt_id, "v1") == ["15040"], prompt_id

    assert gc.out_of_scope_prompts("15040") == [], "15040 在作用域内，不得误判"
    assert gc.out_of_scope_prompts("15043") == [f"{prompt_id}.v1" for prompt_id in prompts]


def test_merge_replaces_course_blocks_and_keeps_point_blocks(monkeypatch, tmp_path):
    """F-405：课程级整块替换 / 考点级按 `block_id` 合并 / 复跑字节一致（plan § Data contracts 4）。"""
    _wire(monkeypatch, tmp_path, record=True, responder=_batch_responder)
    model = _two_chapter_model()
    # 有考期输入 → 三档排程按本批的章推导 → 课程级块逐批不同（替换语义才可测）
    model = {**model, "exam": {**model["exam"], "exam_date": "2026-10-25", "weekly_hours": 6}}
    batch1 = gc.generate_course_content(ROOT, gc.select_chapters(model, ("intro",)), backend="cli")
    batch2 = gc.generate_course_content(ROOT, gc.select_chapters(model, ("ch01",)), backend="cli")
    assert _point_blocks(batch1).keys().isdisjoint(_point_blocks(batch2)), "两批必须是互不相交的考点"
    assert batch1["stage_plan"] != batch2["stage_plan"], "两批的课程级块必须不同（否则本用例测不出替换）"
    assert batch1["review_schedule"] != batch2["review_schedule"]

    path = tmp_path / "courses" / "15040" / "content.json"
    path.parent.mkdir(parents=True)
    path.write_text(gc.serialize(batch1), encoding="utf-8")

    merged = gc.merge_content_file(path, batch2)

    # (a) 课程级块整体来自本次生成（旧批次不得残留）
    assert merged["stage_plan"] == batch2["stage_plan"]
    assert merged["review_schedule"] == batch2["review_schedule"]
    assert _exam_strategy(merged) == _exam_strategy(batch2)
    assert merged["generator"] == batch2["generator"]
    assert merged["generated_at"] == batch2["generated_at"]

    # (b) 上一批的考点级块保留，本批的考点级块进入产物
    assert _point_blocks(merged) == {**_point_blocks(batch1), **_point_blocks(batch2)}

    # 合并后重排（`point_id` → `kind`），课程级块在末尾 → 字节确定性
    keys = [(block["point_id"], block["kind"]) for block in merged["blocks"]]
    assert keys == sorted(keys, key=lambda item: (item[0] is None, item[0] or "", item[1]))

    # (c) 复跑合并字节一致（排序是不动点）
    path.write_text(gc.serialize(merged), encoding="utf-8")
    assert gc.serialize(gc.merge_content_file(path, batch2)) == gc.serialize(merged)


def test_merge_replaces_same_block_id_and_refuses_other_course(monkeypatch, tmp_path):
    """F-405：同 `block_id` 整块替换（不新增重复块）；跨课程合并失败关闭。"""
    _wire(monkeypatch, tmp_path, record=True)
    model = _two_chapter_model()
    batch1 = gc.generate_course_content(ROOT, gc.select_chapters(model, ("intro",)), backend="cli")
    batch2 = gc.generate_course_content(ROOT, gc.select_chapters(model, ("ch01",)), backend="cli")

    rewritten = next(block for block in batch1["blocks"] if block["point_id"] is not None)
    rewritten = {**rewritten, "text_md": "（改版）同 block_id 必须整块替换。"}
    updated = {**batch2, "blocks": [rewritten, *batch2["blocks"]]}

    merged = gc.merge_content_docs(batch1, updated)

    block_ids = [block["block_id"] for block in merged["blocks"]]
    assert len(block_ids) == len(set(block_ids)), "合并不得产生重复 block_id"
    assert [block for block in merged["blocks"] if block["block_id"] == rewritten["block_id"]] == [rewritten]
    assert len(merged["blocks"]) == len(_point_blocks(batch1)) + len(_point_blocks(batch2)) + 1

    with pytest.raises(RuntimeError):
        gc.merge_content_docs(batch1, {**batch2, "course_code": "15043"})


# --------------------------------------------------------------------------------------
# 产物段：真实 content.json + 已录制 fixture
# --------------------------------------------------------------------------------------

def test_replay_backend_is_offline(monkeypatch):
    def _boom(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("replay 不得联网")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    model = _scoped_model(*_artifact_slugs())
    doc = gc.generate_course_content(ROOT, model, backend="replay")

    assert gc.validate_content_doc(doc, model) == []
    by_kind = defaultdict(set)
    for block in doc["blocks"]:
        if block.get("point_id"):
            by_kind[block["kind"]].add(block["point_id"])
    for point_id in _point_ids(model):
        assert point_id in by_kind["explain"] and point_id in by_kind["memorize"], point_id


def test_slice_covers_every_point_in_intro_and_ch01():
    model = _model()
    slice_points = [
        p["id"]
        for c in model["chapters"]
        if c["slug"] in SLICE_SLUGS
        for s in c["sections"]
        for p in s["points"]
    ]
    assert len(slice_points) == 43, "切片 = 导论（5 节 25 点）+ 第一章（3 节 18 点）"

    by_kind = defaultdict(set)
    for block in _artifact()["blocks"]:
        if block.get("point_id"):
            by_kind[block["kind"]].add(block["point_id"])
    for point_id in slice_points:
        assert point_id in by_kind["explain"], f"{point_id} 缺 explain"
        assert point_id in by_kind["memorize"], f"{point_id} 缺 memorize"

    question_types = {block["question_type"] for block in _artifact()["blocks"] if block["kind"] == "drill"}
    assert question_types == set(model["exam"]["question_types"]), "drill 必须覆盖考纲声明的题型"


def test_every_block_labelled():
    _assert_labelled_everywhere(_artifact())


def test_b1_artifacts_have_no_official_sample():
    doc = _artifact()
    drills = [block for block in doc["blocks"] if block["kind"] == "drill"]
    assert drills
    assert {block["source_kind"] for block in drills} == {"ai_generated"}
    assert "official_sample" not in CONTENT_PATH.read_text(encoding="utf-8")
    assert all("provenance" not in block for block in doc["blocks"])


def test_content_quality_bar_for_slice():
    model = _model()
    quotes = _quote_by_point(model)
    block_texts = [
        (block["kind"], block["point_id"], block["text_md"]) for block in _artifact()["blocks"] if block.get("point_id")
    ]
    texts = [text for _, _, text in block_texts]
    assert len(set(texts)) == len(texts), "块文本不得重复（拒绝模板化 / 复制粘贴）"

    for kind, point_id, text in block_texts:
        assert len(text) >= 120, f"{point_id}/{kind} 内容过短"
        lines = {_squash(line) for line in text.splitlines() if line.strip()}
        assert _squash(quotes[point_id]) not in lines, f"{point_id}/{kind} 整行照抄考纲原句"
        if kind == "explain":
            assert "### 要点梳理" in text and "### 易错点" in text, f"{point_id}/explain 缺小节"
        if kind == "memorize":
            assert any(marker in text for marker in MEMORY_MARKERS), f"{point_id}/memorize 缺记忆抓手"

    drills = [block for block in _artifact()["blocks"] if block["kind"] == "drill"]
    for block in drills:
        assert len(block["text_md"]) >= 60 and len(block["answer_md"]) >= 60, block["block_id"]


def test_plagiarism_guard_computable_and_below_threshold():
    source = (ROOT / SYLLABUS_DOC).read_text(encoding="utf-8")
    problems = gc.plagiarism_violations(_artifact(), source)
    assert problems == [], problems

    copied = _squash(source)[1000:1300]
    copied_doc = {
        "blocks": [
            {"block_id": "x/explain", "kind": "explain", "text_md": copied},
            {
                "block_id": "y/drill",
                "kind": "drill",
                "source_kind": "official_sample",
                "text_md": copied,
                "answer_md": copied,
            },
        ]
    }
    assert gc.ngram_overlap_ratio(copied, source) > 0.9
    assert gc.ngram_overlap_ratio("本题内容完全自创，与考纲用词没有交集。", source) < 0.2
    flagged = gc.plagiarism_violations(copied_doc, source)
    assert len(flagged) == 1, "official_sample 转载块必须豁免，普通块必须被抓出"
    assert flagged[0].startswith("x/explain")


def test_replay_doc_is_byte_idempotent_offline(monkeypatch, tmp_path):
    """AC9 幂等口径：录制一次 → 离线 replay 两次，两次产物逐字节一致且等于首次产物。"""
    _wire(monkeypatch, tmp_path, record=True)
    model = _synthetic_model()
    first = gc.generate_course_content(ROOT, model, backend="cli")

    monkeypatch.setattr(llm, "RECORD_FIXTURES", False)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("replay 不得联网"),
    )
    again = gc.generate_course_content(ROOT, model, backend="replay")
    third = gc.generate_course_content(ROOT, model, backend="replay")

    assert gc.serialize(again) == gc.serialize(third) == gc.serialize(first), "replay 复跑必须字节一致"
    assert _normalized(again) == _normalized(first)
    assert again["review_schedule"]["generator"]["backend"] == "cli", "replay 回放录制时的来源后端"


def test_three_backends_produce_field_identical_docs(monkeypatch, tmp_path):
    """GC8：三后端对同一响应必须逐字段同构（agent 用录制响应回填，无 key、无网络）。"""
    model = _synthetic_model()
    payloads = [
        (prompt_id, prompt_version, payload)
        for prompt_id, prompt_version, payload in gc.call_plan(model)
    ]

    _wire(monkeypatch, tmp_path, record=True)
    expected = gc.generate_course_content(ROOT, model, backend="cli")

    recorded = {
        (prompt_id, prompt_version, llm.payload_hash(payload)): llm.complete_json(
            prompt_id, prompt_version, payload, backend="replay"
        )
        for prompt_id, prompt_version, payload in payloads
    }
    monkeypatch.setattr(llm, "RECORD_FIXTURES", False)
    missing = llm.prepare_agent_tasks(model["course_code"], payloads)
    assert missing, "agent 后端必须先写出待回填的任务包"
    for bundle in sorted(llm.agent_task_dir(model["course_code"]).glob("*.json")):
        if bundle.name.endswith(".result.json"):
            continue
        job = _json(bundle)
        assert job["expect_result"] == bundle.with_name(f"{bundle.stem}.result.json").name
        response = recorded[(job["prompt_id"], job["prompt_version"], job["payload_hash"])]
        bundle.with_name(job["expect_result"]).write_text(
            json.dumps(response, ensure_ascii=False), encoding="utf-8"
        )

    agent_doc = gc.generate_course_content(ROOT, model, backend="agent")

    assert _normalized_backend(agent_doc) == _normalized_backend(expected), "agent 后端产物必须与 cli 后端逐字段同构"
    assert agent_doc["generator"]["backend"] == "agent"


def test_record_fixtures_flag_writes_every_prompt_and_replay_is_offline(monkeypatch, tmp_path):
    """`--record-fixtures` 落盘四个提示词的录制响应；此后 replay 在无网络下产出完整文档。"""
    _wire(monkeypatch, tmp_path, record=True)
    model = _synthetic_model()
    gc.generate_course_content(ROOT, model, backend="cli")

    written = sorted(path.name for path in llm.FIXTURES_DIR.glob("*.json"))
    assert written == [
        "drill_point.v1.json",
        "explain_point.v1.json",
        "memorize_point.v1.json",
        "stage_plan.v1.json",
    ], "每个提示词至少一组录制响应（Task 4 Step 5 第 4 条的 fixture 覆盖口径）"

    monkeypatch.setattr(llm, "RECORD_FIXTURES", False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("replay 不得联网"))
    doc = gc.generate_course_content(ROOT, model, backend="replay")

    assert gc.validate_content_doc(doc, model) == []
    for prompt_id in ("explain_point", "memorize_point", "drill_point", "stage_plan"):
        assert doc["generator"]["prompt_versions"][prompt_id] == "v1"


def test_cli_generate_reports_missing_evidence_and_skips_blocked_course():
    """CLI 失败关闭：缺 `evidence.json` → exit 2；非 `L1` → exit 0 且零 AI 产物（spec AC4）。"""
    missing = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "generate", "99999", "--backend", "replay"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 2
    assert "stage=generate missing:" in missing.stderr
    assert "evidence.json" in missing.stderr
    assert not (ROOT / "sources/jiangsu/courses/99999").exists()

    blocked = subprocess.run(
        # `--merge` 必须被 CLI 接受（未识别参数会 exit 2）；非 L1 在合并之前就跳过、零写盘。
        [sys.executable, "scripts/build-course-content.py", "generate", "00023", "--backend", "replay", "--merge"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 0, blocked.stderr
    assert "跳过" in blocked.stdout
    assert not (ROOT / "sources/jiangsu/courses/00023/content.json").exists()


def test_cli_generate_refuses_a_course_without_a_prompt_pack():
    """F-401 失败关闭：15043 是真实 L1 课程但没有提示词包 → 拒绝，不得用 15040 的模板出内容。"""
    proc = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "generate", "15043", "--backend", "replay"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0, proc.stdout
    assert "15043" in proc.stderr
    assert "提示词包" in proc.stderr
    for prompt_id in ("explain_point.v1", "memorize_point.v1", "drill_point.v1", "stage_plan.v1"):
        assert prompt_id in proc.stderr, f"必须点名缺失的提示词包：{prompt_id}"
    assert not (ROOT / "sources/jiangsu/courses/15043/content.json").exists(), "拒绝路径不得写盘"


def test_cli_generate_replay_reproduces_artifact_byte_identically():
    slugs = _artifact_slugs()
    before = CONTENT_PATH.read_bytes()

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/build-course-content.py",
            "generate",
            "15040",
            "--backend",
            "replay",
            "--chapters",
            ",".join(slugs),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "blocks=" in proc.stdout
    assert CONTENT_PATH.read_bytes() == before, "replay 复跑必须字节一致"


def test_full_course_replay_with_a_missing_fixture_fails_loudly(monkeypatch, tmp_path):
    """F-404 守卫：全课 replay 缺任一条录制响应都必须失败关闭 —— 与切片进度无关（不回落模板）。

    用「不完整的合成 fixture 集合」构造缺条场景（而非读实时产物），因此 18 章齐备后同样成立。
    """
    model = _model()
    wanted = llm.payload_hash(gc.call_plan(model)[0][2])
    recorded = _json(llm.FIXTURES_DIR / "explain_point.v1.json")["responses"]
    others = sorted(key for key in recorded if key != wanted)
    assert others, "录制文件必须还有其它 payload 的响应（否则本用例退化为空 fixture 目录）"

    monkeypatch.setattr(llm, "FIXTURES_DIR", tmp_path / "fixtures" / "llm")
    llm.FIXTURES_DIR.mkdir(parents=True)
    (llm.FIXTURES_DIR / "explain_point.v1.json").write_text(
        json.dumps(
            {"prompt_id": "explain_point", "prompt_version": "v1", "responses": {others[0]: recorded[others[0]]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    before = CONTENT_PATH.read_bytes()

    with pytest.raises(RuntimeError) as err:
        gc.generate_course_content(ROOT, model, backend="replay")

    assert "missing fixture" in str(err.value), "缺录制响应必须失败，绝不回落模板"
    assert f"explain_point.v1.json#{wanted}" in str(err.value), "必须点名缺失的 payload"
    assert CONTENT_PATH.read_bytes() == before, "失败路径不得写盘"


def _cli_module():
    """把 kebab-case 入口脚本当模块加载（对齐 `tests/conftest.py` 对其它入口脚本的做法）。"""
    spec = importlib.util.spec_from_file_location("build_course_content", ROOT / "scripts/build-course-content.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cli_root(tmp_path: Path):
    """tmp 根上的 CLI 装置：入口按 `__file__` 推导 ROOT → 加载后把 ROOT 指向 tmp

    复用仓内 `scripts/lib`（软链）与已录制 fixture（`llm_client` 按真实仓根定位），
    只把 15040 的 `evidence.json` / `knowledge-model.json` 与考纲抽取件（软链）放进 tmp 根，
    因此 CLI 写出的 `content.json` 落在 tmp 里、真实产物字节不变。
    """
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "lib").symlink_to(ROOT / "scripts" / "lib", target_is_directory=True)
    course = root / "sources" / "jiangsu" / "courses" / "15040"
    course.mkdir(parents=True)
    for name in ("evidence.json", "knowledge-model.json"):
        shutil.copy(ROOT / "sources" / "jiangsu" / "courses" / "15040" / name, course / name)
    (root / "sources" / "jiangsu" / "processed").symlink_to(
        ROOT / "sources" / "jiangsu" / "processed", target_is_directory=True
    )
    cli = _cli_module()
    cli.ROOT = root
    return cli, course / "content.json"


def test_cli_generate_merge_rewrites_sorted_blocks_and_is_idempotent(tmp_path):
    """F-405 CLI 接线：`--merge` 替换课程级块、保留上一批的考点级块、重排块序、复跑字节一致。"""
    cli, content_path = _cli_root(tmp_path)
    real_before = CONTENT_PATH.read_bytes()

    def _generate(*, merge: bool) -> int:
        return cli.run_generate(
            "15040", backend="replay", chapters=["intro", "ch01"], record_fixtures=False, merge=merge
        )

    assert _generate(merge=False) == 0
    fresh = _json(content_path)

    # 造「上一批的产物」：课程级块已过时 + 一条本批不再生成的考点级块
    stale = json.loads(json.dumps(fresh, ensure_ascii=False))
    stale["stage_plan"][0]["goal"] = "（旧批次）阶段目标"
    kept = {
        **next(block for block in fresh["blocks"] if block["kind"] == "explain"),
        "block_id": "15040-ch02-s1-p1/explain",
        "point_id": "15040-ch02-s1-p1",
        "text_md": "（上一批留下的块）必须保留。",
    }
    stale["blocks"].append(kept)
    content_path.write_text(gc.serialize(stale), encoding="utf-8")

    assert _generate(merge=True) == 0
    merged = _json(content_path)

    assert _point_blocks(merged) == {**_point_blocks(fresh), kept["block_id"]: kept}, "上一批的考点级块必须保留"
    assert merged["stage_plan"] == fresh["stage_plan"], "课程级块必须整块替换为本次生成"
    assert merged["review_schedule"] == fresh["review_schedule"]
    assert _exam_strategy(merged) == _exam_strategy(fresh)
    keys = [(block["point_id"], block["kind"]) for block in merged["blocks"]]
    assert keys == sorted(keys, key=lambda item: (item[0] is None, item[0] or "", item[1])), "合并后必须重排"

    rerun = content_path.read_bytes()
    assert _generate(merge=True) == 0
    assert content_path.read_bytes() == rerun, "复跑合并必须字节一致"
    assert CONTENT_PATH.read_bytes() == real_before, "测试不得改动仓内产物"


def test_suite_has_no_silent_xfail_markers(request):
    """F-402 守卫：套件不得再挂非严格 `xfail` —— `strict=False` 会把真实回归变成静默通过。

    切片已落地，产物段断言都是普通测试（缺切片 / 缺 fixture 直接红灯）；本用例在整包运行时再兜一层：
    任何没有显式 `strict=True` 的 `xfail` 都判失败，因此「重新加标记把红灯变绿」这条路走不通。
    """
    offenders = [
        f"{item.nodeid}: {mark.kwargs}"
        for item in request.session.items
        for mark in item.iter_markers("xfail")
        if mark.kwargs.get("strict") is not True
    ]
    assert offenders == [], f"非严格 xfail 会吞掉真实回归：{offenders}"
