---
module: jiangsu-ai-course-pipeline
date: 2026-09-12
problem_type: convention
category: conventions
severity: critical
plan_id: ai-course-prep-pipeline-b1
applies_when:
  - "Adding or changing a gate layer, or wiring a new pipeline stage into the pipeline CLI"
  - "Making a claim of the form 'the gate fails closed when X'"
  - "Extending the pipeline to a new course code (B2/B3/B4)"
tags:
  - gate-fail-closed
  - enforcement-path
  - page-reach
  - single-writer
  - evidence-layer
---

# Gates must re-derive, and every AI block must land on a page

## Context

B1's first QC tri-review returned `Request Changes` from all three seats with five independent blocking
defects. Two of them shared one shape: **a check that looked present but verified nothing.** The gate
pipeline stage called `check_course_dir` on a `mkdtemp` directory whose basename is not a 5-digit course
code, so the contract check returned an empty list on every run. And the `ai-content` gate asserted that AI
pages carry a banner, but never that any AI content reached a page, so 1180 generated blocks (393 drills,
the five-stage plan, the strategy note, the review schedule) were orphaned while every layer reported green.

Both defects were invisible to a green suite: 249 tests passed, all 7 gate layers passed, and the site built
clean. The class of bug is "a guard whose condition can never be true", which no amount of happy-path
testing detects.

## Guidance

- **Any check that depends on a name, path, or shape must be proven to fire.** If a validator early-returns
  on a pattern mismatch, assert somewhere that the pattern *matches* on the real input. A mutation test
  (corrupt the artefact, then the layer must exit non-zero) is the only honest proof; assert the error count
  changes from zero to at least one, not merely that the call returns a list.
- **A gate must re-derive claims from raw inputs, never trust the artefact's own declaration.** The evidence
  layer now recomputes the eligibility level from the syllabus status plus the textbook-plan status and
  fails closed when a declared `L1` cannot be derived. Before that, a forged `L1` declaration with both
  inputs `missing` passed the gate.
- **A gate that checks presentation is not a gate that checks content.** For each produced content kind,
  assert it *arrived* where the contract says it should (page reach), not just that the page looks right.
  B1's reconciliation had to be extended to all four block kinds after one kind slipped through a
  three-of-four check.
- **One writer per artefact, and the writer set must be closed.** A read-only fallback key that no writer
  emits is an unguarded input channel: it bypassed both the status enum and the no-value-on-unverified-fact
  rule, and printed a forged name as the official H1.
- **Bounds must be enforced on the complete emitted artefact, not the payload.** A quote bound passed for a
  point with no quote field (the check was one-sided), and the 8-gram plagiarism guard measured only one
  block list, so the review schedule reached 85 percent overlap while the documented ceiling was 20.

## Why This Matters

The pipeline's reader-facing promise is "official facts only, AI content labelled, missing data shown as a
named gap". A gate that cannot fail turns that promise into a claim no one can falsify. The B1 pilot
shipped a site where the headline deliverable was entirely absent and every automated check was green,
which is worse than a failing check because it also removes the signal that would have prompted a fix.

## When to Apply

- Wiring a new stage into the pipeline CLI or a new layer into the gate runner.
- Writing any test that asserts that the gate rejects something: prefer a mutation over a happy path.
- Reviewing a plan or report that claims "fails closed when": require the mutation that proves it, and
  check the scope of the claim (B1's claim covered four block kinds while the code covered three).

## Examples

### Before

The staging directory name is not a course-code directory, so the page-contract check silently returns an
empty error list and promotion proceeds unvalidated.

### After

Stage into a code-named subdirectory so the contract check really runs, run both gate layers before
promotion, and assert that every AI block kind reaches a page.
