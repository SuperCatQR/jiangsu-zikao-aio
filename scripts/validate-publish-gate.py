#!/usr/bin/env python3
"""Publish gate CLI — blocks only lifecycle=publishable pages that fail checks.

Usage:
  python scripts/validate-publish-gate.py
  python scripts/validate-publish-gate.py --courses-dir content/jiangsu/courses
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.publish_gate import run_publish_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate publishable course pages")
    parser.add_argument(
        "--courses-dir",
        type=Path,
        default=ROOT / "content" / "jiangsu" / "courses",
        help="Course pages directory",
    )
    args = parser.parse_args()
    result = run_publish_gate(ROOT, args.courses_dir)
    print(
        f"Publish gate: checked={result.pages_checked} "
        f"publishable={result.publishable_pages} "
        f"errors={len(result.errors)} warnings={len(result.warnings)}"
    )
    for w in result.warnings:
        print(f"WARNING: {w}")
    if result.errors:
        print("Publish gate FAILED:")
        for e in result.errors:
            print(f"- {e}")
        return 1
    print("Publish gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
