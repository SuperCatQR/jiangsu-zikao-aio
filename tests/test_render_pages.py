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

# Y3：`15043` 的渲染半边守护用同一套口径（下方 `test_15043_render_reproduces_...`）。
# 修前本文件只渲染 `15040`（`grep -c "courses/15043"` = 0），`15043` 的 16 页字节一致只是报告级声明。
COURSE_15043 = ROOT / "content" / "jiangsu" / "courses" / "15043"

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


def _tracked(fake_root: Path) -> Path:
    """把 copytree 出来的副本根标注为「这些课的 `content.json` 已在版本控制中」，并原样返回它。

    **为什么需要**：`ai-content` 层的答案分布守卫用**该课 `content.json` 的 git 跟踪状态**区分
    「新课失败关闭」与「既有课只报告」（`scripts/lib/ai_content_gate.py`：`enforced = tracked is not True`）。
    `shutil.copytree(ROOT / ...)` 产出的树按定义**没有索引**：`git -C <副本> ls-files --error-unmatch`
    返回 `128`（不是工作树）⇒ `tracked=None` ⇒ 守卫按新课失败关闭。而本仓 `15040` 的答案键本身带历史
    偏置（单选 A 105/194 = 54.1%，判据 > 40%）—— 于是这所**既有课**在 `render → gate` 上被守卫拦下，
    副本根撒谎成「一所尚未入库的新课」，用例根本走不到被测对象（暂存页损坏中止 / 陈旧文件清除 / render 路由）。

    **为什么不是放宽断言**：标注之后断言原文一字不动，且多证明一条 —— 既有课的历史偏置**不阻断**闸门
    （与生产一致：全量跑 7 门课均为 `enforced=false`，只报告）。反向「过滤掉含答案分布的错误」会把
    「守卫在既有课上误报」这一整类回归一起放过，方向恰好反了。

    **与生产的一致性**：仓内 7 门课的 `sources/jiangsu/courses/*/content.json` 全部已被跟踪，而副本是
    整仓快照（`scripts` / `ops` / `sources` / `content`），所以「快照里每门有产物的课都已跟踪」才是生产
    的真实形态；只标注 `15040` 会让同一份副本对其余课继续说谎。

    只用 `git init` + `git add`：跟踪状态读的就是**索引**，既不需要 commit，也不写 user 配置。
    与 `tests/test_ai_content_gate.py::_tracked`（B4a 的同类修复）同一口径。
    """
    subprocess.run(["git", "-C", str(fake_root), "init", "-q"], check=True, capture_output=True)
    rel_paths = sorted(
        path.relative_to(fake_root).as_posix()
        for path in (fake_root / "sources" / "jiangsu" / "courses").glob("*/content.json")
    )
    if rel_paths:
        subprocess.run(
            ["git", "-C", str(fake_root), "add", "-f", "--", *rel_paths],
            check=True,
            capture_output=True,
        )
    return fake_root


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
    _tracked(fake_root)

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
    _tracked(fake_root)
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
    _tracked(fake_root)
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


# --------------------------------------------------------------------------------------
# F-QC3-4：`manual:schedules` 标记被剥掉时不得**静默**换成更薄的默认模板
# --------------------------------------------------------------------------------------

def _schedules_block(text: str) -> str:
    from lib.course_pipeline.render_pages import extract_manual_blocks

    return extract_manual_blocks(text).get("schedules", "")


def test_manual_block_drop_is_detected_not_silently_thinned():
    """F-QC3-4 的闸门侧守护：committed 两门课的 `manual:schedules` **必须比默认模板更厚**。

    改前没有任何检查覆盖这件事。若编辑器把 `<!-- manual:begin id=schedules -->` 标记删掉，
    渲染器取不到既有块，就**静默**回落到 288 字符的 `default_schedules`
    （只剩 `## 通用复习节奏模板（非官方排程）`），`## 14 天压缩复习` 与 `## 7 天冲刺` 整段消失，
    而 7 层闸门全绿 —— 实测：`15040` 681 → 287、`15043` 626 → 287 字符。

    本用例把「不许变薄」钉成产物不变量：两门课的 committed 块都含三档排程标题，
    且长度严格大于默认模板。这样「标记被剥掉」这种退化会在 CI 里直接变红，
    而不是靠人去比对 626 vs 287 的字符数。
    """
    from lib.course_pipeline.render_pages import _render_review  # noqa: PLC0415

    # 默认模板的字节长度：渲染器回落时的实际产出（作为「变薄」的阈值基线）
    rendered_default = _render_review("15043", {}, {}, {})
    default_block = _schedules_block(rendered_default)
    assert "通用复习节奏模板（非官方排程）" in default_block, (
        f"对照前提：无既有块时回落默认模板，实际 {default_block[:80]!r}"
    )

    for code in ("15040", "15043"):
        text = (ROOT / "content" / "jiangsu" / "courses" / code / "review.md").read_text(encoding="utf-8")
        block = _schedules_block(text)
        assert block, f"{code}: review.md 缺少 `manual:schedules` 块（标记被剥掉？）"
        assert len(block) > len(default_block), (
            f"{code}: `manual:schedules` 块（{len(block)} 字符）不得薄于默认模板"
            f"（{len(default_block)} 字符）—— 标记疑似被剥掉后静默回落"
        )
        for heading in ("## 30 天复习", "## 14 天压缩复习", "## 7 天冲刺"):
            assert heading in block, f"{code}: `manual:schedules` 块丢失 {heading}"


def test_manual_block_drop_scenario_can_actually_be_reproduced(tmp_path: Path):
    """F-QC3-4 反向验证：把标记剥掉后重渲染，块**确实**变薄 —— 证明上面的不变量不是恒真。

    若这条路径永不发生，上面的断言就没有守护对象；这里复现一次真实退化（只动副本），
    确认「剥标记 → 287 字符默认模板 → 丢掉两档排程」可被观察到。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    fake_root = tmp_path / "repo"
    shutil.copytree(ROOT / "scripts", fake_root / "scripts")
    shutil.copytree(ROOT / "ops", fake_root / "ops")
    shutil.copytree(ROOT / "sources", fake_root / "sources")
    shutil.copytree(ROOT / "content", fake_root / "content")

    page = fake_root / "content" / "jiangsu" / "courses" / "15043" / "review.md"
    before = _schedules_block(page.read_text(encoding="utf-8"))
    assert "## 14 天压缩复习" in before, "对照前提：committed 块含 14 天档"

    # 模拟编辑器剥掉标记（仓库副本与暂存区都拿不到块 → 渲染器回落默认值）
    stripped = re.sub(r"<!--\s*manual:begin\s+id=schedules\s*-->", "", page.read_text(encoding="utf-8"))
    stripped = re.sub(r"<!--\s*manual:end\s*-->", "", stripped)
    page.write_text(stripped, encoding="utf-8")

    render_course_pages(fake_root, "15043")

    after = _schedules_block(page.read_text(encoding="utf-8"))
    assert "通用复习节奏模板（非官方排程）" in after, "退化后应回落默认模板"
    assert len(after) < len(before), f"退化后应变薄：before={len(before)} after={len(after)}"
    assert "## 14 天压缩复习" not in after, "退化后 14 天档应丢失"
    assert "## 7 天冲刺" not in after, "退化后 7 天冲刺档应丢失"

    # 仓内产物未被本次反向验证触碰
    committed = (ROOT / "content" / "jiangsu" / "courses" / "15043" / "review.md").read_text(encoding="utf-8")
    assert "## 14 天压缩复习" in _schedules_block(committed), "反向验证不得改动仓内产物"


# --------------------------------------------------------------------------------------
# Y3：`15043` 的**渲染**字节一致必须有持久守护（此前只有 `15040` 有；replay 半边见
# `tests/test_generate_content.py::test_cli_generate_replay_reproduces_15043_artifact_byte_identically`）
# --------------------------------------------------------------------------------------

def _snapshot(directory: Path) -> dict[str, bytes]:
    """目录下全部文件的相对路径 → 字节（渲染产物的比较口径：路径集合 + 逐字节）。"""
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _render_into(source: Path, work_dir: Path, code: str) -> dict[str, bytes]:
    """把 `source` 拷成工作副本、用真实渲染器重渲染，返回渲染后的字节快照。"""
    from lib.course_pipeline.render_pages import render_course_pages

    shutil.copytree(source, work_dir)
    render_course_pages(ROOT, code, target_dir=work_dir)
    return _snapshot(work_dir)


def test_15043_render_reproduces_the_committed_pages_byte_identically(tmp_path: Path):
    """Y3：`15043` 的 16 个渲染页 = `f(content 真值源)` —— 重渲染必须**逐字节**重现 committed 产物。

    改前 `15043` 的渲染半边没有任何测试拥有（本文件只渲染 `15040`，`grep -c "courses/15043"` = 0）：
    属性本身成立（QC1 已实测），但下一轮改渲染器或改真值源都不会被这套件发现，只是报告级声明。
    本用例与 `15040` 的既有用例（`test_render_is_deterministic`）同形，只是把课程换成 `15043`：

    - 第一次渲染：证明 committed 产物可由真值源精确重建（路径集合与逐字节都相等）；
    - 第二次渲染（在**已渲染**的工作副本上再来一遍）：证明渲染是**幂等**的（固定点）。
    """
    committed = _snapshot(COURSE_15043)
    # 对照前提：产物页面齐备（否则「字节一致」可能只是两边都空跑）
    assert len(committed) == 16, f"对照前提：15043 应为 16 页，实际 {len(committed)}"
    assert "knowledge/01-ch01.md" in committed and "plan.md" in committed, sorted(committed)

    first = _render_into(COURSE_15043, tmp_path / "run1", "15043")
    assert sorted(first) == sorted(committed), (
        f"渲染产出的页面集合与 committed 不一致：多 {sorted(set(first) - set(committed))}"
        f" / 少 {sorted(set(committed) - set(first))}"
    )
    differing = [rel for rel in committed if first[rel] != committed[rel]]
    assert not differing, f"重渲染未逐字节重现 committed 产物，首个差异页: {differing[0]}"

    # 幂等：在同一份已渲染产物上再渲染一次，必须仍是同一个固定点
    second = _render_into(tmp_path / "run1", tmp_path / "run2", "15043")
    assert second == first, "二次渲染必须字节一致（幂等）"


def test_15043_render_byte_test_is_falsifiable(tmp_path: Path):
    """Y3 反向验证：committed 页面被扰动 **1 字节**时，上一条用例的比对口径必须能发现。

    不满足于「断言写在那儿」：把上一条用例的比较逻辑本身当作被测对象 —— 在工作副本里把某一页的一个字节
    换成另一个字节（不改变长度），然后确认「渲染后的快照 == committed 快照」这一判据**确实**判否。
    否则「字节一致」可能退化成恒真检查（例如比了个空集合、或比了归一化后的文本）。
    """
    rel = "knowledge/01-ch01.md"
    committed = _snapshot(COURSE_15043)
    baseline = _render_into(COURSE_15043, tmp_path / "baseline", "15043")
    assert baseline == committed, "对照前提：未变异的副本渲染后与 committed 一致"

    work = tmp_path / "perturbed"
    shutil.copytree(COURSE_15043, work)
    target = work / rel
    raw = target.read_bytes()
    victim = "要点梳理".encode()
    assert victim in raw, f"对照前提：{rel} 含 `#### 要点梳理` 标题（扰动点存在）"
    mutated = raw.replace(victim, "要点料理".encode(), 1)
    assert mutated != raw, "对照前提：1 字节替换必须改变字节"
    assert len(mutated) == len(raw), "对照前提：扰动只改内容、不改长度"
    target.write_bytes(mutated)

    # 扰动副本自身的快照与 committed 已经不同 —— 这就是上一条用例的失败形态
    perturbed = _snapshot(work)
    assert perturbed != committed, "1 字节扰动必须被逐字节比较判否（否则该断言是恒真的）"

    # 并且渲染器**确实**会读回该页（重渲染把扰动修掉 → 渲染结果又等于 committed），
    # 因此上一条用例守护的是「committed 页面 = 渲染器输出」这个固定点，而非「文件没被动过」。
    from lib.course_pipeline.render_pages import render_course_pages

    render_course_pages(ROOT, "15043", target_dir=work)
    assert _snapshot(work) == committed, "渲染器会重写该页，故重渲染后扰动被修复回 committed 形态"

    # 仓内产物未被本次反向验证触碰
    assert _snapshot(COURSE_15043) == committed, "反向验证不得改动仓内产物"


# --------------------------------------------------------------------------------------
# R49：附录单元页（`appendices[]` → `knowledge/NN-apNN.md`，排在全部章页之后）
# --------------------------------------------------------------------------------------

SOURCES_02333 = ROOT / "sources" / "jiangsu" / "courses" / "02333"
COURSE_02333 = ROOT / "content" / "jiangsu" / "courses" / "02333"


def _appendix_model() -> dict:
    return json.loads((SOURCES_02333 / "knowledge-model.json").read_text(encoding="utf-8"))


def _synthetic_appendix_content(model: dict, code: str) -> dict:
    """用**本课模型自己的** point_id 合成 content.json（含附录点），使附录渲染路径真的被走到。

    `02333` 尚无 `content.json`（Task 3 负责生成），而「附录点是否落到页面」必须现在就可判否：
    合成 blocks 覆盖全部点的 explain / memorize / drill，判据（锚点、文件名、顺序）因此真实。
    """
    blocks = []
    for unit in [*model["chapters"], *model.get("appendices", [])]:
        for section in unit["sections"]:
            for point in section["points"]:
                pid = point["id"]
                for kind, text in (
                    ("explain", "### 要点梳理\n合成讲解。\n### 易错点\n合成易错点。"),
                    ("memorize", "合成记忆法：口诀。"),
                ):
                    blocks.append({
                        "block_id": f"{pid}/{kind}", "kind": kind, "point_id": pid, "text_md": text,
                        "ai_generated": True, "review_state": "machine_draft",
                        "generator": {"backend": "replay", "model": "m", "prompt_id": f"{kind}_point",
                                      "prompt_version": "v1", "generated_at": "2026-01-01"},
                        "evidence_refs": [f"syllabus:{code}#{point['locator']}"],
                    })
                blocks.append({
                    "block_id": f"{pid}/drill", "kind": "drill", "point_id": pid,
                    "question_type": "单项选择题", "text_md": "合成题干。", "answer_md": "合成答案。",
                    "source_kind": "ai_generated", "ai_generated": True, "review_state": "machine_draft",
                    "generator": {"backend": "replay", "model": "m", "prompt_id": "drill_point",
                                  "prompt_version": "v1", "generated_at": "2026-01-01"},
                    "evidence_refs": [f"syllabus:{code}#{point['locator']}"],
                })
    return {
        "schema_version": 1, "course_code": code, "generated_at": "2026-01-01",
        "generator": {"backend": "replay", "model": "m", "prompt_versions": {}},
        "stage_plan": [
            {"stage": stage, "goal": f"{stage}目标", "inputs": ["i"], "how": ["h"], "outputs": ["o"],
             "done_when": "可判定。", "ai_generated": True, "review_state": "machine_draft",
             "generator": {"backend": "replay", "model": "m", "prompt_id": "stage_plan",
                           "prompt_version": "v1", "generated_at": "2026-01-01"},
             "evidence_refs": ["knowledge-model:chapters"]}
            for stage in ("入门", "精读", "刷题", "冲刺", "复盘")
        ],
        "blocks": blocks,
        "review_schedule": {
            "exam_date": None, "weekly_hours": None, "status": "named_gap", "plans": [],
            "gap_impact": "合成缺口影响", "next_evidence": "合成下一证据",
            "ai_generated": True, "review_state": "machine_draft",
            "generator": {"backend": "replay", "model": "m", "prompt_id": "stage_plan",
                          "prompt_version": "v1", "generated_at": "2026-01-01"},
            "evidence_refs": ["knowledge-model:exam"],
        },
    }


def _appendix_render_root(tmp_path: Path) -> Path:
    """假仓：真实 `02333` 模型 + evidence 副本 + 合成 content.json（仓内文件零改动）。"""
    fake = tmp_path / "repo"
    source_dir = fake / "sources" / "jiangsu" / "courses" / "02333"
    source_dir.mkdir(parents=True)
    for name in ("evidence.json", "knowledge-model.json"):
        (source_dir / name).write_bytes((SOURCES_02333 / name).read_bytes())
    model = _appendix_model()
    (source_dir / "content.json").write_text(
        json.dumps(_synthetic_appendix_content(model, "02333"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    target = fake / "content" / "jiangsu" / "courses" / "02333"
    target.mkdir(parents=True)
    # 官方页手写正文照搬：走「有既有页」的 `_read_existing()` 分支
    if COURSE_02333.is_dir():
        for md in COURSE_02333.glob("*.md"):
            (target / md.name).write_text(md.read_text(encoding="utf-8"), encoding="utf-8")
    return fake


def test_appendix_unit_pages_are_rendered_after_every_chapter_page(tmp_path: Path):
    """R49 验收③：每个附录产出一页，命名与章页不撞车，且排在**全部**章页之后。"""
    from lib.course_pipeline.render_pages import render_course_pages

    fake = _appendix_render_root(tmp_path)
    out = fake / "content" / "jiangsu" / "courses" / "02333"
    written = render_course_pages(fake, "02333", target_dir=out)

    model = _appendix_model()
    chapters, appendices = model["chapters"], model["appendices"]
    knowledge = sorted(p.name for p in (out / "knowledge").glob("*.md"))
    assert len(knowledge) == len(chapters) + len(appendices) == 21, knowledge

    # 命名：`NN-slug.md`，附录 `ap01`…；两个命名空间不相交（章是 `intro`/`chNN`）
    appendix_files = [f"{a['ordinal']:02d}-{a['slug']}.md" for a in appendices]
    assert appendix_files == [f"{n:02d}-ap{n:02d}.md" for n in range(1, 8)], appendix_files
    chapter_slugs = {c["slug"] for c in chapters}
    assert not (chapter_slugs & {a["slug"] for a in appendices}), "章与附录的 slug 必须不相交"
    for name in appendix_files:
        assert (out / "knowledge" / name).is_file(), f"缺附录页 {name}"

    # 顺序：`render_course_pages()` 的写入序里，全部章页都在附录页之前（页序 = 阅读序）
    written_rel = [p.relative_to(out).as_posix() for p in written if p.parent.name == "knowledge"]
    first_appendix = min(written_rel.index(f"knowledge/{name}") for name in appendix_files)
    last_chapter = max(
        written_rel.index(f"knowledge/{c['ordinal']:02d}-{c['slug']}.md") for c in chapters
    )
    assert first_appendix > last_chapter, f"附录页必须写在全部章页之后：{written_rel[-10:]}"


def test_appendix_page_surfaces_the_application_level_requirement(tmp_path: Path):
    """R49 的验收点：`02333` 附录七的 `应用` 级要求行（`ap07-s1-p3`）必须**可见地**出现在页面上。

    这是 R41 登记危害的直接判否：「9 个点到达读者」。旧实现只渲染 `chapters[]`，
    该点在任何页面上都不存在。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    fake = _appendix_render_root(tmp_path)
    out = fake / "content" / "jiangsu" / "courses" / "02333"
    render_course_pages(fake, "02333", target_dir=out)

    page = (out / "knowledge" / "07-ap07.md").read_text(encoding="utf-8")
    assert "# 附录七 UML 的模型及图示表示" in page
    assert "### 考点精讲：02333-ap07-s1-p3（应用）" in page, "`应用` 级考点小节缺失"
    assert "#### 要点梳理" in page and "#### 记忆辅助" in page
    assert "### 练习题：02333-ap07-s1-p3" in page
    assert "本附录重点" in page, "附录必须用附录自己的 chapter_focus 小节标题"
    assert "附录导航" in page, "附录页导航措辞必须是附录（不是章）"
    assert "上一附录：附录六 软件维护手册" in page
    assert "这是最后一个附录" in page, "最后一个附录的导航必须自述为最后一个附录"


def test_appendix_pages_are_cross_linked_from_the_official_and_ai_indexes(tmp_path: Path):
    """索引双向可达：`index.md` 的「章节知识精读」、`plan.md` 的学习序列、`practice.md` 的训练索引
    都必须含附录页链接（否则读者从导航进不去附录页）。"""
    from lib.course_pipeline.render_pages import render_course_pages

    fake = _appendix_render_root(tmp_path)
    out = fake / "content" / "jiangsu" / "courses" / "02333"
    render_course_pages(fake, "02333", target_dir=out)

    index = (out / "index.md").read_text(encoding="utf-8")
    assert "### 附录知识精读" in index, "index.md 必须单列附录小节"
    assert "[附录七 UML 的模型及图示表示](knowledge/07-ap07.md)" in index

    plan = (out / "plan.md").read_text(encoding="utf-8")
    assert "knowledge/07-ap07.md" in plan, "plan.md 的学习序列必须链到附录页"
    assert "14 章 + 7 个附录单元" in plan, f"plan.md 的计数文案必须与渲染的单元数一致：{plan[:20]}"

    practice = (out / "practice.md").read_text(encoding="utf-8")
    assert "knowledge/07-ap07.md#ai" in practice, "practice.md 的训练索引必须含附录页"


def test_chapter_count_wording_matches_what_is_rendered(tmp_path: Path):
    """R49 验收④：`plan.md` 的「如何使用」不得声称只有「共 N 章」而实际渲染了附录单元。

    判据取**实际渲染的单元页数**（不是模型条目的自述），因此文案与页面集合之间不可能各自漂移。
    """
    from lib.course_pipeline.render_pages import render_course_pages

    fake = _appendix_render_root(tmp_path)
    out = fake / "content" / "jiangsu" / "courses" / "02333"
    render_course_pages(fake, "02333", target_dir=out)

    model = _appendix_model()
    rendered_units = len(list((out / "knowledge").glob("*.md")))
    assert rendered_units == len(model["chapters"]) + len(model["appendices"]) == 21

    plan = (out / "plan.md").read_text(encoding="utf-8")
    assert f"（共 {rendered_units} 个考核单元）" in plan, f"plan.md 未报出实际渲染的单元数：{rendered_units}"
    assert f"共 {len(model['chapters'])} 章）" not in plan, (
        "plan.md 不得声称「共 13 章」而实际渲染了 21 个单元页（文案藏起附录）"
    )


def test_syllabus_fallback_lists_appendices_in_their_own_table(tmp_path: Path):
    """`syllabus.md` 兜底骨架的章目索引必须含附录索引（首列用 `附录序`，不是 `章序`）。"""
    from lib.course_pipeline.render_pages import render_course_pages

    fake = tmp_path / "repo"
    source_dir = fake / "sources" / "jiangsu" / "courses" / "02333"
    source_dir.mkdir(parents=True)
    for name in ("evidence.json", "knowledge-model.json"):
        (source_dir / name).write_bytes((SOURCES_02333 / name).read_bytes())
    (source_dir / "content.json").write_text(
        json.dumps(_synthetic_appendix_content(_appendix_model(), "02333"), ensure_ascii=False), encoding="utf-8"
    )
    out = fake / "content" / "jiangsu" / "courses" / "02333"
    out.mkdir(parents=True)
    render_course_pages(fake, "02333", target_dir=out)

    syllabus = (out / "syllabus.md").read_text(encoding="utf-8")
    assert "### 附录索引（考纲 Ⅲ 部切片）" in syllabus
    assert "| 附录序 | 附录名 |" in syllabus
    assert "| 附录七 | 附录七 UML 的模型及图示表示 |" in syllabus
    assert "章序 | 章名" in syllabus, "章目索引仍须保留"


def test_appendix_free_models_produce_identical_output_with_or_without_an_empty_key():
    """no-op 的**渲染**半边（结构性可判否）：`appendices` 缺键 ⇔ `appendices: []`，输出逐字符相同。

    手法：对真实 `15040` / `15043` / `15044` / `00898` 模型，把渲染器的每个附录敏感入口各调一次 ——
    `_assessment_units()`（单元序列 = 页集合与页序的真源）、`_chapter_index_block()`（index.md 索引）、
    `_render_plan()`、`_render_practice()`、`_render_syllabus()` —— 分别在「原模型」与「显式插入
    `appendices: []`」两种输入下取输出并逐字符比对。

    为什么这一层而不是端到端：端到端的 `15040` / `15043` 字节一致由既有用例守护
    （`test_15043_render_reproduces_the_committed_pages_byte_identically`）；
    `15044` / `00898` 尚未生成 `content.json`（Task 3 负责），端到端此刻无输入可渲染。
    本用例把「缺键 vs 空值」这条**唯一**的守卫差异钉在入口函数上，因此对尚未生成的两门课同样成立；
    空值守卫若缺失（例如无条件写出 `### 附录知识精读` 标题），本用例立刻判否。
    """
    from lib.course_pipeline import render_pages

    for code in ("15040", "15043", "15044", "00898"):
        model = json.loads(
            (ROOT / f"sources/jiangsu/courses/{code}/knowledge-model.json").read_text(encoding="utf-8")
        )
        assert "appendices" not in model, f"{code}: 对照前提 —— 模型不得含 appendices 键"
        with_empty = {**model, "appendices": []}
        evidence = json.loads(
            (ROOT / f"sources/jiangsu/courses/{code}/evidence.json").read_text(encoding="utf-8")
        )

        units_missing = render_pages._assessment_units(model)
        assert units_missing == render_pages._assessment_units(with_empty), f"{code}: 单元序列不同"
        assert [unit["slug"] for _kind, unit in units_missing] == [
            chapter["slug"] for chapter in model["chapters"]
        ], f"{code}: 无附录时单元序列必须逐个等于 chapters"

        assert render_pages._chapter_index_block(model) == render_pages._chapter_index_block(with_empty), (
            f"{code}: index.md 的章节精读区块被空 appendices 改变"
        )
        assert render_pages._render_plan(code, evidence, model, {}) == render_pages._render_plan(
            code, evidence, with_empty, {}
        ), f"{code}: plan.md 被空 appendices 改变"
        assert render_pages._render_practice(code, evidence, model, {}) == render_pages._render_practice(
            code, evidence, with_empty, {}
        ), f"{code}: practice.md 被空 appendices 改变"
        assert render_pages._render_syllabus(code, evidence, model, "") == render_pages._render_syllabus(
            code, evidence, with_empty, ""
        ), f"{code}: syllabus.md 被空 appendices 改变"

        # 对照前提：这些入口在**有**附录时确实会产出不同的字（否则上面的相等是恒真的）
        assert render_pages._chapter_index_block(_appendix_model()) != render_pages._chapter_index_block(
            {**_appendix_model(), "appendices": []}
        ), "对照前提：有附录时 index.md 区块必须不同（否则判据恒真）"


def test_appendix_render_path_is_falsifiable(tmp_path: Path):
    """反向验证：把附录渲染**摘掉**（只迭代 `chapters`），上一条页序/页数用例必须判否。

    不满足于「断言写在那儿」：把被守护的属性本身当作被测对象 —— 用「章页集合」冒充「全部单元页」，
    确认页数 / 附录文件 / `应用` 级锚点三条判据都会失败。否则这些断言可能退化成恒真检查。
    """
    fake = _appendix_render_root(tmp_path)
    out = fake / "content" / "jiangsu" / "courses" / "02333"

    from lib.course_pipeline import render_pages

    real = render_pages._assessment_units
    try:
        # 变异：单元 = 只有章（旧实现的语义）
        render_pages._assessment_units = lambda model: [("章", c) for c in model.get("chapters", [])]
        render_pages.render_course_pages(fake, "02333", target_dir=out)
    finally:
        render_pages._assessment_units = real

    model = _appendix_model()
    rendered = sorted(p.name for p in (out / "knowledge").glob("*.md"))
    assert len(rendered) == len(model["chapters"]) == 14, f"变异后应只剩章页：{len(rendered)}"
    assert not any(name.endswith("-ap07.md") for name in rendered), "变异后不应有附录页"
    assert not (out / "knowledge" / "07-ap07.md").exists(), "`应用` 级要求行所在页不得存在"

    plan = (out / "plan.md").read_text(encoding="utf-8")
    assert "（共 21 个考核单元）" not in plan, "变异后计数文案必须随之变化（判据确实区分两种实现）"
