"""Course multipage structure + frontmatter schema contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

from lib.course_status import COMPLETENESS, LIFECYCLES
from lib.mdutil import split_frontmatter

DEFAULT_REQUIRED = {
    "index.md": ["页面导航", "sources.md", "practice.md", "plan.md"],
    "sources.md": ["来源", "核验"],
    "practice.md": ["真题"],
    "plan.md": ["阶段目标"],
}
CODE = re.compile(r"^[0-9]{5}$")


def load_schema(root: Path) -> dict:
    path = root / "ops" / "jiangsu" / "schemas" / "course.schema.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check_frontmatter(root: Path, index_path: Path, schema: dict) -> list[str]:
    errors: list[str] = []
    rel = index_path.relative_to(root).as_posix()
    text = index_path.read_text(encoding="utf-8", errors="replace")
    fm, _ = split_frontmatter(text)
    fm_spec = schema.get("frontmatter") or {}
    required = fm_spec.get("required") or ["lifecycle", "completeness"]
    life_vals = set(fm_spec.get("lifecycle_values") or LIFECYCLES)
    comp_vals = set(fm_spec.get("completeness_values") or COMPLETENESS)

    for key in required:
        if key not in fm or not str(fm.get(key, "")).strip():
            # allow status as legacy alias for lifecycle only during transition
            if key == "lifecycle" and fm.get("status") in life_vals:
                continue
            errors.append(f"{rel}: missing frontmatter `{key}`")

    life = (fm.get("lifecycle") or fm.get("status") or "").strip()
    if life and life not in life_vals:
        errors.append(f"{rel}: invalid lifecycle `{life}`")

    comp = (fm.get("completeness") or "").strip()
    if comp and comp not in comp_vals:
        errors.append(f"{rel}: invalid completeness `{comp}`")
    return errors


def check_course_dir(root: Path, d: Path, schema: dict | None = None) -> list[str]:
    errors: list[str] = []
    if not CODE.fullmatch(d.name):
        return errors
    schema = schema or {}
    markers = schema.get("page_markers") or DEFAULT_REQUIRED
    required_files = schema.get("required_files") or list(DEFAULT_REQUIRED.keys())

    for filename in required_files:
        p = d / filename
        if not p.exists():
            errors.append(f"{d.relative_to(root).as_posix()}: missing {filename}")
            continue
        needles = markers.get(filename) or []
        text = p.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in text:
                errors.append(f"{p.relative_to(root).as_posix()}: missing marker {needle}")

    index = d / "index.md"
    if index.exists():
        errors.extend(check_frontmatter(root, index, schema))
    return errors


def run_course_pages_contract(root: Path) -> list[str]:
    courses = root / "content" / "jiangsu" / "courses"
    errors: list[str] = []
    if not courses.is_dir():
        return [f"{courses.as_posix()}: courses dir missing"]
    schema = load_schema(root)
    for d in sorted(courses.iterdir()):
        if d.is_dir():
            errors.extend(check_course_dir(root, d, schema))
    return errors
