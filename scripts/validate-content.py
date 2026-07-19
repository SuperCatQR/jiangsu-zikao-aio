#!/usr/bin/env python3
"""Thin wrapper — implementation in lib.content_gate (P1 / Issue #55)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.content_gate import run_content_gate  # noqa: E402


def main() -> int:
    errors = run_content_gate(ROOT)
    if errors:
        print("Content validation failed:")
        for e in errors:
            print(f"- {e}")
        return 1
    print("Content validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
