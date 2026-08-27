# Iteration Scope Notes (jiangsu-course-completion-xl-2026-08-25)

## Product outcome

For each of the five courses **02324 离散数学, 02333 软件工程, 00898 互联网软件应用与开发, 13015 计算机系统原理, 04735 数据库系统原理**, a reader can land on the course `index.md`, follow a start-here reader path across the six pages (考纲与范围 → 学习计划 → 练习与真题 → 来源核验, with review and sources as the remaining linked kinds) with complete symmetric cross-links, and — for 02333/00898 — scan a chapter-name index sourced from the official gaogang extraction, and — for 04735 — see where every delivered knowledge-tree block comes from. Evidence boundary stays: official-public-only claims, chapter names only (never gaogang body text), gaps stay named, lifecycle capped at `machine_ready`.

## Plan write-ownership (no dual ownership)

| plan_id | Exclusive write surface | Explicitly read-only |
|---------|------------------------|----------------------|
| 02324-reader-path | `content/jiangsu/courses/02324/**` (six pages) | everything else |
| 02333-official-syllabus-reader-path | `content/jiangsu/courses/02333/**` | everything else |
| 00898-official-syllabus-reader-path | `content/jiangsu/courses/00898/**` | everything else |
| 13015-reader-path | `content/jiangsu/courses/13015/**` | everything else |
| 04735-source-trace-reader-path | `content/jiangsu/courses/04735/**` | everything else |

Shared-surface rules:

- **Hub** (`content/jiangsu/courses/index.md`): no plan edits it. It already links all five courses; if a hub fix is discovered during Execute, it is reported to the PM as a named finding, not edited in-plan.
- **`sources/jiangsu/**` extraction artifacts**: read-only inputs for every plan; chapter names are quoted, never re-written into the artifacts.
- **`ops/jiangsu/**` (baseline, gap backlog, maturity)**: out of scope for all plans unless a gate failure forces regeneration — then via PM decision, not in-plan.
- **`scripts/` / schemas / `mkdocs.yml`**: no plan edits them.
- **Tests**: each plan may add course-code-scoped focused tests (e.g. `tests/test_02333_syllabus_index.py`) in its own commit; no shared test file edits.

## Plan dependency order

All five plans are mutually independent (disjoint directories). They run **serially** on one spec integration branch (`iteration/jiangsu-course-completion-xl`), one merge at a time, order: 02333 → 00898 → 02324 → 13015 → 04735 (official-syllabus plans first while context is fresh, 04735 last as the highest-risk read-only-surface plan).

## Measurable acceptance

- Every course page set (5 courses × 6 pages) has a complete symmetric cross-link bar (index ↔ syllabus ↔ plan ↔ review ↔ practice ↔ sources) — link-only, no evidence changes.
- Each course `index.md` has a start-here block with 4 ordered steps (考纲范围 → 学习计划 → 练习与真题 → 来源核验); orientation text only.
- 02333 `syllabus.md`: chapter-name index (3 篇 + 14 章 rows + 7 附录 names, verbatim from the gaogang-4068 artifact window including 第 14 章's verbatim non-assessment qualifier, machine-extraction caveat noted; any structurally-missing 章 row surfaced as a named gap, not guessed) + verified-metadata TOC source row pointing at the existing jseea.cn URL.
- 00898 `syllabus.md`: chapter-name index (第1–16章 flat; 第9、12–16章 carrying their verbatim `（…不作考核要求）` qualifiers) + verified-metadata TOC source row pointing at the existing jseea.cn URL.
- 02324 / 13015 `syllabus.md`: official-syllabus absence stays a visible named gap with reader consequence; no chapter list.
- 02324 / 13015 `plan.md`: executable sequence anchored to the verified textbook-plan metadata; no invented weeks→chapters mapping beyond a generic study cadence clearly labeled as suggested pacing, not exam scope.
- 04735: knowledge-tree chapters gain per-chapter source-trace rows (textbook outline / textbook-plan / `materials://` index as applicable); `sources.md` and `index.md` claims consistent; the 78/78 tree rows are otherwise untouched.
- No plan invents an official URL; the only URLs used are the two jseea.cn syllabus URLs already in `sources.md`/baseline.
- Lifecycle stays `machine_ready` at most; no `publishable`/`reviewed`/`reviewer` anywhere in the diff.
- Default `run-gates.py` (content, materials, contract, publish, maturity-check), focused/full pytest, `check-source-links.py --offline`, `mkdocs build --strict` pass on the integration branch after each plan merge and at close.

## Execution boundaries

- Phase 1 (this artifact set) is planning-only: no `content/**` edits, no commits, no branch creation. Phase 2 (PM dispatch) creates `iteration/jiangsu-course-completion-xl` and runs the five plans serially under SDD.
- Public pages may contain metadata, indexes, paraphrased orientation, and study plans; never textbook/past-paper originals, copied question text, private raw URLs, or unverified exam claims.
- Next-batch work (gap closure: official syllabus acquisition for 02324/13015/04735, 教材计划 hunting for 02333/00898, 真题 ingestion) is out of scope this iteration and stays tracked in `ops/jiangsu/issues/course-gap-issues.json`.
