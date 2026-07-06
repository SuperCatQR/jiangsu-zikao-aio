#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"
REQUIRED = {
    "index.md": ["页面导航", "sources.md", "practice.md", "plan.md"],
    "sources.md": ["来源", "核验"],
    "practice.md": ["真题"],
    "plan.md": ["阶段目标"],
}
CODE = re.compile(r"^[0-9]{5}$")

def check_course_dir(d: Path) -> list[str]:
    errors: list[str] = []
    if not CODE.fullmatch(d.name):
        return errors
    for filename, needles in REQUIRED.items():
        p = d / filename
        if not p.exists():
            errors.append(f"{d.relative_to(ROOT)}: missing {filename}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in text:
                errors.append(f"{p.relative_to(ROOT)}: missing marker {needle}")
    return errors

def main() -> int:
    errors: list[str] = []
    for d in sorted(COURSES.iterdir()):
        if d.is_dir():
            errors.extend(check_course_dir(d))
    if errors:
        print("course pages contract failed:")
        print("\n".join(errors))
        return 1
    print("course pages contract ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
