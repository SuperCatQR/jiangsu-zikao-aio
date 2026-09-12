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


def test_ai_content_gate_fails_closed_on_missing_syllabus_corpus(tmp_path: Path):
    """QC1 F-5：语料按 `evidence.json.syllabus.path` 定位并校验 `sha256`；缺失/不一致即失败关闭（不静默跳过）。"""
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    ev_path = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    data = json.loads(ev_path.read_text(encoding="utf-8"))

    # (a) 抽取件整份移走 → 不得当作「无 8-gram 语料」跳过
    document = fake_root / data["syllabus"]["path"]
    moved = document.with_suffix(".moved")
    document.rename(moved)
    errors = run_ai_content_gate(fake_root)
    assert any("考纲抽取件不存在" in e for e in errors), errors

    # (b) 抽取件内容被替换 → sha256 不一致必须报出（旧实现只 glob，认不出被换掉的文件）
    document.write_text("替换后的考纲内容", encoding="utf-8")
    errors = run_ai_content_gate(fake_root)
    assert any("sha256" in e for e in errors), errors


def test_ai_content_gate_fails_when_ai_block_did_not_reach_a_page(tmp_path: Path):
    """B2 变异证明：AI 块没落到页面就必须失败关闭（这正是 QC3-001 能蒙过关的缺口）。

    九个方向各来一次：`practice.md` 丢 drill、`plan.md` 丢五阶段、`review.md` 丢命名缺口、
    `plan.md` 丢课程级 `exam_strategy`（W1 —— 旧对账只覆盖 3/4 个 `BLOCK_KINDS`），
    以及 B2a 的 N-1 四向：章页丢 `#### 要点梳理`（`explain`）、丢 `#### 记忆辅助`（`memorize`）、
    删掉整个 `knowledge/` 目录、删掉整个课程页目录（旧实现在页面目录缺失时静默 `continue`）。
    """
    from lib.ai_content_gate import run_ai_content_gate

    def _fresh_root(name: str) -> Path:
        fake_root = tmp_path / name / "repo"
        shutil.copytree(ROOT / "sources", fake_root / "sources")
        shutil.copytree(ROOT / "ops", fake_root / "ops")
        shutil.copytree(ROOT / "content", fake_root / "content")
        return fake_root

    course = "content/jiangsu/courses/15040"
    baseline_root = _fresh_root("baseline")
    assert run_ai_content_gate(baseline_root) == [], "未变异的对照根必须全绿"

    # N-1 对照前提：未变异章页上两类标题计数均 > 0（否则下面的「删光」变异是空洞通过）
    chapter = baseline_root / course / "knowledge" / "01-ch01.md"
    baseline_chapter = chapter.read_text(encoding="utf-8")
    assert baseline_chapter.count("#### 要点梳理") > 0, "对照前提：章页含 `#### 要点梳理`"
    assert baseline_chapter.count("#### 记忆辅助") > 0, "对照前提：章页含 `#### 记忆辅助`"

    # (a) practice.md 丢掉全部 AI 练习小节（等价于旧实现的「AI 备考层从未渲染」）
    root_a = _fresh_root("practice")
    practice = root_a / course / "practice.md"
    practice.write_text(
        "\n".join(line for line in practice.read_text(encoding="utf-8").splitlines() if not line.startswith("### ")),
        encoding="utf-8",
    )
    errors_a = run_ai_content_gate(root_a)
    assert any("practice.md" in e and "drill" in e for e in errors_a), errors_a

    # (b) plan.md 丢掉阶段名（stage_plan 未渲染）
    root_b = _fresh_root("plan")
    plan = root_b / course / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("### 阶段：", "### 阶段X："), encoding="utf-8")
    errors_b = run_ai_content_gate(root_b)
    assert any("plan.md" in e and "阶段" in e for e in errors_b), errors_b

    # (c) review.md 丢掉命名缺口区块（等价于排程缺口从未渲染到页面）
    root_c = _fresh_root("review")
    review = root_c / course / "review.md"
    text_c = review.read_text(encoding="utf-8")
    head, _, _tail = text_c.partition("## 命名缺口")
    assert head != text_c, "对照前提：页面含命名缺口区块"
    review.write_text(head + "## 边界\n", encoding="utf-8")
    errors_c = run_ai_content_gate(root_c)
    assert any("review.md" in e and "命名缺口" in e for e in errors_c), errors_c

    # (d) W1：plan.md 丢掉整个 `## 应试策略` 区块（课程级 exam_strategy 未渲染）
    root_d = _fresh_root("exam_strategy")
    plan_d = root_d / course / "plan.md"
    text_d = plan_d.read_text(encoding="utf-8")
    head_d, sep_d, tail_d = text_d.partition("## 应试策略")
    assert sep_d, "对照前提：页面含 `## 应试策略` 区块"
    next_h2 = tail_d.find("\n## ")
    assert next_h2 != -1, "对照前提：`## 应试策略` 之后还有下一个 H2"
    plan_d.write_text(head_d + tail_d[next_h2 + 1 :], encoding="utf-8")
    errors_d = run_ai_content_gate(root_d)
    assert any("应试策略" in e and "exam_strategy" in e for e in errors_d), errors_d

    # (e) W1 第二向：区块还在但正文被换掉 —— 必须按区块**内**内容对账，不能碰巧匹配页面别处
    root_e = _fresh_root("exam_strategy_text")
    plan_e = root_e / course / "plan.md"
    exam_text = _exam_strategy_text(ROOT)
    assert plan_e.read_text(encoding="utf-8").count(exam_text) == 1, "对照前提：正文只在应试策略区块内出现一次"
    plan_e.write_text(plan_e.read_text(encoding="utf-8").replace(exam_text, "（被替换掉的策略正文）"), encoding="utf-8")
    errors_e = run_ai_content_gate(root_e)
    assert any("应试策略" in e and "text_md" in e for e in errors_e), errors_e

    # (f) N-1：`01-ch01.md` 丢掉全部 `#### 要点梳理` 小节（该章的 `explain` 块未渲染到章页）
    root_f = _fresh_root("explain_summary")
    page_f = root_f / course / "knowledge" / "01-ch01.md"
    page_f.write_text(
        "\n".join(line for line in page_f.read_text(encoding="utf-8").splitlines() if line.rstrip() != "#### 要点梳理"),
        encoding="utf-8",
    )
    errors_f = run_ai_content_gate(root_f)
    assert any("要点梳理" in e and "explain" in e for e in errors_f), errors_f

    # (g) N-1：`01-ch01.md` 丢掉全部 `#### 记忆辅助` 小节（该章的 `memorize` 块未渲染到章页）
    root_g = _fresh_root("memorize_aid")
    page_g = root_g / course / "knowledge" / "01-ch01.md"
    page_g.write_text(
        "\n".join(line for line in page_g.read_text(encoding="utf-8").splitlines() if line.rstrip() != "#### 记忆辅助"),
        encoding="utf-8",
    )
    errors_g = run_ai_content_gate(root_g)
    assert any("记忆辅助" in e and "memorize" in e for e in errors_g), errors_g

    # (h) N-1：整个 `knowledge/` 目录消失 —— 旧实现在渲染页目录不存在时静默 `continue`，0 错误
    root_h = _fresh_root("no_knowledge_dir")
    shutil.rmtree(root_h / course / "knowledge")
    errors_h = run_ai_content_gate(root_h)
    assert errors_h, "整个章页目录消失必须报错（不得静默跳过整门课）"

    # (i) N-1 更极端形态（design note §3.1 第三行）：整个课程渲染页目录消失，旧实现同样 0 错误
    root_i = _fresh_root("no_course_dir")
    shutil.rmtree(root_i / course)
    errors_i = run_ai_content_gate(root_i)
    assert errors_i, "整个课程页目录消失必须报错（不得静默跳过整门课）"


def _exam_strategy_text(root: Path) -> str:
    """committed `content.json` 里课程级 `exam_strategy` 块的 `text_md`（渲染必须逐字带上它）。"""
    content = json.loads(
        (root / "sources" / "jiangsu" / "courses" / "15040" / "content.json").read_text(encoding="utf-8")
    )
    block = next(b for b in content["blocks"] if b["kind"] == "exam_strategy")
    return block["text_md"].strip()


def test_exam_strategy_block_is_rendered_on_the_committed_plan_page():
    """W1 产物断言：committed `exam_strategy.text_md` 必须出现在 `plan.md` 的 `## 应试策略` 区块内。"""
    plan = (ROOT / "content" / "jiangsu" / "courses" / "15040" / "plan.md").read_text(encoding="utf-8")
    section_start = plan.find("## 应试策略")
    assert section_start != -1, "plan.md 缺 `## 应试策略` 区块"
    section = plan[section_start:]
    next_h2 = section.find("\n## ", 1)
    if next_h2 != -1:
        section = section[:next_h2]
    text = _exam_strategy_text(ROOT)
    assert len(text) == 248, f"对照前提：committed text_md 为 248 字符，实际 {len(text)}"
    assert text in section, "课程级 exam_strategy 未落到 plan.md 的应试策略区块"
    assert "review_state=machine_draft" in section, "AI 块脚注（generator / evidence_refs / review_state）缺失"
    assert "evidence_refs=knowledge-model:exam" in section, "AI 块脚注缺 evidence_refs"

