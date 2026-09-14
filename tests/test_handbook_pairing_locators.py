"""B3c W-2 —— 手册**对照表行号**的可证伪护栏。

**缺陷类**（QC 两席独立发现，PM 亲自复核）：B3c 的读者缺口叙事在 4 门课 8 个页面上引用
《专业考试计划简编（2026 年 5 月）》的**新旧计划对照表行号**，但此前没有任何检查断言
「被引行确实包含它所声称的那一对课码」。实测中 `03709/index.md` 的第三个定位符 `L935`
落在 **`03708`↔`15043`** 那一行（正确为 `L936`）—— 一行之差，读者按图索骥会读到**另一门课**
的对照关系。本测试把这一类漂移钉死。

**范围（有意收窄）**：只覆盖本分支触及的 4 门课（`03708` / `03709` / `15043` / `15044`）的
`index.md` / `syllabus.md` / `sources.md`，只覆盖**对照表配对行号**。不建通用引用框架。

**选行判据**：同一行既出现「对照表」，又出现「同一行」或「替代/衔接关系」。这两组词共同标出
「本页声称某对课码被列于同一行」的断言句 —— 只有这类句子里的 `L<n>` 才承诺指向对照表行。

**行号口径（QC1 踩过的坑）**：抽取件含 `\\x0c` 分页符，`str.splitlines()` 会按 `\\x0c` 一并断行，
比 `\\n` 口径**多 67 行**（3390 vs 3323），下标整体错位。仓库里的 `L<n>` 是
`sed -n '<n>p'` / `grep -n` 的 1-based 行号，即 **`\\n` 口径** —— 本模块只按 `\\n` 切行。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"
HANDBOOK = (
    ROOT
    / "sources"
    / "jiangsu"
    / "processed"
    / "documents"
    / "jiangsu-plan-handbook-2026-05"
    / "document.extracted.md"
)

# 本分支触及的 4 门课 × 3 个可能承载对照表断言的页面。文件缺失即失败（不静默跳过）：
# 页面被删/改名时护栏必须响，而不是退化成空跑。
PAGES = tuple(
    f"{code}/{name}"
    for code in ("03708", "03709", "15043", "15044")
    for name in ("index.md", "syllabus.md", "sources.md")
)

# 每门课声称的对照表配对（旧代码, 新代码）。这张表是**目录身份**的声明：`150xx` 页面的配对方
# 是旧代码，`037xx` 页面的配对方是新代码。
# `test_pairing_table_matches_page_claim` 反向核对它：页面自己改了配对声称而这张表没跟着改 → 红，
# 因此本表不会静默漂移。
PAIRING = {
    "03708": ("03708", "15043"),
    "03709": ("03709", "15044"),
    "15043": ("03708", "15043"),
    "15044": ("03709", "15044"),
}

TOKEN = re.compile(r"`(L\d+(?:-\d+)?)`")
CODE = re.compile(r"\b\d{5}\b")

# 「本页声称某对课码列于同一行」的判据词。
CLAIM_MARKERS = ("同一行", "替代/衔接关系")

# 从配对断言行里**有意排除**的 `L<n>` 记号及其理由。排除是显式的，不是靠正则碰巧不匹配。
EXCLUDED_TOKEN_REASON = {
    "L87-88": "对照表「横向替代原则」的散文声明，不是对照表行",
    "L80-86": "新旧计划启用/过渡期段落（区间），经「同文件」引用",
    "L80-81": "同上，过渡期原文引用",
    "L156-163": "本科思政课条件式过渡规则（区间），经「同文件」引用",
    "L159-160": "同上，过渡规则细分条款",
    "L162-163": "同上，过渡规则细分条款",
    "L1": "**不是定位符** —— 它是「放行等级」取值 `L1`，出现在机器判定表里",
}


def _handbook_lines() -> list[str]:
    """按仓库定位符口径（`\\n`，1-based）切出手册行。"""
    return HANDBOOK.read_text(encoding="utf-8").split("\n")


def _page_lines(page: str) -> list[str]:
    return (COURSES / page).read_text(encoding="utf-8").split("\n")


def _pairing_locators() -> list[tuple[str, int, str]]:
    """产出 (页面, 行号, 定位符) —— 即「承诺指向对照表行的引用」。"""
    found: list[tuple[str, int, str]] = []
    for page in PAGES:
        for lineno, line in enumerate(_page_lines(page), 1):
            if "对照表" not in line or not any(m in line for m in CLAIM_MARKERS):
                continue
            for token in TOKEN.findall(line):
                if token in EXCLUDED_TOKEN_REASON or "-" in token:
                    continue
                found.append((page, lineno, token))
    return found


LOCATORS = _pairing_locators()


@pytest.mark.parametrize(
    ("page", "lineno", "token"),
    LOCATORS,
    ids=[f"{p}:{n}:{t}" for p, n, t in LOCATORS],
)
def test_cited_locator_holds_the_claimed_pairing(page: str, lineno: int, token: str) -> None:
    """每个被引对照表行号，其手册行必须同时含该页声称的旧代码与新代码（W-2 的回归护栏）。"""
    old, new = PAIRING[page.split("/")[0]]
    handbook = _handbook_lines()
    index = int(token[1:])
    assert 1 <= index <= len(handbook), f"{page}:{lineno} 引用 {token}，超出手册 {len(handbook)} 行"

    cited = handbook[index - 1]
    codes = set(CODE.findall(cited))
    assert {old, new} <= codes, (
        f"{page}:{lineno} 引用 {token}，但该手册行不含 {old}↔{new} 配对\n"
        f"  实际课码：{sorted(codes)}\n"
        f"  该行原文：{cited.strip()}"
    )


def test_selector_is_not_vacuous() -> None:
    """选行判据必须真的选中东西，且不得把「放行等级 L1」当定位符收进来。"""
    assert len(LOCATORS) >= 12, f"只选中 {len(LOCATORS)} 个定位符，判据已失效"
    assert {page for page, _, _ in LOCATORS} == {
        "03708/index.md",
        "03709/index.md",
        "15043/index.md",
        "15043/syllabus.md",
        "15043/sources.md",
        "15044/index.md",
        "15044/syllabus.md",
        "15044/sources.md",
    }, "承载对照表断言的页面集合发生变化"
    assert not [t for _, _, t in LOCATORS if t == "L1"], "`L1` 是放行等级取值，不是定位符"


def test_pairing_table_matches_page_claim() -> None:
    """配对表须与页面自己的声称一致（防止表与页面各说各话、互相掩护）。"""
    for page in PAGES:
        code = page.split("/")[0]
        old, new = PAIRING[code]
        for line in _page_lines(page):
            if "对照表" not in line or not any(m in line for m in CLAIM_MARKERS):
                continue
            named = set(CODE.findall(line))
            if len(named) >= 2:  # syllabus/sources 的表格行只说「旧代码与本课程」，不含课码
                assert {old, new} <= named, (
                    f"{page} 的对照表声称句未同时点名 {old} 与 {new}（实际 {sorted(named)}）；"
                    "页面声称已变，请同步 PAIRING"
                )


def test_handbook_line_indexing_follows_newline_convention() -> None:
    """行号口径护栏：`\\\\n` 口径能找到对照表行，`splitlines()` 口径则错位 —— 钉死口径本身。"""
    text = HANDBOOK.read_text(encoding="utf-8")
    newline_indexed = text.split("\n")
    splitlines_indexed = text.splitlines()

    assert "15043" in newline_indexed[832] and "03708" in newline_indexed[832], "L833 应为对照表行"

    # 分页符 `\x0c` 使 `splitlines()` 多断行；只要该文件仍含分页符，两种口径就必然错位。
    if "\x0c" in text:
        assert len(splitlines_indexed) != len(newline_indexed), (
            "文件含分页符，`splitlines()` 与 `\\n` 口径本应行数不同 —— 口径假设已变，请复核本模块"
        )
        assert not (
            "15043" in splitlines_indexed[832] and "03708" in splitlines_indexed[832]
        ), "`splitlines()` 下标 832 也命中，则该用例无法区分两种口径"
