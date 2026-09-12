#!/usr/bin/env python3
"""Unified content gates entrypoint (P1 / Issue #55).

Layers (order):
  content         — copyright, lifecycle/completeness enums, codes, PDF manifest
  materials       — materials:// refs + private/raw leak scan
  contract        — course multipage required files/markers
  publish         — lifecycle=publishable hard gate
  maturity-check  — non-mutating public page-maturity projection check (default)
  evidence        — official facts layer + knowledge model contracts
  ai-content      — AI prep layer quad annotations + 8-gram + banners
  maturity        — write page-maturity report (optional, non-default)

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

from lib.ai_content_gate import run_ai_content_gate  # noqa: E402
from lib.content_gate import run_content_gate  # noqa: E402
from lib.course_pages_contract import run_course_pages_contract  # noqa: E402
from lib.evidence_gate import run_evidence_gate  # noqa: E402
from lib.materials_policy import run_materials_policy  # noqa: E402
from lib.publish_gate import run_publish_gate  # noqa: E402

DEFAULT_LAYERS = (
    "content",
    "materials",
    "contract",
    "publish",
    "maturity-check",
    "evidence",
    "ai-content",
)
ALL_LAYERS = DEFAULT_LAYERS + ("maturity",)


_COMPUTE_PAGE_MATURITY_MOD = None


def _load_compute_page_maturity(root: Path):
    global _COMPUTE_PAGE_MATURITY_MOD
    if _COMPUTE_PAGE_MATURITY_MOD is not None:
        return _COMPUTE_PAGE_MATURITY_MOD
    import importlib.util

    script = root / "scripts" / "compute-page-maturity.py"
    spec = importlib.util.spec_from_file_location("compute_page_maturity", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _COMPUTE_PAGE_MATURITY_MOD = mod
    return mod


def run_maturity(root: Path) -> list[str]:
    """Import and run compute-page-maturity main() (mutating ops write)."""
    try:
        mod = _load_compute_page_maturity(root)
        if mod is None:
            return ["maturity: cannot load compute-page-maturity.py"]
        code = mod.main([])
        if code:
            return [f"maturity exited {code}"]
    except Exception as e:  # noqa: BLE001
        return [f"maturity error: {e}"]
    return []


def check_public_projection_layer(root: Path) -> list[str]:
    """Non-mutating projection check: public page + ops JSON/report vs grade() rows."""
    try:
        mod = _load_compute_page_maturity(root)
        if mod is None:
            return ["maturity-check: cannot load compute-page-maturity.py"]
        return list(mod.check_projection(root))
    except Exception as e:  # noqa: BLE001
        return [f"maturity-check error: {e}"]


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
        "maturity-check": lambda: check_public_projection_layer(ROOT),
        "evidence": lambda: run_evidence_gate(ROOT),
        "ai-content": lambda: run_ai_content_gate(ROOT),
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
