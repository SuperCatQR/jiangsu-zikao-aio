# Specifications Index

Long-term product/API specs. Iteration-only drafts live under `.mstar/iterations/<id>/`, not here. Do not add knowledge docs at iteration-start (compound at close).

| Spec | Status | Scope |
|------|--------|-------|
| [AI course-prep pipeline](ai-course-prep-pipeline.md) | locked | **Current authority.** Course-code/name-driven AI exam-prep pipeline: official-fact layer + AI 备考层, single `L1` eligibility gate, knowledge model, deterministic rendering, `evidence` / `ai-content` gate layers. Iteration `jiangsu-ai-course-pipeline-2026-09-11` delivers slice B1 (data foundation + 15040 pilot); B2–B4 are later batches. Partially supersedes [Public-source content loop](public-source-content-loop.md). |
| [Public-source content loop](public-source-content-loop.md) | locked (partially superseded) | Official-source evidence and reader-facing completion for Jiangsu courses 15043 中国近现代史纲要 and 15044 马克思主义基本原理 (Batch 1). Iteration `jiangsu-public-loop-expand-2026-08-24` extends that same contract to 15040/00023; the locked body is not rewritten. Evidence discipline, source-record fields, no-copied-text rule and the `machine_ready` ceiling remain in force; the pipeline spec above replaces its production path, batch plan and 15043/15044 coverage limit. |
