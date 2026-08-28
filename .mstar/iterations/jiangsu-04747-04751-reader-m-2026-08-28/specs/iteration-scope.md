# Iteration Scope — 04747 + 04751 Official-Syllabus Reader Paths

## Product outcome

A learner landing on either selected course can identify the official syllabus boundary, scan a bounded chapter-name index, follow an executable study sequence, and reach practice/source pages without dead or asymmetric navigation. Missing official applicability, textbook, true-paper, ISBN, physical-book, and human-review evidence remains explicit rather than being filled with inference.

## Target state and explicit non-goals

**Target state:** each selected course has a names-only, source-bounded 13-row chapter index; a chapter-keyed study sequence distinguishing assessed and reference-only chapters; a four-step start-here path; symmetric links across all six existing pages; and machine-checkable consistency evidence. Lifecycle remains at or below the current machine-safe state.

**Explicit non-goals:** no 13017/13000/13003/13180 work; no syllabus body prose, code, screenshots, question text, exam-period or applicability inference; no textbook, ISBN, physical-book, true-paper, reviewer, `reviewed`, or `publishable` claim; no edits outside the two course write surfaces and permitted focused tests. During Execute, the user explicitly authorized one minimal baseline-contract repair in `tests/test_site_integration.py` for stale assertions against already-current hub wording; the hub remains read-only.

## Deferred roadmap / ownership / trigger

| Deferred slice | Owner | Trigger | Completion definition |
|---|---|---|---|
| 13017 paired-choice reader path | content maintainer + project manager | official syllabus extraction and applicability boundary confirmed | source-bounded reader path and choice relationship are specified and accepted without inference |
| 13000 coverage | content maintainer + project manager | official source record or explicitly triaged public gap | evidence boundary and reader scope are documented before any plan is created |
| 13003/13180 discovery | content maintainer | equivalent official extraction evidence exists | candidate is re-evaluated against a new iteration budget; not absorbed here |

Deferred slices must not become process-only plans or silently expand the two-plan M budget.

## Plan write ownership

| plan_id | Exclusive product write surface | Explicitly read-only |
|---|---|---|
| `04747-official-syllabus-reader-path` | `content/jiangsu/courses/04747/**` plus `tests/test_04747_reader_path.py` if needed | other course pages, `sources/jiangsu/processed/**`, `ops/`, scripts, schemas, hub |
| `04751-official-syllabus-reader-path` | `content/jiangsu/courses/04751/**` plus `tests/test_04751_reader_path.py` if needed | other course pages, `sources/jiangsu/processed/**`, `ops/`, scripts, schemas, hub |

### Execute scope amendment — baseline contract

- User authorization recorded during Execute permits the 04747 plan to update only the stale expected strings in `tests/test_site_integration.py` that no longer match the already-current `content/jiangsu/courses/index.md` headings.
- The permitted file is limited to the two affected test functions and their four stale literals: the shared test remains a read-only product/hub observer; no hub, other shared tests, scripts, or source artifacts may change.
- This is a prerequisite test-contract repair for the existing integration baseline, not a third business plan or a change to the selected reader-path outcome.

- **Control worktree & harness process paths**: All harness artifacts (plans `.mstar/plans/`, SDD directories `.mstar/sdd/`, review bundles `.mstar/sdd/<plan-id>/review/`, workflow snapshots `.mstar/workflows/`) reside strictly on the control filesystem at `/root/workspace/jiangsu-zikao-aio` and are accessed via absolute paths. Harness process artifacts must never be placed into or committed from feature worktrees.
- **Feature worktree isolation**: Each plan is executed in its dedicated feature worktree created by PM with an explicit `execution_lease` before writable dispatch.
- **Serial execution & merge order**: Plans execute and merge serially into the integration branch `iteration/jiangsu-04747-04751-reader-m-2026-08-28`. PM grants the integration merge lease to `04747` first; only after `04747` is fully implemented, verified through QC tri-review + QA gate, and merged does `04751` merge. Neither plan owns the course hub or the shared gap backlog.

## Evidence boundary

- 04747 official syllabus URL: `https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285133106820943872.html`, already recorded in `content/jiangsu/courses/04747/sources.md` and the baseline. Chapter-name input: `sources/jiangsu/processed/syllabus/04747-java-programming-1-gaogang-4067/document.extracted.md` (`高纲 4067`).
- 04751 official syllabus records: the existing jseea.cn HTML and PDF URLs in `content/jiangsu/courses/04751/sources.md` and the baseline. Chapter-name input: `sources/jiangsu/processed/syllabus/04751-computer-network-security-gaogang-4389/document.extracted.md` (`高纲 4389`).
- Local extraction artifacts are machine-draft inputs and remain read-only. Public pages may publish names and qualifiers, not body text, copied code, screenshots, or question text.

## Measurable acceptance

1. 04747 publishes exactly 13 chapter-name rows from the `Ⅲ 课程内容与考核要求` window: 9 assessed (1–6, 8–10) and 4 non-assessed (7, 11, 12, 13) retaining the artifact's verbatim `（本章内容不作考核要求）` qualifier.
2. 04751 publishes exactly 13 chapter-name rows from the same window: 10 assessed (1–10) and 3 non-assessed (11, 12, 13) retaining the artifact's verbatim `（本章内容不作考核要求）` qualifier.
3. Each plan sequence is keyed to its syllabus index and excludes non-assessed chapters from assessed-study claims while retaining a reference-only treatment.
4. Each course's six pages have the same complete cross-link set and an index start-here block with four ordered steps.
5. Existing source URLs are reused verbatim; applicability and remaining material gaps are named; lifecycle remains no higher than the current machine-safe state.
6. Focused tests, repository gates, offline source-link check, strict MkDocs, and whitespace diff checks pass after each plan merge and at close.

## Verification contract

- Focused checks parse the rendered Markdown structure and assert chapter count/order, qualifier preservation, cross-link symmetry, and absence of stale official-syllabus empty-state text.
- Run: `python3 scripts/run-gates.py` → all configured layers pass (exit 0).
- Run: `/root/.local/bin/uv run --with pytest pytest -q` → full suite passes, including both new course-scoped checks (exit 0).
- Run: `python3 scripts/check-source-links.py --offline` → exit 0.
- Run: `mkdocs build --strict` → exit 0.
- Run: `git diff --check` → no output / exit 0.
