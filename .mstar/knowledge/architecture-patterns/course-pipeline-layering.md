---
module: jiangsu-ai-course-pipeline
date: 2026-09-12
problem_type: architecture_pattern
category: architecture-patterns
severity: high
plan_id: ai-course-prep-pipeline-b1
applies_when:
  - "Extending the course pipeline to a new batch of courses (B2/B3/B4)"
  - "Adding a producer or consumer to the official-facts or AI-prep layer"
  - "Deciding where a new artefact's single writer lives"
tags:
  - layered-architecture
  - single-writer
  - pipeline-stages
  - eligibility-gate
  - determinism
---

# Course pipeline layering: one writer per artefact, one eligibility decision

## Context

Before B1 the project was a hand-built metadata index: a maintainer found an official syllabus PDF,
extracted it, hand-picked chapter names, and wrote Markdown. B1 replaced that with a course-code-driven
pipeline that produces the same pages from JSON. Three layers now exist, and the boundary between them is
what keeps the public promise ("official facts only, AI content labelled, gaps named") enforceable.

## Guidance

**Three layers, each deterministic except one, and every artefact has exactly one writer.**

| Layer | Inputs | Producer | Artefact |
|---|---|---|---|
| Data foundation | major pages, plan snapshots, processed extracts | catalog builder | course/major catalog JSON (code+name SSOT) |
| Evidence and extraction (no LLM) | syllabus extracts, textbook-plan documents, read-only link baseline | evidence module, knowledge-model module | per-course evidence JSON (eligibility), knowledge-model JSON |
| AI prep (the only LLM layer) | knowledge model | generation backend | per-course content JSON |
| Render and gate (no network) | the three JSON artefacts | renderer, gate runner | published pages, gate verdicts |

- **One CLI is the pipeline entry**, with stages resolve → acquire → evidence → model → generate → render
  → gate, and a second thin entry only for the catalog check the acceptance criteria name. Do not grow a
  third entry point.
- **The eligibility decision lives in exactly one place.** It is persisted in the course's evidence artefact
  and only *read* by the renderer and the gates. Never re-derive it in a second module; a gate that
  re-derives it independently is the backstop, not a second source of truth.
- **The AI layer is gated on eligibility, not on optimism.** A course that cannot be released produces
  **zero** AI artefacts, and the page shows a named gap instead. This is what makes "we do not invent
  official data" testable rather than aspirational.
- **Rendering is a pure function of the JSON.** No hand-written body text is duplicated into a generated
  page; hand-written pages are preserved by the manual-block mechanism plus declared derived regions
  (see the renderer convention in conventions/).
- **Machine artefacts cap at machine_ready.** No pipeline stage writes reviewed, reviewer, or
  publishable; human review stays a human step.
- **Determinism is a design constraint, not an afterthought.** Only declared timestamp fields may vary
  between runs; see the determinism convention in testing-patterns/.

## Why This Matters

The layering is what allows the two content layers to have different trust rules while sharing one page.
It also bounds the blast radius of a change: a prompt revision touches the AI layer only, an extraction
rule touches the model layer only, and the gate layer is the single place where "release or refuse" is
decided. B1's worst defects were all boundary violations — a second writer of the page tree, an
out-of-contract read that bypassed the fact-status rules, and a gate that never ran.

## When to Apply

- Starting a new course batch: reuse the stage order and the single eligibility artefact; do not add
  per-batch judgement code.
- Adding a new artefact: name its single writer before writing code, and add it to the ownership table.
- Reviewing a pipeline change: check that no layer reaches around another layer's artefact.

## Examples

### Before

A maintainer edits a course page by hand, and a separate script also rewrites the same page tree; the
result is two writers with no ordering rule, and a render silently discards the hand edit.

### After

The catalog, evidence, model, content, and page artefacts each have one producer; gates read the artefacts
they validate; and the only sanctioned way for a human to add durable page text is the manual-block
channel, which the renderer round-trips by id.
