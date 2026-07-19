#!/usr/bin/env python3
"""Thin wrapper — implementation in lib.course_pages_contract (P1 / Issue #55)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.course_pages_contract import run_course_pages_contract  # noqa: E402


def main() -> int:
    errors = run_course_pages_contract(ROOT)
    if errors:
        print("course pages contract failed:")
        print("\n".join(errors))
        return 1
    print("course pages contract ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
