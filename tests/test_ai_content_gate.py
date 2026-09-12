"""Unit and integration tests for ai_content_gate (AI prep layer + markers + 8-gram)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_scope_only_courses_with_products():
    """只有存在 content.json 的课程参与 ai-content 校验；HEAD 状态下 0 errors。"""
    from lib.ai_content_gate import run_ai_content_gate

    errors = run_ai_content_gate(ROOT)
    assert errors == [], f"HEAD ai-content gate failed: {errors}"


def test_ai_content_gate_fails_missing_annotation_fields(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    del data["blocks"][0]["generator"]
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("generator" in e and "15040" in e for e in errors), errors


def test_ai_content_gate_fails_empty_evidence_refs(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["blocks"][0]["evidence_refs"] = []
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("evidence_refs" in e and "15040" in e for e in errors), errors


def test_ai_content_gate_fails_8gram_overlap_over_20(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    # Load syllabus text from document.extracted.md
    syl_file = fake_root / "sources" / "jiangsu" / "processed" / "syllabus" / "15040-xi-thought-gaogang-2024" / "document.extracted.md"
    syl_snippet = syl_file.read_text(encoding="utf-8")[:200]
    data["blocks"][0]["text_md"] = syl_snippet
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("8-gram" in e or "overlap" in e or "重合率" in e for e in errors), errors


def test_ai_content_gate_fails_point_id_not_in_model(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["blocks"][0]["point_id"] = "15040-nonexistent-s1-p1"
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("point_id" in e and "15040-nonexistent-s1-p1" in e for e in errors), errors


def test_ai_content_gate_fails_drill_missing_fields(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    # Find a drill block
    for b in data["blocks"]:
        if b["kind"] == "drill":
            del b["answer_md"]
            break
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("answer_md" in e for e in errors), errors


def test_ai_content_gate_fails_official_sample_missing_provenance(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    for b in data["blocks"]:
        if b["kind"] == "drill":
            b["source_kind"] = "official_sample"
            b.pop("provenance", None)
            break
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("official_sample" in e and "provenance" in e for e in errors), errors


def test_ai_content_gate_fails_stage_plan_not_5(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["stage_plan"].pop()
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("stage_plan" in e and "5" in e for e in errors), errors


def test_ai_content_gate_fails_review_schedule_missing_quad(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    target = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    del data["review_schedule"]["review_state"]
    target.write_text(json.dumps(data), encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("review_schedule" in e and "review_state" in e for e in errors), errors


def test_ai_content_gate_fails_page_banner_missing_or_leaked(tmp_path: Path):
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    # Leak banner into index.md
    idx = fake_root / "content" / "jiangsu" / "courses" / "15040" / "index.md"
    idx.write_text(idx.read_text(encoding="utf-8") + "\n本页由 AI 辅助生成\n", encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert any("index.md" in e and ("banner" in e or "横幅" in e or "AI" in e) for e in errors), errors


def test_docs_mention_new_layers():
    """README.md 和 ops/jiangsu/content-standard.md 提到 evidence 与 ai-content 两层。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    standard = (ROOT / "ops" / "jiangsu" / "content-standard.md").read_text(encoding="utf-8")
    for doc_name, text in [("README.md", readme), ("content-standard.md", standard)]:
        assert "evidence" in text, f"{doc_name} must mention evidence gate layer"
        assert "ai-content" in text, f"{doc_name} must mention ai-content gate layer"
