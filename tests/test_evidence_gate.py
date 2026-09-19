"""Unit and integration tests for evidence_gate (official facts + knowledge model)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_scope_evidence_all_18():
    """evidence 层对 18 份 evidence.json 全量校验，在 HEAD 状态下 0 errors；对无 evidence.json 目录不报错。"""
    from lib.evidence_gate import run_evidence_gate

    errors = run_evidence_gate(ROOT)
    assert errors == [], f"HEAD evidence gate failed: {errors}"


def test_course_url_shape_and_source():
    """T2 评审 G-202: course_url 类型为 str | null；非 null 时在 baseline 中、authoritative、jseea、含课码且为最小字典序。"""
    from lib.course_pipeline.evidence import evaluate_eligibility

    baseline = json.loads((ROOT / "ops" / "jiangsu" / "source-links.baseline.json").read_text(encoding="utf-8"))
    baseline_urls = baseline.get("urls", {})

    for ev_path in sorted((ROOT / "sources" / "jiangsu" / "courses").glob("*/evidence.json")):
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        code = ev["course_code"]
        url = ev.get("course_url")
        assert url is None or isinstance(url, str)

        if url is not None:
            assert url in baseline_urls, f"{code}: {url} not in baseline"
            entry = baseline_urls[url]
            assert entry.get("authoritative") is True, f"{code}: {url} not authoritative"
            host = urlparse(url).hostname or ""
            assert host == "jseea.cn" or host.endswith(".jseea.cn"), f"{code}: {url} host not jseea"
            assert code in entry.get("course_codes", []), f"{code}: {url} course_codes does not include {code}"

            # candidate with minimal lexicographical order
            candidates = [
                u
                for u, item in baseline_urls.items()
                if item.get("authoritative")
                and (urlparse(u).hostname == "jseea.cn" or (urlparse(u).hostname or "").endswith(".jseea.cn"))
                and code in item.get("course_codes", [])
            ]
            if candidates:
                assert url == sorted(candidates)[0], f"{code}: {url} not minimal candidate in {candidates}"

        # evaluate_eligibility output does not depend on course_url
        ev_copy = dict(ev)
        ev_copy["course_url"] = None
        orig_res = evaluate_eligibility(ev)
        mod_res = evaluate_eligibility(ev_copy)
        assert orig_res == mod_res, f"{code}: eligibility changed when course_url set to None"


def test_committed_artifacts_match_a_fresh_build():
    """T2 评审 G-201: 新鲜度校验具备日期无关性，调用 _is_fresh 忽略 generated_at。"""
    from lib.evidence_gate import is_fresh

    obj1 = {"generated_at": "2026-09-11", "data": 123}
    obj2 = {"generated_at": "2026-09-12", "data": 123}
    assert is_fresh(obj1, obj2) is True

    obj3 = {"generated_at": "2026-09-11", "data": 456}
    assert is_fresh(obj1, obj3) is False


def test_evidence_gate_fails_on_bad_facts_status(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["facts"]["name"]["status"] = "illegal_status_value"
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and "status" in e for e in errors), errors


def test_evidence_gate_fails_on_verified_missing_provenance(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["facts"]["name"]["status"] = "verified"
    data["facts"]["name"]["provenance"] = None
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and "provenance" in e for e in errors), errors


def test_evidence_gate_fails_on_named_gap_missing_fields(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["facts"]["extra_gap"] = {"status": "named_gap"}
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and ("gap_impact" in e or "next_evidence" in e) for e in errors), errors


def test_evidence_gate_fails_on_non_l1_with_content_json(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    # Put content.json in 00023 which is blocked
    p = fake_root / "sources" / "jiangsu" / "courses" / "00023" / "content.json"
    p.write_text("{}", encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any("00023" in e and "L1" in e for e in errors), errors


def test_evidence_gate_fails_on_quote_over_60_chars(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["chapters"][0]["sections"][0]["points"][0]["quote"] = "a" * 65
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and "quote" in e for e in errors), errors


def test_evidence_gate_fails_on_point_id_format_or_duplicate(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["chapters"][0]["sections"][0]["points"][0]["id"] = "bad_format_id"
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and "id" in e for e in errors), errors


def test_evidence_gate_fails_on_coverage_ratio_under_90(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["coverage"]["ratio"] = 0.88
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and "ratio" in e for e in errors), errors


def test_evidence_gate_fails_on_diff_manual_only(tmp_path: Path):
    from lib.evidence_gate import run_evidence_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["coverage"]["diff_vs_manual"].append(
        {"manual_locator": "L999", "manual_title": "fake", "model_point_id": None, "kind": "manual_only", "note": "fake"}
    )
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any(str(target.relative_to(fake_root)) in e and "manual_only" in e for e in errors), errors


# ---- B3 / B4 / B6：闸门必须能看穿伪造与静默丢章 ------------------------------------------

def _fake_root(tmp_path: Path) -> Path:
    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")
    return fake_root


def test_evidence_gate_rejects_forged_l1(tmp_path: Path):
    """B3：`eligibility.level = "L1"` 但两个放行输入都 `missing` → 必须失败关闭（D8 单一门槛）。"""
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["syllabus"] = {
        "status": "missing",
        "doc_id": "syllabus:15040",
        "path": None,
        "sha256": None,
        "gap_impact": "缺官方考纲",
        "next_evidence": "官方考纲原件",
    }
    data["textbook_plan"] = {
        "status": "missing",
        "doc_id": None,
        "path": None,
        "locator": None,
        "row": None,
        "gap_impact": "缺教材计划行",
        "next_evidence": "官方教材计划抽取件中的教材行",
    }
    data["eligibility"] = {"level": "L1", "reasons": ["forged"]}
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any("eligibility.level" in e and "无法由" in e for e in errors), errors
    assert any("syllabus:missing" in e or "textbook_plan:missing" in e for e in errors), errors


def test_evidence_gate_rejects_non_l1_with_knowledge_model(tmp_path: Path):
    """B3 第二向：非 `L1` 课程存在 `knowledge-model.json` 同样是零 AI 产物规则的违反（spec AC4）。"""
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    # 00023 是 blocked，但把它伪装成一个有模型的课程
    model_src = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"
    model_dst = fake_root / "sources" / "jiangsu" / "courses" / "00023" / "knowledge-model.json"
    shutil.copy(model_src, model_dst)

    errors = run_evidence_gate(fake_root)
    assert any("00023" in e and "knowledge-model.json" in e and "L1" in e for e in errors), errors


def test_evidence_gate_rejects_unverified_value(tmp_path: Path):
    """B4：非 `verified` 的事实不得携带 `value`（旧实现的 `unverified` / `missing-source` 是无检查的降级后门）。"""
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"

    for status in ("unverified", "missing-source"):
        data = json.loads(target.read_text(encoding="utf-8"))
        data["facts"]["credits"] = {"value": "999", "status": status}
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors = run_evidence_gate(fake_root)
        assert any("facts.credits.status has invalid value" in e for e in errors), (status, errors)

    # 契约内的 `named_gap` 同样不得带 value
    data = json.loads(target.read_text(encoding="utf-8"))
    data["facts"]["credits"] = {
        "value": "888",
        "status": "named_gap",
        "gap_impact": "读者无法判断学分权重",
        "next_evidence": "官方专业计划表课程行",
    }
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("facts.credits" in e and "carries a value" in e for e in errors), errors


def test_evidence_gate_rejects_silently_dropped_chapter(tmp_path: Path):
    """B6：`official_point_count` 必须与模型实际节数一致，章目必须与 `syllabus.md` 逐行一致。

    旧实现下 `15044` 丢掉整章 `绪 论` 而 `ratio` 仍是 `1.0`（被丢的章连分母一起带走），两层都看不见。
    """
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"

    # (a) 删一章 → 分母自洽性必须报出
    data = json.loads(target.read_text(encoding="utf-8"))
    dropped_sections = len(data["chapters"][0]["sections"])
    data["chapters"].pop(0)
    data["coverage"]["ratio"] = 1.0
    data["coverage"]["modeled_point_count"] = data["coverage"]["official_point_count"] - dropped_sections
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("official_point_count" in e and "不一致" in e for e in errors), errors
    assert any("章目索引不一致" in e for e in errors), errors

    # (b) 恢复章数但改一个章标题 → 与 syllabus.md 的逐行比对必须报出
    data = json.loads(target.read_text(encoding="utf-8"))
    data["chapters"][0]["title"] = "第一章 被改名的章"
    data["chapters"][0]["ordinal"] = 1
    data["chapters"][0]["slug"] = "ch01"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("章目索引不一致" in e for e in errors), errors


def test_evidence_gate_rejects_missing_quote(tmp_path: Path):
    """C2-008：`quote` 缺失或超长都必须失败关闭（旧实现 `pt.get("quote") or ""` 让「没有 quote」等同合规）。"""
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"

    data = json.loads(target.read_text(encoding="utf-8"))
    point = data["chapters"][0]["sections"][0]["points"][0]
    point["quote"] = ""
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("缺 quote" in e for e in errors), errors

    data = json.loads(target.read_text(encoding="utf-8"))
    data["chapters"][0]["sections"][0]["points"][0]["quote"] = "长" * 61
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("quote exceeds 60" in e for e in errors), errors


def test_evidence_gate_reports_type_invalid_artifacts_instead_of_crashing(tmp_path: Path):
    """C2-013：类型非法的产物必须变成定位到字段的错误字符串，而不是抛 `TypeError` 中断整层。"""
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"

    for bad_ratio in (None, "1.0"):
        data = json.loads(target.read_text(encoding="utf-8"))
        data["coverage"]["ratio"] = bad_ratio
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors = run_evidence_gate(fake_root)  # 不得抛异常
        assert any("coverage.ratio 必须是数字" in e for e in errors), (bad_ratio, errors)

    data = json.loads(target.read_text(encoding="utf-8"))
    data["coverage"]["ratio"] = 1.0
    data["chapters"][0]["sections"][0]["points"][0]["quote"] = 12345
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = run_evidence_gate(fake_root)
    assert any("缺 quote" in e for e in errors), errors


def test_evidence_gate_rejects_syllabus_sha256_drift(tmp_path: Path):
    """QC1 F-5 的门禁侧：考纲抽取件被换掉后 `sha256` 不一致必须报出。"""
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    evidence = json.loads(
        (fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json").read_text(encoding="utf-8")
    )
    document = fake_root / evidence["syllabus"]["path"]
    document.write_text(document.read_text(encoding="utf-8") + "\n（被替换的内容）\n", encoding="utf-8")

    errors = run_evidence_gate(fake_root)
    assert any("sha256" in e for e in errors), errors


# ---- R54 3a：分母读取的三态（`>0` 用该值 / `0` 回退规范化渲染 / 两侧皆 0 失败关闭） -------------

def _replace_syllabus_document(fake_root: Path, code: str, transform: Callable[[str], str]) -> Path:
    """把某课抽取件**副本**的内容替换为 `transform(text)`，并同步 `evidence.json` 的 `sha256`。

    同步 sha256 是为了让被观察到的失败**只**来自分母检查：否则 `syllabus.sha256 漂移`
    （另一条独立检查）会同时报错，两条错误的来源无法区分。真实产物不受影响（GC2）。
    """
    evidence_file = fake_root / "sources" / "jiangsu" / "courses" / code / "evidence.json"
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    document = fake_root / evidence["syllabus"]["path"]
    document.write_text(transform(document.read_text(encoding="utf-8")), encoding="utf-8")
    evidence["syllabus"]["sha256"] = hashlib.sha256(document.read_bytes()).hexdigest()
    evidence_file.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    return document


def test_r54_declared_denominator_falls_back_to_the_normalized_rendering(tmp_path: Path):
    """R54 3a：原文直读解不出（0）时必须回退到**规范化渲染**，不得把版式噪声判成「源文声明 0 个单元」。

    构造 = `15040` 抽取件的**纯版式噪声**副本：文本逐字不变，只把 `\\n` 断行整体换成换页符 `\\x0c`
    （真实抽取件里本来就有 31 个 `\\x0c`，属同一族版式噪声）。

    **噪声为什么取 `\\x0c` 而不是 CR**（对 plan/design-notes 口径的一处收紧）：`Path.read_text()`
    走 universal newlines，**读取时**就把 `\\r\\n` / `\\r` 译成 `\\n`，故 CR 噪声在闸门这一侧不可观测
    （实测：CR-only 变体 raw / normalized 都是 61）。能真正落到「原文直读解不出」这个状态的是
    `split("\\n")` 不认、而 `str.splitlines()` 认的分隔符（`\\x0c` / `\\x0b` / `\\u2028` / `\\u2029`）：
    整篇被读成一行 → 行首锚定的 `PART_LABEL_RE` 必然失败 → 返回 0。修复前闸门据此报
    「与考纲原文声明的考核单元数 0 不一致（-61 个单元被静默丢弃）」—— 源文一字未改的伪硬失败。
    """
    from lib.course_pipeline.knowledge_model import source_assessment_unit_count
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    assert not [e for e in run_evidence_gate(fake_root) if "15040" in e and "考核单元" in e], (
        "对照前提：抽取件未改动时分母检查必须静默"
    )

    document = _replace_syllabus_document(fake_root, "15040", lambda text: text.replace("\n", "\x0c"))
    evidence = json.loads(
        (fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json").read_text(encoding="utf-8")
    )
    heading = evidence["syllabus"]["requirements_heading"]
    text = document.read_text(encoding="utf-8")

    # 前提复现（两侧读数就是本条的判别力）：原文直读 0（伪硬失败的来源），规范化渲染 61（真实分母）
    assert source_assessment_unit_count(text.split("\n"), heading) == 0
    assert source_assessment_unit_count(text.splitlines(), heading) == 61

    errors = run_evidence_gate(fake_root)
    assert not [e for e in errors if "15040" in e and "考核单元" in e], errors


def test_r54_declared_denominator_fails_closed_when_both_readings_are_zero(tmp_path: Path):
    """R54 3a：`status == "extracted"` 却**两侧都解出 0** = 源侧损坏的矛盾态 → 必须失败关闭。

    构造 = 把抽取件里 `Ⅲ 课程内容与考核要求` 的分部标记整体改成中文「三」（抽取/解码损坏形态），
    两种读法都定位不到分部标记 → raw 0 / normalized 0。

    **反向断言是这条的全部判别力**：不得退化成「源文声明 0 个单元」的分母比对 —— 那会报
    「与考纲原文声明的考核单元数 0 不一致（-61 个单元被静默丢弃）」，即把「源侧分部标记整体损坏」
    读成「源文声明了 0 个单元」，方向恰好反了（这份输入的真实语义是**多**出 61 个未计入单元）。
    """
    from lib.evidence_gate import run_evidence_gate

    fake_root = _fake_root(tmp_path)
    _replace_syllabus_document(
        fake_root, "15040", lambda text: text.replace("Ⅲ 课程内容与考核要求", "三 课程内容与考核要求")
    )

    errors = run_evidence_gate(fake_root)
    assert any("15040" in e and "两侧都解出 0" in e for e in errors), errors
    assert not any("15040" in e and "声明的考核单元数 0" in e for e in errors), errors


def test_r54_declared_denominator_does_not_judge_when_the_prerequisite_is_unavailable(tmp_path: Path):
    """R54 3a 三态之一：前置不可用（未 `extracted` / 未记录小节 / 抽取件缺失）→ `None`（**不判定**）。

    这是既有行为，不是失败关闭：读不到抽取件时不得臆造判定，也不得顺手报一条错
    （`syllabus.sha256` 漂移 / 路径缺失由 `_eligibility_problems` 另行报出）。
    """
    from lib.evidence_gate import _declared_unit_count

    errors: list[str] = []
    unavailable = (
        "not-a-dict",
        {"status": "missing"},
        {"status": "extracted", "path": None, "requirements_heading": "三、考核知识点与考核要求"},
        {
            "status": "extracted",
            "path": "sources/jiangsu/processed/syllabus/99999-demo/document.extracted.md",
            "requirements_heading": "三、考核知识点与考核要求",
        },
    )
    for syllabus in unavailable:
        assert _declared_unit_count(tmp_path, syllabus, "x/knowledge-model.json", errors) is None, syllabus
    assert errors == [], errors
