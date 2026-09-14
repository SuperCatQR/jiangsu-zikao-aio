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
import os
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


BLOCK_KIND_ORDER = {"explain": 0, "memorize": 1, "drill": 2, "exam_strategy": 3}


def _canonical_keys(model: dict, blocks: list[dict]) -> list[tuple]:
    """源侧探针：唯一规范序 = 知识模型章序 → 节序 → 点序 → `kind`，课程级块（`point_id: null`）在末尾。

    独立复算（不调用生产 helper），因此「两条生成路径是否同序」这件事测的是产物而不是实现自述。
    """
    positions = {
        point["id"]: (chapter["ordinal"], section_index, point_index)
        for chapter in model["chapters"]
        for section_index, section in enumerate(chapter["sections"])
        for point_index, point in enumerate(section["points"])
    }
    keys = []
    for block in blocks:
        point_id = block.get("point_id")
        prefix = (1, 0, 0, 0) if point_id is None else (0, *positions[point_id])
        keys.append((*prefix, BLOCK_KIND_ORDER[block["kind"]]))
    return keys


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


def test_agent_bundle_index_is_built_once_per_batch(monkeypatch, tmp_path):
    """W5/QC3-010：目录索引必须**每批构建一次**并被复用，而不是每个 job 重建（O(n²) → O(n)）。

    旧实现 `prepare_agent_tasks` 构建 `indexes[prompt_id]` 后**从不读取**它，下一行仍调用
    `write_agent_bundle()`（内部又自行 `_bundle_index()`），且 `_call_agent` 每次再来一遍。
    实测 1196 个 bundle × 60 µs × 2 遍 ≈ 86 秒纯重复解析。

    断言方式：把 `_bundle_index` 计数打桩，跑一批 3+3 个 job（两个 prompt_id），
    重建次数必须 ≤ prompt_id 数量（每 id 一次），而不是 job 数量。
    """
    _wire(monkeypatch, tmp_path, record=False)
    model = _synthetic_model()
    jobs = [
        (prompt_id, version, payload)
        for prompt_id, version, payload in gc.call_plan(model)
        if prompt_id in {"explain_point", "drill_point"}
    ]
    assert len(jobs) >= 4, f"对照前提：至少两个 prompt_id 的多个 job，实际 {len(jobs)}"
    prompt_ids = {prompt_id for prompt_id, _v, _p in jobs}
    assert len(prompt_ids) >= 2

    real_index = llm._bundle_index
    calls: list[tuple[str, str]] = []

    def _counting(directory, prompt_id):
        calls.append((str(directory), prompt_id))
        return real_index(directory, prompt_id)

    monkeypatch.setattr(llm, "_bundle_index", _counting)
    llm.prepare_agent_tasks(model["course_code"], jobs)

    assert len(calls) <= len(prompt_ids), (
        f"索引必须每批每 prompt_id 只构建一次；job 数 {len(jobs)}、prompt_id 数 {len(prompt_ids)}、"
        f"实际重建 {len(calls)} 次"
    )
    assert sorted({prompt_id for _dir, prompt_id in calls}) == sorted(prompt_ids)

    # 第三向：索引在**同一目录未变更**时必须命中缓存（跨批次复用，`prepare_agent_tasks` 之外的路径）
    llm._BUNDLE_INDEX_CACHE.clear()
    calls.clear()
    directory = llm.agent_task_dir(model["course_code"])
    first = llm._bundle_index(directory, "explain_point")
    again = llm._bundle_index(directory, "explain_point")
    assert len(calls) == 2, "打桩本身必须被调用（否则断言是空转）"
    assert again is first, "目录未变更时索引必须走缓存返回同一对象"

    # 目录变更（新增 bundle）→ 缓存失效并重建，新键可见
    (directory / "explain_point-999.json").write_text(
        json.dumps({"payload_hash": "sentinel-hash-999"}, ensure_ascii=False), encoding="utf-8"
    )
    refreshed = llm._bundle_index(directory, "explain_point")
    assert "sentinel-hash-999" in refreshed, "目录 mtime 变化后索引必须重建，不得返回陈旧快照"


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
        # C2-009：豁免必须建立在可核验凭据上（doc_id + locator + kind），不是「有个真值 dict」
        "provenance": {"doc_id": "syllabus:99999", "locator": "L6", "kind": "official_syllabus"},
    }
    with_provenance = {**doc, "blocks": [*doc["blocks"], official]}
    assert gc.validate_content_doc(with_provenance, model) == []

    without_provenance = {**doc, "blocks": [*doc["blocks"], {k: v for k, v in official.items() if k != "provenance"}]}
    problems = gc.validate_content_doc(without_provenance, model)
    assert any("provenance" in problem for problem in problems), problems

    # C2-009 第二向：真值但**不完整**的 provenance 不得豁免（旧实现只判真值）
    hollow = {**doc, "blocks": [*doc["blocks"], {**official, "provenance": {"doc_id": "x"}}]}
    hollow_problems = gc.validate_content_doc(hollow, model)
    assert any("kind" in problem for problem in hollow_problems), hollow_problems

    # C2-009 第三向：转载长度必须有界
    overlong = {
        **doc,
        "blocks": [
            *doc["blocks"],
            {**official, "text_md": "官" * (gc.MAX_OFFICIAL_SAMPLE_CHARS + 1), "answer_md": "案"},
        ],
    }
    assert any("转载长度" in problem for problem in gc.validate_content_doc(overlong, model)), "超长转载必须被抓出"


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
    """F-401：四个提示词模板声明 `course_scope`；作用域外的课程没有提示词包。

    P-2（plan § 决议记录 R-1）：B-1 把作用域放宽到 `15043`，但**它不是通配**——
    作用域仍是一个显式白名单，作用域外的课码必须继续被拒。
    """
    prompts = ("explain_point", "memorize_point", "drill_point", "stage_plan")

    for prompt_id in prompts:
        scope = llm.prompt_course_scope(prompt_id, "v1")
        assert "15040" in scope, f"{prompt_id}：15040 必须在作用域内"
        assert "15043" in scope, f"{prompt_id}：B-1 放宽后 15043 必须在作用域内"
        assert "*" not in scope and "any" not in scope, f"{prompt_id}：作用域不得放宽成通配"

    assert gc.out_of_scope_prompts("15040") == [], "15040 在作用域内，不得误判"
    assert gc.out_of_scope_prompts("15043") == [], "B-1：15043 在作用域内，generate 必须可推进"

    # 反向用例（守护本用例存在的意义）：作用域外的课码仍必须 fail closed —— 15100 是 L1 课程，
    # 但仍不在提示词作用域内，不得因为「放宽」而变成「任何课程都能用这四个模板生成」。
    assert gc.out_of_scope_prompts("15044") == [f"{prompt_id}.v1" for prompt_id in prompts]
    assert gc.out_of_scope_prompts("99999") == [f"{prompt_id}.v1" for prompt_id in prompts]


def test_prompt_bodies_are_course_agnostic():
    """B-1 / P-2：模板正文不得绑定某一门课 —— 课码与学科事实一律由 payload 提供。

    只改 `course_scope` 而不改正文，就是用思政课模板给「中国近现代史纲要」出 255 个考点的内容
    （design note §0 的 P-3，已被 R-1 否决）；本用例锁住「正文去课程化」这一半。
    """
    banned = ("习近平", "新时代", "中国特色", "马克思主义", "两个确立", "15040", "15043")

    for prompt_id in ("explain_point", "memorize_point", "drill_point", "stage_plan"):
        text, _schema = llm.load_prompt(prompt_id, "v1")
        body = text.split("\n---\n", 1)[1]  # 去 frontmatter：`course_scope` 是唯一允许出现课码的地方
        for literal in banned:
            assert literal not in body, f"{prompt_id} 正文仍含课程绑定字面量：{literal}"
        assert "course_code" in body, f"{prompt_id} 必须把课程归属指向 payload 的 course_code"


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

    merged = gc.merge_content_file(path, batch2, model)

    # (a) 课程级块整体来自本次生成（旧批次不得残留）
    assert merged["stage_plan"] == batch2["stage_plan"]
    assert merged["review_schedule"] == batch2["review_schedule"]
    assert _exam_strategy(merged) == _exam_strategy(batch2)
    assert merged["generator"] == batch2["generator"]
    assert merged["generated_at"] == batch2["generated_at"]

    # (b) 上一批的考点级块保留，本批的考点级块进入产物
    assert _point_blocks(merged) == {**_point_blocks(batch1), **_point_blocks(batch2)}

    # 合并后按唯一规范序重排（知识模型章序 → 节序 → 点序 → `kind`），课程级块在末尾 → 两条路径字节可比
    keys = _canonical_keys(model, merged["blocks"])
    assert keys == sorted(keys), "合并后必须按知识模型的规范序重排（章序 → 节序 → 点序 → kind）"

    # (c) 复跑合并字节一致（排序是不动点）
    path.write_text(gc.serialize(merged), encoding="utf-8")
    assert gc.serialize(gc.merge_content_file(path, batch2, model)) == gc.serialize(merged)


def test_merge_replaces_same_block_id_and_refuses_other_course(monkeypatch, tmp_path):
    """F-405：同 `block_id` 整块替换（不新增重复块）；跨课程合并失败关闭。"""
    _wire(monkeypatch, tmp_path, record=True)
    model = _two_chapter_model()
    batch1 = gc.generate_course_content(ROOT, gc.select_chapters(model, ("intro",)), backend="cli")
    batch2 = gc.generate_course_content(ROOT, gc.select_chapters(model, ("ch01",)), backend="cli")

    rewritten = next(block for block in batch1["blocks"] if block["point_id"] is not None)
    rewritten = {**rewritten, "text_md": "（改版）同 block_id 必须整块替换。"}
    updated = {**batch2, "blocks": [rewritten, *batch2["blocks"]]}

    merged = gc.merge_content_docs(batch1, updated, model)

    block_ids = [block["block_id"] for block in merged["blocks"]]
    assert len(block_ids) == len(set(block_ids)), "合并不得产生重复 block_id"
    assert [block for block in merged["blocks"] if block["block_id"] == rewritten["block_id"]] == [rewritten]
    assert len(merged["blocks"]) == len(_point_blocks(batch1)) + len(_point_blocks(batch2)) + 1

    with pytest.raises(RuntimeError):
        gc.merge_content_docs(batch1, {**batch2, "course_code": "15043"}, model)


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


def test_exam_strategy_block_is_required_by_the_content_self_check():
    """W1 变异证明：删掉课程级 `exam_strategy` 块必须在 `validate_content_doc()` 处失败关闭。

    PM 实测的缺口：旧实现只在块**存在时**校验它的字段，于是 1180 → 1179 后
    `run_ai_content_gate` 与 `run_evidence_gate` 都返回 `[]`，248 字的应试策略无声消失。
    """
    model = _model()
    doc = _artifact()
    assert gc.validate_content_doc(doc, model) == [], "对照前提：committed content.json 自检通过"
    assert len(doc["blocks"]) == 1180, f"对照前提：committed blocks 为 1180，实际 {len(doc['blocks'])}"

    without = {**doc, "blocks": [b for b in doc["blocks"] if b["kind"] != "exam_strategy"]}
    assert len(without["blocks"]) == 1179
    problems = gc.validate_content_doc(without, model)
    assert any("exam_strategy" in p for p in problems), problems

    # 第二向：重复的课程级块也不得蒙混过关（闸门按「恰 1 个」对账）
    duplicated = {**doc, "blocks": [*doc["blocks"], next(b for b in doc["blocks"] if b["kind"] == "exam_strategy")]}
    dup_problems = gc.validate_content_doc(duplicated, model)
    assert any("exam_strategy" in p for p in dup_problems), dup_problems
    assert any("block_id 重复" in p for p in dup_problems), dup_problems


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
    assert "x/explain" in flagged[0]


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
    """F-401 失败关闭：作用域**外**的 L1 课程没有提示词包 → 拒绝，不得用别人的模板出内容。

    B-1 之后 `15043` 已进入作用域（见 `test_cli_generate_accepts_an_in_scope_course`），
    故这里改用仍是 L1、但不在作用域内的 `15044`：作用域是白名单而非通配，这一条必须一直是红的。
    """
    proc = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "generate", "15044", "--backend", "replay"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0, proc.stdout
    assert "15044" in proc.stderr
    assert "提示词包" in proc.stderr
    for prompt_id in ("explain_point.v1", "memorize_point.v1", "drill_point.v1", "stage_plan.v1"):
        assert prompt_id in proc.stderr, f"必须点名缺失的提示词包：{prompt_id}"
    assert not (ROOT / "sources/jiangsu/courses/15044/content.json").exists(), "拒绝路径不得写盘"


def test_cli_generate_accepts_an_in_scope_course():
    """B-1 的正向面：`15043` 进入作用域后，CLI 必须越过 scope 判据继续推进。

    本片（Task 1）只为 `15043` **解锁** generate。**I-1 裁定（评审后续修，2026-09-12）**：本用例只锁定
    「作用域守卫已放行」这一件事，断言与 Task 4/Task 5 的进度**无关**，避免被它们的正确工作推翻。
    """
    proc = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "generate", "15043", "--backend", "replay"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert "无提示词包" not in proc.stderr, f"B-1 未修好：15043 仍被 scope 判据拦下\n{proc.stderr}"
    assert "course_scope" not in proc.stderr, proc.stderr
    # `exit != 2` = 不再走「无提示词包」那条失败分支；若仍失败，失败路径不得写盘。
    assert proc.returncode != 2, f"15043 仍被判为 scope 外（exit 2）：{proc.stderr}"
    if proc.returncode != 0:
        assert not (ROOT / "sources/jiangsu/courses/15043/content.json").exists(), "失败路径不得写盘"


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


# --------------------------------------------------------------------------------------
# R6 / F-QC3-5：`15043` 的 replay 字节一致必须有**持久**守护（此前只有 `15040` 有）
# --------------------------------------------------------------------------------------

COURSE_43 = "15043"
MODEL_43_PATH = Path(f"sources/jiangsu/courses/{COURSE_43}/knowledge-model.json")
CONTENT_43_PATH = Path(f"sources/jiangsu/courses/{COURSE_43}/content.json")


def _artifact_43() -> dict:
    return _json(ROOT / CONTENT_43_PATH)


def _artifact_43_slugs() -> tuple[str, ...]:
    """`15043` 产物覆盖的章 slug（由 `point_id` 反推，口径与 `_artifact_slugs()` 相同）。"""
    slugs = {b["point_id"].split("-")[1] for b in _artifact_43()["blocks"] if b.get("point_id")}
    model = _json(ROOT / MODEL_43_PATH)
    return tuple(c["slug"] for c in model["chapters"] if c["slug"] in slugs)


def _generate_43_replay() -> subprocess.CompletedProcess:
    """CLI `generate 15043 --backend replay`（全课，不传 `--chapters`）。"""
    return subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "generate", COURSE_43, "--backend", "replay"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_generate_replay_reproduces_15043_artifact_byte_identically():
    """R6：`15043` 的 `content.json` = `f(fixture)` —— replay 复跑必须**逐字节**重现 committed 产物。

    改前 `15043` 的唯一覆盖是 `test_cli_generate_accepts_an_in_scope_course` 的 `returncode != 2`
    弱断言（只锁「作用域放行」），字节一致性只在 `15040` 上被守护（`MODEL_PATH` / `CONTENT_PATH` 钉死
    `15040`，`tests/test_render_pages.py:15` 亦然）。于是「产物 = f(fixture)」对 `15043` 是一次性人工验证，
    下一轮改 fixture 或改生成逻辑都不会被这套件发现。

    两次运行都比对 committed 字节：第一次证明「committed 产物可由 fixture 精确重建」，
    第二次证明「重建是幂等的」（`generated_at` 在 replay 下取自录制响应，故无需归一化）。
    断言用 sha256 + 精确字节双重口径，失败信息里直接给出摘要便于定位。
    """
    import hashlib

    committed_path = ROOT / CONTENT_43_PATH
    assert committed_path.is_file(), f"committed 产物缺失: {CONTENT_43_PATH}"
    committed = committed_path.read_bytes()
    committed_sha = hashlib.sha256(committed).hexdigest()

    # 对照前提：产物确实覆盖全部 10 章、766 块（否则「字节一致」可能只是空跑）
    artifact = _artifact_43()
    assert len(artifact["blocks"]) == 766, f"对照前提：15043 blocks 应为 766，实际 {len(artifact['blocks'])}"
    assert len(_artifact_43_slugs()) == 10, "对照前提：15043 覆盖 10 章"

    # 第一次：replay 重建必须与 committed 逐字节相同
    proc = _generate_43_replay()
    assert proc.returncode == 0, f"replay 失败：{proc.stderr}"
    assert "15043" in proc.stdout, proc.stdout
    first = committed_path.read_bytes()
    assert hashlib.sha256(first).hexdigest() == committed_sha, (
        "replay 未能逐字节重现 committed 产物："
        f"committed={committed_sha} replayed={hashlib.sha256(first).hexdigest()}"
    )
    assert first == committed, "replay 复跑必须与 committed 字节一致"

    # 第二次：再跑一次必须与第一次逐字节相同（幂等）
    proc2 = _generate_43_replay()
    assert proc2.returncode == 0, f"replay 复跑失败：{proc2.stderr}"
    assert committed_path.read_bytes() == first, "replay 二次复跑必须字节一致（幂等）"


def test_15043_replay_byte_test_is_falsifiable(tmp_path):
    """R6 反向验证：committed 产物**扰动一个字节**时，上一条用例的比对口径必须能发现。

    不跑 CLI（那只证明「磁盘变了」），而是把上一条用例的比对逻辑本身当作被测对象：
    在同一份字节上做 1 字节变异 → sha256 与字节相等都必须判否。这样「字节一致」的断言
    不会退化成恒真检查。
    """
    import hashlib

    committed = (ROOT / CONTENT_43_PATH).read_bytes()
    assert len(committed) > 1, "对照前提：产物非空"

    # 在空白区做 1 字节替换（保持 JSON 仍可解析，证明检查不是靠「解析失败」侥幸通过）
    mutated = committed.replace(b'"blocks"', b'"blockz"', 1)
    assert mutated != committed, "对照前提：1 字节变异必须改变字节"
    assert len(mutated) == len(committed), "对照前提：变异只改内容、不改长度"
    assert json.loads(mutated.decode("utf-8")), "对照前提：变异后仍是合法 JSON"

    assert hashlib.sha256(mutated).hexdigest() != hashlib.sha256(committed).hexdigest(), (
        "1 字节扰动必须改变 sha256（否则字节判定是恒真的）"
    )
    assert mutated != committed, "1 字节扰动必须被字节相等判定抓到"

    # 同时钉住：committed 产物本身没被本次变异污染
    assert (ROOT / CONTENT_43_PATH).read_bytes() == committed, "反向验证不得改动仓内产物"


def test_committed_fixtures_resolve_every_call_plan_payload_for_each_course():
    """QC1-S-2：每门有 `content.json` 的课程，`call_plan(model)` 的**每个** `payload_hash` 都必须能在
    录制文件里解析到响应 —— 这把「replay 可复现」从报告级声明变成机器校验的属性。

    QC1 当初只人工重建了 `15043` 的 766 个键（255 explain / 255 memorize / 255 drill / 1 stage_plan），
    并在 `qc1.md` 里记为「效果上被 R6 取代、但未交付」。R6 的 replay 用例确实**蕴含**该性质
    （键缺失时 `complete_json` 会抛 `missing fixture`，字节一致就不可能成立），但那是**间接**蕴含：
    它只能证明「跑到的那些键在」，键集合一旦漂移只能从 CLI 失败里倒推。本用例把它**直接**钉住，
    并且按课参数化 —— 下一门课（B2b）接入后**自动**进入守护范围，无需再补一次性重建。

    第三门课的接入前提由此写明：新课程只需让 `call_plan(model)` 的每个 payload 都有录制响应。
    """
    courses = sorted(
        path.parent.name
        for path in (ROOT / "sources" / "jiangsu" / "courses").glob("*/content.json")
    )
    # 对照前提：当前有产物（content.json）的课程都被覆盖到，而不是空集合上的恒真检查
    assert courses == ["15040", "15043"], f"对照前提：有 content.json 的课程为 15040/15043，实际 {courses}"

    for code in courses:
        model = _json(ROOT / f"sources/jiangsu/courses/{code}/knowledge-model.json")
        plan = gc.call_plan(model)
        assert plan, f"{code}: call_plan 不得为空"

        resolved: dict[tuple[str, str], int] = defaultdict(int)
        misses: list[str] = []
        for prompt_id, prompt_version, payload in plan:
            digest = llm.payload_hash(payload)
            fixture = _json(llm.fixture_path(prompt_id, prompt_version))
            if digest not in (fixture.get("responses") or {}):
                misses.append(f"{prompt_id}.{prompt_version}.json#{digest}")
            resolved[(prompt_id, prompt_version)] += 1

        assert not misses, (
            f"{code}: {len(misses)} 个 payload 在录制文件里无响应（replay 会失败关闭）—— 首个 {misses[0]}"
        )
        assert sum(resolved.values()) == len(plan), f"{code}: 覆盖数必须等于 call_plan 长度"

        # 与产物自身的块数对账（口径独立于 fixture）：产物有多少块，就该有多少条对应该块的调用
        artifact = _json(ROOT / f"sources/jiangsu/courses/{code}/content.json")
        blocks = artifact["blocks"]
        for kind, prompt_id in (("explain", "explain_point"), ("memorize", "memorize_point"), ("drill", "drill_point")):
            assert resolved[(prompt_id, "v1")] == len([b for b in blocks if b.get("kind") == kind]), (
                f"{code}: {prompt_id} 的调用数必须等于产物里 {kind} 块数"
            )
        # 课程级调用各恰一条：stage_plan 走 prompt（1 条调用 → 5 个阶段条目），
        # `exam_strategy` 是**无 prompt 的**课程级块（由 `stage_plan` 响应之外的常量/模型派生，不在 call_plan 里）
        assert resolved[("stage_plan", "v1")] == 1, f"{code}: stage_plan 调用应恰为 1 条"
        assert len([b for b in blocks if b.get("kind") == "exam_strategy"]) == 1, (
            f"{code}: 课程级 exam_strategy 块应恰为 1 条"
        )


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
    """tmp 根上的 CLI 装置：入口按 `__file__` 推导 ROOT → 加载后把 ROOT 指向 tmp。

    复用仓内 `scripts/lib`（软链），把已录制的 **fixture 拷进 tmp 根**、并把 15040 的
    `evidence.json` / `knowledge-model.json` 与考纲抽取件（软链）放进 tmp 根 —— 因此
    `run_generate()` 的 `_sync_roots()`（QC3-007 / C2-010）会把 `llm_client` 的三个根对齐到 tmp，
    CLI 真正作用于**被测的那棵树**，不再回落到真实仓的 fixture。
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
    # 提示词与录制响应必须随根走，否则 `_sync_roots()` 后 replay 找不到 fixture（这正是本条修复的意义）
    (root / "scripts" / "lib" / "course_pipeline").is_dir()  # 软链复用 prompts
    fixtures = root / "tests" / "fixtures" / "course_pipeline" / "llm"
    shutil.copytree(ROOT / "tests" / "fixtures" / "course_pipeline" / "llm", fixtures)
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
    keys = _canonical_keys(_model(), merged["blocks"])
    assert keys == sorted(keys), "合并后必须按知识模型的规范序重排"

    rerun = content_path.read_bytes()
    assert _generate(merge=True) == 0
    assert content_path.read_bytes() == rerun, "复跑合并必须字节一致"
    assert CONTENT_PATH.read_bytes() == real_before, "测试不得改动仓内产物"


def test_merge_and_full_generation_are_byte_equal_for_the_same_content_set(tmp_path):
    """F-405 二次裁决：同一个内容集合，逐批 `--merge` 与一次性全量生成必须逐字节一致。

    两批都用仓内已录制的 replay fixture（离线）：A = 导论 + 第一章，B = 第二章 + 第三章。
    旧实现把合并结果按 `point_id` 字典序重排（`ch01…` 排在 `intro…` 之前），与全量生成序不同 →
    本用例 (a) 在旧实现下必红，是「两条路径同序」的回归锁。
    """
    real_before = CONTENT_PATH.read_bytes()
    batched_cli, batched_path = _cli_root(tmp_path / "batched")
    oneshot_cli, oneshot_path = _cli_root(tmp_path / "oneshot")
    batch_a, batch_b = ("intro", "ch01"), ("ch02", "ch03")
    both = (*batch_a, *batch_b)

    def _generate(cli, chapters: tuple[str, ...], *, merge: bool) -> int:
        return cli.run_generate(
            "15040", backend="replay", chapters=list(chapters), record_fixtures=False, merge=merge
        )

    # 逐批：A 先落盘（首批没有既有产物），再把 B 合并进 A
    assert _generate(batched_cli, batch_a, merge=True) == 0
    assert _generate(batched_cli, batch_b, merge=True) == 0
    batched = _json(batched_path)
    # 一次性全量：同一内容集合 A ∪ B
    assert _generate(oneshot_cli, both, merge=False) == 0
    oneshot = _json(oneshot_path)

    # (a) 考点级块：同一内容集合下逐块同序、逐字节相等
    batched_points = [block for block in batched["blocks"] if block.get("point_id") is not None]
    oneshot_points = [block for block in oneshot["blocks"] if block.get("point_id") is not None]
    assert len(batched_points) == len(oneshot_points) == 246, "两批加起来 = 导论–第三章的 82 点 × 3"
    assert [block["block_id"] for block in batched_points] == [block["block_id"] for block in oneshot_points]
    assert gc.serialize({"blocks": batched_points}) == gc.serialize({"blocks": oneshot_points})
    for doc in (batched, oneshot):
        keys = _canonical_keys(_model(), doc["blocks"])
        assert keys == sorted(keys), "两条路径都必须落在唯一规范序上"

    # (b) 同一内容集合（合并的最后一次生成覆盖累积章集，即 plan § Data contracts 4 的权威路径）
    #     → 整份产物逐字节一致：`--merge` 不是另一种产物形态
    assert _generate(batched_cli, both, merge=True) == 0
    assert batched_path.read_bytes() == oneshot_path.read_bytes()

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


# --------------------------------------------------------------------------------------
# W10 / C2-010：`--backend agent` 的**真实 CLI 入口**（子进程）失败关闭路径
# --------------------------------------------------------------------------------------

def _agent_cli_root(tmp_path: Path) -> Path:
    """子进程用的副本根：`scripts` + `sources` + `tests/fixtures` 自足，且 `lib` 是**真实拷贝**。

    与 `_cli_root()`（进程内装置，软链复用仓内 `lib`）不同，这里跑的是 `subprocess`，
    因此把 `scripts` 整棵拷进去 —— 子进程的 `__file__` 推导才会落在副本内（QC3-007 的根对齐），
    fixture 也必须随根走，否则 agent 后端会因为找不到提示词而失败在与被测行为无关的原因上。
    """
    root = tmp_path / "agent-root"
    shutil.copytree(ROOT / "scripts", root / "scripts")
    course = root / "sources" / "jiangsu" / "courses" / "15040"
    course.mkdir(parents=True)
    for name in ("evidence.json", "knowledge-model.json"):
        shutil.copy(ROOT / "sources" / "jiangsu" / "courses" / "15040" / name, course / name)
    (root / "sources" / "jiangsu" / "processed").symlink_to(
        ROOT / "sources" / "jiangsu" / "processed", target_is_directory=True
    )
    fixtures = root / "tests" / "fixtures" / "course_pipeline" / "llm"
    fixtures.parent.mkdir(parents=True)
    shutil.copytree(ROOT / "tests" / "fixtures" / "course_pipeline" / "llm", fixtures)
    return root


def test_cli_agent_backend_fails_closed_without_results(tmp_path):
    """W10 / C2-010 的 CLI 半边：`generate 15040 --backend agent` 在无 key、无回填结果时必须 exit 2。

    spec AC9 的命令就是这条 CLI 调用。库层已有覆盖（`test_agent_backend_bundle_round_trip`），
    但 CLI 的 `AgentTasksPendingError → exit 2` 映射（`build-course-content.py:146-148`）此前
    **没有任何子进程级测试** —— 映射写错（比如吞成 exit 0）会让「缺回填结果」静默变成成功。

    三个方向：(a) 缺回填 → exit 2 且点名 `.result.json`，不产出 `content.json`；
    (b) 任务包真的写出来了（不是空跑）；(c) 回填后同一命令 exit 0 并产出 `content.json`（AC9 的完整口径）。
    """
    root = _agent_cli_root(tmp_path)
    content_path = root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZIKAO_LLM_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "scripts/build-course-content.py", "generate", "15040", "--backend", "agent"],
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
        )

    # (a) 无回填结果 → exit 2（失败关闭），且明确点名缺失的结果文件
    first = _run()
    assert first.returncode == 2, f"缺回填结果必须 exit 2：{first.returncode}\n{first.stdout}\n{first.stderr}"
    assert "stage=generate missing" in first.stderr, first.stderr
    assert ".result.json" in first.stderr, f"必须点名缺失的回填结果：{first.stderr}"
    assert not content_path.is_file(), "失败路径不得产出 content.json（不写半成品）"

    task_dir = root / "sources" / "jiangsu" / "courses" / "15040" / ".agent-task"
    bundles = sorted(p for p in task_dir.glob("*.json") if not p.name.endswith(".result.json"))
    assert len(bundles) == 1180, f"agent 后端必须把全部任务包写出来：{len(bundles)}"
    bundle = _json(bundles[0])
    assert bundle["expect_result"] == bundles[0].with_name(f"{bundles[0].stem}.result.json").name
    assert "instructions" in bundle and "payload" in bundle

    # (b) 用 **replay fixture** 的录制响应回填（不联网、不伪造），再跑同一命令 → exit 0
    for path in bundles:
        job = _json(path)
        response = llm.complete_json(job["prompt_id"], job["prompt_version"], job["payload"], backend="replay")
        path.with_name(job["expect_result"]).write_text(
            json.dumps(response, ensure_ascii=False), encoding="utf-8"
        )

    second = _run()
    assert second.returncode == 0, f"回填齐备后必须 exit 0：{second.returncode}\n{second.stdout}\n{second.stderr}"
    assert content_path.is_file(), "成功路径必须产出 content.json"
    doc = _json(content_path)
    assert doc["generator"]["backend"] == "agent"


# --------------------------------------------------------------------------------------
# R49：附录单元（`appendices[]`）必须进生成路径（Task 3a 建模了，但旧消费者不读它）
# --------------------------------------------------------------------------------------

APPENDIX_COURSE = "02333"


def _appendix_model() -> dict:
    """真实 `02333` 知识模型（7 个附录 / 9 个点，含 `应用` 级 `ap07-s1-p3`）。"""
    return _json(ROOT / f"sources/jiangsu/courses/{APPENDIX_COURSE}/knowledge-model.json")


def _synthetic_appendix_model() -> dict:
    """合成模型：章 `ch01`（1 节 3 点）+ 附录 `ap01`（1 节 3 点）。

    合成而非只读真实模型：本用例要能对「附录点是否真的进了 jobs / 规范序 / 排程」下断言，
    而真实 `02333` 的 `question_types` 是 `named_gap`（空），生成会 fail-closed 抛错。
    """
    model = _synthetic_model()
    appendix = json.loads(json.dumps(model["chapters"][0], ensure_ascii=False))
    appendix.update({"ordinal": 1, "index": "附录一", "slug": "ap01", "title": "附录一 合成附录"})
    for section in appendix["sections"]:
        for point in section["points"]:
            point["id"] = point["id"].replace("-intro-", "-ap01-")
    return {**model, "appendices": [appendix]}


def _all_point_ids(model: dict) -> list[str]:
    """源侧探针（独立于生产 `_point_ids()`，含附录）。"""
    units = [*model["chapters"], *(model.get("appendices") or [])]
    return [p["id"] for u in units for s in u["sections"] for p in s["points"]]


def test_appendix_points_are_generated_as_their_own_units(monkeypatch, tmp_path):
    """R49 主判据：`appendices[]` 的考点必须真的进 `call_plan()` 与产物 —— 不是一个都不读。

    旧实现只迭代 `model["chapters"]`，于是 `02333` 的 9 个附录点（含 `应用` 级 `ap07-s1-p3`）
    既没有 prompt 调用、也不会出现在 `content.json` 的 blocks 里：它们「被建模但永不到达读者」，
    即 R41 登记的危害原样保留。本用例把它变成可判否的属性。
    """
    _wire(monkeypatch, tmp_path, record=True)
    model = _synthetic_appendix_model()
    appendix_points = [
        p["id"] for a in model["appendices"] for s in a["sections"] for p in s["points"]
    ]
    assert len(appendix_points) == 3, "对照前提：合成附录有 3 个考核点"

    plan = gc.call_plan(model)
    payload_point_ids = {payload["point"]["id"] for _pid, _ver, payload in plan if "point" in payload}
    for point_id in appendix_points:
        assert point_id in payload_point_ids, f"附录点 {point_id} 没有 prompt 调用（未被生成）"

    doc = gc.generate_course_content(ROOT, model, backend="cli")
    generated = {block["point_id"] for block in doc["blocks"] if block.get("point_id")}
    for point_id in appendix_points:
        assert point_id in generated, f"附录点 {point_id} 未产出任何块"

    # 按点计数：块数 = 点数 × 3 + 1（章 3 点 + 附录 3 点 = 6 点 → 19 块）
    assert len(doc["blocks"]) == len(_all_point_ids(model)) * 3 + 1, (
        f"块数必须按**点**算（含附录点）：{len(doc['blocks'])}"
    )
    # 附录的 explain 必须带附录自己的 `chapter_focus`（不是第 14 章的，Task 3a 的 R41 语义）
    appendix_explain = next(
        payload for _pid, _v, payload in plan
        if payload.get("point", {}).get("id") == appendix_points[0] and "question_type" not in payload
    )
    assert appendix_explain["chapter"]["index"] == "附录一", appendix_explain["chapter"]
    assert appendix_explain["chapter_focus"] == ["合成本章重点"], appendix_explain["chapter_focus"]


def test_appendix_ordering_puts_every_appendix_point_after_every_chapter_point():
    """规范序：附录点在**全部**章节点之后。

    判据必须针对**真实撞车形态**：`02333` 的 `第1章` 与 `附录一` 的 `ordinal` **都是 1**
    （附录 `ordinal` 与章同域）。若 `_point_order()` 只用 `ordinal` 排序，`附录一` 的点会排到
    `第1章` 与 `第2章` 之间 —— 本用例用真实模型 + 一条合成附录来复现这个撞车，
    合成模型里的 `ordinal 0 / 1` 不撞车，因此测不出该缺陷（第一版正是这样漏掉的）。
    """
    model = _appendix_model()
    # 造一个 ordinal 与真实附录撞车的附录，插到 7 个真实附录之前（阅读序仍是章 → 附录）
    collision = json.loads(json.dumps(model["appendices"][0], ensure_ascii=False))
    assert model["chapters"][0]["ordinal"] == 1 and collision["ordinal"] == 1, (
        "对照前提：第1章与附录一的 ordinal 必须撞车（都是 1）"
    )
    for section in collision["sections"]:
        for point in section["points"]:
            point["id"] = "02333-ap99-s1-p1"

    blocks = [
        {"block_id": f"{pid}/explain", "kind": "explain", "point_id": pid}
        for pid in reversed(_all_point_ids(model))
    ]
    ordered = [block["point_id"] for block in gc.order_blocks(blocks, model)]
    appendix_points = [p["id"] for a in model["appendices"] for s in a["sections"] for p in s["points"]]
    chapter_points = [p["id"] for c in model["chapters"] for s in c["sections"] for p in s["points"]]
    last_chapter = max(ordered.index(pid) for pid in chapter_points)
    first_appendix = min(ordered.index(pid) for pid in appendix_points)
    assert first_appendix > last_chapter, (
        f"附录点必须排在全部章节点之后（附录一 ordinal=1 与第1章撞车）：{ordered[:20]}"
    )
    # 逐单元确认：每个附录点都排在每个章节点之后（不只是首尾）
    for appendix_point in appendix_points:
        for chapter_point in chapter_points:
            assert ordered.index(appendix_point) > ordered.index(chapter_point), (
                f"{appendix_point} 排在了 {chapter_point} 之前"
            )
    assert collision["ordinal"] == 1  # 撞车形态已构造（对照前提）


def test_appendix_points_enter_the_review_schedule():
    """排程按点算：附录点必须进 `items[].point_ids` 与 `spaced_repetition`（否则它们不进复习节奏）。"""
    model = {
        **_synthetic_appendix_model(),
        "exam": {**_synthetic_model()["exam"], "exam_date": "2026-10-25", "weekly_hours": 6},
    }
    schedule = gc._review_schedule(model, generator={"backend": "replay", "model": "m",
                                                     "prompt_id": "p", "prompt_version": "v1",
                                                     "generated_at": "2026-01-01"})
    appendix_points = {p["id"] for a in model["appendices"] for s in a["sections"] for p in s["points"]}
    for plan in schedule["plans"]:
        scheduled = {pid for item in plan["items"] for pid in item["point_ids"]}
        repeated = {r["point_id"] for r in plan["spaced_repetition"]}
        missing = appendix_points - scheduled
        assert not missing, f"{plan['tier']}: 附录点未进 items[].point_ids：{sorted(missing)}"
        assert not (appendix_points - repeated), f"{plan['tier']}: 附录点未进 spaced_repetition"


def test_stage_plan_payload_lists_appendices_separately_and_omits_the_key_when_empty():
    """课程级 payload：附录以**独立键**列出；无附录时**整个键省略**（`15040`/`15043` 字节不变的结构前提）。"""
    model = _synthetic_appendix_model()
    payload = gc._stage_plan_payload(model)
    assert [a["index"] for a in payload["appendices"]] == ["附录一"], payload.get("appendices")
    assert [c["index"] for c in payload["chapters"]] == ["导论"], "附录不得混进 chapters"
    # point_total 按点算（含附录点）
    assert payload["point_total"] == len(_all_point_ids(model)) == 6

    plain = gc._stage_plan_payload(_synthetic_model())
    assert "appendices" not in plain, "无附录的课程不得新增 appendices 键（payload 哈希会漂移）"
    assert plain["point_total"] == 3


def test_select_chapters_accepts_appendix_selectors_and_keeps_chapter_selectors_working():
    """R49 验收②：`select_chapters` 对附录可寻址（slug `ap01` / 序标签 `附录一` / ordinal），
    且章的既有选择器语义不变（`intro` / `导论` / `0`）。"""
    model = _synthetic_appendix_model()

    by_slug = gc.select_chapters(model, ("ap01",))
    assert [a["slug"] for a in by_slug["appendices"]] == ["ap01"]
    assert by_slug["chapters"] == [], "只选附录时 chapters 必须是空列表（不是缺失键）"

    for selector in ("附录一", "1"):
        picked = gc.select_chapters(model, (selector,))
        assert [a["slug"] for a in picked["appendices"]] == ["ap01"], f"选择器 {selector!r} 未命中附录"

    # 章与附录混选：各自留各自的列表，顺序仍是知识模型内序
    mixed = gc.select_chapters(model, ("intro", "ap01"))
    assert [c["slug"] for c in mixed["chapters"]] == ["intro"]
    assert [a["slug"] for a in mixed["appendices"]] == ["ap01"]

    # 章的既有选择器：slug / 序标签 / ordinal 三种形态都仍可用
    for selector in ("intro", "导论", "0"):
        picked = gc.select_chapters(model, (selector,))
        assert [c["slug"] for c in picked["chapters"]] == ["intro"], f"章选择器 {selector!r} 失效"
        assert picked["appendices"] == [], f"章选择器 {selector!r} 不得带上附录"

    # 无附录课程：不得新增 appendices 键（no-op 结构前提）
    plain = gc.select_chapters(_synthetic_model(), ("intro",))
    assert "appendices" not in plain


def test_select_chapters_rejects_an_unknown_appendix_selector():
    model = _synthetic_appendix_model()
    with pytest.raises(ValueError):
        gc.select_chapters(model, ("ap99",))
    with pytest.raises(ValueError):
        gc.select_chapters(model, ("附录九",))


def test_committed_02333_model_has_nine_appendix_points_reachable():
    """产物级对照前提：`02333` 的模型确实有 7 附录 / 9 点（含 `应用` 级），且它们全部进 call_plan。

    这是「9 个点会到达读者」这条验收的**起点**：模型侧 9 点 + 消费者侧可达，两者缺一不可
    （Task 3a 只做到前者）。

    `02333` 的 `exam.question_types` 是 `named_gap`（空列表）→ `call_plan()` 按**既有**契约 fail-closed
    抛错（`declared_question_types()`）。本用例只补一个合成题型集让 jobs 真正展开，其余事实
    （7 附录 / 9 点 / 层级 / point id）全部取自**真实模型**，不改仓内文件。
    """
    model = _appendix_model()
    assert len(model["appendices"]) == 7
    appendix_points = [p["id"] for a in model["appendices"] for s in a["sections"] for p in s["points"]]
    assert len(appendix_points) == 9, appendix_points
    assert "02333-ap07-s1-p3" in appendix_points, "`应用` 级要求行必须在模型里"
    assert (
        next(
            p for a in model["appendices"] for s in a["sections"] for p in s["points"]
            if p["id"] == "02333-ap07-s1-p3"
        )["requirement"]
        == "应用"
    )
    # 消费者侧：9 个附录点全部进 jobs 的 payload（旧实现里它们是 0 条）
    declared = {**model, "exam": {**model["exam"], "question_types": ["单项选择题", "简答题", "材料题"]}}
    plan = gc.call_plan(declared)
    payload_point_ids = {payload["point"]["id"] for _pid, _v, payload in plan if "point" in payload}
    assert set(appendix_points) <= payload_point_ids, (
        f"未进 call_plan 的附录点：{sorted(set(appendix_points) - payload_point_ids)}"
    )
    # 预算口径（plan § Task 3b）：块数**按点**算 = 153 点（144 章节点 + 9 附录点）→ 153×3 + 1 = 460
    assert len(payload_point_ids) == 153, f"点数 = 144 + 9 = 153，实际 {len(payload_point_ids)}"
    assert len(plan) == 153 * 3 + 1, f"调用计划长度 = 点数×3 + 1（stage_plan），实际 {len(plan)}"
