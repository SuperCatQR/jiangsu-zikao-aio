#!/usr/bin/env python3
"""Compute red/yellow/green maturity for Jiangsu course pages."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "content" / "jiangsu" / "courses"
OUT_JSON = ROOT / "ops" / "jiangsu" / "page-maturity.json"
OUT_MD = ROOT / "ops" / "jiangsu" / "page-maturity.report.md"
REQUIRED = ["index.md", "sources.md", "practice.md", "plan.md"]


def front_status(text: str) -> str:
    m = re.search(r"(?m)^status:\s*([^\n#]+)", text)
    return m.group(1).strip().strip("\"'") if m else "unknown"


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
    index = (d / "index.md").read_text(encoding="utf-8", errors="replace") if (d / "index.md").exists() else ""
    status = front_status(index)
    reasons: list[str] = []
    if missing:
        reasons.append("missing:" + ",".join(missing))
    if status in {"missing-source", "needs-review"}:
        reasons.append("status:" + status)
    if reasons:
        level = "red"
    elif status == "complete":
        t = {n: (d / n).read_text(encoding="utf-8", errors="replace") for n in REQUIRED}
        ok = non_empty_after(t["sources.md"], "核验") and non_empty_after(t["practice.md"], "真题") and non_empty_after(t["plan.md"], "阶段目标")
        level = "green" if ok else "yellow"
        if not ok:
            reasons.append("complete-but-thin")
    else:
        level = "yellow"
        reasons.append("status:" + status)
    return {"code": d.name, "status": status, "maturity": level, "reasons": reasons}


def main() -> int:
    rows = [grade(d) for d in sorted(COURSES.iterdir()) if d.is_dir() and re.fullmatch(r"\d{5}", d.name)]
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 页面成熟度报告", "", "|课程|status|成熟度|原因|", "|-|-|-|-|"]
    for r in rows:
        lines.append(f"|{r['code']}|{r['status']}|{r['maturity']}|{'; '.join(r['reasons']) or '-'}|")
    tally = {k: sum(1 for r in rows if r["maturity"] == k) for k in ("red", "yellow", "green")}
    lines += ["", f"合计：red={tally['red']} yellow={tally['yellow']} green={tally['green']}"]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"maturity computed: {len(rows)} courses; {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
