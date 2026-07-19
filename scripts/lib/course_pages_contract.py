"""Course multipage structure contract (index/sources/practice/plan markers)."""
from __future__ import annotations

import re
from pathlib import Path

REQUIRED = {
    "index.md": ["页面导航", "sources.md", "practice.md", "plan.md"],
    "sources.md": ["来源", "核验"],
    "practice.md": ["真题"],
    "plan.md": ["阶段目标"],
}
CODE = re.compile(r"^[0-9]{5}$")


def check_course_dir(root: Path, d: Path) -> list[str]:
    errors: list[str] = []
    if not CODE.fullmatch(d.name):
        return errors
    for filename, needles in REQUIRED.items():
        p = d / filename
        if not p.exists():
            errors.append(f"{d.relative_to(root).as_posix()}: missing {filename}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in text:
                errors.append(f"{p.relative_to(root).as_posix()}: missing marker {needle}")
    return errors


def run_course_pages_contract(root: Path) -> list[str]:
    courses = root / "content" / "jiangsu" / "courses"
    errors: list[str] = []
    if not courses.is_dir():
        return [f"{courses.as_posix()}: courses dir missing"]
    for d in sorted(courses.iterdir()):
        if d.is_dir():
            errors.extend(check_course_dir(root, d))
    return errors
