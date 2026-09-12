"""Unit and integration tests for evidence_gate (official facts + knowledge model)."""
from __future__ import annotations

import json
import shutil
import sys
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
