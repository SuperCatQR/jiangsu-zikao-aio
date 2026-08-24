---
module: page-maturity-gates
date: 2026-08-24
problem_type: tooling_decision
category: tooling-decisions
severity: medium
plan_id: public-maturity-projection-drift-check
applies_when:
  - "Changing page-maturity calculation or public gap tables"
  - "Adding layers to scripts/run-gates.py"
tags:
  - grade
  - maturity-check
  - run-gates
  - projection
---

# Public maturity projection check

## Context

Operational maturity reports and the public page-maturity table must show the same `grade()` rows. A mutating default gate would rewrite ops files on every CI run. Calling a nested `main()` with the parent process argv made the optional maturity layer abort on argparse when `--layers` was present.

## Guidance

- `grade()` in `scripts/compute-page-maturity.py` is the only maturity calculator. Public Markdown is a projection of those rows (lifecycle, completeness, 成熟度, 原因, 公开下一步).
- Default CI layer is `maturity-check` → non-mutating `check_public_projection`. Optional `maturity` still writes ops JSON/MD and is **not** on `DEFAULT_LAYERS`.
- Nested CLIs invoked in-process must receive an explicit argv (`main([])`), never inherit `--layers`.
- Do not add a second algorithm. Do not put `status` or `unknown` cells on the public table. Filter private path markers from reasons.

## Why This Matters

Drift between ops and public views ships stale schema. A mutating default layer dirties the worktree. Parent argv leaks fail closed as a process crash instead of a gate error list.

## When to Apply

- Editing `scripts/compute-page-maturity.py`, `scripts/run-gates.py`, or `content/jiangsu/gaps/page-maturity.md`.
- Wiring a new default gate that imports another argparse script.

## Examples

### Before

`runners["maturity"] = run_maturity` on the default path; `mod.main()` parsed `--layers`.

### After

`DEFAULT_LAYERS` ends with `maturity-check`; `run_maturity` calls `mod.main([])`; tests lock `* maturity-check` and reject `* maturity`.
