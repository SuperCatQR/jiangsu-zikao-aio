---
iteration_id: jiangsu-course-completion-xl-2026-08-25
start_date: 2026-08-25
end_date: 2026-08-29
status: completed
enforcement: soft
effort_budget: XL
iteration_base_branch: main
spec_integration_branch: iteration/jiangsu-course-completion-xl
target_branch: main
plans:
  - 02324-reader-path
  - 02333-official-syllabus-reader-path
  - 00898-official-syllabus-reader-path
  - 13015-reader-path
  - 04735-source-trace-reader-path
---

# jiangsu-course-completion-xl-2026-08-25 Delivery Compass

## Direction Lock

Improve the reader-facing course pages of five Jiangsu 080901 计算机科学与技术 courses using **existing verified sources only**: 02324 离散数学, 02333 软件工程, 00898 互联网软件应用与开发, 13015 计算机系统原理, 04735 数据库系统原理. The iteration extends the proven reader-path pattern from `jiangsu-15043-15044-deepen-2026-08-24` (start-here block, symmetric cross-link bars, chapter-name index where an official syllabus extraction exists, executable study sequences) to these five courses. The long-term spec `.mstar/specs/public-source-content-loop.md` stays **locked**; nothing in this iteration changes its evidence contract.

### Decisions recorded (PM delegation, 2026-08-25)

- Direction: five business course-content plans, exactly the five plan_ids listed in the frontmatter; no other course codes enter this iteration.
- Evidence policy unchanged: official-public-only claims; every unsupported field stays a **named gap**; never invent official URLs — the only official URLs usable are the ones already recorded in `sources.md` / `ops/jiangsu/source-links.baseline.json`.
- Lifecycle cap: automated lifecycle never exceeds `machine_ready`; no `publishable`, no `reviewed: true`, no `reviewer`.
- Branch: `main` -> `iteration/jiangsu-course-completion-xl` -> `main` (PR to `main` at Phase 4, merge after user confirmation — standing policy from prior iterations).
- The site hub (`content/jiangsu/courses/index.md`) already links all five courses; hub rows are **out of scope** for every plan (avoids dual hub ownership across five parallel plans).
- Budget: **XL** — five independent course-scoped plans run serially per the SDD discipline; each plan is S/M-sized, but the iteration as a whole is near-subsystem scale (five page sets + shared gates).

## Scope

- **Plan 1 (P1/S) — `02324-reader-path`**: 离散数学 reader paths. Textbook-plan metadata already `verified-metadata` (辛运帏, 机械工业出版社, 2014, 附大纲); official syllabus URL is a named gap. Start-here block, symmetric cross-links, plan/review/practice alignment to the actual evidence state; chapter index stays a **named gap** (no official syllabus source to extract from).
- **Plan 2 (P1/M) — `02333-official-syllabus-reader-path`**: 软件工程. Official syllabus URL already `official-url-ok` + local extraction `sources/jiangsu/processed/syllabus/02333-software-engineering-gaogang-4068/document.extracted.md` (第一/二/三篇, 第1–14章 + 附录一–七; 第14章 verbatim-marked 不作考核要求). Publish chapter-name index on `syllabus.md`, executable per-chapter study sequence on `plan.md`, reader paths. 教材计划元数据 is a named gap.
- **Plan 3 (P1/M) — `00898-official-syllabus-reader-path`**: 互联网软件应用与开发. Official syllabus URL already `official-url-ok` + local extraction `00898-internet-software-development-gaogang-4295/document.extracted.md` (第1–16章 flat; 第9、12–16章 verbatim-marked 不作考核要求). Same shape as Plan 2. 教材计划元数据 is a named gap.
- **Plan 4 (P1/S) — `13015-reader-path`**: 计算机系统原理. Textbook-plan metadata `verified-metadata` (袁春风, 机械工业出版社, 2023, 附大纲); official syllabus URL is a named gap. Same shape as Plan 1.
- **Plan 5 (P0/M) — `04735-source-trace-reader-path`**: 数据库系统原理 (only P0 in this iteration). Existing rich v2.1 machine draft (78/78 knowledge points from the local 2018 textbook outline). Focus: **source-trace reader path** — per-block source traceability, cross-link symmetry, start-here, consistency between `index.md` claims and `sources.md` rows, without rewriting the delivered knowledge tree. Official syllabus URL / 真题 / ISBN verification stay named gaps.
- **Write-ownership**: each plan is the exclusive writer of its own course directory (`content/jiangsu/courses/<code>/`); no page is dual-owned. No plan edits the hub, `scripts/`, `ops/`, or another course's pages. Focused tests (if any) live per-plan under `tests/` with course-code-scoped names.

## Plans

| plan_id | Name | Status | Notes |
|---------|------|--------|-------|
| 02324-reader-path | 离散数学 reader paths (no official syllabus) | Done | P1/S; gaps stay named; no chapter index; mandatory QA PASS; merged into `iteration/jiangsu-course-completion-xl` |
| 02333-official-syllabus-reader-path | 软件工程 chapter index from official gaogang-4068 | Done | P1/M; QC tri-review + targeted revalidation approved; mandatory QA PASS; merged into `iteration/jiangsu-course-completion-xl` |
| 00898-official-syllabus-reader-path | 互联网软件应用与开发 chapter index from gaogang-4295 | Done | P1/M; 16 章 flat; 第9、12–16章 non-assessed (qualifiers verbatim); QC/QA PASS; merged into `iteration/jiangsu-course-completion-xl` |
| 13015-reader-path | 计算机系统原理 reader paths (no official syllabus) | Done | P1/S; gaps stay named; no chapter index; QC/QA PASS; merged as `1bed7e7` into `iteration/jiangsu-course-completion-xl` |
| 04735-source-trace-reader-path | 数据库系统原理 source-trace reader path | Done | P0/M; trace existing v2.1 content; no rewrite of knowledge tree; QC consolidated Approve; mandatory QA PASS; merged as `0c68464` into `iteration/jiangsu-course-completion-xl` |

Status values: `Todo` | `InProgress` | `InReview` | `Done` | `Blocked`

## Milestones

| Milestone | Target date | Status |
|-----------|-------------|--------|
| Direction lock + Phase 1 artifacts | 2026-08-25 | done |
| Plans 1–2 (02324, 02333) delivered | 2026-08-29 | done |
| Plans 3–4 (00898, 13015) delivered | 2026-08-29 | done |
| Plan 5 (04735) delivered | 2026-08-29 | done |
| Iteration close + PR to `main` | 2026-08-29 | close complete; PR delivery next |

## Acceptance Criteria

- Each of the five courses has a complete, symmetric cross-link bar across its six pages (index, syllabus, plan, review, practice, sources) and a start-here reader path on `index.md` (orientation only, no new evidence claims).
- 02333 and 00898 `syllabus.md` pages carry a chapter-name index sourced verbatim (names only, including verbatim chapter-level non-assessment qualifiers) from the already-extracted official gaogang documents, with a verified-metadata TOC source row; no body text, no exam-range inference.
- 02324 and 13015 keep the official-syllabus absence as visible named gaps; their `plan.md` pages are executable against the verified textbook-plan metadata without invented chapters, ISBNs, or dates.
- 04735 knowledge-tree blocks trace to their existing sources (textbook outline extraction, textbook-plan row, existing `materials://` index); `sources.md` rows and `index.md` claims are consistent; no rewrite of delivered v2.1 content beyond traceability and navigation.
- Every public claim points to an official URL already in `sources.md`/baseline or stays a named gap; no new official URLs are invented.
- Lifecycle never exceeds `machine_ready`; no `publishable` / `reviewed` / `reviewer` claims anywhere in the diff.
- Default `run-gates.py`, focused/full pytest, `check-source-links.py --offline`, and `mkdocs build --strict` pass on the integration branch.

## Non-Goals

- New course codes (13000, 03708/03709 legacy pages, 04747, 04751, 13017, …).
- Editing `content/jiangsu/courses/index.md` (hub) rows or `mkdocs.yml` nav.
- Closing named gaps: no fetching new official syllabi for 02324/13015/04735, no 教材计划 hunting for 02333/00898, no 真题 acquisition, no ISBN verification.
- Copying gaogang body text beyond chapter/篇/附录 names; no textbook outline body republication (04735 tree already delivered — traced, not expanded).
- Changing `scripts/compute-page-maturity.py` `grade()`, gate layers, or schemas.
- Lifecycle promotion beyond `machine_ready`; human-review or publish simulation.
- Editing `content/**` during Phase 1 (this phase is planning only).

## Roadmap Position

- **Current iteration (jiangsu-course-completion-xl-2026-08-25)**: **delivered** — all five 080901 core-course page sets reached the deepen-iteration reader-path standard using existing evidence; named gaps remain open by policy.
- **Next iteration trigger**: any of the named gaps (official syllabus URL for 02324/13015/04735, 教材计划 for 02333/00898, 真题 ingestion from `zikao-materials`) once a verified source record exists; next owner is PM-led Prepare for the relevant gap-closure plan.
- **Final target**: every included Jiangsu course has auditable public evidence, truthful lifecycle/completeness state, and a human-controlled publish gate.

## Delivery Branch Policy

| Field | Value |
|-------|-------|
| `iteration_base_branch` | `main` |
| `spec_integration_branch` | `iteration/jiangsu-course-completion-xl` |
| `target_branch` | `main` |

Plans merge to `iteration/jiangsu-course-completion-xl` one at a time (serial); after iteration close, one PR to `main`.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Chapter-name extraction from machine-draft gaogang artifacts contains OCR spacing variants | High | Med | Publish verbatim names with a needs-review note; never paraphrase or normalize silently; cross-check count (02333: 3 篇/14 章/7 附录; 00898: 16 章) |
| 04735 v2.1 content accidentally rewritten by "improvement" | Med | High | Plan 5 write-ownership is trace/navigation-only; knowledge-tree rows are read-only surface |
| Five parallel plans drift on shared conventions | Med | Med | Serial SDD dispatch; this compass + iteration-scope.md fix the shared contracts verbatim |
| Reader-path copy introduces implicit claims (考期, 版本, "已就绪") | Med | Med | Orientation-only rule; named-gap language mandatory; QC/QA gates |
| URL hygiene: edits drop extractable official URLs out of IN_SCOPE sections | Low | Med | Offline `check-source-links.py` gate; no plan adds/removes URLs |

## Iteration package

| Path | Purpose |
|------|---------|
| `README.md` | Package document index |
| `guides/direction-lock.md` | Direction decisions, source-matrix evidence, per-course facts |
| `specs/iteration-scope.md` | Plan write-ownership, measurable acceptance, execution boundaries |

## Quality Gate Summary

> Filled at iteration-close.

| plan_id | QC decision | QA gate | Residuals | Durable summary |
|---------|-------------|---------|-----------|-----------------|
| 02324-reader-path | Approve | PASS | none | serial reader-path pages; official syllabus/true-exam/ISBN gaps remain named |
| 02333-official-syllabus-reader-path | Approve | PASS | none | official gaogang chapter-name index and reader paths;教材计划/真题/实物 gaps remain named |
| 00898-official-syllabus-reader-path | Approve | PASS | none | official gaogang 16-chapter index and reader paths;教材计划/真题/实物 gaps remain named |
| 13015-reader-path | Approve | PASS | none | reader paths with verified textbook metadata; official syllabus/true-exam/ISBN gaps remain named |
| 04735-source-trace-reader-path | Approve after QC1 F-001 targeted revalidation | PASS | none | 8 trace rows, 6-page reader path, 78/78 tree preserved; official syllabus/true-exam/ISBN gaps remain named |

## Compound Round Summary

- **Inventory completed:** package `jiangsu-course-completion-xl-2026-08-25/` contains `README.md`, `guides/direction-lock.md`, `specs/iteration-scope.md`, and the excluded compass itself. The compass was excluded from promotion by default.
- **Triage:** `README.md` — Keep snapshot (package index/history); `guides/direction-lock.md` — Keep snapshot (iteration-specific source matrix, decisions, and plan mapping); `specs/iteration-scope.md` — Keep snapshot (iteration-only ownership and measurable acceptance). None was promoted.
- **Q1–Q8 / overlap result:** no new durable document met the novelty bar. Official-only evidence and named-gap handling overlap the existing `knowledge/conventions/official-public-source-evidence.md`; chapter extraction and study-sequence guidance overlap existing knowledge docs. Creating duplicates would reduce discoverability.
- **Knowledge output:** 0 new docs, 0 updates, 0 archived docs; no new CONCEPTS.md vocabulary. Existing package documents remain the auditable iteration snapshot and are indexed by the package README.

## Iteration Retrospective (minimal)

- **Delivered:** five serial SDD plans merged into the integration branch; all course sets now expose complete reader paths, and 02333/00898 expose official extraction-based chapter-name indexes while 04735 exposes per-chapter traceability over its preserved 78/78 tree.
- **Quality:** per-task L2 reviews, plan-level QC tri-review, targeted QC1 revalidation, and mandatory full QA completed; final gates include 88 passing tests, 5-layer gates, offline source-link check, strict MkDocs, and focused preservation audits.
- **What required correction:** source-claim drift in 04735 was caught by QC1 and fixed by narrowing index wording; the feature/control worktree boundary also required explicit protection of pre-existing user changes. No residual findings remain.
- **Remaining gaps / next action:** official syllabus artifacts for 02324/13015/04735, 教材计划 metadata for 02333/00898, true-exam ingestion, and physical textbook/ISBN checks remain named gaps. Phase 4 opens one PR to `main`; merge remains subject to the standing manual confirmation policy.
