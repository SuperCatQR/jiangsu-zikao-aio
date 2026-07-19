"""Minimal Markdown helpers shared by content gates."""
from __future__ import annotations

import re
from pathlib import Path


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse a simple YAML-like frontmatter block into a flat string dict.

    Nested lines indented with two spaces are collapsed onto the parent key
    (same behaviour as the former build-course-pages helper).
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    data: dict[str, str] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  ") and current_key:
            data[current_key] = (data[current_key] + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            data[current_key] = value.strip().strip('"')
    return data, body


def parse_meta_table(body: str) -> dict[str, str]:
    """Parse the first ``| 字段 | 内容 |`` table in a course page body."""
    lines = body.splitlines()
    table: dict[str, str] = {}
    for i, line in enumerate(lines):
        if line.strip() == "| 字段 | 内容 |" and i + 1 < len(lines):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if len(cells) >= 2:
                    table[cells[0]] = cells[1]
                j += 1
            break
    return table


def parse_heading_title(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "课程页"


def code_for_source(path: Path) -> str:
    if path.name == "index.md" and re.fullmatch(r"\d{5}", path.parent.name):
        return path.parent.name
    return path.stem


def route_for_source(path: Path) -> str:
    return f"/courses/{code_for_source(path)}/"


def raw_text_for_frontmatter(fm: dict[str, str]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in fm.items())


def parse_exam_index_from_frontmatter(fm: dict[str, str]) -> tuple[list[str], list[str]]:
    """Parse current_exam_periods / legacy_comparison_periods lists."""

    def _extract_list(raw: str, key: str) -> list[str]:
        m = re.search(rf"{key}\s*:\s*\[([^\]]*)\]", raw)
        if m:
            items = [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]
            return [item for item in items if item]
        m = re.search(rf"{key}\s*:\s*\n((?:\s+-\s+[^\n]+\n?)*)", raw)
        if m:
            items = re.findall(r"-\s+([^\n]+)", m.group(1))
            return [item.strip().strip("'\"") for item in items if item.strip()]
        return []

    raw = raw_text_for_frontmatter(fm)
    return _extract_list(raw, "current_exam_periods"), _extract_list(raw, "legacy_comparison_periods")


def git_head_commit(repo_root: Path) -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
