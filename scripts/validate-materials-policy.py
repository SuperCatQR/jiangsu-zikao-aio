#!/usr/bin/env python3
"""Thin wrapper — implementation in lib.materials_policy (P1 / Issue #55)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.materials_policy import run_materials_policy  # noqa: E402


def main() -> int:
    errors = run_materials_policy(ROOT)
    if errors:
        print("materials policy violations:")
        print("\n".join(errors))
        return 1
    print("materials policy ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
