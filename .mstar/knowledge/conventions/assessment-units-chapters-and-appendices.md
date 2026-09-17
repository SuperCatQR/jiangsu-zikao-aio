---
module: jiangsu-ai-course-pipeline
date: 2026-09-14
problem_type: convention
category: conventions
severity: high
plan_id: ai-course-prep-pipeline-b3b-course-generation
applies_when:
  - "A syllabus declares assessed content outside its numbered chapters (appendices, 附录N)"
  - "Extending the knowledge model with a second kind of top-level assessment unit"
  - "Adding a selector, count, or ordering key that addresses units across two numbering namespaces"
tags:
  - assessment-unit
  - appendix-units
  - selector-namespaces
  - ordinal-collision
  - denominator
related_components:
  - knowledge_model
  - generate_content
  - render_pages
  - evidence_gate
---

# Assessment units: chapters and appendices share one address space, never one ordinal space

## Context

`02333` (软件工程) declares **nine assessed requirement lines in seven appendices** (`附录一 可行性研究报告`
… `附录七 UML 的模型及图示表示`), one of them at the `应用` level. The extractor's chapter slicer ended the
last chapter's body at the next 部次 label (`Ⅳ 关于大纲的说明与考核实施要求`), so all seven appendix blocks
fell *inside* chapter 14's slice, were attributed to a chapter whose own title says
`（本章内容不作考核要求）`, and were then dropped by the requirement-block reader.

Every guard stayed green while that happened. The coverage ratio read `1.0` **because the ratio and the
section list were computed from the same parse** — a self-consistent count can never notice content its own
parser lost. The defect survived a plan, an L2 review and a QC wave before a seat measured the syllabus by
hand.

The fix models appendices as **first-class assessment units** in a new top-level `appendices[]` key, siblings
of `chapters[]`, and deliberately does **not** merge them into `chapters[]`.

## Guidance

- **Keep the two families structurally separate, and put the seam in one helper.** `appendices[]` is a
  sibling key, omitted entirely when empty. A single `_units()` / `_assessment_units()` helper yields
  `chapters + appendices` in canonical order, and every consumer routes through it. Keeping the key absent
  when empty is what makes the change a **provable no-op** for the other courses (a consumer extension cannot
  alter an artefact whose new key does not exist).

- **Do not relax the chapter-ordinal continuity guard to make room for appendices.** That guard requires a
  chapter's ordinal to start at 0 or 1 and increase by exactly 1, and it exists because filling a numbering
  hole silently is its own defect class. An appendix labelled `附录一` is ordinally 1 *and* is not chapter 1;
  merging the families would either corrupt the guard or require weakening it. Separate keys keep the guard
  intact and let appendices carry their own `ordinal` / `index` / `slug`.

- **Never let two numbering namespaces share one selector.** With both families carrying `ordinal` 1…N,
  `_unit_selectors()` once returned `{slug, index, str(ordinal)}` for every unit, so the batch selector `1`
  matched **chapter 1 and appendix 1 at once** (`--chapters 5` selected `ch05` *and* `ap05`). Batched
  generation was silently widened. The rule now: **ordinals address chapters only**; appendices are
  addressed by `slug` (`ap01`…) and by their label (`附录一`…). When two collections are numbered
  independently, pick which one owns the bare ordinal and make the other's selectors unambiguous.

- **Point ids carry the unit slug, and the slug grammar is part of the contract.** Appendix points use the
  same shape as chapters with the unit slug substituted: `02333-ap07-s1-p1` alongside
  `02333-ch01-s1-p1`, i.e. `<code>-(intro|ch\d{2}|ap\d{2})-s\d+-p\d+`. A parser accepting a unit heading
  **must also require its title**: `附录一` alone matched an appendix pattern and two source lines
  (`附录一 X` and `附录 1 X`) both mapped to number 1, which would mint the same `ap01` twice. Require a
  non-empty title, and fail closed naming both locators when two lines claim one number.

- **An independent denominator is the only defence against a same-parse ratio.** Because the ratio and the
  units come from one parse, the evidence gate needed a denominator derived from the **source text**
  (`source_assessment_unit_count()` counting the syllabus's own declared assessment-unit lines) rather than
  from `sections[]`. The two counts now agree on every course (61 / 34 / 28 / 50 / 20) and disagreed
  (13 vs 20) precisely on the pre-fix `02333` — which is what a faithful independent count looks like.

- **Recovered content is not recovered until a reader can reach it.** Modelling the appendix points made
  them exist in JSON and nothing else: no consumer read `appendices[]`, so they would never have been
  rendered. The reader-reach step is part of the unit's definition — extend every consumer and prove the
  `应用`-level point appears on a real page (`02333-ap07-s1-p3` in the rendered appendix page).

## Why This Matters

The published promise is that missing official data is shown as a gap and never invented. An appendix that is
declared as assessed but silently dropped is the same failure in the other direction: the reader is told the
course is complete while ~9 requirement lines — one of them taught at the `应用` level — are absent. And
because both the loss and the ratio came from one parse, the defect is invisible to the entire test suite; only
a count taken from the source can see it.

Keeping the two families in separate keys is also what keeps the fix cheap: every other course has no
`appendices` key at all, so the extension is a structural no-op for them rather than a behavioural change to be
re-verified across the catalogue.

## When to Apply

- The syllabus has assessed content outside its numbered chapters (appendices, schedules, 附则), especially
  when a chapter title says the chapter itself is not assessed.
- A course is added whose syllabus numbers two collections independently — decide which owns the bare ordinal
  before writing any selector.
- A coverage ratio, count, or percentage is used as a completeness argument: check whether it is computed from
  the same parse it is meant to validate, and if so, add a source-side count.
- Adding a top-level key to the knowledge model: state its no-op condition and prove the no-op by diffing the
  other courses' artefacts.

## Examples

### Before

Chapters are the only unit type; the last chapter's slice runs to the next 部次 label, so seven appendix
paragraphs are filed under chapter 14, the requirement reader drops nine lines, and the coverage ratio reports
`1.0` because it counts the same `sections[]` the parse produced. A batch selector of `1` silently selects
`ch01` **and** `ap01` once appendices exist.

### After

`appendices[]` holds seven units `ap01`…`ap07` as siblings of `chapters[]`, omitted when empty; the chapter
continuity guard is untouched; `_units()` is the one seam every consumer uses; ordinals select chapters only
while `ap01` / `附录一` select appendices; the gate's denominator is recounted from the syllabus source
(61/34/28/50/20); and the `应用`-level appendix point is verified present on the rendered page.
