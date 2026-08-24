---
module: course-plan-pages
date: 2026-08-24
problem_type: convention
category: conventions
severity: medium
plan_id: 00023-study-plan
applies_when:
  - "Writing an executable study plan when the official outline is missing-source"
  - "Grounded plan content for courses with only a verified textbook plan row"
tags:
  - textbook-grounded
  - study-plan
  - named-gap
  - stage-based
---

# Textbook-grounded study plan when the outline is missing

## Context

00023 高等数学（工本） has no official 考纲 URL (missing-source), so a per-chapter study plan from an outline is impossible. The only verified evidence is the textbook-plan row (`00023 高等数学(工本)` / `000231 高等数学(工本)(附大纲)` / 陈兆斗、马鹏 / 北京大学出版社 / 2023年). The study plan must still be executable without inventing chapters.

## Guidance

- Ground the plan **only** in verified metadata: textbook name/author/publisher/year as recorded in the course sources page. Treat `附大纲` as part of the book title, never as a TOC.
- Use a **stage-based sequence** when no chapter index exists: 核对教材计划元数据 → 通读教材对应章节 → 公式与例题练习 → 自检与错题 → 真题待补. No invented chapter numbers, weeks, ISBN, exam dates, or 真题 lists.
- Keep 考纲/真题/适用考期/ISBN as named gaps; the plan references the missing sources instead of filling them.
- Do not infer an outline from a textbook plan row — a textbook exists does not mean the syllabus chapters are known.

## Why This Matters

A truthful stage-based plan is executable (reader knows what to do) without claiming outline knowledge that does not exist. It preserves the never-infer boundary.

## When to Apply

- Any course whose plan page needs content but the official outline is missing-source (e.g. 13000 later, once its textbook plan is located).
- Extending 00023 plan pages further.

## Examples

### Before

Empty-state “以官方 PDF 为准” with no executable steps.

### After

Five-stage sequence citing only the verified textbook metadata; 考纲/真题/适用考期/ISBN stay named gaps; tests reject invented 第一章 lists and D1- calendars.
