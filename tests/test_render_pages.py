"""Unit and integration tests for course page rendering and site integration."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

COURSE_15040 = ROOT / "content" / "jiangsu" / "courses" / "15040"
SOURCES_15040 = ROOT / "sources" / "jiangsu" / "courses" / "15040"

DERIVED_BEGIN_RE = re.compile(r"<!--\s*derived:begin\s+id=([a-zA-Z0-9_-]+)\s*-->")
DERIVED_END_RE = re.compile(r"<!--\s*derived:end\s*-->")


def _derived_layout_problems(text: str, where: str) -> list[str]:
    """`derived:` 区块的**结构**问题：未配平（孤儿 begin/end）或区块嵌套（一个区块包住另一个）。

    X1：`chapter-links` 曾包住 `release-status`，而匹配用的是非贪婪「到第一个 `derived:end` 为止」，
    因此「刷新章节链接」会把内层区块整段吞掉并留下孤儿结束标记。结构必须可独立断言 ——
    否则这条路径只能靠触发它才发现（两个缺陷当时正互相掩盖）。
    """
    markers: list[tuple[int, str, str]] = []
    for pattern, kind in ((DERIVED_BEGIN_RE, "begin"), (DERIVED_END_RE, "end")):
        for matched in pattern.finditer(text):
            markers.append((matched.start(), kind, matched.group(1) if kind == "begin" else ""))
    problems: list[str] = []
    stack: list[str] = []
    for _offset, kind, block_id in sorted(markers):
        if kind == "begin":
            if stack:
                problems.append(f"{where}: {block_id} 区块嵌在 {stack[-1]} 区块内部")
            stack.append(block_id)
        elif stack:
            stack.pop()
        else:
            problems.append(f"{where}: 出现无配对 begin 的孤儿 derived:end")
    problems += [f"{where}: {block_id} 区块缺少配对的 derived:end" for block_id in stack]
    return problems


def _derived_region(text: str, block_id: str) -> str:
    """取 `id=block_id` 区块的**内部正文**（配平扫描，故嵌套/外层不受影响）。区块缺失即断言失败。"""
    opened = text.find(f"<!-- derived:begin id={block_id} -->")
    assert opened != -1, f"缺少 {block_id} 区块"
    cursor = opened + len(f"<!-- derived:begin id={block_id} -->")
    depth = 1
    while depth:
        nxt_begin = DERIVED_BEGIN_RE.search(text, cursor)
        nxt_end = DERIVED_END_RE.search(text, cursor)
        assert nxt_end is not None, f"{block_id} 区块缺少配对的 derived:end"
        if nxt_begin is not None and nxt_begin.start() < nxt_end.start():
            depth += 1
            cursor = nxt_begin.end()
        else:
            depth -= 1
            cursor = nxt_end.end()
    return text[opened + len(f"<!-- derived:begin id={block_id} -->") : cursor - len("<!-- derived:end -->")]


def test_render_is_deterministic(tmp_path: Path):
    """连续渲染两次，除 generated_at 行外字节一致。"""
    from lib.course_pipeline.render_pages import render_course_pages

    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"
    shutil.copytree(COURSE_15040, dir1)
    shutil.copytree(COURSE_15040, dir2)

    render_course_pages(ROOT, "15040", target_dir=dir1)
    render_course_pages(ROOT, "15040", target_dir=dir2)

    files1 = sorted(p.relative_to(dir1).as_posix() for p in dir1.glob("**/*") if p.is_file())
    files2 = sorted(p.relative_to(dir2).as_posix() for p in dir2.glob("**/*") if p.is_file())
    assert files1 == files2

    for rel in files1:
        t1 = (dir1 / rel).read_text(encoding="utf-8")
        t2 = (dir2 / rel).read_text(encoding="utf-8")
        assert t1 == t2, f"Nondeterministic rendering output for {rel}"


def test_manual_block_preserved(tmp_path: Path):
    """在 manual:begin/end 内写入哨兵文本 → 重渲染后仍在原位且内容不变。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    sentinel = "<!-- SENTINEL_MANUAL_TEXT_99999 -->"
    review_file = work_dir / "review.md"
    orig_text = review_file.read_text(encoding="utf-8")
    if "<!-- manual:begin" in orig_text:
        modified = re.sub(
            r"(<!-- manual:begin id=[a-zA-Z0-9_-]+ -->)",
            rf"\1\n{sentinel}\n",
            orig_text,
            count=1,
        )
    else:
        modified = orig_text + f"\n<!-- manual:begin id=schedules -->\n{sentinel}\n<!-- manual:end -->\n"
    review_file.write_text(modified, encoding="utf-8")

    render_course_pages(ROOT, "15040", target_dir=work_dir)
    rendered_text = (work_dir / "review.md").read_text(encoding="utf-8")
    assert sentinel in rendered_text, "Manual block sentinel text must be preserved after render"


def test_frontmatter_preserved_bytewise(tmp_path: Path):
    """15040/index.md 的 frontmatter（:1-58）在渲染前后字节一致。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    orig_text = (work_dir / "index.md").read_text(encoding="utf-8")
    orig_fm = "\n".join(orig_text.splitlines()[:58]) + "\n"

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    rendered_text = (work_dir / "index.md").read_text(encoding="utf-8")
    rendered_fm = "\n".join(rendered_text.splitlines()[:58]) + "\n"
    assert rendered_fm == orig_fm, "Frontmatter bytes must match exactly"


def test_practice_first_line_is_canonical_h1(tmp_path: Path):
    """渲染后 practice.md 首行 == `# 习近平新时代中国特色社会主义思想概论（15040）：练习与真题`；generated-by 注释在其之后。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    lines = (work_dir / "practice.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# 习近平新时代中国特色社会主义思想概论（15040）：练习与真题"
    assert any("<!-- generated by scripts/build-course-content.py; do not edit -->" in line for line in lines[1:5])


def test_practice_h2_set_unchanged(tmp_path: Path):
    """渲染后 practice.md 的 H2 序列 == `["## 资料状态","## 练习流程","## 记录模板","## 边界"]`（AI 练习块必须是 `###` 层级）。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    lines = (work_dir / "practice.md").read_text(encoding="utf-8").splitlines()
    h2s = [line.strip() for line in lines if line.startswith("## ")]
    assert h2s == ["## 资料状态", "## 练习流程", "## 记录模板", "## 边界"]


def test_practice_zhenti_row_status(tmp_path: Path):
    """## 资料状态 的 历年真题 行第 4 列为 metadata-only。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    text = (work_dir / "practice.md").read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if "历年真题" in line and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and cells[0] == "历年真题":
                rows.append(cells)
    assert rows, "missing 历年真题 row in practice.md"
    assert rows[0][3] == "metadata-only"


def test_contract_markers_present(tmp_path: Path):
    """index.md 含 页面导航 / sources.md / practice.md / plan.md；sources.md 含 来源 / 核验；practice.md 含 真题；plan.md 含 阶段目标。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    idx = (work_dir / "index.md").read_text(encoding="utf-8")
    for marker in ["页面导航", "sources.md", "practice.md", "plan.md"]:
        assert marker in idx, f"index.md missing marker {marker}"

    src = (work_dir / "sources.md").read_text(encoding="utf-8")
    for marker in ["来源", "核验"]:
        assert marker in src, f"sources.md missing marker {marker}"

    prac = (work_dir / "practice.md").read_text(encoding="utf-8")
    assert "真题" in prac, "practice.md missing marker 真题"

    pln = (work_dir / "plan.md").read_text(encoding="utf-8")
    assert "阶段目标" in pln, "plan.md missing marker 阶段目标"


def test_start_here_block_and_cross_links(tmp_path: Path):
    """index.md 的 ## 开始学习 四步顺序 == [考纲与范围→syllabus.md, 学习计划→plan.md, 练习与真题→practice.md, 来源与核验→sources.md]；每页互链栏包含其余四类页面且不自链。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    idx = (work_dir / "index.md").read_text(encoding="utf-8")
    assert "## 开始学习" in idx

    steps = []
    for line in idx.splitlines():
        m = re.match(r"^(\d+)\.\s+\[([^\]]+)\]\(([^)]+)\)\s*$", line.strip())
        if m:
            steps.append((m.group(2), m.group(3).split("#", 1)[0]))
    assert steps == [
        ("考纲与范围", "syllabus.md"),
        ("学习计划", "plan.md"),
        ("练习与真题", "practice.md"),
        ("来源与核验", "sources.md"),
    ]

    five_pages = ["index.md", "sources.md", "syllabus.md", "plan.md", "practice.md"]
    for page in five_pages:
        text = (work_dir / page).read_text(encoding="utf-8")
        bars = [line for line in text.splitlines() if "｜" in line and "](" in line]
        assert bars, f"{page} missing cross-link bar"
        bar = bars[0]
        hrefs = set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", bar))
        expected_links = {p for p in five_pages if p != page}
        assert expected_links.issubset(hrefs), f"{page} bar missing {expected_links - hrefs}: {bar}"
        assert page not in hrefs, f"{page} bar must not self link: {bar}"


def test_ai_banner_presence_and_absence(tmp_path: Path):
    """plan.md / practice.md / review.md / knowledge/*.md 含 本页由 AI 辅助生成；index.md / syllabus.md / sources.md 不含。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    banner = "本页由 AI 辅助生成"
    for name in ["plan.md", "practice.md", "review.md"]:
        text = (work_dir / name).read_text(encoding="utf-8")
        assert banner in text, f"{name} must contain banner"

    ch_pages = list((work_dir / "knowledge").glob("*.md"))
    assert len(ch_pages) == 18
    for ch in ch_pages:
        text = ch.read_text(encoding="utf-8")
        assert banner in text, f"{ch.name} must contain banner"

    for name in ["index.md", "syllabus.md", "sources.md"]:
        text = (work_dir / name).read_text(encoding="utf-8")
        assert banner not in text, f"{name} must NOT contain banner"


def test_no_blockquote_over_80_chars(tmp_path: Path):
    """渲染器**产出**的页面中不存在长度 > 80 的 `>` 引用块，且引用块不含题文特征。

    作用域 = 渲染器生成的页面（`plan.md` / `practice.md` / `review.md` / `knowledge/*.md`）。
    `index.md` / `syllabus.md` / `sources.md` 的正文是**手写官方事实页**，渲染器不得改写
    （plan § Data contracts 5 第 2/3 条；QC3-002 / QC3-006 / C2-011）；对它们的断言见
    `test_official_page_prose_is_not_rewritten`。旧版本把 `index.md` 一并纳入 `rglob`，只有靠渲染器
    删掉 base `index.md` 里 **10** 行手写正文的 `>` 前缀才可能变绿 —— 那正是被判定为 Critical 的缺陷本身
    （plan F11：按本测试口径复算为 10；「33」是 fix-wave 1 报告里的错误数字，无任何口径可得）。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    generated = [work_dir / "plan.md", work_dir / "practice.md", work_dir / "review.md"]
    generated += sorted((work_dir / "knowledge").glob("*.md"))
    assert len(generated) == 21, "3 页 + 18 章页"

    for md_file in generated:
        for line in md_file.read_text(encoding="utf-8").splitlines():
            stripped = line.lstrip()
            if stripped.startswith(">"):
                quote = stripped.lstrip(">").strip()
                assert len(quote) <= 80, f"{md_file.name} blockquote > 80 chars ({len(quote)}): {quote[:40]}..."
                assert not re.search(r"(选择题|填空题|简答题|材料题|下列.*正确)", quote), (
                    f"{md_file.name} leaked question quote: {quote}"
                )


def test_official_page_prose_is_not_rewritten(tmp_path: Path):
    """手写官方事实页正文（含 `>` 引用块）在渲染前后**逐字不变**（QC3-002 / QC3-006 / C2-011）。

    这三页的正文是人工校对成果，其中 `index.md` 的合规披露明示「不得移除本提示」；
    渲染器只允许在 frontmatter 之后插入生成标识注释、追加派生的章节链接区块。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    def _body(text: str) -> list[str]:
        """去掉 frontmatter 与 generated-by 注释后的正文行。"""
        generated_comment = "<!-- generated by scripts/build-course-content.py; do not edit -->"
        lines = text.splitlines()
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            lines = text[end + 5 :].splitlines()
        return [line for line in lines if line.strip() != generated_comment]

    for name in ("index.md", "syllabus.md", "sources.md"):
        before = _body((work_dir / name).read_text(encoding="utf-8"))
        render_course_pages(ROOT, "15040", target_dir=work_dir)
        after = _body((work_dir / name).read_text(encoding="utf-8"))
        # 渲染只允许**追加**（章节链接区块），不允许改写既有的任何一行
        assert after[: len(before)] == before, f"{name} 的手写正文被渲染器改写"


def test_named_gap_course_name_never_renders_a_forged_value(tmp_path: Path):
    """W2 变异证明：`facts.name` 非 `verified` 时只回落**课码**。

    旧实现 `get_course_name()` 的回落分支是 `evidence.get("course_name") or code` —— 而
    `course_name` 是**契约外键**（`grep -rn '"course_name"' scripts/**` 只有这一处读取，没有任何写入者，
    也不在 plan § Data contracts 2 的键集合里），闸门因此看不见它。于是
    「`facts.name` 降级为 `named_gap` + 一个游离的顶层 `course_name`」能把伪造值印成 **官方 H1**
    （`syllabus.md` / `sources.md` / `plan.md` / `practice.md` / `review.md` 的 `# <课名>（<code>）`），
    而这两页里 `syllabus.md` / `sources.md` 是 `official_only`、不带 AI 横幅。

    本用例用**无既有页面**的副本根渲染（走兜底骨架路径），因此断言的是纯 `get_course_name()` 的结果。
    """
    from lib.course_pipeline.render_pages import get_course_name, render_course_pages

    forged = "伪造的官方课名 FORGED-VIA-COURSE-NAME"
    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    evidence_path = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["facts"]["name"] = {
        "value": None,
        "status": "named_gap",
        "gap_impact": "读者无法确认该课码对应的官方课程名",
        "next_evidence": "官方专业计划表中的课程行",
    }
    evidence["course_name"] = forged  # 契约外键：任何闸门都不校验它
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert get_course_name(evidence, "15040") == "15040", "非 verified 的 facts.name 必须回落课码"

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    render_course_pages(fake_root, "15040", target_dir=out_dir)

    written = sorted(out_dir.rglob("*.md"))
    assert written, "副本根必须渲染出页面（否则断言是空转）"
    for md_file in written:
        text = md_file.read_text(encoding="utf-8")
        assert forged not in text, f"{md_file.relative_to(out_dir)} 把契约外的 course_name 洗成了官方事实"
    assert "# 15040（15040）：考纲与范围" in (out_dir / "syllabus.md").read_text(encoding="utf-8"), (
        "回落值必须是课码"
    )


def test_release_status_is_rendered_from_the_json_ssot_and_refreshes(tmp_path: Path):
    """W6/QC3-008：放行状态必须由 `evidence.json` 渲染到官方页，且**随 SSOT 刷新**（不再是冻结快照）。

    两个方向：
    (a) 产物侧：`eligibility.level` 出现在 `official_only` 页面上（旧实现 `grep -rln "L1|eligibility"
        content/jiangsu/courses/15040/*.md` 无命中，而 `evidence.json` 记着 `L1`）；
    (b) 刷新侧：把 SSOT 里的放行判定改掉再渲染 → 页面上的派生死区必须跟着变，且**手写正文逐字不动**。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    course = ROOT / "content" / "jiangsu" / "courses" / "15040"
    # (a) 产物侧
    for name in ("index.md", "syllabus.md", "sources.md"):
        text = (course / name).read_text(encoding="utf-8")
        assert "## 放行状态（机器判定）" in text, f"{name} 未渲染放行状态"
        assert "eligibility" in text, f"{name} 的放行状态未指明取值来源"
    assert "放行等级 | `L1`" in (course / "index.md").read_text(encoding="utf-8")

    # (b) 刷新侧：合成根上把 release-status 的输入改掉（不动仓内产物）
    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "content", fake_root / "content")
    evidence_path = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["eligibility"] = {"level": "blocked", "reasons": ["syllabus:missing", "textbook_plan:missing"]}
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inline_derived = re.compile(r"<!-- derived:begin id=[a-zA-Z0-9_-]+ -->.*?<!-- derived:end -->\n?", re.DOTALL)

    def _handwritten(text: str) -> str:
        """剥掉 generated-by 注释与全部 `derived:` 区块后的**手写正文**（唯一的渲染不可改区）。"""
        generated_comment = "<!-- generated by scripts/build-course-content.py; do not edit -->"
        text = "\n".join(line for line in text.splitlines() if line.strip() != generated_comment)
        return inline_derived.sub("", text).strip("\n")

    work_dir = fake_root / "content" / "jiangsu" / "courses" / "15040"
    names = ("index.md", "syllabus.md", "sources.md")
    before = {name: _handwritten((work_dir / name).read_text(encoding="utf-8")) for name in names}

    render_course_pages(fake_root, "15040", target_dir=work_dir)

    after_index = (work_dir / "index.md").read_text(encoding="utf-8")
    assert "放行等级 | `blocked`" in after_index, "放行状态未随 evidence.json 刷新（仍是冻结快照）"
    assert "`syllabus:missing textbook_plan:missing`" in after_index, "判定依据未刷新"
    assert "未放行（零 AI 产物）" in after_index

    # 刷新只改派生区块：手写正文必须逐字保留（C2-011 / QC3-002 / QC3-006）
    for name in names:
        now = _handwritten((work_dir / name).read_text(encoding="utf-8"))
        assert now == before[name], f"{name} 的手写正文被渲染器改写"


def test_official_pages_are_idempotent_and_free_of_duplicate_derived_sections(tmp_path: Path):
    """W6：官方页的派生死区不得重复堆叠，且连续两次渲染字节一致。

    旧页面的 `## 章节知识精读` 是**无标记裸文本**；接管顺序写错（先追加派生块、再删裸文本）会把
    派生块的 `derived:begin` 标记一并删掉，于是每次渲染都再追加一块 —— 本用例锁住这个回归。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)
    first = {p.relative_to(work_dir): p.read_text(encoding="utf-8") for p in work_dir.rglob("*.md")}

    render_course_pages(ROOT, "15040", target_dir=work_dir)
    second = {p.relative_to(work_dir): p.read_text(encoding="utf-8") for p in work_dir.rglob("*.md")}

    assert first == second, "官方页渲染必须幂等（连续两次渲染字节一致）"
    for rel, text in second.items():
        assert text.count("## 章节知识精读") <= 1, f"{rel} 有重复的 ## 章节知识精读 区块"
        assert text.count("## 放行状态（机器判定）") <= 1, f"{rel} 有重复的放行状态区块"
        assert text.count("<!-- derived:begin id=chapter-links -->") <= 1, f"{rel} 的 chapter-links 区块重复"
        assert text.count("<!-- derived:end -->") == text.count("<!-- derived:begin "), (
            f"{rel} 的 derived 标记不成对（标记被吞掉会导致每次渲染都追加）"
        )


def test_committed_official_pages_have_flat_balanced_derived_regions():
    """X1 结构不变量：仓内 `official_only` 页的 `derived:` 区块**互不嵌套**，且 begin/end 一一配对。

    这是对**已提交产物**的断言（不是渲染输出）：`chapter-links` 曾包住 `release-status`，
    并在 EOF 留下一个孤儿 `derived:end`。嵌套 + 非贪婪匹配意味着「刷新外层」会吞掉内层，
    因此结构本身必须单独锁住，不能只靠渲染后的幂等断言。
    """
    for name in ("index.md", "syllabus.md", "sources.md"):
        text = (COURSE_15040 / name).read_text(encoding="utf-8")
        assert _derived_layout_problems(text, name) == [], f"{name} 的 derived 区块结构不良"


def test_chapter_links_refresh_on_an_already_rendered_page(tmp_path: Path):
    """X1 刷新不变量：模型变更后，**已带 `chapter-links` 区块**的页面必须更新链接列表。

    旧实现把唯一的 `render_derived_block("chapter-links", …)` 调用挂在
    `"derived:begin id=chapter-links" not in text` 之下 —— 标记一旦存在，区块就再也不重算：
    它只在「创建标记的那一次渲染」里刷新，之后永久冻结（QC3 第 2 轮的唯一阻塞项）。
    本用例对**已渲染页**做模型变异（新增一章 + 改一章标题），断言链接列表随之更新，
    且手写正文逐字不动。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "content", fake_root / "content")

    work_dir = fake_root / "content" / "jiangsu" / "courses" / "15040"
    # 前提：被测页面**已经带** chapter-links 区块（否则本用例是空转）
    for name in ("index.md", "syllabus.md"):
        assert "<!-- derived:begin id=chapter-links -->" in (work_dir / name).read_text(encoding="utf-8"), (
            f"{name} 未带 chapter-links 区块，本用例的前提不成立"
        )
    handwritten = {
        name: (work_dir / name).read_text(encoding="utf-8").split("<!-- derived:begin id=chapter-links -->")[0]
        for name in ("index.md", "syllabus.md")
    }

    model_path = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "knowledge-model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    renamed = "第二章 以中国式现代化全面推进中华民族伟大复兴"
    mutated_title = "第二章 改过的章名 X1-MUTATED-TITLE"
    for chapter in model["chapters"]:
        if chapter["title"] == renamed:
            chapter["title"] = mutated_title
    new_title = "第十八章 X1-ADDED-CHAPTER"
    model["chapters"].append(
        {
            "ordinal": 18,
            "index": "第十八章",
            "slug": "ch18",
            "title": new_title,
            "sections": [],
            "chapter_focus": [],
            "unmodeled": [],
        }
    )
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    render_course_pages(fake_root, "15040", target_dir=work_dir)

    for name in ("index.md", "syllabus.md"):
        after = (work_dir / name).read_text(encoding="utf-8")
        links = _derived_region(after, "chapter-links")
        assert new_title in links, f"{name} 的章节链接未随模型刷新（新增章缺失）"
        assert mutated_title in links, f"{name} 的章节链接未随模型刷新（改名的章仍是旧名）"
        assert renamed not in links, f"{name} 的章节链接里仍留着改名前的旧标题"

    # 刷新只改派生区块：区块之前的正文（手写官方事实）必须逐字不变
    for name in ("index.md", "syllabus.md"):
        after_prefix = (work_dir / name).read_text(encoding="utf-8").split(
            "<!-- derived:begin id=chapter-links -->"
        )[0]
        assert after_prefix == handwritten[name], f"{name} 的刷新改动了区块之前的正文"


def test_render_is_a_fixed_point_from_a_fresh_course_directory(tmp_path: Path):
    """X1 幂等不变量：**没有既有页面**的全新课程目录，一次渲染即达不动点（`render(render(x)) == render(x)`）。

    旧实现的兜底骨架路径不经过 `derived:` 写入，于是新课程的官方页第一遍没有区块、第二遍才有 ——
    同一类「派生死区只在第二遍出现」的缺陷。B2/B3 的新课码正是这条输入。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    work_dir = fake_root / "content" / "jiangsu" / "courses" / "15040"
    work_dir.mkdir(parents=True)

    render_course_pages(fake_root, "15040", target_dir=work_dir)
    first = {p.relative_to(work_dir): p.read_text(encoding="utf-8") for p in work_dir.rglob("*.md")}
    render_course_pages(fake_root, "15040", target_dir=work_dir)
    second = {p.relative_to(work_dir): p.read_text(encoding="utf-8") for p in work_dir.rglob("*.md")}

    differing = sorted(rel.as_posix() for rel in first if first[rel] != second[rel])
    assert not differing, f"全新课程目录的首次渲染不是不动点（第二遍会再改这些页）：{differing}"
    for name in ("index.md", "syllabus.md", "sources.md"):
        text = second[Path(name)]
        assert _derived_layout_problems(text, name) == [], f"{name} 的 derived 区块结构不良"
        assert "## 放行状态（机器判定）" in text, f"{name} 的派生死区未在首次渲染落盘"


def test_index_compliance_disclosure_survives_render(tmp_path: Path):
    """`index.md` 的合规披露在渲染后仍在（QC3-002：结尾为「不得移除本提示或标记为 🟢」）。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    text = (work_dir / "index.md").read_text(encoding="utf-8")
    assert "以下内容为 AI 辅助" in text, "合规披露被渲染器删除"
    assert "不得移除本提示" in text, "合规披露的不可移除声明被渲染器删除"


def test_all_relative_links_resolve(tmp_path: Path):
    """遍历产物中所有 ](...) 相对链接（含 knowledge/*.md 的 ../index.md），逐个断言目标文件存在。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    for md_file in work_dir.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        for _label, href in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if href.startswith(("http://", "https://", "mailto:", "materials://")):
                continue
            clean_target = href.split("#", 1)[0]
            if not clean_target:
                continue
            resolved = (md_file.parent / clean_target).resolve()
            if str(resolved).startswith(str(work_dir)):
                assert resolved.is_file(), f"{md_file.relative_to(work_dir)} links {href}, but {resolved} does not exist"
            else:
                # Sibling course link (e.g. ../15043/index.md) -> resolve against real repository
                rel_file = COURSE_15040 / md_file.relative_to(work_dir)
                repo_resolved = (rel_file.parent / clean_target).resolve()
                assert repo_resolved.is_file(), f"{md_file.relative_to(work_dir)} links {href}, but {repo_resolved} does not exist"


def test_chapter_pages_link_back(tmp_path: Path):
    """每个 knowledge/<NN>-<slug>.md 含 ../index.md 回链，文件名与模型 ordinal / slug 一一对应（18 个）。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    km = json.loads((SOURCES_15040 / "knowledge-model.json").read_text(encoding="utf-8"))
    assert len(km["chapters"]) == 18

    for ch in km["chapters"]:
        fname = f"{ch['ordinal']:02d}-{ch['slug']}.md"
        ch_path = work_dir / "knowledge" / fname
        assert ch_path.is_file(), f"missing chapter file {fname}"
        text = ch_path.read_text(encoding="utf-8")
        assert "../index.md" in text, f"{fname} missing ../index.md backlink"


def test_failed_build_writes_nothing(tmp_path: Path):
    """缺**不可再生**的前置 → `build … --backend replay` exit ≠ 0、stderr 含 `stage=`，
    且 `content/jiangsu/courses/15040/**` 的文件集合与 mtime 快照不变（spec AC1 第 3 句）。

    C2-010 / QC3-007：副本仓必须自带 fixture 与提示词，否则失败可能发生在**读到真实仓之后**
    （旧实现 `llm_client` 按 `__file__` 推导真实仓根），测试就会为一个与被测树无关的原因通过。
    本用例先断言副本仓的 fixture 根确实被解析到副本内，再验证失败路径。

    前置选择说明：删 `content.json` 不是有效注入（`generate` 会用已录制 fixture 重新生成它）；
    删考纲抽取件会让课程降级为 `blocked`，那是**成功**的零 AI 产物路径（exit 0，spec AC4）。
    真正让 `build` 失败的是一条产物侧的闸门违规：把 `content.json` 的 `stage_plan` 改成 4 条，
    `render` 仍能跑，但 `gate` 阶段必须失败关闭，且产物目录零改动。
    """
    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "scripts", fake_root / "scripts")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "content", fake_root / "content")
    # 副本自带 fixture（与提示词一起），使 replay 的取数根落在副本内
    (fake_root / "tests").mkdir()
    shutil.copytree(ROOT / "tests" / "fixtures", fake_root / "tests" / "fixtures")

    # 前提断言：入口把 fixture 根对齐到**副本**，而不是真实仓
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util,sys;"
            "spec=importlib.util.spec_from_file_location('b', r'%s');"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
            "from lib.course_pipeline import llm_client as l;"
            "print(l.FIXTURES_DIR)" % (fake_root / "scripts" / "build-course-content.py"),
        ],
        cwd=fake_root,
        capture_output=True,
        text=True,
    )
    assert str(fake_root) in probe.stdout, f"fixture 根必须解析到副本仓：{probe.stdout}{probe.stderr}"

    # 产物侧闸门违规：stage_plan 只有 4 条（契约要求恰 5 条）→ `ai-content` 层必须拦下
    content_path = fake_root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    content["stage_plan"].pop()
    content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    course_dir = fake_root / "content" / "jiangsu" / "courses" / "15040"
    snapshot_before = {p.relative_to(course_dir): p.stat().st_mtime_ns for p in course_dir.rglob("*") if p.is_file()}

    res = subprocess.run(
        [sys.executable, "scripts/build-course-content.py", "build", "15040", "--backend", "replay", "--stages", "render,gate"],
        cwd=fake_root,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, f"Expected non-zero exit code, got {res.returncode}, stdout={res.stdout}, stderr={res.stderr}"
    assert "stage=gate" in res.stderr, f"失败必须来自 gate 阶段：{res.stderr}"
    assert "stage_plan" in res.stderr, f"失败原因须指向被破坏的 stage_plan：{res.stderr}"

    snapshot_after = {p.relative_to(course_dir): p.stat().st_mtime_ns for p in course_dir.rglob("*") if p.is_file()}
    assert snapshot_before == snapshot_after, "Failed build must write nothing"


def test_inter_chapter_navigation_and_formatting(tmp_path: Path):
    """P0/P1 UI/UX: 校验章节流转、标题降级(H4)、无字典泄露及计划/练习直链。"""
    from lib.course_pipeline.render_pages import render_course_pages

    work_dir = tmp_path / "course"
    shutil.copytree(COURSE_15040, work_dir)

    render_course_pages(ROOT, "15040", target_dir=work_dir)

    km = json.loads((SOURCES_15040 / "knowledge-model.json").read_text(encoding="utf-8"))
    ch_list = km["chapters"]

    # 1. Inter-chapter navigation
    intro_txt = (work_dir / "knowledge" / f"{ch_list[0]['ordinal']:02d}-{ch_list[0]['slug']}.md").read_text(encoding="utf-8")
    assert "这是第一章" in intro_txt
    assert "下一章：" in intro_txt

    last_txt = (work_dir / "knowledge" / f"{ch_list[-1]['ordinal']:02d}-{ch_list[-1]['slug']}.md").read_text(encoding="utf-8")
    assert "上一章：" in last_txt
    assert "这是最后一章" in last_txt

    mid_txt = (work_dir / "knowledge" / f"{ch_list[1]['ordinal']:02d}-{ch_list[1]['slug']}.md").read_text(encoding="utf-8")
    assert "上一章：" in mid_txt
    assert "下一章：" in mid_txt
    assert mid_txt.count("**章节导航**：") == 2

    # 2. Heading demotion & dict prevention across all chapter pages
    for ch in ch_list:
        fname = f"{ch['ordinal']:02d}-{ch['slug']}.md"
        ch_txt = (work_dir / "knowledge" / fname).read_text(encoding="utf-8")
        lines = [line.strip() for line in ch_txt.splitlines()]
        assert not any(line.startswith("### 要点梳理") for line in lines), f"{fname} contains H3 要点梳理"
        assert not any(line.startswith("### 易错点") for line in lines), f"{fname} contains H3 易错点"
        assert any(line.startswith("#### 要点梳理") for line in lines), f"{fname} missing H4 要点梳理"
        assert any(line.startswith("#### 易错点") for line in lines), f"{fname} missing H4 易错点"
        assert "{'text':" not in ch_txt, f"{fname} leaked dict in chapter_focus"

    # 3. Plan and practice direct links
    plan_txt = (work_dir / "plan.md").read_text(encoding="utf-8")
    assert "[进入考点精读与自测](knowledge/00-intro.md)" in plan_txt

    prac_txt = (work_dir / "practice.md").read_text(encoding="utf-8")
    assert "(knowledge/00-intro.md#ai)" in prac_txt


# ---- B1：`gate` 阶段必须真的校验暂存区（QC1 F-1 / C2-001 / QC3-003） ----------------------

def _cli_module_for_build():
    """把 CLI 入口当模块加载，以便在进程内对 `run_build` 打桩（子进程无法注入损坏页面）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_course_content_gate", ROOT / "scripts/build-course-content.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_staging_dir_is_course_code_named_so_the_contract_check_really_runs():
    """B1：暂存目录必须是**课码命名**目录，否则 `check_course_dir` 静默早返回 `[]`。

    旧实现 `mkdtemp(prefix="build_15040_")` 的 basename 是 `build_15040_xxxx`，不匹配 `^[0-9]{5}$`，
    于是整页契约检查形同虚设。本用例直接对暂存区做变异：只放 `index.md`（缺其余必备文件）→ 必须报错。
    """
    import tempfile

    from lib import course_pages_contract

    cli = _cli_module_for_build()
    schema = course_pages_contract.load_schema(ROOT)

    # 旧形态：basename 不是课码 → 契约检查永远返回 []
    old_style = Path(tempfile.mkdtemp(prefix="build_15040_"))
    (old_style / "index.md").write_text("<!-- generated by scripts/build-course-content.py; do not edit -->\n## 页面导航\n")
    try:
        assert course_pages_contract.check_course_dir(old_style.parent, old_style, schema) == [], (
            "对照前提：非课码目录名让契约检查静默早返回"
        )

        # 新形态：`<mkdtemp>/<code>/` → 契约检查真的执行，缺必备文件必须被报出
        stage_root = Path(tempfile.mkdtemp())
        stage_dir = stage_root / "15040"
        stage_dir.mkdir()
        (stage_dir / "index.md").write_text(
            "<!-- generated by scripts/build-course-content.py; do not edit -->\n## 页面导航\n"
        )
        errors = cli._validate_staging_gates(ROOT, stage_dir, "15040")
        assert any("missing sources.md" in e for e in errors), errors
        assert any("missing practice.md" in e for e in errors), errors
        assert any("missing plan.md" in e for e in errors), errors
    finally:
        shutil.rmtree(old_style, ignore_errors=True)
        shutil.rmtree(stage_root, ignore_errors=True)


def test_corrupted_staged_page_aborts_build_and_promotes_nothing(tmp_path: Path, monkeypatch):
    """B1 变异证明：暂存页违反 `page_markers` → `build` exit ≠ 0，且产物目录零改动。"""
    cli = _cli_module_for_build()
    real_root = ROOT
    fake_root = tmp_path / "repo"
    shutil.copytree(real_root / "scripts", fake_root / "scripts")
    shutil.copytree(real_root / "ops", fake_root / "ops")
    shutil.copytree(real_root / "sources", fake_root / "sources")
    shutil.copytree(real_root / "content", fake_root / "content")

    cli.ROOT = fake_root
    # 只跑到 render+gate：上游阶段已被既有产物满足（evidence/model/content 都在 fake_root 里）
    stages = ["render", "gate"]

    baseline = {
        p.relative_to(fake_root / "content/jiangsu/courses/15040"): p.read_bytes()
        for p in (fake_root / "content/jiangsu/courses/15040").rglob("*")
        if p.is_file()
    }

    # 对照：未变异的 staged 页面必须通过 gate 并提升
    assert cli.run_build("15040", backend="replay", stages=stages, dry_run=False, record_fixtures=False) == 0

    # 变异：渲染出的 `plan.md` 丢掉 `page_markers` 要求的 `阶段目标`
    real_render = cli.render_pages_mod.render_course_pages

    def _corrupt(root, code, *, target_dir=None):
        written = real_render(root, code, target_dir=target_dir)
        target = Path(target_dir) / "plan.md"
        target.write_text(target.read_text(encoding="utf-8").replace("## 阶段目标", "## 阶段安排"), encoding="utf-8")
        return written

    monkeypatch.setattr(cli.render_pages_mod, "render_course_pages", _corrupt)
    rc = cli.run_build("15040", backend="replay", stages=stages, dry_run=False, record_fixtures=False)

    assert rc != 0, "违反 page_markers 的暂存页必须让 build 失败"
    after = {
        p.relative_to(fake_root / "content/jiangsu/courses/15040"): p.read_bytes()
        for p in (fake_root / "content/jiangsu/courses/15040").rglob("*")
        if p.is_file()
    }
    assert after == baseline, "gate 失败路径不得改动产物目录（无半成品）"


def test_promotion_prunes_stale_files(tmp_path: Path):
    """B1/QC1 F-6：目录级原子提升必须清掉不再产出的陈旧文件（如改 slug 后的孤儿章页）。"""
    cli = _cli_module_for_build()
    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "scripts", fake_root / "scripts")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "content", fake_root / "content")
    cli.ROOT = fake_root

    stale = fake_root / "content/jiangsu/courses/15040/knowledge/99-orphan.md"
    stale.write_text("# 陈旧章页\n", encoding="utf-8")

    assert cli.run_build("15040", backend="replay", stages=["render", "gate"], dry_run=False, record_fixtures=False) == 0
    assert not stale.exists(), "提升后陈旧文件必须被清除（否则孤儿页会被 mkdocs 发布）"
    assert (fake_root / "content/jiangsu/courses/15040/knowledge/00-intro.md").is_file()


def test_render_subcommand_routes_through_staging_and_gate(tmp_path: Path):
    """QC3-012：`render` 子命令不得直写 `content/**`；它必须走 render → gate → 原子提升。

    旧实现直接调 `render_course_pages(ROOT, code, target_dir=None)`，是本流水线**唯一**能留下
    半套页面的路径（24 个文件逐个覆盖、零校验）。这里用副本根验证：`render` 通过暂存+闸门，
    且闸门拦下违规时不产生任何改动。
    """
    cli = _cli_module_for_build()
    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "scripts", fake_root / "scripts")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "content", fake_root / "content")
    cli.ROOT = fake_root

    course_dir = fake_root / "content" / "jiangsu" / "courses" / "15040"

    # (a) 正常路径：`run_render` 走完整的 render+gate+提升，产物页面齐备
    real_render = cli.render_pages_mod.render_course_pages
    calls: list[dict] = []

    def _spy(root, code, *, target_dir=None):
        calls.append({"target_dir": target_dir})
        return real_render(root, code, target_dir=target_dir)

    cli.render_pages_mod.render_course_pages = _spy
    try:
        assert cli.run_render("15040") == 0
        assert calls, "run_render 必须调用渲染器"
        assert all(call["target_dir"] is not None for call in calls), (
            "render 必须渲染到暂存区，而不是直接写 content/**"
        )
    finally:
        cli.render_pages_mod.render_course_pages = real_render

    assert (course_dir / "practice.md").is_file()
    assert len(list((course_dir / "knowledge").glob("*.md"))) == 18
