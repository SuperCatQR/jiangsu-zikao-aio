---
module: jiangsu-ai-course-pipeline
date: 2026-09-18
problem_type: workflow_issue
category: workflow-patterns
severity: medium
plan_id: ai-course-prep-pipeline-b4b-two-more-courses
applies_when:
  - "A wave changes the inputs of a derived artefact (projection, index, census, baseline snapshot)"
  - "Writing a wave's acceptance list for a render / generate / content wave"
  - "A gate fails one wave later with a message about a projection rather than about the changed content"
tags:
  - derived-artifacts
  - same-wave-refresh
  - acceptance-list
  - page-maturity
  - provenance
---

# Derived artefacts must be refreshed in the wave that changes their inputs

## Context

B4b's render wave (W4) produced the reader-visible deliverable: 38 pages for the two new courses, 26 of them new
chapter pages. It committed them, and its own acceptance list — page counts, banner/marker contract, official-page
preservation, zero-point chapters, determinism — all passed.

One wave later, `scripts/run-gates.py` failed: `maturity-check FAILED (3)`. The **page-maturity projections**
(`ops/jiangsu/page-maturity.json`, `content/jiangsu/gaps/page-maturity.md`, `ops/jiangsu/page-maturity.report.md`) still
described the two courses as thin placeholder pages, because W4 never refreshed them. The precedent was already in the
repository — B3b's render wave (`3a708af`) refreshed the same projections inside its own wave — but no acceptance item in
W4's list named it, so the wave had no reason to look.

Cost: the failure surfaced one wave later, was diagnosed as "which wave owns this?", and was closed by a separate
commit (`a401610`) using the gate's own two remediation commands. The content was never wrong; only the derived view of
it was.

The same class covers several artefacts in this repository: page-maturity projections, the source-link baseline
(`ops/jiangsu/source-links.baseline.json`), course/gap indexes, the generated page census, and anything else whose value
is a function of committed content.

## Guidance

- **Derive the ownership from the input, not from the artefact's location.** An artefact belongs to the wave that changed
  what it is derived from. If the render wave changes the pages, the render wave owns the projection refresh.
- **Name it in the acceptance list.** A wave cannot satisfy a requirement nobody wrote down. For every wave that changes
  content, check what else is a function of that content and add an explicit acceptance item — with the producing command
  (`scripts/compute-page-maturity.py` with its `--write-public` flag) so the implementer does not have to discover it.
- **Prefer the gate's own prescribed remediation.** Here the failing layer printed the exact commands to fix it; using
  them keeps the derived state in the shape the gate expects.
- **Diff the recomputation before committing it.** The refresh touched only the two new courses' rows; the other 16 were
  byte-identical. That check is what distinguishes "refresh" from "churn", and it is cheap (compare in memory first).
- **Do not confuse generated with disposable.** `content/jiangsu/gaps/page-maturity.md` is a *published* page (it is in
  `mkdocs.yml`'s nav) — so "it is only a derived artefact" is not a licence to let it drift. Derived, published, and
  drift-guarded can all be true at once.

## Why This Matters

A stale projection is worse than a missing one: it is machine-generated, it is often *published to readers or operators*,
and it is guarded by a layer that will fail — but only in a later wave, where the cause is no longer in the diff. The
diagnosis then costs a wave, and the risk is that a later wave "fixes" the gate rather than the projection. Making the
refresher explicit in the acceptance list turns a one-wave-late failure into a same-wave checklist item.

## When to Apply

- While planning any wave that renders, generates, or deletes content.
- When a gate message names a projection/index/census rather than the content itself.
- When adopting a new derived artefact: add both its producing command and its owning wave to the plan template.

## Examples

### Before

W4's acceptance: page counts, banner contract, official-page insertions-only, zero-point chapters, determinism, the two
repo gates → all green. Projections untouched. The gate script at W5: `maturity-check FAILED (3)` — the layer that guards
exactly this drift.

### After

W5 ran the layer's own two remediation commands, diffed the recomputation in memory first (only the two new courses
moved; the other 16 rows byte-identical), committed it as its own change, and re-ran `scripts/run-gates.py` → 7/7 layers. The close
record notes the gap as an acceptance-design defect (the wave was not at fault) and registers the general rule.
