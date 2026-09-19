---
module: jiangsu-ai-course-pipeline
date: 2026-09-19
problem_type: developer_experience
category: developer-experience
severity: medium
plan_id: ci-pr-gate-2026-09-19
applies_when:
  - "Writing harness state by hand because the host has no mstar CLI"
  - "A harness status surface reports an unreadable or invalid artifact"
  - "Copying a field value from one harness file into another file that happens to share the field name"
tags:
  - harness-state
  - snapshot-schema
  - enum-trap
  - engine-validator
  - hand-written-state
---

# Hand-written harness state must be validated against the engine's own schema

## Context

This host has no `mstar` CLI, so harness state (workflow snapshots, the root register, registers) is written by hand.
Registering a standalone plan, I wrote its snapshot by analogy with the neighbouring, known-good iteration snapshot and
introduced two defects at once:

1. `"schema": 3` instead of the required `"schema_version": 1`;
2. `"status": "active"` — a value copied from the **root register** entry, where `active` is legal, but which is **not
   in the workflow-snapshot status enum** at all.

The engine's response was a session-wide, every-turn error: `workflow.selection.snapshot-unreadable`. Note what that
message actually meant: the file existed and parsed as JSON; the *validation* failed inside the reader's `try`, and the
catch reports "unreadable". Fixing only the first defect did not help, because the second was independent.

The two enums, from the installed engine bundle:

- workflow snapshot: `status` ∈ `running | paused | completed | failed | stopped` — **no `active`**;
- the root register's `workflows[]` entries: `status: active` is the normal value.

## Guidance

- **Mirror the key set of a known-good artifact first, then check every enum.** Copying a *shape* is cheap and correct;
  copying a *value* across files because the key name matches is the trap. The same key (`status`) carries different
  domains in different files.
- **Diagnose by reading the engine's own validator, not by analogy.** When a message says "unreadable", distinguish
  *missing* from *invalid*: here the reader only reports "cannot read" when the file is absent, and "unreadable" when
  validation throws. Grep the installed bundle for the stable code you were given, read the surrounding function, and
  read the enum constants next to it. That is a two-minute detour that replaces guessing.
- **Know which fields are not snapshot fields.** `main_worktree_branch` looks plausible next to `integration_worktree_path`
  and appears in the conventions as a *plan-header* value — it is not a snapshot key at all (zero occurrences in the
  bundle). Reserved/unknown-key mistakes are silent in some validators and fatal in others.
- **Reserved discriminators:** the root file uses `version`; workflow snapshots use `schema_version` and it must be `1`.
  Mixing them is a stable, reported violation (`workflow.snapshot.missing-schema-version`).
- **Pre-flight cheaply before the next session sees it.** After writing state by hand, re-read it the way a consumer
  would: dump the key set, compare it with a known-good file, and confirm each enumerated field's value against the
  engine constants. If the host exposes a status line, check it right after the write — the error surfaces there
  immediately.

## Why This Matters

The failure mode is loud but opaque, and it is *shared*: the selection error replaced the whole workflow status surface
for every subsequent turn, so it looked like a global harness fault rather than a typo in one file. On a host without the
CLI, hand-written state is the only path — which makes "validate against the engine's schema" the sole guardrail. It
also compounds: a session that trusts a broken snapshot cannot read its own plan rows.

## When to Apply

- Whenever you create or edit a workflow snapshot, the root register, or a plan row by hand.
- When any harness surface reports an unreadable/invalid artifact: check absence vs validation before editing.
- Before copying a field value between two harness files that share a field name.

## Examples

### Before (rejected by the engine)

```json
{
  "schema": 3,
  "id": "ci-pr-gate-2026-09-19",
  "type": "plan",
  "status": "active",
  "main_worktree_branch": "main",
  "branch": {"base": "main", "source": "ci/pr-gate", "target": "main"},
  "plans": [{"id": "ci-pr-gate-2026-09-19", "status": "InProgress", "plan_path": ".mstar/plans/ci-pr-gate-2026-09-19.md"}]
}
```

Symptom: `workflow.selection.snapshot-unreadable` on every turn. Note that the plan row here also used a wrong key
(`plan_path`; the validator wants `file`, and `title` is mandatory).

### After (accepted)

```json
{
  "schema_version": 1,
  "id": "ci-pr-gate-2026-09-19",
  "type": "plan",
  "status": "running",
  "started_at": "2026-09-19",
  "updated_at": "2026-09-19",
  "delivery_kind": "development",
  "branch": {"base": "main", "source": "ci/pr-gate", "target": "main"},
  "plans": [{"id": "ci-pr-gate-2026-09-19", "title": "…", "status": "InProgress", "progress": 10,
             "updated_at": "2026-09-19", "file": ".mstar/plans/ci-pr-gate-2026-09-19.md", "metadata": {}}]
}
```

The status line recovered on the next turn (`workflow ci-pr-gate-2026-09-19 (plan) running`).
