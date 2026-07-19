"""Course lifecycle + completeness status machine (P0).

Two independent dimensions:

* lifecycle — publish pipeline position (machine source of truth)
* completeness — material / content completeness for readers & maturity

Emoji badges are display-only and must not drive gates.
"""
from __future__ import annotations

from dataclasses import dataclass

LIFECYCLES = ("draft", "machine_ready", "in_review", "publishable")
COMPLETENESS = ("complete", "metadata-only", "missing-source", "needs-review")

# Legacy frontmatter `status` → lifecycle
LEGACY_STATUS_TO_LIFECYCLE = {
    "draft": "draft",
    "yellow": "machine_ready",
    "red": "draft",
    "green": "publishable",  # only if someone already claimed green; still gate-checked
    "complete": "machine_ready",  # old misuse of completeness as status
    "metadata-only": "draft",
    "missing-source": "draft",
    "needs-review": "draft",
    "unknown": "draft",
}

LIFECYCLE_EMOJI = {
    "draft": "🔴",
    "machine_ready": "🟡",
    "in_review": "🟡",
    "publishable": "🟢",
}

LIFECYCLE_LABEL_ZH = {
    "draft": "建设中",
    "machine_ready": "机器初稿",
    "in_review": "审查中",
    "publishable": "可发布",
}


@dataclass(frozen=True)
class CourseStatus:
    lifecycle: str
    completeness: str

    def display_status(self) -> str:
        emoji = LIFECYCLE_EMOJI.get(self.lifecycle, "🔴")
        label = LIFECYCLE_LABEL_ZH.get(self.lifecycle, self.lifecycle)
        return f"{emoji} {label}"

    def is_publishable(self) -> bool:
        return self.lifecycle == "publishable"


def normalize_lifecycle(raw: str | None) -> str:
    if not raw:
        return "draft"
    value = raw.strip().strip("\"'")
    if value in LIFECYCLES:
        return value
    # tolerate emoji-prefixed display strings
    for life, emoji in LIFECYCLE_EMOJI.items():
        if value.startswith(emoji) or life in value:
            if value in LIFECYCLES or value.startswith(emoji):
                if value in LIFECYCLES:
                    return value
    mapped = LEGACY_STATUS_TO_LIFECYCLE.get(value)
    if mapped:
        return mapped
    # strip emoji then retry
    for emoji in ("🔴", "🟡", "🟢"):
        if value.startswith(emoji):
            rest = value[len(emoji) :].strip()
            if rest in LIFECYCLES:
                return rest
            mapped = LEGACY_STATUS_TO_LIFECYCLE.get(rest)
            if mapped:
                return mapped
            # Chinese labels
            for life, label in LIFECYCLE_LABEL_ZH.items():
                if label in rest:
                    return life
    return "draft"


def normalize_completeness(raw: str | None) -> str:
    if not raw:
        return "needs-review"
    value = raw.strip().strip("\"'")
    if value in COMPLETENESS:
        return value
    return "needs-review"


def parse_course_status(frontmatter: dict[str, str], meta: dict[str, str] | None = None) -> CourseStatus:
    """Resolve lifecycle + completeness from frontmatter (preferred) and meta table."""
    meta = meta or {}

    life_raw = frontmatter.get("lifecycle") or frontmatter.get("status") or ""
    # Prefer explicit lifecycle; fall back to legacy status
    lifecycle = normalize_lifecycle(life_raw)

    comp_raw = (
        frontmatter.get("completeness")
        or meta.get("资料状态")
        or frontmatter.get("资料状态")
        or ""
    )
    # If only legacy status held a completeness value, don't double-count as life
    completeness = normalize_completeness(comp_raw)

    return CourseStatus(lifecycle=lifecycle, completeness=completeness)


def maturity_level(status: CourseStatus, thin: bool = False) -> str:
    """Map two dimensions to red/yellow/green maturity."""
    if status.completeness in {"missing-source", "needs-review"} and status.lifecycle == "draft":
        return "red"
    if status.lifecycle == "publishable" and status.completeness == "complete" and not thin:
        return "green"
    if status.lifecycle in {"machine_ready", "in_review", "publishable"}:
        return "yellow" if thin or status.completeness != "complete" else "yellow"
    if status.lifecycle == "draft":
        return "red" if status.completeness == "missing-source" else "yellow"
    return "yellow"


def map_legacy_status_field(raw: str | None) -> str:
    """One-shot migration: old frontmatter status → lifecycle."""
    if not raw:
        return "draft"
    value = raw.strip().strip("\"'")
    if value in LIFECYCLES:
        return value
    return LEGACY_STATUS_TO_LIFECYCLE.get(value, "draft")
