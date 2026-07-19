"""materials:// path policy and private/raw leak scan."""
from __future__ import annotations

import re
from pathlib import Path

BAD = re.compile(
    r"https://github\.com/.+/(zikao-materials/.+|raw|download)|"
    r"(?:^|[\s(])(?:\.\./)?(?:materials|e-books|papers|past-papers|syllabus|"
    r"official-archives|official-packages)/[^\s)]+\.(?:pdf|zip|rar)\b",
    re.I,
)
MAT = re.compile(r"materials://([^\s)>'\"]+)")


def check_ref(ref: str) -> str | None:
    ref = ref.rstrip("`。，；,.;:")
    if ref.startswith("...") or ref in {
        "<path>",
        "<relative-path-without-extension-or-sensitive-name>",
    }:
        return None
    if ".." in ref or "\\" in ref:
        return "bad materials path"
    if re.search(r"(secret|token|key|password)", ref, re.I):
        return "sensitive word in path"
    return None


def run_materials_policy(root: Path) -> list[str]:
    errors: list[str] = []
    for p in (root / "content").rglob("*.md"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel = p.relative_to(root).as_posix()
        for m in MAT.finditer(text):
            err = check_ref(m.group(1))
            if err:
                errors.append(f"{rel}: {err}: {m.group(0)}")
        for line_no, line in enumerate(text.splitlines(), 1):
            if "materials://" in line:
                continue
            if BAD.search(line) and "jseea.cn" not in line:
                errors.append(f"{rel}:{line_no}: possible private/raw file leak")
    return errors
