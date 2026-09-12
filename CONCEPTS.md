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

## Lifecycle

### machine_ready
The highest automated course lifecycle. Human review, `reviewed`, and `publishable` are never written by plans or gates.

## Projection

### Public projection
The reader-facing maturity table generated from the same `grade()` rows as the operational report.

### maturity-check
The default non-mutating gate that fails closed when the public projection drifts. Distinct from optional `maturity`, which writes operational reports.
