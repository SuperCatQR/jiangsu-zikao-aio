#!/usr/bin/env python3
"""Compute red/yellow/green maturity from lifecycle + completeness (P0)."""
from __future__ import annotations

import argparse
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
PUBLIC_MD_REL = Path("content") / "jiangsu" / "gaps" / "page-maturity.md"
REQUIRED = ["index.md", "sources.md", "practice.md", "plan.md"]
_PRIVATE_REASON_MARKERS = ("materials://", "zikao-materials", "raw.githubusercontent.com")


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


def compute_rows(root: Path) -> list[dict]:
    """Same ordering and grade() dicts as main() uses today."""
    courses = root / "content" / "jiangsu" / "courses"
    return [
        grade(d)
        for d in sorted(courses.iterdir())
        if d.is_dir() and re.fullmatch(r"\d{5}", d.name)
    ]


def _public_reasons(reasons: list[str]) -> str:
    kept: list[str] = []
    for reason in reasons:
        if any(marker in reason for marker in _PRIVATE_REASON_MARKERS):
            continue
        kept.append(reason)
    return "; ".join(kept) if kept else "-"


def _public_next(row: dict) -> str:
    for reason in row.get("reasons") or []:
        if reason.startswith("missing:"):
            field = reason.split(":", 1)[1].split(",")[0].strip() or "pages"
            return f"gap: {field}"
        if reason == "thin-required-pages":
            return "gap: 核验"
    return f"/courses/{row['code']}/"


def _cell(value: str, *, allow_unknown: bool = False) -> str:
    text = str(value).strip() or "-"
    if not allow_unknown and text.lower() == "unknown":
        return "draft"
    return text


def render_public_markdown(rows: list[dict]) -> str:
    """Deterministic Markdown for content/jiangsu/gaps/page-maturity.md."""
    lines = [
        "# 页面成熟度报告",
        "",
        "本页由当前课程 lifecycle/completeness 行投影生成，供站点展示。",
        "",
        "|课程|lifecycle|completeness|成熟度|原因|公开下一步|",
        "|-|-|-|-|-|-|",
    ]
    for row in rows:
        lines.append(
            f"|{row['code']}|"
            f"{_cell(row['lifecycle'])}|"
            f"{_cell(row['completeness'])}|"
            f"{_cell(row['maturity'], allow_unknown=True)}|"
            f"{_public_reasons(row.get('reasons') or [])}|"
            f"{_public_next(row)}|"
        )
    tally = {k: sum(1 for r in rows if r["maturity"] == k) for k in ("red", "yellow", "green")}
    lines += ["", f"合计：red={tally['red']} yellow={tally['yellow']} green={tally['green']}", ""]
    return "\n".join(lines)


def check_public_projection(root: Path) -> list[str]:
    """Non-mutating. Empty list if public file matches render_public_markdown(compute_rows(root))."""
    path = root / PUBLIC_MD_REL
    expected = render_public_markdown(compute_rows(root))
    actual = path.read_text(encoding="utf-8") if path.exists() else ""
    if actual == expected:
        return []
    return [
        f"{PUBLIC_MD_REL.as_posix()} is stale; regenerate with "
        "`python scripts/compute-page-maturity.py --write-public` "
        "then verify with `python scripts/compute-page-maturity.py --check`"
    ]


def _write_ops(rows: list[dict]) -> dict[str, int]:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
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
    return tally


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute page maturity (ops write; public check)")
    parser.add_argument("--check", action="store_true", help="non-mutating public projection check")
    parser.add_argument(
        "--write-public",
        action="store_true",
        help="write only content/jiangsu/gaps/page-maturity.md",
    )
    args = parser.parse_args(argv)

    if args.check:
        errors = check_public_projection(ROOT)
        for err in errors:
            print(err, file=sys.stderr)
        return 1 if errors else 0

    if args.write_public:
        text = render_public_markdown(compute_rows(ROOT))
        public_path = ROOT / PUBLIC_MD_REL
        public_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.write_text(text, encoding="utf-8")
        print(f"wrote {PUBLIC_MD_REL.as_posix()}")
        return 0

    rows = compute_rows(ROOT)
    tally = _write_ops(rows)
    print(f"maturity computed: {len(rows)} courses; {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
