---
module: course-syllabus-pages
date: 2026-08-24
problem_type: convention
category: conventions
severity: medium
plan_id: 15043-15044-chapter-index-study-plan
applies_when:
  - "Publishing syllabus chapter indexes from official PDF TOCs"
  - "Writing executable per-chapter study plans"
tags:
  - toc-extraction
  - chapter-index
  - study-plan
  - verbatim
---

# Chapter TOC extraction and study-sequence spine

## Context

15043/15044 official outline PDFs are locally extracted under the per-course `sources/jiangsu/processed/syllabus/` directories. The public pages previously could only say “章节级大纲缺失” because the HTML page has no chapter list — but the PDF TOC does. Extracting chapter names unlocks a real syllabus index and an executable study plan without copying body text.

## Guidance

- Extract chapter names **only** from the `大纲目录` slice of the local PDF extraction artifact (the per-course extraction Markdown file). The Ⅰ–Ⅳ outline labels (`课程性质与课程目标`, `考核目标`, `课程内容与考核要求`, `关于大纲的说明与考核实施要求`) are section labels, **not** chapters.
- Keep names **verbatim** as extracted: 15044's TOC prints `绪 论` with a space — never paraphrase to `绪论`. Tests must reject the paraphrase.
- The plan page's study sequence uses the syllabus chapter index as its spine: same names, same order; one row per chapter with generic per-chapter tasks (通读该章大纲范围 / 记录不理解点 / 自检章末要求) — no invented weeks, no ISBN, no exam dates, no 真题 lists.
- The course sources page gap status splits: chapter **names** supported (verified-metadata from PDF TOC); chapter **body** and HTML TOC remain named gaps.
- Date claims stay “as stated in the PDF preface (2024-08)”, never an applicability/version inference.

## Why This Matters

A truthful chapter index turns “无章目” into a navigable syllabus while preserving the never-infer boundary. Verbatim extraction + plan↔index consistency tests prevent silent drift between pages.

## When to Apply

- Adding chapter indexes or study sequences for any course whose official PDF TOC is locally extracted.
- Extending 15043/15044 syllabus/plan pages further.

## Examples

### Before

Course syllabus page gap row: 章节级大纲 missing; course plan page empty-state “以官方 PDF 为准”.

### After

Course syllabus page: 章目索引 table (章序 | 章名) from `大纲目录` + verified-metadata TOC row; course plan page: per-chapter sequence mirroring the index; tests lock names/counts/order and the `绪 论` spacing.
