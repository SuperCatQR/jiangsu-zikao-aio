---
module: jiangsu-ai-course-pipeline
date: 2026-09-12
problem_type: workflow_issue
category: workflow-patterns
severity: high
plan_id: ai-course-prep-pipeline-b1
applies_when:
  - "Consolidating QC/QA findings into a plan record or residual register"
  - "A reviewer reports a defect with a measured before/after figure"
  - "Comparing file line numbers across tools or languages"
tags:
  - false-positive
  - line-number-semantics
  - form-feed
  - pm-verification
  - evidence-discipline
---

# Reviewer findings need PM reproduction — two seats reported false positives in one round

## Context

B1's plan QC tri-review produced 7 Criticals and 24 Warnings across three seats. Two of the seat findings
were **false positives**, and both arrived with confident measured evidence. Had they been written straight
into the plan record, the plan would have carried two permanent, wrong "facts".

1. **Seat 2 — "the new flank scan introduced a cross-course mis-citation"** (`02208` now citing `02207`'s
   row at `L89`; catalog-wide cross-course citations "0 → 1", with a real per-line sweep behind it).
2. **Seat 3 — "plan row F12 cites a non-resolving path"** (`scripts/lib/ai_content_gate.py` claimed wrong).

The first is the instructive one, because the numbers were real and the conclusion was still wrong.

## Guidance

- **Reproduce before recording.** A finding is not plan-record material until PM has independently
  reproduced it. Sample, don't transcribe: apply the seat's own predicate in one self-contained command.
- **Line numbers are only meaningful with the split semantics that produced them.** The locator contract
  here is `Path.read_text().split("\n")` — and the source files contain **`\x0c` form feeds**. Using
  `str.splitlines()` (which splits on `\x0c` as well) shifts every subsequent line number. PM's first
  reproduction attempt made exactly this error and "confirmed" the seat's false positive; the corrected
  sweep (contract semantics, all 1004 (course, source) pairs) returned **1004/1004 correct**, with the two
  disputed locators byte-identical to the base commit — wave 2 had never touched them.
- **Check whether the artifact was even in scope of the change.** A "regression introduced by commit X"
  claim is refuted immediately if `git show` proves X did not modify the lines. Do this before evaluating
  the mechanism.
- **Distinguish the mechanism from the metric.** In the same finding, the *diagnosis* was sound (the flank
  scan's ordering genuinely could cite an adjacent row) while the *measured claim* was not reproducible.
  Record the confirmed half as a real (smaller) item; refute the other half explicitly so it cannot be cited
  later.
- **A wrong "fact" in the register is worse than a missing one.** Once written into a plan or residual
  register, a false positive acquires authority: the next session reads it as established. Give refutations
  their own tracked row (B1: plan F13, F15③) stating what was claimed, how it was refuted, and the exact
  corrected measurement.

## Why This Matters

Multi-seat review is the main quality mechanism in this harness, and it works — the same round caught a
Critical defect (the AI layer never reaching a page) that no automated check could see. But seats are
leaf executors with a narrow channel: they cannot run the project's tests, and their probes are
self-authored, so they can share a methodological blind spot with anyone who follows their lead. PM
reproduction is the cheapest place to catch it, and the cost of not doing it is a permanently wrong record.

## When to Apply

- Consolidating any QC/QA round into the plan, the residual register, or a close-out summary.
- Whenever a finding carries a before/after number, a catalog-wide sweep, or a "0 → N regression" claim.
- Whenever a finding turns on line numbers, character offsets, or any position derived from a file read.

## Examples

### Before

Seat report: "`02208` now cites `02207`'s row; cross-course citations 0 → 1." Recorded as a regression.

### After

PM re-applied the contract's own split semantics (read the file text and split on newline only, since the
source contains form feeds that a general line splitter would treat as breaks), re-checked every one of the
1004 course/source pairs, and confirmed the disputed locators were byte-identical to the base commit, which
proves the commit under review never touched them.

Recorded as plan F13: *false positive, refuted; the mechanism half (flank ordering) was real and fixed.*
