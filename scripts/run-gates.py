#!/usr/bin/env python3
"""Unified content gates entrypoint (P1 / Issue #55).

Layers (order):
  content   — copyright, lifecycle/completeness enums, codes, PDF manifest
  materials — materials:// refs + private/raw leak scan
  contract  — course multipage required files/markers
  publish   — lifecycle=publishable hard gate
  maturity  — write page-maturity report (optional, non-default)

Usage:
  python scripts/run-gates.py
  python scripts/run-gates.py --layers content,publish
  python scripts/run-gates.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.content_gate import run_content_gate  # noqa: E402
from lib.course_pages_contract import run_course_pages_contract  # noqa: E402
from lib.materials_policy import run_materials_policy  # noqa: E402
from lib.publish_gate import run_publish_gate  # noqa: E402

DEFAULT_LAYERS = ("content", "materials", "contract", "publish")
ALL_LAYERS = DEFAULT_LAYERS + ("maturity",)


def run_maturity(root: Path) -> list[str]:
    """Import and run compute-page-maturity main()."""
    # Load sibling script as module by path
    import importlib.util

    script = root / "scripts" / "compute-page-maturity.py"
    spec = importlib.util.spec_from_file_location("compute_page_maturity", script)
    if spec is None or spec.loader is None:
        return ["maturity: cannot load compute-page-maturity.py"]
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        code = mod.main()
        if code:
            return [f"maturity exited {code}"]
    except Exception as e:  # noqa: BLE001
        return [f"maturity error: {e}"]
    return []


def _publish_errors() -> list[str]:
    result = run_publish_gate(ROOT)
    return list(result.errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run layered content gates")
    parser.add_argument(
        "--layers",
        default=",".join(DEFAULT_LAYERS),
        help=f"comma-separated layers (default: {','.join(DEFAULT_LAYERS)})",
    )
    parser.add_argument("--list", action="store_true", help="list layers and exit")
    args = parser.parse_args()

    if args.list:
        for name in ALL_LAYERS:
            mark = "*" if name in DEFAULT_LAYERS else " "
            print(f"{mark} {name}")
        return 0

    layers = [x.strip() for x in args.layers.split(",") if x.strip()]
    unknown = [x for x in layers if x not in ALL_LAYERS]
    if unknown:
        print(f"Unknown layers: {', '.join(unknown)}")
        print(f"Known: {', '.join(ALL_LAYERS)}")
        return 2

    runners = {
        "content": lambda: run_content_gate(ROOT),
        "materials": lambda: run_materials_policy(ROOT),
        "contract": lambda: run_course_pages_contract(ROOT),
        "publish": _publish_errors,
        "maturity": lambda: run_maturity(ROOT),
    }

    failed = 0
    for layer in layers:
        errors = runners[layer]()
        if errors:
            failed += 1
            print(f"[{layer}] FAILED ({len(errors)})")
            for e in errors:
                print(f"- {e}")
        else:
            print(f"[{layer}] ok")
    if failed:
        print(f"Gates failed: {failed}/{len(layers)} layers")
        return 1
    print(f"All gates passed ({len(layers)} layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
