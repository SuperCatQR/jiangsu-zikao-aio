"""Load major Chinese name → English slug dictionary."""
from __future__ import annotations

import json
from pathlib import Path

_CACHE: dict[str, str] | None = None


def load_major_slugs(root: Path) -> dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = root / "ops" / "jiangsu" / "major-slugs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    _CACHE = dict(data.get("slugs") or {})
    return _CACHE


def slug_for_major_name(root: Path, name: str, fallback: str | None = None) -> str:
    slugs = load_major_slugs(root)
    if name in slugs:
        return slugs[name]
    if fallback:
        return fallback
    # ASCII-ish fallback
    import re

    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "major"
