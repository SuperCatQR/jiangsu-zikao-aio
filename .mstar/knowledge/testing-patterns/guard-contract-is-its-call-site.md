---
module: jiangsu-ai-course-pipeline
date: 2026-09-18
problem_type: testing_pattern
category: testing-patterns
severity: medium
plan_id: ai-course-prep-pipeline-b4b-two-more-courses
applies_when:
  - "Reading, hardening, or reviewing a guard implemented as a regex/predicate over text"
  - "A reviewer reports a guard defect with a probe that calls the primitive directly"
  - "Authoring content that a downstream guard will parse (pre-flight)"
tags:
  - guard-contract
  - call-site-semantics
  - fail-open-states
  - preflight-parsers
  - refuted-finding
---

# A guard's contract is its call site, not its raw pattern

## Context

Two paired findings in B4b, both about the same guard family, show the two ways a guard's real contract gets lost.

**(a) A refuted finding — the pattern was read without its call site.** After the endpoint assertion
(`([A-D])(?![\s、,，/;；\-–—|*和或与及至]*[A-D])`) landed, a QC seat reported that the separator class matches `\n`, so the
lookahead crosses line breaks and **467 of 1312 delivered drills** would be excluded from the distribution sample. The
probe was real: applied to a multi-line string with `search()`, the regex genuinely refuses. But the shipped path takes
`answer_md.split("\n", 1)[0]` and calls `.match(first_line)` — a newline can never reach the regex. Measured through the
shipped function: **719 of 719 selection-family drills parsed, `unparseable` = 0**, and all 467 cross-line-shaped drills
parsed normally. The finding was refuted; only a one-clause comment precision item survived.

**(b) A real defect — the same guard's sibling collapsed two states into one.** `_chapter_titles_from_syllabus()`, which
feeds the model↔page chapter-index cross-check, ended `return rows or None`. So "the `### 章目索引` heading exists but
parses to zero rows" (a corrupted table) and "there is no such section" (a course with no page-side source) returned the
**same** `None`, and the caller skipped the whole cross-check. A garbled table could therefore switch the guard off
silently — the exact failure class ("a chapter silently disappeared") the check exists to catch, one level up. Fixed by a
three-state contract: no section → `None` (skip, unchanged); rows → compare; **heading present but zero rows → fail
closed** with an error naming the page and the condition.

## Guidance

- **Derive the contract from what the guard is fed.** Before judging a pattern, find its call site and the shape of the
  value that reaches it (one line? the whole document? a normalised view?). A probe that invokes the inner primitive
  directly answers a different question than the one the guard answers.
- **Reproduce a guard finding through the shipped path.** If the finding cannot be reproduced by calling the function the
  product calls, it is not yet a finding — it is a hypothesis about the primitive. Record the refutation in its own row
  (with the measurement) so it cannot be cited later as a live defect.
- **Split `None`/empty when it means more than one thing.** "Absent" and "present but unreadable" must not share a return
  value: the first is a legitimate skip, the second is a contradiction and must fail closed. This file's existing
  `_declared_unit_count()` already had the same three-state shape — reach for the project's own precedent.
- **Pre-flight with the guard's own parsers.** Before merging authored results into the recorded artefact, run the
  guard's parsers over them. W3 did this and caught three otherwise-silent defects — the mandatory `### 易错点` section
  missing from all 59 explains, single-choice answers written as `参考答案：X。` (a form the single-choice regex does not
  accept, which would have failed the gate **after** the fixtures were recorded), and 15 prompts under the schema's
  `minLength`. Pre-flight turns a post-recording failure into a cheap pre-recording fix.
- **Keep the fire proof.** The fail-closed branch was accepted only with mutation controls (renamed / missing / reordered
  chapter rows must still fail), and the preserved skip was proved separately (`00898`/`02333` still return `None` with no
  errors) — a guard change that makes a legitimate skip start failing is as bad as one that never fires.

## Why This Matters

Guards here are the load-bearing quality mechanism, and they are written in text-processing code where the interesting
behaviour is almost always at the call site, not in the pattern. Two opposite mistakes cost real time in one plan: a
finding that was wrong because the pattern was tested in isolation (an hour of PM reproduction), and a defect that was
real because a return value was overloaded (a latent silent-skip path in an anti-silent-loss guard). Both are cheap to
prevent with the same habit — ask what the caller actually passes.

## When to Apply

- Reviewing any guard whose implementation is a regex, predicate, or parser.
- When a reviewer's probe disagrees with the product's behaviour: check the call site before recording either side.
- When designing a helper that may legitimately find nothing: give "absent" and "unreadable" different returns.
- Immediately before a recording/merge step that freezes authored content into a committed artefact.

## Examples

### Before

> QC finding: "the endpoint class crosses newlines; 467/1312 drills are silently excluded."

### After

> PM reproduction through the shipped function: the parser matches the **first line only**, so the newline never reaches
> the regex — 719 of 719 parsed, `unparseable` = 0, all 467 shapes parsed. Recorded as a refutation plus a low
> comment-precision residual; the passing distribution rows were unchanged before and after.
