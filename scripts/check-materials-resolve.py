#!/usr/bin/env python3
"""CLI: report materials:// resolve status against private zikao-materials.

Usage:
  python scripts/check-materials-resolve.py
  python scripts/check-materials-resolve.py --require-root
  set ZIKAO_MATERIALS_ROOT=C:\\path\\to\\zikao-materials
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.materials_resolve import (  # noqa: E402
    find_materials_root,
    resolve_ref,
    scan_content_refs,
    run_materials_resolve,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-root", action="store_true")
    parser.add_argument("--quiet-ok", action="store_true", help="only print missing/invalid")
    args = parser.parse_args()

    mroot = find_materials_root(ROOT)
    print(f"materials root: {mroot or '(not found)'}")
    hits = scan_content_refs(ROOT)
    print(f"refs found: {len(hits)}")
    missing = 0
    for page, ref in hits:
        result = resolve_ref(ref, mroot)
        rel = page.relative_to(ROOT).as_posix()
        if result.reason.startswith("ok"):
            if not args.quiet_ok:
                c = ", ".join(p.name for p in result.candidates[:3])
                print(f"OK  {rel}: {ref.uri} -> {c}")
        else:
            missing += 1
            print(f"!!  {rel}: {result.reason}: {ref.uri}")

    errors = run_materials_resolve(ROOT, require_root=args.require_root)
    if errors:
        print("resolve gate:")
        for e in errors:
            print(f"- {e}")
        return 1
    print("materials resolve ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
