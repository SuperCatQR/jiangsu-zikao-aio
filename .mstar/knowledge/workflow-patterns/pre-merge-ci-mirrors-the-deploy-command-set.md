---
module: jiangsu-ai-course-pipeline
date: 2026-09-19
problem_type: workflow_issue
category: workflow-patterns
severity: high
plan_id: ci-pr-gate-2026-09-19
applies_when:
  - "A plan defers a verification leg to \"CI\""
  - "Adding or changing a pull-request gate"
  - "A gate is declared configured but has never been observed blocking anything"
tags:
  - pre-merge-ci
  - deploy-parity
  - branch-protection
  - defer-to-ci
  - attributable-red
---

# A pre-merge gate must mirror the post-merge deploy — and be proven to block

## Context

For seven pull requests this repository had **no PR-triggered CI at all**. The only workflow that ran the verification
command set (.github/workflows/deploy-pages.yml) was triggered by `push: main` — i.e. **after** the merge; the second
(`.github/workflows/source-link-monitor.yml`) ran on a schedule. So a plan instruction of the form "run the full suite
in CI" silently meant "run it on `main` once the change is already in".

That is not a theoretical gap. On the previous iteration's PR the **first** full-suite result came from a
locally-authorised run, and it found **three red tests** (`tests/test_render_pages.py`, a fixture that did not reproduce
repository state). Had it merged, the red set would have landed on `main` and broken the Pages deploy — and the
deploy workflow, being the only full run, would have been the thing that discovered it.

The fix delivered one 33-line file that mirrors the deploy build job and runs on `pull_request`, plus branch protection
requiring that check.

## Guidance

- **Parity is the deliverable, not speed.** A pre-merge check is worth having only if *a red PR predicts a red main*.
  So copy the post-merge command set **command for command** — same Python version, same flags, same order — and cut the
  workflow at the point where it stops verifying and starts deploying (here: everything before
  `configure-pages@v5`). Locate that cut point programmatically; do not hand-pick steps.
- **Check the trigger before trusting the phrase "in CI".** When a plan, review or residual says a leg is "deferred to
  CI", verify *which event* runs it. `pull_request` is a pre-merge gate; `push` on the default branch is a
  post-merge alarm. This is the same class as any other unmeasured plan premise — one `gh run list` or a look at the
  `on:` block settles it.
- **A gate has three states, and each needs its own proof.** (1) *Authored* — the YAML parses; (2) *runs* — GitHub
  accepts the file and a run appears for the head; (3) *blocks* — a red run actually prevents the merge. A parse-clean
  file proves nothing about (2), and a read-back of the protection settings proves nothing about (3).
- **Make the red attributable and quantitative.** The control commit adds exactly one deliberate failing test, so the
  log shows `1 failed, 459 passed` on the red head while the clean head shows `459 passed` — the same tests, plus the
  injected failure whose node id is visible in the log. An unrelated red is a delivery finding, not a proof.
- **Keep a same-tree baseline.** Sequence the runs so the clean head is measured *before* the control and again after
  the revert. If a run is already in flight on the clean head, **wait it out rather than cancelling it**: the extra wall
  clock buys a baseline measured on the identical tree seconds before the control run.
- **Restore with a lease, never a bare force.** After the control commit, reset to the original commit and push with
  `--force-with-lease=<branch>:<observed-oid>` after recording the remote OID; then verify `git rev-parse HEAD`,
  `git ls-remote origin <branch>` and the PR head all agree, and that the working tree diff against the original commit
  is empty. The control commit survives as a dangling object in the run history — useful evidence, not a live head.
- **Protection needs its own fire proof, with a real merge attempt.** Configure the required check by the name GitHub
  actually reports for the job (read it from the check-runs API, not from the workflow's `name:`), then open a
  deliberately red throwaway PR, record `mergeStateStatus: BLOCKED` (note: `mergeable: MERGEABLE` is about content
  conflicts — the two fields answer different questions), and attempt **one** merge. A refusal such as
  *"the base branch policy prohibits the merge"*, from the repository owner under `enforce_admins`, is the evidence.
  Never use `--admin` to "check" — that fires the real merge.
- **Say which bypasses you deliberately did not exercise.** The `--admin` path was left configuration-verified because
  exercising it risked merging the red control into the default branch. An unexercised path that is honestly declared
  is a known limit; one that is silently assumed to be covered is a future incident.
- **Clean up the experiment.** Close the throwaway PR, delete its branch and worktree, and prove the default branch and
  the real feature branch did not move (`git ls-remote` before/after). An experiment that leaves refs behind teaches the
  next session the wrong history.

## Why This Matters

The whole point of a pre-merge gate is to move discovery earlier than the deploy. If it does not mirror the deploy, it
moves nothing: it can be green while the deploy is red, which is worse than no gate at all because it manufactures
confidence. And an unproven gate is indistinguishable from a broken one — this repository has already shipped guards
that could not fire (`.mstar/knowledge/test-failures/dead-guards-need-a-fire-proof.md`); a CI gate is the same object one level up, with
the extra twist that its "configuration" lives outside the repository, where no diff review can see it.

## When to Apply

- Whenever a verification leg is deferred to "CI" — check the trigger's event first.
- When adding or editing a pull-request workflow: mirror the post-merge command set, and prove all three states.
- When enabling branch protection: name the check from the check-runs API, prove it blocks with a red PR, and record
  which bypasses remain unexercised.
- When a gate's evidence is a settings read-back rather than an observed refusal.

## Examples

### Before

`.github/workflows/deploy-pages.yml` (`on: push: [main]`) was the only workflow running `scripts/run-gates.py`, `pytest -q`, `ruff`,
`check-source-links.py --offline` and `mkdocs build --strict`. PR #6's first full-suite result came from a local run and
found 3 red tests; `gh pr view 6 --json statusCheckRollup` returned **0 checks**; `main` had no branch protection.

### After

| Run | Head | Conclusion | Note |
|---|---|---|---|
| 35438716058 | `15fe0a3` (clean) | **success** | 12/12 steps, 459 passed in 1063.95s — same-tree baseline |
| 35439569741 | `712add1` (red control) | **failure** | failing step `Run tests`, `1 failed, 459 passed` — only the injected test |
| 35440278550 | `15fe0a3` (restored) | **success** | 459 passed in 1074.44s |

Branch protection requires check `verify` with `enforce_admins` on; a throwaway red PR showed
`mergeStateStatus: BLOCKED` and its merge attempt was refused with *"the base branch policy prohibits the merge"*, from
the owner's own account, leaving `mergedAt: null`. The unprotected status quo — PR merged green by luck of a manual run —
is now a machine-enforced precondition.
