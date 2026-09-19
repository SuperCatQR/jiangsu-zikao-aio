---
module: jiangsu-ai-course-pipeline
date: 2026-09-18
problem_type: workflow_issue
category: workflow-patterns
severity: high
plan_id: ai-course-prep-pipeline-b4b-two-more-courses
applies_when:
  - "Writing a plan section that asserts a capability is already in place ('already widened', 'already included', 'already matched')"
  - "A plan states a count, a scope list, or a measured shape that a later wave will consume"
  - "A wave fails closed on a premise the plan treated as satisfied"
tags:
  - plan-premises
  - measure-first
  - in-plan-amendment
  - falsified-assumption
  - expectation-vs-target
---

# Plan premises must be measured, not asserted — four falsified premises in one iteration

## Context

Iteration B4 (`jiangsu-ai-course-pipeline-b4-2026-09-18`) carried **four** premises that the plan text treated as
established facts. All four were false, and each one was discovered only when the wave that depended on it ran:

| # | Plan text said | Measured reality | Cost |
|---|---|---|---|
| 1 | B4a Task 3 acceptance: the question types "stay 6 / 4" | existing five courses measure **3 / 3 / 3 / 4 / 4**; `6` is structurally unreachable for them | acceptance criterion rewritten; the number had to be kept out of the register |
| 2 | B4b § 非目标: "both courses are already inside `course_scope` (B3b already widened it)" | the four prompt templates' `course_scope` = the five original codes only → `generate` exits 2 **before any write** | a new plan task (Task 0) + a wave; two committed tests lost their subject |
| 3 | B4b GC11: "the six hand-written pages are preserved byte-for-byte" | `course.schema.json → generated_page_markers` puts `plan`/`practice`/`review` in **`ai_pages`** (renderer-owned, regenerated) and only `index`/`syllabus`/`sources` are `official_only` | GC11 restated by page ownership; the acceptance for the render wave rewritten |
| 4 | B4b: the model↔page chapter-index cross-check would pass | the model keeps the extraction's verbatim `第 6 章` while the hand-written table prints `第6章` → the gate **fails closed before rendering** | a new task (0b) relaxing the *comparison*, with 12 rows permanently accepted |

None of the four was a surprise in the sense of being unknowable: every one was **one command away** (a probe, a
`grep`, a schema read) at plan-writing time.

## Guidance

- **A plan premise is a claim, and claims need evidence.** Whenever a plan asserts that something is already true —
  a flag is set, a scope is open, a page is protected, a count holds — spend one command proving it before the plan is
  locked. Put the command's output in the plan or its design notes, not the bare assertion.
- **Treat plan numbers as expectations, never as targets.** Give the implementing wave the number *and* the instruction
  "measure and report; if it differs, escalate — do not tune anything to match this text". Premise 1 was caught exactly
  because the wave was told to measure; had it been told to satisfy "6 / 4", it would have bent the data.
- **When a premise fails, amend the plan in-plan.** Do not work around it (a bypass, a hand-written artefact, a
  "temporary" source edit) and do not silently drop the wave. Add the task, give it explicit ownership of the files the
  fix needs, and record the falsification, the measurement, and the rejected alternatives.
- **Rejected alternatives belong in the record.** For premise 4 the plan records why normalising the *model* (breaks the
  verbatim-extraction convention), editing the *hand-written table* (corrupts the guard's independent second source),
  and bypassing the gate (`--stages render`) were each refused. The next reader otherwise re-proposes them.
- **Watch for a premise appearing twice.** Premise 1 and premise 4 are the same defect class in different plans of the
  same iteration — a signal that the class is systemic, which is what made this document worth writing.

## Why This Matters

A false premise does not stay local. It propagates into acceptance criteria (which then cannot be met), into
"non-goals" (which silently forbid the only legal fix), into test expectations, and — worst — into the residual
register, where a wrong number acquires authority. In this iteration the cost of the four premises was three plan
amendments, one extra wave, two re-anchored test modules, and one QA-gate failure; the cost of measuring them at
plan-writing time would have been four commands.

## When to Apply

- While writing or reviewing any plan section: `## 非目标` / **Non-Goals**, `## Current state`, acceptance criteria, and
  "already X" sentences in the goal or architecture paragraphs.
- Before locking a plan, run a premise sweep: list every assertion of the form "already …", "… is in place",
  "… covers N", and reduce each to a command.
- When a wave fails closed on a premise: amend the plan, do not bypass the guard.

## Examples

### Before

> **非目标**：不改提示词的作用域机制（两门课已含在 `course_scope` 内，B3b 已放宽）。

The wave then ran `generate 04747 --backend agent` → `EXIT=2`, `无提示词包（course_scope 不含该课码）`, zero writes.
The only legal fix was the one the plan had forbidden itself from making.

### After

The premise line is struck through and points at a measured correction record; a new `Task 0 (W1.5)` owns the four
template files and the two tests that lose their subject, and the wave's assignment carries the measurement command
plus the instruction to escalate rather than tune. The reviewer of that wave independently re-derived the scope for all
seven L1 courses and confirmed an unknown code is still refused — the amendment made the whitelist *correct*, not
merely wider.
