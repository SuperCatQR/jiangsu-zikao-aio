"""materials:// path resolve + existence check against private materials repo.

Resolution order for materials root:
1. env ``ZIKAO_MATERIALS_ROOT``
2. sibling directory ``../zikao-materials`` relative to AIO root
3. None (resolve unavailable — caller may skip hard checks)
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

MAT_RE = re.compile(r"materials://([^\s)>'\"`]+)")

# Trailing punctuation often glued to markdown links
_TRAIL = ".,;:)]}>\"'"


@dataclass(frozen=True)
class MaterialsRef:
    raw: str
    path: str  # normalized relative path without scheme

    @property
    def uri(self) -> str:
        return f"materials://{self.path}"


@dataclass(frozen=True)
class ResolveResult:
    ref: MaterialsRef
    root: Path | None
    candidates: tuple[Path, ...]
    exists: bool
    reason: str  # ok | missing | invalid | no-root | skipped-placeholder


def parse_materials_uri(uri: str) -> MaterialsRef | None:
    uri = uri.strip()
    if not uri.startswith("materials://"):
        m = MAT_RE.search(uri)
        if not m:
            return None
        path = m.group(1)
    else:
        path = uri[len("materials://") :]
    path = path.rstrip(_TRAIL).strip()
    if not path or path.startswith("...") or path.startswith("<"):
        return None
    path = path.replace("\\", "/").lstrip("/")
    return MaterialsRef(raw=uri if uri.startswith("materials://") else f"materials://{path}", path=path)


def find_materials_root(aio_root: Path) -> Path | None:
    env = os.environ.get("ZIKAO_MATERIALS_ROOT", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p.resolve()
    sibling = (aio_root.parent / "zikao-materials").resolve()
    if sibling.is_dir():
        return sibling
    return None


def _validate_rel(path: str) -> str | None:
    if ".." in path.split("/") or path.startswith("/"):
        return "path-escape"
    if re.search(r"(secret|token|key|password)", path, re.I):
        return "sensitive"
    return None


def resolve_ref(ref: MaterialsRef, materials_root: Path | None) -> ResolveResult:
    bad = _validate_rel(ref.path)
    if bad:
        return ResolveResult(ref, materials_root, (), False, f"invalid:{bad}")
    if materials_root is None:
        return ResolveResult(ref, None, (), False, "no-root")

    exact = materials_root / Path(*ref.path.split("/"))
    candidates: list[Path] = []
    if exact.exists():
        candidates.append(exact)
        return ResolveResult(ref, materials_root, (exact,), True, "ok")

    # Prefix match: materials://e-books/jiangsu/04735 → files starting with 04735
    parent = exact.parent
    stem = exact.name
    if parent.is_dir() and stem:
        # Match "{code} *" or "{code}-*" or exact stem prefix
        for child in parent.iterdir():
            name = child.name
            if name == stem or name.startswith(stem + " ") or name.startswith(stem + "-") or name.startswith(stem + "（"):
                candidates.append(child)
        if candidates:
            return ResolveResult(ref, materials_root, tuple(sorted(candidates)), True, "ok-prefix")

    # If path is a directory prefix that exists
    if exact.is_dir():
        return ResolveResult(ref, materials_root, (exact,), True, "ok-dir")

    return ResolveResult(ref, materials_root, (), False, "missing")


def extract_refs_from_text(text: str) -> list[MaterialsRef]:
    seen: set[str] = set()
    out: list[MaterialsRef] = []
    for m in MAT_RE.finditer(text):
        ref = parse_materials_uri(m.group(0))
        if ref is None:
            continue
        if ref.path in seen:
            continue
        seen.add(ref.path)
        out.append(ref)
    return out


def scan_content_refs(aio_root: Path) -> list[tuple[Path, MaterialsRef]]:
    hits: list[tuple[Path, MaterialsRef]] = []
    content = aio_root / "content"
    if not content.is_dir():
        return hits
    for p in content.rglob("*.md"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for ref in extract_refs_from_text(text):
            hits.append((p, ref))
    return hits


def run_materials_resolve(
    aio_root: Path,
    *,
    require_root: bool = False,
    require_exists: bool = False,
) -> list[str]:
    """Return error strings. Soft by default when materials root is absent.

    * require_root=True — fail if private repo cannot be located
    * require_exists=True — fail on missing targets when root is available
      (default True when root is available)
    """
    root = find_materials_root(aio_root)
    errors: list[str] = []
    if root is None:
        if require_root:
            errors.append(
                "materials root not found; set ZIKAO_MATERIALS_ROOT or place "
                "zikao-materials as sibling of AIO"
            )
        return errors

    # When root is available, existence checks are on by default
    if not require_exists and require_exists is False:
        # always check exists when root present unless explicitly disabled via env
        pass
    check_exists = os.environ.get("ZIKAO_MATERIALS_RESOLVE", "1") not in {"0", "false", "off"}

    hits = scan_content_refs(aio_root)
    if not hits:
        return errors

    for page, ref in hits:
        result = resolve_ref(ref, root)
        rel = page.relative_to(aio_root).as_posix()
        if result.reason.startswith("invalid"):
            errors.append(f"{rel}: {result.reason}: {ref.uri}")
        elif result.reason == "missing" and check_exists:
            errors.append(f"{rel}: materials missing: {ref.uri}")
    return errors
