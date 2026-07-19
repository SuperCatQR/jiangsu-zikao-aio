#!/usr/bin/env python3
"""Compute red/yellow/green maturity from lifecycle + completeness (P0)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.course_status import maturity_level, parse_course_status  # noqa: E402
from lib.mdutil import parse_meta_table, split_frontmatter  # noqa: E402

COURSES = ROOT / "content" / "jiangsu" / "courses"
OUT_JSON = ROOT / "ops" / "jiangsu" / "page-maturity.json"
OUT_MD = ROOT / "ops" / "jiangsu" / "page-maturity.report.md"
REQUIRED = ["index.md", "sources.md", "practice.md", "plan.md"]


def non_empty_after(text: str, word: str) -> bool:
    i = text.find(word)
    if i < 0:
        return False
    for line in text[i:].splitlines()[1:8]:
        s = line.strip()
        if s and not s.startswith(("#", "|", "<!--", ">")):
            return True
    return False


def grade(d: Path) -> dict:
    missing = [n for n in REQUIRED if not (d / n).exists()]
    index_path = d / "index.md"
    index = index_path.read_text(encoding="utf-8", errors="replace") if index_path.exists() else ""
    fm, body = split_frontmatter(index)
    meta = parse_meta_table(body)
    status = parse_course_status(fm, meta)

    reasons: list[str] = []
    if missing:
        reasons.append("missing:" + ",".join(missing))

    thin = False
    if not missing:
        t = {n: (d / n).read_text(encoding="utf-8", errors="replace") for n in REQUIRED}
        thin = not (
            non_empty_after(t["sources.md"], "核验")
            and non_empty_after(t["practice.md"], "真题")
            and non_empty_after(t["plan.md"], "阶段目标")
        )
        if thin:
            reasons.append("thin-required-pages")

    level = maturity_level(status, thin=thin or bool(missing))
    if missing and level != "red":
        level = "red"
    reasons.append(f"lifecycle:{status.lifecycle}")
    reasons.append(f"completeness:{status.completeness}")

    return {
        "code": d.name,
        "lifecycle": status.lifecycle,
        "completeness": status.completeness,
        "status": status.lifecycle,  # back-compat key
        "maturity": level,
        "reasons": reasons,
    }


def main() -> int:
    rows = [
        grade(d)
        for d in sorted(COURSES.iterdir())
        if d.is_dir() and re.fullmatch(r"\d{5}", d.name)
    ]
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 页面成熟度报告", "", "|课程|lifecycle|completeness|成熟度|原因|", "|-|-|-|-|-|"]
    for r in rows:
        lines.append(
            f"|{r['code']}|{r['lifecycle']}|{r['completeness']}|{r['maturity']}|"
            f"{'; '.join(r['reasons']) or '-'}|"
        )
    tally = {k: sum(1 for r in rows if r["maturity"] == k) for k in ("red", "yellow", "green")}
    lines += ["", f"合计：red={tally['red']} yellow={tally['yellow']} green={tally['green']}"]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"maturity computed: {len(rows)} courses; {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
