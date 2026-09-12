"""Unit and integration tests for ai_content_gate (AI prep layer + markers + 8-gram)."""
from __future__ import annotations

import json
import re
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
    再加 F-QC2-1 两向（(j)/(k)）：章页丢掉**某一个**考核点的整个小节、再在别的章页补一条同名标题
    把全局计数补平 —— 计数对账（`rendered != expected`）对此 0 错误，必须由**逐点锚点**对账点名缺失的
    `point_id`，否则闸门只能看出「渲染了几个」而看不出「渲染了哪几个」。
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
    # M-1（T2 评审跟进）：断言到**具体消息**，与 (f)/(g) 同级；只断言「非空」会放过「报了别的错」。
    assert any("要点梳理" in e and "explain" in e for e in errors_h), errors_h
    assert any("记忆辅助" in e and "memorize" in e for e in errors_h), errors_h

    # (i) N-1 更极端形态（design note §3.1 第三行）：整个课程渲染页目录消失，旧实现同样 0 错误
    root_i = _fresh_root("no_course_dir")
    shutil.rmtree(root_i / course)
    errors_i = run_ai_content_gate(root_i)
    # M-1：必须点名「渲染页目录不存在」，而不是任何一条无关错误
    assert any("渲染页目录不存在" in e for e in errors_i), errors_i

    # (j) F-QC2-1（QC2 反例，逐字复现）：只删一个考核点的 `#### 要点梳理` **标题 + 正文**，
    #     该点锚点小节里的 `#### 记忆辅助` 不受影响；再在别的章页补一条同名标题把全局计数补平
    #     （255 → 255）。此时计数对账 **0 错误** —— QC2 在改前的闸门上实测 `errors == []` ——
    #     必须由逐点锚点对账点名缺失的 `point_id`。
    from lib.ai_content_gate import (
        EXPLAIN_SUMMARY_RE,
        MEMORIZE_AID_RE,
        POINT_ANCHOR_RE,
    )

    course_43 = "content/jiangsu/courses/15043"
    victim = "15043-ch01-s1-p1"

    def _chapter_text(root: Path) -> str:
        return "".join(
            page.read_text(encoding="utf-8")
            for page in sorted((root / course_43 / "knowledge").glob("*.md"))
        )

    def _explain_section(page: Path, point_id: str) -> str:
        """该 `point_id` 的 `### 考点精讲：<id>` 锚点小节原文（到下一个 H3 或页尾为止）。"""
        text = page.read_text(encoding="utf-8")
        start = text.index(f"### 考点精讲：{point_id}（")
        nxt = re.search(r"(?m)^### ", text[start + 1 :])
        return text[start : start + 1 + nxt.start()] if nxt else text[start:]

    def _drop_marker_section(page: Path, marker: str) -> None:
        """删掉页面上**第一条** `marker` 标题及其正文（到下一个标题为止）。"""
        lines = page.read_text(encoding="utf-8").splitlines(keepends=True)
        i = next(n for n, line in enumerate(lines) if line.rstrip("\n") == marker)
        j = next(n for n in range(i + 1, len(lines)) if lines[n].startswith("#"))
        page.write_text("".join(lines[:i] + lines[j:]), encoding="utf-8")

    root_j = _fresh_root("anchor_explain")
    page_j = root_j / course_43 / "knowledge" / "01-ch01.md"
    baseline_page_j = (baseline_root / course_43 / "knowledge" / "01-ch01.md").read_text(encoding="utf-8")
    assert f"### 考点精讲：{victim}（" in baseline_page_j, "对照前提：受害点在对照页上有渲染器锚点"
    victim_section = _explain_section(page_j, victim)
    assert "#### 要点梳理" in victim_section, "对照前提：受害点的锚点小节内含 `#### 要点梳理`"
    assert "#### 记忆辅助" in victim_section, "对照前提：受害点的锚点小节内含 `#### 记忆辅助`"
    assert victim_section.count("#### ") == 3, "对照前提：该节含 要点梳理 / 易错点 / 记忆辅助 三个 H4 小节"
    assert len(re.findall(r"(?m)^### ", victim_section)) == 1, "对照前提：该节的边界只由自己的锚点 H3 划定"

    explain_before = len(EXPLAIN_SUMMARY_RE.findall(_chapter_text(root_j)))
    memorize_before = len(MEMORIZE_AID_RE.findall(_chapter_text(root_j)))
    _drop_marker_section(page_j, "#### 要点梳理")
    # 在别的章页补一条同名标题，把全局计数补平（删一条 + 补一条 = 255 不变）
    pad_j = root_j / course_43 / "knowledge" / "10-ch10.md"
    pad_j.write_text(pad_j.read_text(encoding="utf-8") + "\n#### 要点梳理\n", encoding="utf-8")
    # QC2 的反例前提：全局计数被补平，计数对账看不见这个丢块
    assert len(EXPLAIN_SUMMARY_RE.findall(_chapter_text(root_j))) == explain_before, "对照前提：计数已补平"
    assert len(MEMORIZE_AID_RE.findall(_chapter_text(root_j))) == memorize_before, "对照前提：记忆辅助计数未受影响"
    assert POINT_ANCHOR_RE.search(f"### 考点精讲：{victim}（识记）"), "对照前提：锚点正则匹配渲染器契约标题"

    errors_j = run_ai_content_gate(root_j)
    # 断言到**具体消息**：必须是逐点对账那条，且点名受害 point_id（只断言「非空」会放过「报了别的错」）
    assert any("锚点小节内缺少" in e and "要点梳理" in e and victim in e for e in errors_j), errors_j

    # (k) 补强：受害点整个小节（锚点 + explain + memorize）消失时，两个 kind 都要点名它
    root_k = _fresh_root("anchor_section")
    page_k = root_k / course_43 / "knowledge" / "01-ch01.md"
    page_k.write_text(
        page_k.read_text(encoding="utf-8").replace(_explain_section(page_k, victim), "", 1), encoding="utf-8"
    )
    assert f"### 考点精讲：{victim}（" not in page_k.read_text(encoding="utf-8"), "对照前提：整节（含锚点）已删除"
    errors_k = run_ai_content_gate(root_k)
    assert any("锚点" in e and victim in e for e in errors_k), errors_k
    assert len([e for e in errors_k if victim in e]) >= 2, f"explain 与 memorize 都要点名 {victim}: {errors_k}"


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


# --------------------------------------------------------------------------------------
# X2（F-QC3-2）：作用域键不得自我关闭 —— AI 页面在、真值源不在 = 必须报错
# --------------------------------------------------------------------------------------

def test_scope_key_cannot_switch_itself_off(tmp_path: Path):
    """X2 变异证明：删掉 `content.json` 但保留 AI 渲染页 → 必须报错（改前为 0 错误 / 7 层全绿）。

    这是发布安全面：真值源缺失时 16 个 AI 页面照常部署，而 `run-gates.py` 主路径 exit 0。
    """
    from lib.ai_content_gate import run_ai_content_gate

    def _fresh_root(name: str) -> Path:
        fake_root = tmp_path / name / "repo"
        shutil.copytree(ROOT / "sources", fake_root / "sources")
        shutil.copytree(ROOT / "ops", fake_root / "ops")
        shutil.copytree(ROOT / "content", fake_root / "content")
        return fake_root

    root = _fresh_root("x2")
    assert run_ai_content_gate(root) == [], "未变异的对照根必须全绿"

    # 对照前提：变异前该课程的渲染页确实带 AI 横幅（否则「删 content.json 报错」可能来自无关原因）
    page = root / "content" / "jiangsu" / "courses" / "15043" / "knowledge" / "01-ch01.md"
    assert "本页由 AI 辅助生成" in page.read_text(encoding="utf-8"), "对照前提：AI 横幅在渲染页上"
    (root / "sources" / "jiangsu" / "courses" / "15043" / "content.json").unlink()

    errors = run_ai_content_gate(root)
    assert any("15043" in e and "content.json" in e for e in errors), errors
    assert any("真值源缺失" in e for e in errors), errors


def test_scope_rule_still_silences_courses_without_any_ai_products(tmp_path: Path):
    """X2 反向对照：既无 `content.json` 又无 AI 页面的课程**必须保持静默**（不破坏作用域规则）。

    其余 16 门课正是这个形态：只有 3 个非 AI 页（`index.md` / `syllabus.md` / `sources.md`），
    既没有 AI 横幅、也没有 `content.json`。若 X2 的反向判定认错信号，这里会整片飘红。
    """
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "x2-control" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    errors = run_ai_content_gate(fake_root)
    assert errors == [], f"无 AI 产物的课程不得被 X2 反向判定误伤: {errors}"
    assert not any("03708" in e for e in errors), errors


def test_reverse_condition_stays_silent_when_the_ai_pages_are_gone_too(tmp_path: Path):
    """X2 边界：`content.json` 与 AI 页目录**一起**消失 = 这门课没有 AI 层，保持静默。

    反向判定只在「AI 产物在仓内、真值源不在」时报错；两者都没有时与其余 16 门课同形。
    """
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "x2-both-gone" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    (fake_root / "sources" / "jiangsu" / "courses" / "15043" / "content.json").unlink()
    shutil.rmtree(fake_root / "content" / "jiangsu" / "courses" / "15043")

    errors = run_ai_content_gate(fake_root)
    assert errors == [], f"AI 层整体不存在时不得报错: {errors}"


# --------------------------------------------------------------------------------------
# Y1（R18）：删掉**整个源目录**时作用域判定不得跟着消失 —— 「产物存在」蕴含「源存在」
# --------------------------------------------------------------------------------------

def test_scope_rule_survives_deleting_the_whole_source_dir(tmp_path: Path):
    """Y1 变异证明：`rmtree sources/jiangsu/courses/15043/`（16 个渲染页仍在）→ 必须报错。

    改前为 0 错误、`run-gates.py` 7/7 绿。根因是作用域键只从**源侧**取：X2 的反向判定以
    `content.json` **单文件**为键，整目录缺失时源侧迭代器里已经没有这门课，于是连反向判定都不会被走到
    —— 删得越彻底越安全，与 X2 想堵的方向恰好相反。

    修法：作用域键取**源侧 ∪ 产物侧**的课码并集，「产物存在」蕴含「源存在」。报文点名缺失的是**目录**
    而非 `content.json`（后者在整目录缺失时并不单独存在），错误文案里仍带课码与「真值源缺失」。

    同时钉住 `run-gates.py` 主路径：这一层是发布安全面，闸门必须 exit ≠ 0。
    """
    import subprocess
    import sys

    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "y1" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")
    shutil.copytree(ROOT / "scripts", fake_root / "scripts")

    # 对照前提：删之前该课的渲染页确实带 AI 横幅（否则「报错」可能来自无关原因）
    rendered = fake_root / "content" / "jiangsu" / "courses" / "15043"
    page = rendered / "knowledge" / "01-ch01.md"
    assert "本页由 AI 辅助生成" in page.read_text(encoding="utf-8"), "对照前提：AI 横幅在渲染页上"
    assert run_ai_content_gate(fake_root) == [], "未变异的对照根必须全绿"

    pages_before = len(list(rendered.rglob("*.md")))
    shutil.rmtree(fake_root / "sources" / "jiangsu" / "courses" / "15043")
    assert len(list(rendered.rglob("*.md"))) == pages_before == 16, "对照前提：16 个渲染页仍在"

    errors = run_ai_content_gate(fake_root)
    assert any("15043" in e and "真值源缺失" in e for e in errors), errors
    assert any("整个源目录缺失" in e for e in errors), (
        f"报文必须点名缺失的**目录**（整目录缺失时 content.json 并不单独存在）: {errors}"
    )

    # 发布安全面：run-gates 主路径必须失败（改前 exit 0 / 7 层全绿）
    proc = subprocess.run(
        [sys.executable, str(fake_root / "scripts" / "run-gates.py")],
        cwd=fake_root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, f"整目录缺失必须让 run-gates 失败\n{proc.stdout}"
    assert "[ai-content] FAILED" in proc.stdout, proc.stdout


def test_scope_rule_still_silences_courses_without_ai_pages_on_a_mutated_tree(tmp_path: Path):
    """Y1 对照：作用域键扩到产物侧后，**无 AI 页**的课程仍必须静默（不误伤其余 16 门课）。

    与 `test_scope_rule_still_silences_courses_without_any_ai_products` 的差别在**同一棵已变异的树**上：
    那一条证明「干净树上不误伤」，这一条证明「`15043` 源目录缺失的树上，`03708` 仍不被牵连」——
    并集键若认错信号（例如把「有目录」当「有 AI 产物」），16 门课会整片飘红。
    """
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "y1-control" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    shutil.rmtree(fake_root / "sources" / "jiangsu" / "courses" / "15043")

    errors = run_ai_content_gate(fake_root)
    assert run_ai_content_gate(fake_root, course_code="03708") == [], "无 AI 页的课程必须静默"
    assert not any("03708" in e for e in errors), errors
    assert not any("15040" in e for e in errors), errors
    # 只有 15043 这一门被点名（并集键不得放大成整片飘红）
    assert [e.split(":")[0] for e in errors] == ["course 15043"], errors


def test_scope_rule_stays_silent_when_source_dir_and_ai_pages_are_both_gone(tmp_path: Path):
    """Y1 边界：源目录与 AI 页目录**一起**消失 = 这门课没有 AI 层，保持静默。

    这是正确的「无产物」态（与其余 16 门课同形）：反向判定只在「AI 产物在仓内、真值源不在」时报错。
    **必须在干净的新树上验**：`maturity-check` 读的是生成态投影（不 import 本模块），
    在同一棵树里先做过别的变异后它会独立误红 —— 那是另一层，不是本层的作用域判定。
    """
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "y1-both-gone" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    shutil.rmtree(fake_root / "sources" / "jiangsu" / "courses" / "15043")
    shutil.rmtree(fake_root / "content" / "jiangsu" / "courses" / "15043")

    errors = run_ai_content_gate(fake_root)
    assert errors == [], f"AI 层整体不存在时不得报错: {errors}"


def test_scope_rule_stays_silent_when_the_ai_pages_are_replaced_by_official_only(tmp_path: Path):
    """Y1 第三控制：源目录缺失、但产物侧只剩**非 AI 页**（3 张官方事实页）→ 静默。

    判定认的是「带 AI 横幅的 AI 分类页面」，不是「目录存在」。若并集键退化成「产物侧有目录就算
    AI 产物」，这条会误报 —— 而它正是其余 16 门课的真实形态（`content/jiangsu/courses/<code>/`
    一律存在，但只有 `index.md` / `syllabus.md` / `sources.md`）。
    """
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "y1-official-only" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    shutil.rmtree(fake_root / "sources" / "jiangsu" / "courses" / "15043")
    rendered = fake_root / "content" / "jiangsu" / "courses" / "15043"
    for name in ("plan.md", "practice.md", "review.md"):
        (rendered / name).unlink()
    shutil.rmtree(rendered / "knowledge")

    errors = run_ai_content_gate(fake_root)
    assert errors == [], f"只剩官方页的课程不得被并集键误判成 AI 产物: {errors}"


# --------------------------------------------------------------------------------------
# X1 (a)/(c)（F-QC3-1）：逐点对账必须挡住「清空正文」与「围栏内填充标题」
# --------------------------------------------------------------------------------------

def test_per_point_reconciliation_rejects_emptied_body_and_fenced_padding(tmp_path: Path):
    """X1 剩余两种规避的变异证明（QC3 在 `8e8c190` 上复现，改前均 0 错误）。

    (a) 标题保留、**正文被清空**（含只留 `<!-- ai-block -->` 脚注的形态）→ 空壳不算到达；
    (c) 标题被放进**代码围栏**（` ``` ` / `~~~`）→ 围栏内的行不是渲染证据，等价于标题不存在；
    另附 (b) 的回归（重复填充标题仍必须被点名）与 15040 的对照（改动不得误伤另一门课）。
    """
    from lib.ai_content_gate import run_ai_content_gate

    def _fresh_root(name: str) -> Path:
        fake_root = tmp_path / name / "repo"
        shutil.copytree(ROOT / "sources", fake_root / "sources")
        shutil.copytree(ROOT / "ops", fake_root / "ops")
        shutil.copytree(ROOT / "content", fake_root / "content")
        return fake_root

    course = "content/jiangsu/courses/15043"
    victim = "15043-ch01-s1-p1"
    baseline_root = _fresh_root("baseline")
    assert run_ai_content_gate(baseline_root) == [], "未变异的对照根必须全绿"

    page_path = baseline_root / course / "knowledge" / "01-ch01.md"
    baseline_page = page_path.read_text(encoding="utf-8")
    assert f"### 考点精讲：{victim}（" in baseline_page, "对照前提：受害点在对照页上有渲染器锚点"

    def _section_page_text(root: Path, name: str) -> str:
        return (root / course / "knowledge" / name).read_text(encoding="utf-8")

    def _drop_heading_body(page: Path, marker: str) -> None:
        """删掉 `marker` 标题与其正文（到下一个标题为止），**保留**标题行由调用方决定。"""
        lines = page.read_text(encoding="utf-8").splitlines(keepends=True)
        i = next(n for n, line in enumerate(lines) if line.rstrip("\n") == marker)
        j = next(n for n in range(i + 1, len(lines)) if lines[n].startswith("#"))
        del lines[i + 1 : j]
        page.write_text("".join(lines), encoding="utf-8")

    # (a) 正文清空、标题保留 —— 改前 0 错误
    root_a = _fresh_root("emptied_body")
    _drop_heading_body(root_a / course / "knowledge" / "01-ch01.md", "#### 要点梳理")
    errors_a = run_ai_content_gate(root_a)
    assert any("正文为空" in e and victim in e for e in errors_a), errors_a

    # (a') 清空正文但留下 `<!-- ai-block -->` 脚注 —— 注释不是正文，同样必须失败
    root_a2 = _fresh_root("emptied_body_footer")
    page_a2 = root_a2 / course / "knowledge" / "01-ch01.md"
    text_a2 = page_a2.read_text(encoding="utf-8")
    i2 = text_a2.index("#### 要点梳理")
    j2 = text_a2.index("#### 记忆辅助")
    footer = re.search(r"<!-- ai-block .*?-->", text_a2[i2:j2], re.S)
    assert footer is not None, "对照前提：explain 块脚注在 要点梳理 与 记忆辅助 之间"
    page_a2.write_text(
        text_a2[:i2] + "#### 要点梳理\n\n" + footer.group(0) + "\n\n" + text_a2[j2:], encoding="utf-8"
    )
    errors_a2 = run_ai_content_gate(root_a2)
    assert any("正文为空" in e and victim in e for e in errors_a2), errors_a2

    # (c) 标题被塞进代码围栏（原地：受害点的锚点小节内）—— 改前 0 错误
    root_c = _fresh_root("fenced_pad")
    page_c = root_c / course / "knowledge" / "10-ch10.md"
    lines_c = page_c.read_text(encoding="utf-8").splitlines(keepends=True)
    heading_index = [n for n, line in enumerate(lines_c) if line.rstrip("\n") == "#### 要点梳理"][-1]
    anchor_index = max(n for n in range(heading_index) if lines_c[n].startswith("### 考点精讲："))
    fenced_victim = lines_c[anchor_index].rstrip("\n").split("：", 1)[1].split("（", 1)[0]
    end_index = next(
        n for n in range(heading_index + 1, len(lines_c)) if lines_c[n].startswith("#")
    )
    del lines_c[heading_index:end_index]
    lines_c.insert(anchor_index + 1, "\n```markdown\n#### 要点梳理\n- 填充正文\n```\n\n")
    page_c.write_text("".join(lines_c), encoding="utf-8")
    assert "```" in _section_page_text(root_c, "10-ch10.md"), "对照前提：围栏已插入"
    errors_c = run_ai_content_gate(root_c)
    assert any("锚点小节内缺少" in e and fenced_victim in e for e in errors_c), errors_c
    assert any("小节数" in e for e in errors_c), f"围栏内的标题不得计入次级计数: {errors_c}"

    # (c') 删标题 + 在**别的章页**用围栏补一条同名标题（把全局裸行计数补平）
    root_c2 = _fresh_root("fenced_pad_elsewhere")
    lines_c2 = (root_c2 / course / "knowledge" / "01-ch01.md").read_text(encoding="utf-8").splitlines(
        keepends=True
    )
    i_c2 = next(n for n, line in enumerate(lines_c2) if line.rstrip("\n") == "#### 要点梳理")
    j_c2 = next(n for n in range(i_c2 + 1, len(lines_c2)) if lines_c2[n].startswith("#"))
    del lines_c2[i_c2:j_c2]
    (root_c2 / course / "knowledge" / "01-ch01.md").write_text("".join(lines_c2), encoding="utf-8")
    pad_c2 = root_c2 / course / "knowledge" / "10-ch10.md"
    pad_c2.write_text(
        pad_c2.read_text(encoding="utf-8") + "\n```\n#### 要点梳理\n```\n", encoding="utf-8"
    )
    errors_c2 = run_ai_content_gate(root_c2)
    assert any(victim in e for e in errors_c2), errors_c2

    # (b) 回归：围栏**之外**的重复填充标题仍必须点名受害点（F-QC2-1 不因本次改动回退）
    root_b = _fresh_root("unfenced_pad")
    lines_b = (root_b / course / "knowledge" / "01-ch01.md").read_text(encoding="utf-8").splitlines(
        keepends=True
    )
    i_b = next(n for n, line in enumerate(lines_b) if line.rstrip("\n") == "#### 要点梳理")
    j_b = next(n for n in range(i_b + 1, len(lines_b)) if lines_b[n].startswith("#"))
    del lines_b[i_b:j_b]
    (root_b / course / "knowledge" / "01-ch01.md").write_text("".join(lines_b), encoding="utf-8")
    pad_b = root_b / course / "knowledge" / "10-ch10.md"
    pad_b.write_text(pad_b.read_text(encoding="utf-8") + "\n#### 要点梳理\n- 填充正文\n", encoding="utf-8")
    errors_b = run_ai_content_gate(root_b)
    assert any(victim in e for e in errors_b), errors_b

    # 对照：另一门课（15040）在同样的 fence-aware 口径下仍然全绿
    root_40 = _fresh_root("course_15040")
    assert run_ai_content_gate(root_40) == [], "15040 必须零回归"


def test_chapter_page_pattern_comes_from_the_schema(tmp_path: Path):
    """R9/W-2：章页模式由 schema 的 `generated_page_markers.ai_pages` 派生，模块内不再有第二份字面量。

    变异证明：把 schema 里的 `knowledge/*.md` 换成另一个子目录模式后，闸门按**新**模式选章页
    （若还硬编码旧字面量，则会因为「找不到任何章页」而报出一堆计数/锚点错误）。
    """
    import lib.course_pages_contract as cpc
    from lib.ai_content_gate import _chapter_page_patterns

    markers = cpc.generated_page_markers(cpc.load_schema(ROOT))
    assert _chapter_page_patterns(markers) == {"knowledge/*.md"}, _chapter_page_patterns(markers)

    def _with_ai_pages(*patterns: str) -> dict:
        return {**markers, "ai_pages": set(patterns)}

    mutated = _with_ai_pages("plan.md", "practice.md", "review.md", "knowledge/*.md", "chapters/*.md")
    assert _chapter_page_patterns(mutated) == {"knowledge/*.md", "chapters/*.md"}, "必须随 schema 变化"

    # 不含 `/` 的模式（课程级 AI 页）不得被当成章页模式
    only_top = _with_ai_pages("plan.md", "practice.md")
    assert _chapter_page_patterns(only_top) == {"plan.md", "practice.md"}, "退化时仍不得为空集"


# --------------------------------------------------------------------------------------
# Y2（R19）：注释包住标题与注释包住正文必须同判 —— 剥注释要发生在**标题扫描之前**
# --------------------------------------------------------------------------------------

def test_comment_wrapped_heading_is_not_render_evidence(tmp_path: Path):
    """Y2 变异证明：`<!--` 开在 `#### 要点梳理` 标题行**之前**、`-->` 收在正文之后 → 必须报错。

    改前为 **0 错误**（`run-gates.py` 7/7 绿）。根因是注释只被 `_is_empty_body()` 在**正文切片内**剥掉：
    `<!--` 落在切片之外，切片里只剩注释尾巴，剥完仍非空 → 判「已到达」。而该节对读者**完全不可见**。

    区分性对照（QC3 提供，证明这不是「检查太严」）：标题在注释**之外**、**正文**被注释掉 → 改前**能**
    抓到（1 条错误）。两种形状对读者等价，判定必须同形；缺口正是这条**不对称**。

    本用例同时钉住对照形状**行为不退化**：包正文的那一侧仍报错并点名同一个 `point_id`。
    """
    from lib.ai_content_gate import EXPLAIN_SUMMARY_RE, run_ai_content_gate

    def _fresh_root(name: str) -> Path:
        fake_root = tmp_path / name / "repo"
        shutil.copytree(ROOT / "sources", fake_root / "sources")
        shutil.copytree(ROOT / "ops", fake_root / "ops")
        shutil.copytree(ROOT / "content", fake_root / "content")
        return fake_root

    course = "content/jiangsu/courses/15043"
    victim = "15043-ch01-s1-p1"

    baseline_root = _fresh_root("baseline")
    assert run_ai_content_gate(baseline_root) == [], "未变异的对照根必须全绿"

    def _heading_and_next(page: Path) -> tuple[list[str], int, int]:
        lines = page.read_text(encoding="utf-8").splitlines(keepends=True)
        heading = next(n for n, line in enumerate(lines) if line.rstrip("\n") == "#### 要点梳理")
        following = next(n for n in range(heading + 1, len(lines)) if lines[n].startswith("#"))
        return lines, heading, following

    # 对照前提：受害点在对照页上有锚点，且该锚点小节内确有 `#### 要点梳理`
    page_path = baseline_root / course / "knowledge" / "01-ch01.md"
    assert f"### 考点精讲：{victim}（" in page_path.read_text(encoding="utf-8"), (
        "对照前提：受害点在对照页上有渲染器锚点"
    )

    # (A) 缺口形态：注释开在标题行**之前**、收在该节正文之后 → 标题 + 整段正文对读者不可见
    root_a = _fresh_root("comment_before_heading")
    page_a = root_a / course / "knowledge" / "01-ch01.md"
    lines_a, heading_a, next_a = _heading_and_next(page_a)
    page_a.write_text(
        "".join(lines_a[:heading_a] + ["<!--\n"] + lines_a[heading_a:next_a] + ["-->\n"] + lines_a[next_a:]),
        encoding="utf-8",
    )
    # 对照前提：标题行落在两个注释记号**之间**（真的是「包住标题」而不是别处）
    text_a = page_a.read_text(encoding="utf-8")
    assert text_a.index("<!--") < text_a.index("#### 要点梳理") < text_a.rindex("-->"), (
        "对照前提：`<!--` 在标题之前、`-->` 在标题之后"
    )
    assert len(EXPLAIN_SUMMARY_RE.findall(text_a)) > 0, "对照前提：标题行文本仍逐字在页面上（只是被注释包住）"

    errors_a = run_ai_content_gate(root_a)
    assert any("要点梳理" in e and "explain" in e and victim in e for e in errors_a), (
        f"注释包住的标题不是渲染证据，必须点名 {victim}: {errors_a}"
    )

    # (B) QC3 的对照形状：标题在注释**之外**、正文被注释掉 → 改前就能抓到，**必须不退化**
    root_b = _fresh_root("comment_wraps_body")
    page_b = root_b / course / "knowledge" / "01-ch01.md"
    lines_b, heading_b, next_b = _heading_and_next(page_b)
    lines_b.insert(next_b, "-->\n")
    lines_b.insert(heading_b + 1, "<!--\n")
    page_b.write_text("".join(lines_b), encoding="utf-8")
    errors_b = run_ai_content_gate(root_b)
    assert any("正文为空" in e and victim in e for e in errors_b), (
        f"对照形状（正文被注释）行为不得退化: {errors_b}"
    )

    # (C) 干净根零回归：两门课都不得因剥注释而误报
    assert run_ai_content_gate(_fresh_root("clean")) == [], "干净树上不得误报"

    # (D) 非回归：注释与围栏**都**不参与判定，但围栏内的标题仍不算证据（F-QC3-1(c) 未被本次改动放松）
    root_d = _fresh_root("fenced_pad")
    page_d = root_d / course / "knowledge" / "01-ch01.md"
    lines_d, heading_d, next_d = _heading_and_next(page_d)
    del lines_d[heading_d:next_d]
    lines_d.insert(heading_d, "```markdown\n#### 要点梳理\n- 填充正文\n```\n")
    page_d.write_text("".join(lines_d), encoding="utf-8")
    errors_d = run_ai_content_gate(root_d)
    assert any("锚点小节内缺少" in e and victim in e for e in errors_d), errors_d


def test_comment_stripping_does_not_swallow_later_headings(tmp_path: Path):
    """Y2 反向控制：剥注释只剥**配对完整**的注释，绝不把其后的标题一并吞掉（不制造误报）。

    若实现改成「`<!--` 起、直到文件尾」这种贪婪口径，一条未闭合的示例注释就会让整个后文失去证据，
    真标题被当成缺失 → 误报。本用例用**未闭合**的 `<!--` 验证真标题仍被认作证据。
    """
    from lib.ai_content_gate import run_ai_content_gate

    fake_root = tmp_path / "unclosed-comment" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    page = fake_root / "content" / "jiangsu" / "courses" / "15043" / "knowledge" / "01-ch01.md"
    page.write_text(page.read_text(encoding="utf-8") + "\n<!-- 未闭合的示例注释\n", encoding="utf-8")

    errors = run_ai_content_gate(fake_root)
    assert errors == [], f"未闭合注释不得吞掉其后的证据、制造误报: {errors}"


def test_visible_heading_count_ignores_commented_headings(tmp_path: Path):
    """Y2 次级界限同形：注释里的同名标题不计入「已渲染」的可见小节数。

    主判据是逐点锚点；这一条钉住**次级页级界限**的同一口径 —— 若计数仍用裸行匹配，把一条
    `#### 要点梳理` 塞进注释即可把计数补平（与 F-QC2-1 的 padding 同一失败形态）。
    """
    from lib.ai_content_gate import EXPLAIN_SUMMARY_RE, run_ai_content_gate

    fake_root = tmp_path / "commented-pad" / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "content", fake_root / "content")

    course = "content/jiangsu/courses/15043"
    page = fake_root / course / "knowledge" / "01-ch01.md"
    text = page.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # 删掉第一个真标题 + 正文，再在同页补一条**注释里**的同名标题（裸行计数不变、可见计数 -1）
    heading = next(n for n, line in enumerate(lines) if line.rstrip("\n") == "#### 要点梳理")
    following = next(n for n in range(heading + 1, len(lines)) if lines[n].startswith("#"))
    del lines[heading:following]
    lines.append("<!--\n#### 要点梳理\n-->\n")
    page.write_text("".join(lines), encoding="utf-8")

    padded = page.read_text(encoding="utf-8")
    assert len(EXPLAIN_SUMMARY_RE.findall(padded)) == len(EXPLAIN_SUMMARY_RE.findall(text)), (
        "对照前提：裸行计数被补平（注释里的同名标题仍被裸正则数到）"
    )

    errors = run_ai_content_gate(fake_root)
    assert any("小节数" in e and "explain" in e for e in errors), (
        f"注释里的标题不得计入可见小节数（否则计数可被注释补平）: {errors}"
    )
