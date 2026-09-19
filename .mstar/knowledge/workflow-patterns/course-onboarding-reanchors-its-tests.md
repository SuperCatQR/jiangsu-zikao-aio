---
module: jiangsu-ai-course-pipeline
date: 2026-09-18
problem_type: workflow_issue
category: workflow-patterns
severity: high
plan_id: ai-course-prep-pipeline-b4b-two-more-courses
applies_when:
  - "A course (or any entity) moves from hand-written pages into the generated pipeline"
  - "Planning a wave whose renderer will regenerate pages that older tests assert by hand-written shape"
  - "Building the red-window / expected-red inventory for a plan"
tags:
  - course-onboarding
  - stale-test-contracts
  - red-window-inventory
  - qa-gate-backstop
  - re-anchoring
---

# Onboarding a course into the pipeline re-anchors the tests that locked its hand-written pages

## Context

B4b brought two courses (`04747`, `04751`) into the content pipeline for the first time. Their plan.md,
practice.md and review.md pages had been **hand-written placeholders**; per the (corrected) page-ownership rule they are
`ai_pages` — renderer-owned — so the render wave legitimately regenerated them.

Two pre-existing test modules, `tests/test_04747_reader_path.py` and `tests/test_04751_reader_path.py`, had been written
for the hand-written pages. Nobody touched them during the plan. At the final revision **6 of their tests were red**:

- `plan_sequence_matches_syllabus_index_order` — asserted the hand-written `## 建议节奏：按章节顺序执行` table;
- `plan_assessed_and_non_assessed_partition` — asserted that table's `类型` column;
- `six_pages_symmetric_navigation` — asserted a 30-link pairwise navigation matrix.

The PM's red-window inventory had listed the two `ai-content` tests and (after a mid-plan blocker) the `evidence` test —
but **never** these modules, because every wave's L2 review only sees its own delta, and nothing in any wave's acceptance
list mentioned them. The failure was found by the **independent L4 QA gate**, which ran a controlled experiment: the
same unchanged modules pass against the base content (`cdf6d9a`) and fail at the delivered revision.

The consequence was not cosmetic: CI runs `pytest -q`, which is precisely the leg the plan had deferred to CI. A
deferred *execution* does not excuse a **red branch fact**.

## Guidance

- **Inventory before you start.** As soon as a plan proposes to regenerate an entity's pages, grep for every test module
  that names it or asserts its page structure (a `grep -rl` over `tests/` with the course code), and read each one for hand-written-shape
  assumptions. Put that list in the plan with a decision per module: re-anchor / keep / delete-with-reason.
- **Re-anchor in the same plan, not later.** These modules were red from the render wave onward. Landing the re-anchor in
  the same plan keeps the branch green at every commit and keeps the reviewer's job scoped.
- **Re-express the property, do not drop the assertion.** Each hand-written assertion protected something real. Rewrite
  it against the new architecture in a form that is still falsifiable:
  - order → the renderer's own sequence table, plus an **ordinal leg** (row *k* must link to a page that exists, whose H1
    is byte-equal to the row's chapter name, and which is the *k*-th chapter page — this catches a self-consistent
    reorder that a membership check would miss);
  - partition → the syllabus qualifier on **every surface** that carries it (chapter H1, plan rows, index links,
    syllabus table);
  - navigation → **reachability from the course index** rather than a pairwise matrix, plus a dead-end check.
- **Prove each rewritten assertion can still fail.** Mutation controls on a copy (reorder → red; strip the qualifier → red;
  drop the links → red), and check *specificity*: a mutation aimed at one property should not redden the others.
- **Say what you dropped and why.** Here the action-level wording (`读 → 记 → 查` / `仅参考阅读`) had no counterpart on the
  rendered plan page — but the wording survives verbatim on each course's index page, so no reader-visible distinction
  was lost. That sentence is what makes the drop reviewable; a silent deletion would not be.
- **Treat the QA gate as the backstop, not the plan.** It caught this because it is the only seat that reads the whole
  branch's test surface. That is an argument for keeping the gate independent — not for skipping the inventory.

## Why This Matters

A green-looking wave list plus a red branch is the worst combination: each wave's review passes, the deliverables are
correct, and the repository still cannot merge. The failure mode is structural (per-delta review cannot see cross-module
tests), so it will recur for every remaining course — this pipeline has **11 more courses** waiting on syllabus
acquisition, and each one will regenerate the same three page types.

## When to Apply

- Any plan that moves an entity from hand-authored artefacts into a generator.
- When writing the plan's expected-red / red-window list: it must cover **every** test that asserts the entity's old
  shape, not just the gates whose output changes.
- When a renderer legitimately changes a page type: before declaring the wave done, ask which tests asserted the old type.

## Examples

### Before

Plan red-window note: "the two `ai-content` tests and the `evidence` test will be red until the render wave closes them."
Delivered revision: `6 failed, 12 passed` in two modules nobody had listed, and `pytest -q` — the CI leg — red.

### After

Re-anchored modules: `18 passed`, assertion count **up** (44 → 52 and 43 → 51), no `skip`/`xfail`/deselect, 8 mutation
controls (four of them specific), one reasoned drop with its reader meaning shown to survive elsewhere, and a QA re-run
verdict of `PASS-with-notes` with the finding closed. The registered follow-up records the one residual gap the reviewer
found (the index page's chapter links are compared by qualifier flags only).
