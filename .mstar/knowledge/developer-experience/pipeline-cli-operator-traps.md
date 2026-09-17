---
module: jiangsu-ai-course-pipeline
date: 2026-09-14
problem_type: developer_experience
category: developer-experience
severity: medium
plan_id: ai-course-prep-pipeline-b3b-course-generation
applies_when:
  - "Driving the pipeline CLI to author, merge, record, replay or render a course batch"
  - "Running the repository's test suite on a machine where /tmp is a small tmpfs"
  - "Reading a mass-failure test result or a large machine-generated diff"
tags:
  - pipeline-cli
  - operator-traps
  - dry-run
  - fixture-churn
  - tmpfs
related_components:
  - build-course-content
  - llm_client
  - generate_content
  - pytest
---

# Pipeline operator traps: six ways the tooling makes an honest operator report a false result

## Context

B3b ran ~1,150 authored content items, three course merges and two review rounds through
`scripts/build-course-content.py` and `pytest`. Every mistake recorded here was made by the PM or a seat while
doing legitimate work, and each one produced a **plausible but wrong** result rather than an error. They are
collected because the failure mode is the same: the tooling's surface suggests one semantics and implements
another.

## Guidance

- **A chapter *subset* changes the `stage_plan` payload.** `generate --chapters <subset>` narrows the
  stage-plan payload's unit list, so the merge pass demands a stage-plan response that no authoring batch ever
  wrote. It fails closed (缺少 1 个回填结果 … stage_plan-7.result.json (a missing back-fill result)) — correct behaviour, confusing
  message. Rule: **batches are for authoring; the merge pass runs the full-course selector** (no
  `--chapters`), which resolves the already-recorded full-course payload.

- **`--record-fixtures` re-records every payload it sees, and re-record overwrites the same key.** Responses
  are keyed by payload hash, so re-running a course refreshes the `generator` metadata (`generated_at`) of
  entries that were already committed — 579 diff lines of pure date churn with byte-identical response bodies.
  Rule: after recording, compute `added` / `removed` / `changed_existing` over the fixture key space before
  believing a diff. Restoring the original `generator` blocks for response-identical keys makes the fixture
  diff purely additive, which is the property the plan's "additive-only" constraint actually means.

- **`--dry-run` does not mean "touches nothing".** Its help text says 只演练不落盘, and it does protect the
  final promotion into the per-course page directory under content/jiangsu/courses/ — but the `generate` and
  `evidence` stages still write the three per-course artefacts under sources/jiangsu/courses/
  (content.json, evidence.json, knowledge-model.json — see `sources/jiangsu/courses/02333/content.json`), and
  because `generate` re-stamps `generated_at`, those writes change committed files. A read-only review probe
  left 3 modified files (12 in the seat's run). Rule: verify a checkout-affecting command on a scratch
  **copy**, and treat `generated_at` as the tell that a "read-only" command wrote.

- **`generated_at` is re-stamped by every build, so "byte-identical" is only true modulo that field.**
  `replay` returns the *recorded* date while `generate` writes the *build* date. The repository's own guard
  normalises exactly that one field (its helper is commented as the replay-idempotency contract) — so a claim
  of byte-equality must name the normalisation, including in this project's own acceptance criteria. A raw
  byte comparison will fail for a reason that is not a defect.

- **A partial content.json makes whole-course gate layers red — that is expected, not breakage.** The
  `ai-content` layer validates a course as a whole, so mid-authoring states report hundreds of errors. The
  plan assigns the zero-error gate to the **final** task; reading an intermediate red as a regression wastes a
  round. Conversely, a red layer is the signal that the course is not finished.

- **On this machine, the full suite needs a base temp on the real disk.** /tmp is a 3.7 GB tmpfs and
  pytest's base temp holds a whole tree copy (~3.7 GB), so the default run fills it. The symptom is
  `OSError: [Errno 28] No space left on device` surfacing as **152 failed / 259 passed across unrelated
  files**; the same tree with --basetemp=/var/tmp/pytest-root gives **411 passed**. Rule: check
  df -h /tmp before believing any mass-failure result, and clean /tmp/pytest-of-root after a run.

- **A parser selector keyed on a display label is not keyed on the model's slug.** The authoring worklist
  matched bundles by bundle payload chapter index (the chapter.index field) — the *Chinese* label (`第1章`, `第10章`, `附录一`), not the model
  slug (`ch01`, `ap01`). Passing the slug returned an empty list and no error, which reads exactly like "this
  chapter is already complete". The tool now exits non-zero and prints the available keys; the general rule is
  to make an unmatched selector loud rather than empty.

## Why This Matters

Each trap costs a round at best and a corrupted artefact at worst: a wrong verification command can overwrite
the accumulated course file with a single chapter's worth of content, and a misread red/`--dry-run` result can
send a fix round after a defect that does not exist while the real one stays in the tree. They are also
invisible in review, because the operator's report reads as a normal result — which is why they belong in
durable knowledge rather than in a session summary.

## When to Apply

- Before replaying or merging a batch: confirm the selector is the **full-course** one, and that the block
  count did not **drop** (a shrinking count is the tell for the single-chapter overwrite).
- Before trusting a fixture diff: compare key-space sets, not the file.
- Before running a "read-only" pipeline command: say what it writes, and check `git status` after.
- Before believing a mass-failure suite or a `--dry-run` change: check the disk, the base temp, and the
  normalisation list.

## Examples

### Before

A verification run used `generate <code> --backend replay` (no `--merge`), which wrote a single-chapter
document over the accumulated 76-block artefact; the shrunken state was committed before anyone noticed. In
the same batch, a read-only seat's `--dry-run` probe modified 12 committed files, and a full suite reported
152 failures caused by a full tmpfs.

### After

The merge pass runs the full-course selector with `--merge`, and every replay asserts the block count did not
decrease and the artefact hash is unchanged. Fixture re-records are checked for `changed_existing == 0` before
commit. The suite runs with `--basetemp` on the real disk and /tmp/pytest-of-root is removed afterwards.
