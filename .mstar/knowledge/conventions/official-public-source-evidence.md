---
module: jiangsu-course-pages
date: 2026-08-24
problem_type: convention
category: conventions
severity: high
plan_id: 15043-15044-public-source-content-loop
applies_when:
  - "Publishing Jiangsu course evidence, syllabus indexes, or study plans"
  - "Expanding the public-source loop to another course code"
tags:
  - official-source
  - named-gap
  - machine-ready
  - jseea
---

# Official public-source evidence

## Context

Public course pages for 15043 / 15044 must be useful without private archives. Official Jiangsu outline HTML pages can name a course and attach a PDF while still omitting chapter lists, ISBN, exam range, and applicability dates. Inferring those fields from third-party pages or from “this year’s exam” produced QC Request Changes.

## Guidance

- Published claims need an official public URL (Jiangsu Education Examination Authority, host school, or another clearly official institution). Third-party pages are discovery leads only.
- Record URL, title, stated publication/applicability when the official page states it, course-code/name match, verification date, and supported fields. Missing official support is a **named gap**: field, reader impact, next official evidence.
- Do not infer exam range, ISBN, textbook edition, outline version, or replacement/顶替 rules. If the official HTML has no chapter list, the public hub must say so; do not treat the syllabus page as a second outline SSOT.
- Automated lifecycle stops at `machine_ready`. Never write `publishable`, `reviewed: true`, or a `reviewer` field from a plan.
- Official PDFs stay at their URL. Do not paste PDF body or private extracted document bodies into the public tree.

## Why This Matters

Readers and release gates must distinguish supported scope from missing evidence. Inferred dates and dual outline trees look complete and fail review.

## When to Apply

- Adding or editing a Jiangsu course page set (`content/jiangsu/courses/15043/` or a later course directory).
- Next-batch candidates (00023, 13000, 15040) once each has a verified official record or an explicit public gap.

## Examples

### Before

Official page linked, then “2024 版 / 2025 年考试范围 / 顶替截止日期” filled from non-official calendar knowledge.

### After

Official HTML + PDF URLs recorded; applicability `未声明`; 章节知识树 / 高频概念 named as gaps; lifecycle `machine_ready`, completeness `metadata-only`.
