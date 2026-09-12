"""Evidence Gate: validates official facts layer and knowledge model contracts (Issue #55 / Task 6)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

VALID_STATUSES = {"verified", "unverified", "named_gap", "missing-source"}
POINT_ID_RE = re.compile(r"^\d{5}-(intro|ch\d{2})-s\d+-p\d+$")


def _strip_generated_at(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_generated_at(v) for k, v in obj.items() if k != "generated_at"}
    if isinstance(obj, list):
        return [_strip_generated_at(x) for x in obj]
    return obj


def is_fresh(obj1: Any, obj2: Any) -> bool:
    """Compare two data objects ignoring generated_at timestamps."""
    return _strip_generated_at(obj1) == _strip_generated_at(obj2)


def run_evidence_gate(root: Path) -> list[str]:
    """Validate 18 evidence.json and knowledge-model.json files."""
    errors: list[str] = []
    courses_dir = root / "sources" / "jiangsu" / "courses"
    if not courses_dir.is_dir():
        return errors

    baseline_file = root / "ops" / "jiangsu" / "source-links.baseline.json"
    baseline_urls: dict[str, Any] = {}
    if baseline_file.is_file():
        baseline_data = json.loads(baseline_file.read_text(encoding="utf-8"))
        baseline_urls = baseline_data.get("urls", {})

    for ev_file in sorted(courses_dir.glob("*/evidence.json")):
        rel = ev_file.relative_to(root).as_posix()
        try:
            ev = json.loads(ev_file.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{rel}: JSON decode error: {exc}")
            continue

        code = ev.get("course_code")
        if not code or not re.fullmatch(r"\d{5}", code):
            errors.append(f"{rel}: invalid course_code: {code!r}")

        # Validate facts
        facts = ev.get("facts")
        if not isinstance(facts, dict):
            errors.append(f"{rel}: facts must be dict")
        else:
            for k, fact in facts.items():
                if not isinstance(fact, dict):
                    errors.append(f"{rel}: facts.{k} must be dict")
                    continue
                status = fact.get("status")
                if status not in VALID_STATUSES:
                    errors.append(f"{rel}: facts.{k}.status has invalid value: {status!r}")
                elif status == "verified":
                    prov = fact.get("provenance")
                    if not prov or not isinstance(prov, dict):
                        errors.append(f"{rel}: facts.{k} has status 'verified' but missing provenance")
                elif status == "named_gap":
                    if not fact.get("gap_impact") or not fact.get("next_evidence"):
                        errors.append(f"{rel}: facts.{k} has status 'named_gap' but missing gap_impact or next_evidence")

        # Validate eligibility vs content.json
        eligibility = ev.get("eligibility") or {}
        level = eligibility.get("level")
        content_file = ev_file.parent / "content.json"
        if level != "L1" and content_file.is_file():
            errors.append(
                f"{rel}: eligibility level is {level!r} (not L1), but content.json exists at {content_file.relative_to(root).as_posix()}"
            )

        # Validate course_url
        url = ev.get("course_url")
        if url is not None:
            if not isinstance(url, str):
                errors.append(f"{rel}: course_url must be string or null")
            elif baseline_urls:
                if url not in baseline_urls:
                    errors.append(f"{rel}: course_url {url!r} not found in source-links baseline")
                else:
                    entry = baseline_urls[url]
                    if not entry.get("authoritative"):
                        errors.append(f"{rel}: course_url {url!r} is not authoritative")
                    host = urlparse(url).hostname or ""
                    if host != "jseea.cn" and not host.endswith(".jseea.cn"):
                        errors.append(f"{rel}: course_url {url!r} host {host!r} is not jseea.cn")
                    if code and code not in entry.get("course_codes", []):
                        errors.append(f"{rel}: course_url {url!r} course_codes does not include {code}")

        # Validate knowledge-model.json if present
        km_file = ev_file.parent / "knowledge-model.json"
        if km_file.is_file():
            rel_km = km_file.relative_to(root).as_posix()
            try:
                km = json.loads(km_file.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{rel_km}: JSON decode error: {exc}")
                continue

            seen_point_ids: set[str] = set()
            pattern = re.compile(rf"^{code}-(intro|ch\d{{2}})-s\d+-p\d+$")
            for ch in km.get("chapters", []):
                for sec in ch.get("sections", []):
                    for pt in sec.get("points", []):
                        pid = pt.get("id")
                        if not pid or not pattern.fullmatch(pid):
                            errors.append(f"{rel_km}: invalid point id format: {pid!r}")
                        elif pid in seen_point_ids:
                            errors.append(f"{rel_km}: duplicate point id: {pid!r}")
                        else:
                            seen_point_ids.add(pid)

                        quote = pt.get("quote") or ""
                        if len(quote) > 60:
                            errors.append(f"{rel_km}: point {pid} quote exceeds 60 chars ({len(quote)}): {quote[:40]}...")

            coverage = km.get("coverage") or {}
            ratio = coverage.get("ratio", 0.0)
            if ratio < 0.90:
                errors.append(f"{rel_km}: coverage ratio {ratio:.2f} is under 0.90")

            diff = coverage.get("diff_vs_manual", [])
            for item in diff:
                if item.get("kind") == "manual_only":
                    errors.append(f"{rel_km}: diff_vs_manual contains manual_only entry: {item}")

    return errors
