---
module: jiangsu-ai-course-pipeline
date: 2026-09-18
problem_type: testing_pattern
category: testing-patterns
severity: medium
plan_id: ai-course-prep-pipeline-b4a-debt-and-guards
applies_when:
  - "A production guard decides behaviour from git state (tracked / untracked / ignored)"
  - "Writing or fixing fixture roots that simulate a course, a package, or any tracked artefact"
  - "A new guard turns a large block of pre-existing assertions red on a clean checkout"
tags:
  - git-scoped-guards
  - copytree-fixtures
  - fixture-realism
  - no-loosening
  - fail-closed-scope
---

# Git-scoped guards read `copytree` fixtures as brand new — fix the fixture, not the assertion

## Context

B4a's answer-distribution guard decides its behaviour from the git tracking state of each course's content.json file:
**untracked ⇒ new course ⇒ fail closed**, tracked ⇒ existing course ⇒ report only. That is the right signal for
production (a freshly generated product is untracked at generation time) and it is deliberately **not** a hardcoded
course list.

The moment the guard landed, **15 pre-existing assertions** went red. The cause was not the guard:

- the ai-content tests build a fake repository root by copying the sources tree (shutil.copytree) into a temp directory;
- a copied tree is, by definition, **not under version control** — so every fixture root read as "a brand new course";
- those fixtures simulate **existing** courses, including two that legitimately exceed the bias threshold
  (`15040` A 105/194 = 54.1 %, `15043` A 129/173 = 74.6 %), so the guard did exactly what it promises and blocked them.

The tempting fix — filter the distribution error out of those assertions — would have been a **loosening**: it would let
the entire "the guard misfires on existing courses" regression class through. The fix that was applied instead gives each
fixture root a real git index: `git init -q` plus `git add -f` of that course's content.json path, nothing else (no commit,
no user-level git config), so the guard reads the fixture exactly as it reads production.

## Guidance

- **When a guard's scope comes from the environment, the fixture must model that environment.** Ask: what does the
  production path look like from the guard's point of view, and does my fixture reproduce it? A copied tree reproduces
  files, not repository state.
- **Give the fixture the missing state, minimally.** Here: initialise a git index inside the fixture root and add exactly
  the paths the signal reads. No commit is needed for "tracked" semantics, and no global config should be touched.
- **Never loosen the assertion to absorb a guard that is working as designed.** The correct failure of a correct guard is
  a signal that the *fixture* is wrong. Loosening also removes the only test coverage for the misfire class.
- **Keep a fixture that deliberately stays untracked.** The new distribution tests keep untracked roots on purpose, so the
  fail-closed direction (new course ⇒ error) is pinned alongside the report-only direction — both directions must have a
  fixture.
- **Re-check the direction of the signal before "fixing" the fixture.** The guard's three states matter: tracked ⇒
  report; untracked ⇒ enforce; **undetermined ⇒ enforce and say so** (fail closed). A fixture that accidentally lands in
  the third state tests the wrong branch.

## Why This Matters

Any guard in this repository that scopes itself by git state (and the pipeline now has at least two: the distribution
guard's course scope, and the evidence gate's page/document sources) will collide with `copytree`-style fixtures. The
collision looks like a guard defect — 15 red assertions on a clean checkout is a dramatic signal — so the default
reaction is to relax the guard or the assertions. Both are wrong: the environment the guard is judging is the test's
responsibility, and the fail-closed direction is the property worth protecting.

## When to Apply

- When adding a guard whose behaviour depends on tracked/ignored/absent state.
- When a guard change reddens a block of fixture-based assertions at once — suspect the fixtures before the guard.
- When writing new fixtures for such a guard: decide explicitly whether the fixture should be tracked, untracked, or in
  the undetermined state, and say which branch it is meant to exercise.

## Examples

### Before

`copytree` fixture root + a distribution guard reading git tracking ⇒ the fixture reads as a new course ⇒ the guard fails
closed on `15040`/`15043` ⇒ **15 pre-existing assertions red** on a clean checkout, with the guard behaving correctly.

### After

`_tracked(fake_root)`: `git init -q` + `git add -f --` the course content.json paths inside the fixture root, returning
it. The pre-existing test file gained **56 inserted lines and 0 deleted lines** — no assertion was edited — and the new
distribution tests keep their own untracked roots so both directions stay covered. The PM review that approved this
concluded it was an "honest fixture-realism fix, not masking", having reproduced the mechanism and confirmed the guard
still fires on the real new-course path.
