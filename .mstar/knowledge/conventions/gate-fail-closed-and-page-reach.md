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
last_updated: 2026-09-13
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
- **A gate's scope predicate must not be its own off-switch.** B2a found the `ai-content` layer chose its scope
  by "does this course have `sources/jiangsu/courses/15043/content.json`?" — so *deleting the source of truth* removed the course from scope
  and all seven layers passed while 16 AI-generated pages remained publishable. The added fail-closed error sat
  *downstream* of the scope `continue`, so it could never run. Key the scope on the **artefact side** (rendered
  pages bearing the schema-declared AI banner) and let "artefacts exist" *imply* "source exists", rather than
  treating source presence as the precondition for checking. Verify by deleting the source in a copy and
  asserting the runner exits non-zero.
- **Cardinality is not identity: a count is satisfied by *any* N items.** B2a's `explain`/`memorize`
  reconciliation compared a global heading count to a block count, so dropping one point's section and padding a
  heading elsewhere kept `255 == 255` and the layer green — the count answers "how many", never "which". Reconcile
  **per item** against an anchor the writer already emits (B2a reuses the renderer's per-point anchor), and keep
  the count only as a secondary bound. Equality is no safer than `>=` here: both are blind to substitution.
- **A parser-based predicate must name what can hide the token.** A heading scan that only handles code fences
  still misses an HTML comment opened before the heading, and stripping comments only inside the body slice
  leaves a comment that opens on the heading line itself. Strip comments and fences **before** the scan, through
  one shared entry point, so the several judgements built on it cannot drift apart.

## Why This Matters

The pipeline's reader-facing promise is "official facts only, AI content labelled, missing data shown as a
named gap". A gate that cannot fail turns that promise into a claim no one can falsify. The B1 pilot
shipped a site where the headline deliverable was entirely absent and every automated check was green,
which is worse than a failing check because it also removes the signal that would have prompted a fix.
B2a added the mirror-image case: a gate that can fail, but only when someone else's file is present — and
that removes itself from scope exactly when the artefact it guards is orphaned.

## When to Apply

- Wiring a new stage into the pipeline CLI or a new layer into the gate runner.
- Writing any test that asserts that the gate rejects something: prefer a mutation over a happy path.
- Reviewing a plan or report that claims "fails closed when": require the mutation that proves it, and
  check the scope of the claim (B1's claim covered four block kinds while the code covered three).
- Choosing a gate's **scope**: ask what determines whether the check runs at all, and whether an actor could
  remove a course from scope by damaging the very artefact the check protects.
- Writing any reconciliation: if it compares counts, ask whether a substitution could keep the count while
  changing the membership.

## Examples

### Before

The staging directory name is not a course-code directory, so the page-contract check silently returns an
empty error list and promotion proceeds unvalidated.

### After

Stage into a code-named subdirectory so the contract check really runs, run both gate layers before
promotion, and assert that every AI block kind reaches a page.
