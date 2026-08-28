---
iteration_id: jiangsu-04747-04751-reader-m-2026-08-28
start_date: 2026-08-28
status: locked
locked_at: 2026-08-28
effort_budget: M
iteration_base_branch: main
spec_integration_branch: iteration/jiangsu-04747-04751-reader-m-2026-08-28
target_branch: main
plans:
  - 04747-official-syllabus-reader-path
  - 04751-official-syllabus-reader-path
---

# jiangsu-04747-04751-reader-m-2026-08-28 Delivery Compass

## Direction Lock (autonomous)

**Locked direction:** use the already-recorded official syllabus evidence to move `04747 Java 语言程序设计（一）` and `04751 计算机网络安全` from migration skeletons to truthful, navigable reader paths: chapter-name indexes, executable study sequences, complete six-page navigation, and visible evidence gaps. The public-source contract remains locked; no private material or human-review claim is introduced.

**Direction input:** none supplied; the loop default is code-first research with autonomous lock.

### Candidate exploration and trade-offs

| Candidate | Evidence | Trade-off | Decision |
|---|---|---|---|
| **04747 + 04751 official-syllabus reader paths** | `content/jiangsu/courses/04747/sources.md:13` and `04751/sources.md:13` already record authoritative jseea.cn syllabus URLs; local gaogang extraction artifacts exist at `sources/jiangsu/processed/syllabus/04747-java-programming-1-gaogang-4067/document.extracted.md` and `04751-computer-network-security-gaogang-4389/document.extracted.md`; both course sets are still generic migration pages | Machine-extraction caveat and 04747 code-sample risk require names-only indexes and no new generated claims; two plans fit M | **Selected** |
| 13017 paired-choice reader path | `content/jiangsu/courses/13017/sources.md:12-13` has textbook metadata and an official source URL, but no local syllabus extraction; the page must also explain the 2026-10 choice with 04751 | Useful follow-on, but chapter index cannot be published from current evidence and the paired-choice product decision is not yet resolved | Deferred |
| 13000 gap-first coverage | `content/jiangsu/courses/13000/sources.md:12-13` records both textbook-plan and syllabus as missing-source | The roadmap recommends it only after a verified official source or a triaged public gap; current evidence cannot support a richer reader path | Deferred |
| 13003 / 13180 broader technical-course batch | Existing pages and gap rows exist, but this survey found no local official syllabus extraction comparable to 04747/04751 | A larger batch would spend M budget on discovery rather than a shippable reader outcome | Deferred |

**Why the selected candidate wins:** it has the highest evidence readiness and the smallest product gap. Both selected courses already have official URL records and local extraction inputs, while their public `syllabus.md` pages still say the official syllabus is missing (`04747/syllabus.md:11`, `04751/syllabus.md:11`) and their `plan.md` pages remain generic 30-day stubs. The selected slice reuses the proven 02333/00898 reader-path shape without widening the evidence contract.

## Review-chain branch note

Phase 1 review and edit work is performed directly on `iteration/jiangsu-course-completion-xl` per the Assignment branch policy as planning-only artifact polish; no product worktree, merge, or commit is performed in this chain. In Phase 2, the project manager will create the recorded integration branch `iteration/jiangsu-04747-04751-reader-m-2026-08-28` from the explicit `main` base anchor, establish control/feature worktrees with execution leases, and execute plans serially.

## Scope

- Publish chapter **names only** from the existing 04747 gaogang-4067 and 04751 gaogang-4389 extraction windows; preserve each chapter-level `（本章内容不作考核要求）` qualifier exactly as found in the extraction artifacts.
- Replace both stale syllabus empty states with bounded chapter indexes and verified-metadata source rows that point to the URLs already present in each course `sources.md` and the baseline.
- Replace both generic plan stubs with executable, evidence-bounded study sequences; suggested pacing is guidance, never an official exam-period claim.
- Add four-step start-here blocks, complete symmetric cross-link bars, and status/gap alignment across each course's six existing pages.
- Keep current textbook-plan, true-paper, ISBN/physical-book, applicability, and human-review gaps visible unless this iteration has direct evidence to close them.

## Plans

| plan_id | Name | Status | Notes |
|---------|------|--------|-------|
| `04747-official-syllabus-reader-path` | 04747 Java official-syllabus chapter index and reader path | InProgress | P1/M; resumed by explicit user instruction; Task 4 four-literal baseline test repair pending delegated execution |
| `04751-official-syllabus-reader-path` | 04751 network-security official-syllabus chapter index and reader path | Todo | P1/M; local gaogang-4389 extraction; 13 chapters, 10 assessed (1–10), 3 non-assessed (11–13) |

Status values: `Todo` | `InProgress` | `InReview` | `Done` | `Blocked`

## Milestones

| Milestone | Target date | Status |
|-----------|-------------|--------|
| Autonomous direction lock and Prepare freeze | 2026-08-28 | completed |
| Spec / plans locked | 2026-08-28 | completed |
| 04747 and 04751 implementation, QC, QA | 2026-08-28 | pending |
| Iteration close | 2026-08-28 | pending |

## Acceptance Criteria

- `content/jiangsu/courses/04747/syllabus.md` contains the 13 chapter-name rows from the gaogang-4067 `Ⅲ` window; chapters 7, 11, 12, and 13 retain their verbatim non-assessment qualifiers (`（本章内容不作考核要求）`), and no gaogang body prose or code sample is copied into the public page.
- `content/jiangsu/courses/04751/syllabus.md` contains the 13 chapter-name rows from the gaogang-4389 `Ⅲ` window; chapters 11, 12, and 13 retain their verbatim non-assessment qualifiers (`（本章内容不作考核要求）`), and no gaogang body prose is copied into the public page.
- Each selected course has an executable plan keyed to its published chapter index, a four-step start-here block, and a complete symmetric cross-link bar across `index.md`, `syllabus.md`, `plan.md`, `review.md`, `practice.md`, and `sources.md`.
- Official URLs are limited to the pre-existing records in the two course `sources.md` files and `ops/jiangsu/source-links.baseline.json`; no URL is invented or refreshed in this iteration.
- Named gaps remain honest: no automatic `reviewed`, `publishable`, `reviewer`, ISBN, physical-book, true-paper, or applicability claim is added; lifecycle remains no higher than the current machine-safe state.
- Course-scoped consistency tests plus `python3 scripts/run-gates.py`, `/root/.local/bin/uv run --with pytest pytest -q`, `python3 scripts/check-source-links.py --offline`, `mkdocs build --strict`, and `git diff --check` pass on the integration branch.

## Non-Goals

- `13017` paired-choice content, `13000`, `13003`, `13180`, or any course not listed in the Plans table.
- Acquiring or inferring official evidence, exam periods, ISBNs, physical textbooks, true-paper originals, answer text, or private `materials://` contents.
- Copying syllabus body text, PDF screenshots, code examples, or copyrighted question text into `content/`.
- Changing the locked long-term spec, hub ownership, scripts, schemas, source extraction artifacts, or the shared gap backlog in this business slice.
- Any automated lifecycle transition to `reviewed` or `publishable`; Phase 1 review/edit and Phase 2 QC/QA remain required process gates outside the business-plan count.

## Roadmap Position

- **Current iteration (planned)**: deliver the evidence-backed 04747 and 04751 reader paths described above; status becomes `delivered` only after Phase 3 close.
- **Next iteration**: resolve the 13017 paired-choice reader path after its official syllabus extraction / applicability boundary is confirmed, or take 13000 only after a verified official source record or an explicitly triaged public gap; owner: content maintainer and project manager; trigger: the stated evidence boundary is confirmed.
- **Overflow / deferred**: 13003 and 13180 remain discovery candidates until equivalent official source evidence is available; owner: content maintainer; trigger: equivalent official extraction evidence exists; they are not silently absorbed into this M budget.
- **Final target**: every included Jiangsu course has an auditable public-source record, useful reader content, truthful lifecycle/completeness state, and a human-controlled publish gate.

## Delivery Branch Policy

> Mirror of frontmatter; keep in sync with workflow snapshot `.mstar/workflows/jiangsu-04747-04751-reader-m-2026-08-28/snapshot.json` branch anchors.

| Field | Value |
|-------|-------|
| `iteration_base_branch` | `main` (resolved from the prior iteration snapshot/compass; local ref will be fast-forwarded to `origin/main` before branch creation) |
| `spec_integration_branch` | `iteration/jiangsu-04747-04751-reader-m-2026-08-28` |
| `target_branch` | `main` |

### Harness and Isolation Architecture

- **Control worktree & process paths**: PM provisions the control worktree and process paths (`.mstar/plans/...`, `.mstar/sdd/...`, `.mstar/workflows/...`) on the control filesystem (`/root/workspace/jiangsu-zikao-aio`) before writable dispatch. Harness process artifacts must never be placed inside feature worktrees.
- **Feature worktrees & execution leases**: PM creates dedicated feature worktrees with explicit `Worktree path`, `Working branch`, and verified `execution_lease` before dispatching writable tasks (Task 2 onwards). Product edits remain isolated within each plan's feature worktree.
- **Integration merge lease & serial flow**: Top-level integration merge lease is claimed for serial merges into `iteration/jiangsu-04747-04751-reader-m-2026-08-28`. 04747 completes implementation, mandatory QC tri-review, QA verification, and merge before 04751 starts its merge.
- **QC tri-review & QA gate**: Every plan requires mandatory tri-review (`qc1.md`, `qc2.md`, `qc3.md` + `qc-consolidated.md`) and mandatory QA alignment on the exact same `Review cwd`, `Working branch`, `plan_id`, and `Review range / Diff basis`.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Machine extraction has OCR/spacing defects | Medium | Medium | Re-enumerate only the `Ⅲ` chapter headings, preserve names/qualifiers, and surface disagreement as a named gap rather than guessing |
| 04747 contains runnable code in its existing draft | High | Medium | Publish chapter names and generic study actions only; do not expand or validate code examples in this slice |
| Official applicability period is not stated | High | Medium | Keep applicability/version as a named gap and do not infer an exam window from URL dates |
| Generic page edits break symmetric links | Medium | Low | Add course-scoped tests and run strict link/content gates after each plan merge |

## Iteration package

| Path | Purpose |
|------|---------|
| [`guides/direction-lock.md`](guides/direction-lock.md) | Code-first candidate evidence, ranking, and autonomous lock rationale |
| [`specs/iteration-scope.md`](specs/iteration-scope.md) | Iteration-level product outcome, write ownership, and measurable boundaries |
| [`README.md`](README.md) | Package index and plan handoff |

> This package is iteration-local; compound may promote reusable guidance only at Phase 3 close.

## Quality Gate Summary

> Filled at iteration-close; raw reports remain under each plan's `.mstar/sdd/<plan-id>/review/` bundle.

| plan_id | QC decision | QA gate | Residuals | Durable summary |
|---------|-------------|---------|-----------|-----------------|
| `04747-official-syllabus-reader-path` | pending | mandatory | none pending | [`.mstar/plans/04747-official-syllabus-reader-path.md#review-gate-summary`](../../plans/04747-official-syllabus-reader-path.md#review-gate-summary) |
| `04751-official-syllabus-reader-path` | pending | mandatory | none pending | [`.mstar/plans/04751-official-syllabus-reader-path.md#review-gate-summary`](../../plans/04751-official-syllabus-reader-path.md#review-gate-summary) |

## Compound Round Summary

> Filled at iteration-close.

- 结晶文档数：pending
- 新增 `CONCEPTS.md` 条目：pending
- 触发 compound-refresh：pending
- package 盘点：pending（默认排除本 compass；逐篇 guides/specs/README triage）

## Iteration Retrospective (minimal)

> Filled at iteration-close.

- 做得好的：pending
- 可改进的：pending
- 下迭代建议：pending
