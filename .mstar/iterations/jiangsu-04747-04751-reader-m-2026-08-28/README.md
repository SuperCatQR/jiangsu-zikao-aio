# jiangsu-04747-04751-reader-m-2026-08-28 Package

This iteration package records the autonomous direction lock and iteration-local scope. The long-term contract remains `.mstar/specs/public-source-content-loop.md` (locked); reusable implementation guidance is promoted only at iteration-close.

| Document | Kind | Purpose |
|----------|------|---------|
| [delivery-compass.md](delivery-compass.md) | compass | Locked direction, two-plan M budget, acceptance, branch policy, and close gates |
| [guides/direction-lock.md](guides/direction-lock.md) | guide | Candidate evidence and trade-offs for 04747/04751 selection |
| [specs/iteration-scope.md](specs/iteration-scope.md) | iteration spec | Product outcome, plan ownership, evidence boundary, and verification contract |

## Plans

| plan_id | Plan file | Scope |
|---------|-----------|-------|
| `04747-official-syllabus-reader-path` | [`.mstar/plans/04747-official-syllabus-reader-path.md`](../../plans/04747-official-syllabus-reader-path.md) | 04747 official-syllabus chapter index and reader path |
| `04751-official-syllabus-reader-path` | [`.mstar/plans/04751-official-syllabus-reader-path.md`](../../plans/04751-official-syllabus-reader-path.md) | 04751 official-syllabus chapter index and reader path |

## Artifact boundary

- `content/jiangsu/courses/04747/**` and `content/jiangsu/courses/04751/**` (plus focused tests `tests/test_04747_reader_path.py` / `tests/test_04751_reader_path.py` if needed) are the exclusive product write surfaces for the two business plans inside their respective feature worktrees.
- `sources/jiangsu/processed/**`, `ops/jiangsu/**`, scripts, schemas, and the course hub are read-only for these plans.
- Control worktree `/root/workspace/jiangsu-zikao-aio` hosts all harness process artifacts (`.mstar/plans/`, `.mstar/sdd/<plan-id>/`, review bundles `.mstar/sdd/<plan-id>/review/`, workflow snapshots `.mstar/workflows/`). Harness process artifacts must never be placed inside feature worktrees.
- PM creates `execution_lease` and integration merge leases prior to writable dispatch. Plans execute and merge serially.
- `.mstar/sdd/<plan-id>/` remains ephemeral runtime evidence; durable gate summaries belong in the main plans and workflow snapshot.
