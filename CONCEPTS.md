# Concepts

Project-specific nouns for Jiangsu self-taught exam public content. Implementation paths live in knowledge docs, not here.

## Evidence

### Official source
A public page or file from Jiangsu Education Examination Authority, a host school, or another clearly official institution that can support a published claim.

### Discovery lead
A third-party URL used only to find official sources. It cannot justify a published conclusion.

### Named gap
A missing official field recorded with the field name, reader impact, and the next official evidence needed. Silence or inferred filler is not a gap.

### Official facts layer
Course metadata, authoritative syllabus sources, textbook records, and knowledge model (`evidence.json`, `knowledge-model.json`). Validated by the `evidence` gate layer.

### AI prep layer
AI-generated study plans, point-by-point explanations, memory aids, and drills (`content.json`). Requires full quad annotations (`ai_generated`, `generator`, `evidence_refs`, `review_state`), 8-gram plagiarism checks against official syllabus text, and is validated by the `ai-content` gate layer.

### L1 eligibility
The prerequisite standard allowing a course to enter AI prep content generation: authoritative syllabus and official textbook information must both be fully verified. Non-L1 courses are strictly barred from having `content.json`.

## Content model

### Assessment unit
One assessed top-level block of a course: either a chapter or an appendix. Units are the denominator of
coverage claims, the address space of batch selectors, and the ordering spine of the knowledge model.

Chapters and appendices are **siblings**, never merged: a chapter's ordinal is its position in a contiguous
1..N sequence, an appendix's ordinal is its own 1..N sequence, and only chapters answer to a bare ordinal
selector. An appendix is not part of the chapter it follows.

### Appendix unit
An assessed block declared outside a syllabus's numbered chapters (附录一 … 附录N) that carries its own
requirement lines, including 应用-level ones. It is modelled as an assessment unit in its own right; filing
its content under the preceding chapter is the defect this distinction prevents.

### Quad annotation
The four labels every AI prep block must carry: `ai_generated`, `generator`, a non-empty `evidence_refs`,
and `review_state`. A block missing any of them is not publishable, and the `ai-content` gate layer is what
enforces it.

## Lifecycle

### machine_ready
The highest automated course lifecycle. Human review, `reviewed`, and `publishable` are never written by plans or gates.

## Projection

### Public projection
The reader-facing maturity table generated from the same `grade()` rows as the operational report.

### maturity-check
The default non-mutating gate that fails closed when the public projection drifts. Distinct from optional `maturity`, which writes operational reports.

## Pipeline

### Stage
One deterministic step of the course pipeline, in fixed order: resolve (code/name to course) → acquire (verify the
read-only source baseline) → evidence (eligibility) → model (syllabus to knowledge model) → generate (AI prep
layer) → render (JSON to pages) → gate (validate before promotion). Only `generate` may call an LLM.

### Block kind
The four kinds of AI prep content that must each reach a page: `explain`, `memorize`, `drill` (per knowledge
point, on the chapter pages; `drill` also on the practice page), and `exam_strategy` (course level, on the plan
page). A gate reconciles every kind against its landing page.

### Derived region
A renderer-owned span on a hand-written page, delimited by paired begin/end markers and refreshed on every
render. Regions are siblings, never nested, and hand-written prose outside them is byte-preserved.

### Manual block
The sanctioned channel for durable human-written page text: a marker-delimited span that the renderer
round-trips by id instead of regenerating.

### Zero AI artifacts
The state of a course that has not reached L1 eligibility: no content artefact exists at all, and the page
shows a named gap instead. The failing mode this prevents is inventing official data to fill a page.

### Backend
One of the three interchangeable generation executors behind a single schema: the production HTTP CLI, the
keyless agent that fills the same JSON by hand, and the offline fixture replay used by CI. All three pass
through the same validation path.
