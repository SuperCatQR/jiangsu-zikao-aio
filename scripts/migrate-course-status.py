#!/usr/bin/env python3
"""One-shot migration: legacy frontmatter status → lifecycle + completeness.

Mapping (P0 decision):
  missing / draft → lifecycle: draft
  yellow → lifecycle: machine_ready
  never batch-promote to publishable

completeness:
  from table 资料状态 if present, else metadata-only (current default)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.course_status import (  # noqa: E402
    COMPLETENESS,
    LIFECYCLES,
    map_legacy_status_field,
    normalize_completeness,
)
from lib.mdutil import parse_meta_table, split_frontmatter  # noqa: E402


def _set_or_replace_fm_key(fm_block: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*:.*$")
    line = f"{key}: {value}"
    if pattern.search(fm_block):
        return pattern.sub(line, fm_block, count=1)
    # insert after opening --- content: append before end
    return fm_block.rstrip() + "\n" + line + "\n"


def _remove_fm_key(fm_block: str, key: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*:.*\n?")
    return pattern.sub("", fm_block)


def migrate_text(text: str) -> tuple[str, dict[str, str]]:
    if not text.startswith("---\n"):
        return text, {"skipped": "no-frontmatter"}
    end = text.find("\n---\n", 4)
    if end == -1:
        return text, {"skipped": "broken-frontmatter"}
    fm_block = text[4:end] + "\n"
    body = text[end + 5 :]
    fm, _ = split_frontmatter(text)
    meta = parse_meta_table(body)

    old_status = fm.get("lifecycle") or fm.get("status") or ""
    lifecycle = map_legacy_status_field(old_status if "lifecycle" not in fm else fm.get("lifecycle"))
    # Never promote to publishable via migration
    if lifecycle == "publishable" and "lifecycle" not in fm:
        lifecycle = "machine_ready"

    comp_raw = fm.get("completeness") or meta.get("资料状态") or "metadata-only"
    completeness = normalize_completeness(comp_raw)
    if completeness not in COMPLETENESS:
        completeness = "metadata-only"

    info = {
        "old_status": old_status or "(none)",
        "lifecycle": lifecycle,
        "completeness": completeness,
    }

    fm_block = _set_or_replace_fm_key(fm_block, "lifecycle", lifecycle)
    fm_block = _set_or_replace_fm_key(fm_block, "completeness", completeness)
    # Keep legacy `status` only if it was already a lifecycle value; else rewrite for compat readers
    fm_block = _set_or_replace_fm_key(fm_block, "status", lifecycle)

    # Update display 状态 cell in meta table when present
    display = {
        "draft": "🔴 建设中",
        "machine_ready": "🟡 机器初稿",
        "in_review": "🟡 审查中",
        "publishable": "🟢 可发布",
    }[lifecycle if lifecycle in LIFECYCLES else "draft"]

    def _repl_status_row(m: re.Match[str]) -> str:
        return f"| 状态 | {display} |"

    body2 = re.sub(r"(?m)^\|\s*状态\s*\|\s*[^|]+\|", _repl_status_row, body, count=1)

    def _repl_comp_row(m: re.Match[str]) -> str:
        # 资料状态 table may be 3 or 4 columns
        cols = [c.strip() for c in m.group(0).strip().strip("|").split("|")]
        if len(cols) >= 3:
            # | 资料状态 | value | source? | status? |
            cols[1] = completeness
            return "| " + " | ".join(cols) + " |"
        return f"| 资料状态 | {completeness} |"

    body2 = re.sub(r"(?m)^\|\s*资料状态\s*\|[^|]*\|.*$", _repl_comp_row, body2, count=1)

    new_text = "---\n" + fm_block.lstrip("\n")
    if not new_text.endswith("\n"):
        new_text += "\n"
    # ensure single trailing newline before closing ---
    new_text = new_text.rstrip() + "\n---\n" + body2
    return new_text, info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--courses-dir",
        type=Path,
        default=ROOT / "content" / "jiangsu" / "courses",
    )
    args = parser.parse_args()
    changed = 0
    for path in sorted(args.courses_dir.glob("*/index.md")):
        if not re.fullmatch(r"\d{5}", path.parent.name):
            continue
        text = path.read_text(encoding="utf-8")
        new_text, info = migrate_text(text)
        if "skipped" in info:
            print(f"{path.parent.name}: skip {info['skipped']}")
            continue
        print(
            f"{path.parent.name}: {info['old_status']} → "
            f"lifecycle={info['lifecycle']} completeness={info['completeness']}"
        )
        if new_text != text:
            changed += 1
            if not args.dry_run:
                path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"{'Would change' if args.dry_run else 'Changed'} {changed} course index pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
