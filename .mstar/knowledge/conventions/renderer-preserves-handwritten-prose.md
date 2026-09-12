---
module: jiangsu-ai-course-pipeline
date: 2026-09-12
problem_type: convention
category: conventions
severity: critical
plan_id: ai-course-prep-pipeline-b1
applies_when:
  - "Rendering generated pages over hand-written course pages in the published course tree"
  - "Adding or changing a derived region, a marker, or a positional anchor in the renderer"
  - "Deciding whether a renderer may rewrite text it did not author"
tags:
  - renderer
  - byte-preservation
  - derived-regions
  - compliance-notice
  - idempotency
---

# The renderer must not rewrite hand-written prose

## Context

B1 made the course pages a deterministic function of three JSON artefacts. The renderer had to add generated
headers and chapter links to pages that already contained hand-written, human-reviewed prose, including a
93-character compliance notice that ends with a sentence forbidding its own removal. Two defects followed,
both graded Critical by the tri-review.

The first: to preserve a line-number anchor, the renderer matched the notice by substring at a fixed body
index and replaced it with an inert HTML comment, and a helper stripped blockquote markers from ten more
hand-written lines to satisfy a length bound. The page shipped without its disclosure, and the test covering
that bound was green only because the markers had already been removed by the same helper.

The second: a derived region was emitted with a non-greedy pattern spanning from its begin marker to the
first end marker. Because one region was nested inside another, forcing a refresh would have destroyed the
inner region and left unbalanced markers. A guard that prevented the refresh was the only thing preventing
the destruction, and a frozen region was the visible symptom of the two masking each other.

## Guidance

- **Split the surface by ownership.** Renderer-owned pages may be regenerated wholesale. Hand-written
  official pages must be byte-preserved except for explicitly declared insertions. Prove it with an
  insertions-only diff and a byte-level preservation test.
- **Never edit text to satisfy a positional anchor.** Line-number and index arithmetic is a smell that will
  corrupt a different course's page. Anchor on parsed structure, or use the sanctioned manual-block channel.
- **Derived regions must be siblings, not nested, and must refresh unconditionally.** Match spans with a
  depth-counting scan rather than a non-greedy pattern, and assert structure: no region contains another,
  every begin has exactly one end, and no orphan markers exist.
- **Idempotency is the acceptance test.** Render of the committed pages must equal the committed bytes, a
  second render must equal the first, and rendering an older release tree must reproduce the committed
  result so a migration is lossless. Test from a fresh course directory too.
- **A bound scoped to quotations must not be applied to hand-written metadata prose.** State the scope in
  the governing ops document and name both enforcing tests, so the exemption is a documented decision.

## Why This Matters

The public repository's credibility rests on the official pages being exactly what a human approved. A
renderer that normalises prose destroys review provenance silently, and in this case also destroyed the
compliance disclosure that tells readers which content is machine-generated. The nested-region variant is
worse: it appears to work until a model change needs to refresh the page, and then it corrupts it.

## When to Apply

- Any renderer change that touches a page carrying hand-written content.
- Reviewing a diff on a hand-written official page: an inserted or deleted line there is a red flag unless
  it is a declared marker or an explicitly derived block.
- Designing a new generated region for a later batch of courses.

## Examples

### Before

The renderer rewrote hand-written prose to preserve a line-number anchor and de-quoted manual text to
satisfy a length bound, so the shipped page lost its compliance notice and the guarding test passed only
by virtue of that removal.

### After

Derived regions are emitted as siblings with balanced markers and refreshed on every render, and the three
hand-written official pages change only by declared insertions, guarded by an insertions-only diff and a
byte-level preservation test.
