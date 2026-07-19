#!/usr/bin/env python3
"""Lightweight content gate for Jiangsu self-study exam pages."""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "jiangsu"
ALLOWED_COMPLETENESS = {"complete", "metadata-only", "missing-source", "needs-review"}
ALLOWED_LIFECYCLE = {"draft", "machine_ready", "in_review", "publishable"}
# Back-compat: table cell 资料状态 still uses completeness enum
ALLOWED_STATUS = ALLOWED_COMPLETENESS
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
COURSE_CODE_RE = re.compile(r"^[0-9]{5}$")
MAJOR_CODE_RE = re.compile(r"^[0-9]{6}[A-Z]?$")
RAW_PRIVATE_RE = re.compile(r"https://raw\.githubusercontent\.com/[^\s)]+/(zikao-materials|.*private)", re.I)
GITHUB_PRIVATE_BLOB_RE = re.compile(r"https://github\.com/[^\s)]+/zikao-materials/(?:blob|raw)/", re.I)
WINDOWS_EBOOK_RE = re.compile(r"[A-Z]:\\[^\n|`]*\\e-books\\", re.I)
PDF_RE = re.compile(r"`([^`]+\.pdf)`", re.I)


def table_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[0] not in {"字段", "项目", "类型", "类别"}:
            fields.setdefault(cells[0], cells[1])
    return fields


def rel_label(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def validate_file(path: Path) -> list[str]:
    rel = rel_label(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    fields = table_fields(text)
    errors: list[str] = []

    if RAW_PRIVATE_RE.search(text) or GITHUB_PRIVATE_BLOB_RE.search(text):
        errors.append(f"{rel}: 禁止引用 GitHub private/raw 资料 URL，改用 materials://")
    if WINDOWS_EBOOK_RE.search(text):
        errors.append(f"{rel}: 禁止公开写入本机 e-books 绝对路径，改用 materials://")

    # completeness (table 资料状态) + lifecycle (frontmatter when present)
    status = fields.get("资料状态")
    if status and status not in ALLOWED_COMPLETENESS:
        errors.append(f"{rel}: 资料状态(completeness)非法：{status}")

    fm_lifecycle = None
    if text.startswith("---"):
        end = text.find("\n---\n", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if line.startswith("lifecycle:"):
                    fm_lifecycle = line.split(":", 1)[1].strip().strip("\"'")
                elif line.startswith("status:") and fm_lifecycle is None:
                    # legacy status may still appear during migration
                    raw = line.split(":", 1)[1].strip().strip("\"'")
                    if raw in ALLOWED_LIFECYCLE:
                        fm_lifecycle = raw
    if fm_lifecycle and fm_lifecycle not in ALLOWED_LIFECYCLE:
        errors.append(f"{rel}: lifecycle 非法：{fm_lifecycle}")

    last_verified = fields.get("最后核验日期")
    if last_verified and not DATE_RE.fullmatch(last_verified):
        errors.append(f"{rel}: 最后核验日期须为 YYYY-MM-DD：{last_verified}")

    if "/courses/" in rel and path.name == "index.md" and path.parent.name != "courses":
        code = fields.get("课程代码") or path.parent.name
        if not COURSE_CODE_RE.fullmatch(code):
            errors.append(f"{rel}: 课程代码须为 5 位数字：{code}")
    if "/majors/" in rel and path.name == "index.md" and path.parent.name != "majors":
        code = fields.get("专业代码") or path.parent.name.split("-", 1)[0]
        if not MAJOR_CODE_RE.fullmatch(code):
            errors.append(f"{rel}: 专业代码格式异常：{code}")
        for required in ["省份", "专业代码", "专业名称", "层次"]:
            if required not in fields:
                errors.append(f"{rel}: 缺必填字段：{required}")

    for pdf in PDF_RE.findall(text):
        norm = pdf.replace("\\", "/")
        if "e-books/" in norm.lower() and not norm.startswith("materials://"):
            errors.append(f"{rel}: PDF 教材原件须用 materials:// 引用：{pdf}")
    return errors


MANIFEST = ROOT / "sources" / "jiangsu" / "processed" / "source-records" / "pdf-processing-manifest.csv"
MANIFEST_REQUIRED = {"type", "source_pdf", "raw_xml", "raw_txt", "raw_view_html", "extracted_md", "source_sha256", "extraction_policy"}


def validate_pdf_manifest(path: Path = MANIFEST) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{rel_label(path)}: 缺 PDF 处理 manifest"]
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    fields = set(rows[0].keys()) if rows else set()
    missing = MANIFEST_REQUIRED - fields
    if missing:
        errors.append(f"{rel_label(path)}: manifest 缺字段：{', '.join(sorted(missing))}")
    for i, row in enumerate(rows, 2):
        for key in ["source_pdf", "raw_xml", "raw_txt", "raw_view_html", "extracted_md"]:
            rel = row.get(key, "")
            if not rel:
                errors.append(f"{rel_label(path)}:{i}: {key} 为空")
                continue
            target = ROOT / rel.replace("\\", "/")
            if not target.exists():
                errors.append(f"{rel_label(path)}:{i}: {key} 不存在：{rel}")
            elif key == "source_pdf" and target.stat().st_mtime > path.stat().st_mtime + 1:
                errors.append(f"{rel_label(path)}:{i}: manifest 旧于源 PDF：{rel}")
        sha = row.get("source_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            errors.append(f"{rel_label(path)}:{i}: source_sha256 非 SHA256：{sha}")
        if not row.get("extraction_policy"):
            errors.append(f"{rel_label(path)}:{i}: extraction_policy 为空")
    return errors


def main() -> int:
    errors: list[str] = []
    for md in CONTENT.rglob("*.md"):
        # Machine extraction drafts can preserve source text; gate rendered pages and source lists.
        if md.name in {"plan.extracted.md", "plan.pipeline-notes.md"}:
            continue
        errors.extend(validate_file(md))
    errors.extend(validate_pdf_manifest())
    if errors:
        print("Content validation failed:")
        for e in errors:
            print(f"- {e}")
        return 1
    print("Content validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
