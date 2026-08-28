"""Site-integration: five-kind cross-links, start-here path, hub cards."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"
CODES = ("15043", "15044")
EXPAND_CODES = ("15040", "00023")
FIVE_KIND_CODES = CODES + EXPAND_CODES
PAGE_KINDS = ("index.md", "sources.md", "syllabus.md", "plan.md", "practice.md")
START_HERE_STEPS = (
    ("考纲与范围", "syllabus.md"),
    ("学习计划", "plan.md"),
    ("练习与真题", "practice.md"),
    ("来源与核验", "sources.md"),
)
MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _read(code: str, page: str) -> str:
    return (COURSES / code / page).read_text(encoding="utf-8")


def _cross_link_bar(text: str, *, page: str) -> str:
    for line in text.splitlines():
        if "｜" not in line or "](" not in line:
            continue
        return line
    raise AssertionError(f"no cross-link bar on {page}")


def _hrefs(line: str) -> list[str]:
    return [href.split("#", 1)[0] for _label, href in MD_LINK.findall(line)]


def _section_after(text: str, heading: str) -> str:
    idx = text.index(heading)
    rest = text[idx:]
    nxt = rest.find("\n## ", 1)
    return rest if nxt == -1 else rest[:nxt]


def test_five_page_kinds_exist_for_both_courses():
    for code in FIVE_KIND_CODES:
        for page in PAGE_KINDS:
            path = COURSES / code / page
            assert path.is_file(), f"missing {path.relative_to(ROOT)}"


def test_cross_link_bar_is_symmetric_and_targets_exist():
    for code in FIVE_KIND_CODES:
        for page in PAGE_KINDS:
            bar = _cross_link_bar(_read(code, page), page=f"{code}/{page}")
            hrefs = set(_hrefs(bar))
            expected = {other for other in PAGE_KINDS if other != page}
            missing = expected - hrefs
            assert not missing, f"{code}/{page} bar missing {sorted(missing)}: {bar}"
            extra_self = page in hrefs
            assert not extra_self, f"{code}/{page} bar must not self-link: {bar}"
            for target in expected:
                dest = COURSES / code / target
                assert dest.is_file(), f"{code}/{page} links {target} but file missing"


def test_start_here_block_has_four_reader_path_steps():
    for code in FIVE_KIND_CODES:
        text = _read(code, "index.md")
        assert "## 开始学习" in text, f"{code}/index.md missing 开始学习 heading"
        block = _section_after(text, "## 开始学习")
        steps = []
        for line in block.splitlines():
            m = re.match(r"^(\d+)\.\s+\[([^\]]+)\]\(([^)]+)\)\s*$", line)
            if m:
                steps.append((int(m.group(1)), m.group(2), m.group(3).split("#", 1)[0]))
        assert [n for n, _label, _href in steps] == [1, 2, 3, 4], steps
        got = [(label, href) for _n, label, href in steps]
        assert got == list(START_HERE_STEPS), f"{code} start-here steps {got}"
        for _label, href in START_HERE_STEPS:
            assert (COURSES / code / href).is_file()


def test_hub_lists_15043_and_15044_with_five_page_kinds():
    hub = COURSES / "index.md"
    text = hub.read_text(encoding="utf-8")
    assert "章节索引与学习计划已整理" in text
    deepened = _section_after(text, "## 示范课程（15043 / 15044）")
    for code in CODES:
        for page in PAGE_KINDS:
            rel = f"./{code}/{page}"
            assert rel in deepened, f"hub deepened section missing {rel}"
            assert (COURSES / code / page).is_file()


def test_hub_lists_15040_and_00023_with_five_page_kinds():
    hub = COURSES / "index.md"
    text = hub.read_text(encoding="utf-8")
    assert "章节索引与学习计划已整理" in text
    assert "教材导向学习计划已整理" in text
    expand = _section_after(text, "## 深化课程（15040 / 00023）")
    for code in EXPAND_CODES:
        for page in PAGE_KINDS:
            rel = f"./{code}/{page}"
            assert rel in expand, f"hub expand section missing {rel}"
            assert (COURSES / code / page).is_file()
