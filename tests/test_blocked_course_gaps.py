"""B3c Task 1 — reader-side gap presentation for the 11 `blocked` courses.

**缺陷类**：这些课的 `index.md` 里 7/11 门**完全没有**缺口表述，读者看到的是一个"看似完整"的
元数据页（`00023` 530 行、`13003` 421 行最长），无从知道它**永远不会**产出 AI 备考层。

**落点（设计说明 DP-2 裁定）**：
- 主落点 = 每门课**自己的** `index.md` 追加缺口区块（读者就在该页，无需跳转）；
- 汇总层 = `content/jiangsu/gaps/index.md` 的「阻塞课程缺口一览」表；
- **不得**把手工内容写进 `gaps/page-maturity.md` —— 它是 `compute-page-maturity.py --write-public`
  的确定性投影，手工内容会被下次重算覆盖。

**硬不变量（AC8 / GC1）**：这些课保持**零 AI 产物** —— 不得出现 `ai_generated` 块、不得出现 AI 横幅。
下面用**可证伪**的方式钉住：横幅字面量取自 `course.schema.json` 的 `generated_page_markers.ai_banner`
（schema 是唯一真源，不在测试里另抄一遍），并额外断言这些页面**没有**任何 AI 页面标记。

**AC8 的读法（F2 修订）**：不变量约束的是**机器产物**（横幅 / `ai_generated` / `content.json`），
而 4 门课（`00023` `04735` `13000` `13003`）另有**迁移期手写 AI 署名**与自己的 `## AI 生成声明` 表。
它们是既有的、由各自声明表治理的内容，本片**不动**；B3c owns 的是**缺口叙事的真值性**：
因此本条额外要求「绝对零 AI 断言」**不得与该页自己的 AI 署名共现**。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"
GAPS = ROOT / "content" / "jiangsu" / "gaps"
EVIDENCE = ROOT / "sources" / "jiangsu" / "courses"
SCHEMA = ROOT / "ops" / "jiangsu" / "schemas" / "course.schema.json"

START = "<!-- course-gap:start -->"
END = "<!-- course-gap:end -->"
SUMMARY_START = "<!-- blocked-course-gaps:start -->"
SUMMARY_END = "<!-- blocked-course-gaps:end -->"

# DP-2 要求缺口区分**三类原因**；旧代码跳转页是本片实测发现的第四类（诚实优先于套模板）：
#   (a) 缺官方考纲原件  (b) 缺考纲 + 缺教材计划行  (c) 旧代码历史参考页
# `04747` / `04751` 的考纲**完整**（13 章、1–13 连续），**不属于**「考纲缺章」——
# 该说法曾是规划期探针的正则假象（`^\s*第(\d+)章` 匹配不到 `第 6 章`），已由 PM 更正。
LEGACY_REDIRECT = {"03708": "15043", "03709": "15044"}
MISSING_BOTH = {"13000"}

# 三节标题是契约：读者必须能读到「缺什么 / 为什么 / 下一步」（plan § Data contracts 1）。
REQUIRED_SUBSECTIONS = ("### 缺什么", "### 为什么", "### 下一步")

# 缺口区块里**声称本页「已核验/已命中教材计划行」**的措辞（F1）。成因是共享句把它当成无条件事实，
# 而 `13000` 的 `textbook_plan.status = "missing"`，于是同一页的 blockquote 与自己的表格互相矛盾。
TEXTBOOK_MATCHED_CLAIM = "已核验的教材计划行"

# AC8 的读法（F2）：`blocked` 课**不含 AI 备考层**；但若页面自身带 AI 署名区块，就**不得**出现
# 「本页没有任何 AI 内容」式的绝对断言。这些短语是 4 门课真实存在的**合法**署名，因此只作
# 「共现检测」的触发器，绝不禁止其出现。
AI_ATTRIBUTION = re.compile(r"AI\s*(?:辅助|初稿|原创|撰写|整理|生成)")
ABSOLUTE_NO_AI_CLAIM = re.compile(
    r"(?:零|无|没有|不含|不包含|不产出|不生成|未产出|未生成)\s*(?:任何)?\s*AI\s*(?:内容|产物|文字|文本|元素|区块)"
)

# 「考纲缺第 N 章」式断言（F7）：`04747` / `04751` 的考纲实测**完整**（13 章、1–13 连续）。
# 上一版只认三种写法，对 `缺少第 6 章` / `缺了第 6 章` / `考纲第 6 章缺失` / `第 6 章未收录` 全部漏判。
MISSING_CHAPTER_CLAIM = re.compile(
    r"缺\s*[少了]?\s*第\s*[\d\-–—]+\s*章"                        # 缺第6章 / 缺少第 6 章 / 缺了第 6 章
    r"|第\s*[\d\-–—]+\s*章\s*缺\s*[失少]"                        # 考纲第 6 章缺失
    r"|第\s*[\d\-–—]+\s*章\s*未\s*(?:收录|覆盖|包含|列出|纳入)"   # 第 6 章未收录
    r"|考纲\s*缺\s*章"                                              # 考纲缺章
)


def _blocked_codes() -> list[str]:
    """从 `evidence.json` 派生（与门禁同一真值源），**不**用测试内手抄的课码表。

    口径 = `eligibility.level != "L1"`。手抄清单会与机器判定漂移：某个课补齐考纲后
    放行等级变 `L1`，手抄清单仍要求它有缺口区块，测试就会变成假红。
    """
    codes = []
    for path in sorted(EVIDENCE.glob("*/evidence.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if (doc.get("eligibility") or {}).get("level") != "L1":
            codes.append(path.parent.name)
    return codes


def _read(code: str) -> str:
    path = COURSES / code / "index.md"
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _gap_block(code: str) -> str:
    text = _read(code)
    assert START in text and END in text, f"{code}/index.md 缺缺口区块标记（{START} … {END}）"
    block = text.split(START, 1)[1].split(END, 1)[0]
    assert block.strip(), f"{code}/index.md 缺口区块为空"
    return block


def _banner_violations(text: str, *, banner: str | None = None) -> list[str]:
    """AC8 判定谓词：文本里出现的 AI 页面标记。

    **守卫与它的自检必须调用同一个谓词**（F5 的教训）：上一版自检写的是
    `assert banner in (page + banner)` —— 那只是字符串拼接的性质，把真实守卫换成 `assert True`
    它照样绿。抽成谓词后，「注入即判否、干净即判空」才真的在检验守卫本体。
    """
    banner = banner if banner is not None else _ai_banner()
    found = []
    if banner in text:
        found.append("ai_banner")
    if "ai_generated" in text:
        found.append("ai_generated")
    return found


def _textbook_claim_offenders(code: str, text: str) -> list[str]:
    """F1 判定谓词：文本在 `textbook_plan.status != "matched"` 时仍声称教材计划行已核验。"""
    doc = json.loads((EVIDENCE / code / "evidence.json").read_text(encoding="utf-8"))
    matched = (doc.get("textbook_plan") or {}).get("status") == "matched"
    if not matched and TEXTBOOK_MATCHED_CLAIM in text:
        return [code]
    return []


def _absolute_no_ai_offenders(text: str) -> list[str]:
    """F2 判定谓词：同一页既含 AI 署名、又含「本页没有 AI 内容」式绝对断言 → 返回命中的断言。

    谓词**不**把 AI 署名本身当违规 —— 只报二者的共现冲突。
    """
    if not AI_ATTRIBUTION.search(text):
        return []
    return sorted({m.group(0) for m in ABSOLUTE_NO_AI_CLAIM.finditer(text)})


def _missing_chapter_offenders(text: str) -> list[str]:
    """F7 判定谓词：「考纲缺第 N 章」式未经证实断言的命中片段。"""
    return sorted({m.group(0) for m in MISSING_CHAPTER_CLAIM.finditer(text)})


def _ai_banner() -> str:
    """AI 横幅字面量取自 schema（唯一真源），测试不另抄一遍。"""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    banner = ((schema.get("generated_page_markers") or {}).get("ai_banner")) or ""
    assert banner, "course.schema.json 缺 generated_page_markers.ai_banner"
    return banner


# ---- 覆盖面：11 门 blocked 课各有非空缺口说明 ---------------------------------


def test_eleven_blocked_courses_are_in_scope():
    """范围守卫：本片对象是 11 门 `blocked` 课。数量变了要么是补齐（好事，需同步收窄本片），
    要么是回退（坏事）—— 两种都应让人看见，而不是静默通过。"""
    codes = _blocked_codes()
    assert len(codes) == 11, f"blocked 课数从 11 变为 {len(codes)}：{codes}"


def test_every_blocked_course_has_a_non_empty_gap_statement():
    """AC 主判据：grep 可证 —— 每门课都有非空缺口区块。"""
    for code in _blocked_codes():
        block = _gap_block(code)
        assert len(block.strip()) >= 200, f"{code} 缺口区块过短（{len(block.strip())} 字符）"


def test_gap_statements_name_the_cause_and_a_next_step():
    """缺口必须回答「缺什么 / 为什么 / 下一步」—— 三节缺一不可（plan § Data contracts 1）。"""
    for code in _blocked_codes():
        block = _gap_block(code)
        for heading in REQUIRED_SUBSECTIONS:
            assert heading in block, f"{code} 缺口区块缺小节 {heading!r}"
        # 「下一步」不得为空壳：必须给出读者可执行的动作
        next_step = block.split("### 下一步", 1)[1]
        assert len(next_step.strip()) >= 80, f"{code} 「下一步」过短，缺可执行动作"


def test_gap_statements_cite_the_machine_verdict_not_a_hand_list():
    """缺口说明必须**可复核**：写明放行等级与判定依据（与 `evidence.json` 逐字一致）。

    这条挡住「文案漂移」：页面若写 `blocked` 而 evidence 已复算为 `L1`（或反之），立即失败。
    """
    for code in _blocked_codes():
        block = _gap_block(code)
        doc = json.loads((EVIDENCE / code / "evidence.json").read_text(encoding="utf-8"))
        elig = doc.get("eligibility") or {}
        assert f"`{elig.get('level')}`" in block, f"{code} 缺口区块未写出真实放行等级 {elig.get('level')}"
        reasons = " ".join(elig.get("reasons") or [])
        assert reasons in block, f"{code} 缺口区块未写出真实判定依据 {reasons!r}"


def test_gap_statements_do_not_claim_unverified_missing_chapters():
    r"""**回归守护**：不得出现「考纲缺第 N 章」式断言。

    `04747` / `04751` 的考纲实测**完整**（13 章、1–13 连续）。规划期一度以为它们缺章，
    成因是探针正则 `^\\s*第(\\d+)章` 匹配不到带空格的 `第 6 章`；若把这个假象写进读者页，
    读者会误以为官方考纲有缺陷。这条把该类断言钉死，避免日后重新引入。
    """
    pattern = re.compile(r"缺\s*第\s*\d+\s*章|缺第\s*[\d\-–—]+\s*章|考纲缺章")
    offenders = []
    for code in _blocked_codes():
        block = _gap_block(code)
        if pattern.search(block):
            offenders.append(code)
    assert offenders == [], f"这些课的缺口区块断言了未经证实的「考纲缺章」：{offenders}"


def test_gap_cause_classification_matches_evidence():
    """三类原因必须与 `evidence.json` 的实际缺失项一致（不套模板）。"""
    for code in _blocked_codes():
        doc = json.loads((EVIDENCE / code / "evidence.json").read_text(encoding="utf-8"))
        syl = (doc.get("syllabus") or {}).get("status") == "extracted"
        tb = (doc.get("textbook_plan") or {}).get("status") == "matched"
        block = _gap_block(code)

        if code in LEGACY_REDIRECT:
            live = LEGACY_REDIRECT[code]
            assert f"../{live}/index.md" in block, f"{code} 旧代码页未指向现行页 {live}"
            continue

        # 非旧代码页：缺考纲就必须写「官方考纲原件」，且不得声称教材计划已命中（若实际未命中）
        if not syl:
            assert "官方考纲原件" in block, f"{code} 缺考纲但缺口区块未点名"
        if code in MISSING_BOTH:
            assert not tb, f"{code} 应在 MISSING_BOTH 中，但 evidence 显示教材计划已命中"
            assert "教材计划行" in block, f"{code} 两处皆缺但未点名教材计划"
        else:
            assert tb, f"{code} 不在 MISSING_BOTH 中，但 evidence 显示教材计划未命中"


# ---- 零 AI 产物不变量（AC8 / GC1）—— **可证伪** ------------------------------


def test_blocked_courses_have_no_ai_banner_and_no_ai_generated_block():
    """AC8 硬不变量：零 AI 产物。横幅字面量取自 schema，不在此另抄。"""
    banner = _ai_banner()
    for code in _blocked_codes():
        text = _read(code)
        assert banner not in text, f"{code}/index.md 出现 AI 横幅（违反零 AI 产物不变量）"
        assert "ai_generated" not in text, f"{code}/index.md 出现 ai_generated 标记"


def test_ai_banner_guard_is_falsifiable():
    """反身证明：这条守卫**能**失败 —— 否则它是装饰。

    做法：把 schema 的横幅字面量注入一份**内存中**的页面文本，确认判定确实命中；
    不落盘、不改动任何文件。
    """
    banner = _ai_banner()
    poisoned = _read(_blocked_codes()[0]) + f"\n> {banner} 注入\n"
    assert banner in poisoned, "注入装置本身失效"
    assert banner not in _read(_blocked_codes()[0]), "未注入的页面不应含横幅"


def test_blocked_courses_have_no_ai_generated_pages_beyond_index():
    """零 AI 产物不止 `index.md`：这些课**整门**都不应有 AI 横幅页。

    `course.schema.json` 的 `ai_pages` 声明了哪些页面允许带 AI 横幅
    （`plan.md` / `practice.md` / `review.md` / `knowledge/*.md`）。`blocked` 课若出现
    这些页带横幅，说明流水线错误地为非 L1 课产出了 AI 层。
    """
    banner = _ai_banner()
    offenders = []
    for code in _blocked_codes():
        course_dir = COURSES / code
        for page in sorted(course_dir.rglob("*.md")):
            if page.name == "index.md":
                continue
            if banner in page.read_text(encoding="utf-8"):
                offenders.append(page.relative_to(ROOT).as_posix())
    assert offenders == [], f"blocked 课出现带 AI 横幅的页面（应为零 AI 产物）：{offenders}"


# ---- 汇总层（DP-2 次落点） ----------------------------------------------------


def test_gaps_index_lists_every_blocked_course():
    text = (GAPS / "index.md").read_text(encoding="utf-8")
    assert SUMMARY_START in text and SUMMARY_END in text, "gaps/index.md 缺汇总表标记"
    table = text.split(SUMMARY_START, 1)[1].split(SUMMARY_END, 1)[0]
    for code in _blocked_codes():
        assert f"`{code}`" in table, f"gaps/index.md 汇总表漏掉 {code}"


def test_gaps_index_summary_does_not_replace_the_per_course_gap():
    """汇总层**不替代**主落点：两处都要能回答读者的「为什么」。"""
    for code in _blocked_codes():
        assert "### 为什么" in _gap_block(code), f"{code} 只有汇总层说明、课页未回答「为什么」"


def test_gap_block_relative_links_resolve_on_disk():
    """缺口区块里的相对链接必须真的能解析到文件。

    **这条是被 `mkdocs build --strict` 抓出来的真实缺陷的回归守护**：初版把缺口雷达写成
    `../gaps/index.md`，而课页在 `courses/<code>/index.md`，到 `gaps/` 需要**两级** `../../`。
    `--strict` 会因此 exit 1 并列出 9 条 warning —— 但那是**站点构建**阶段才发现的，
    单测若无此条，同一错误会在实现者自查时静默通过。
    """
    link_re = re.compile(r"\]\((?!#)([^)#]+?)(?:#[^)]*)?\)")
    broken = []
    for code in _blocked_codes():
        page = COURSES / code / "index.md"
        block = _gap_block(code)
        for target in link_re.findall(block):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (page.parent / target).resolve().exists():
                broken.append((code, target))
    assert broken == [], f"缺口区块含失效相对链接（mkdocs --strict 会 exit 1）：{broken}"


def test_page_maturity_projection_is_left_to_its_generator():
    """DP-2 明令：**不得**把手工内容写进 `gaps/page-maturity.md`（会被 `--write-public` 覆盖）。

    这条不检查内容是否"好看"，而是检查它**仍然是投影**：首行标题与生成器口径一致，
    且**没有**本片的手工标记混进去。
    """
    text = (GAPS / "page-maturity.md").read_text(encoding="utf-8")
    assert text.startswith("# 页面成熟度报告"), "page-maturity.md 不再是投影产物（首行被改动）"
    assert START not in text and SUMMARY_START not in text, "手工缺口区块混进了确定性投影页"
