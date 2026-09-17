---
module: jiangsu-ai-course-pipeline
date: 2026-09-14
problem_type: test_failure
category: test-failures
severity: high
symptoms:
  - "Every gate layer passes and the suite is green while the defect the new guard targets is still present"
  - "A guard predicate exists in the source but nothing calls it (each name occurs once, on its own def line)"
  - "A test asserts a tautology, so it passes for every possible value of the guard it claims to cover"
  - "A residual is closed on an agent's self-report and the test body is later found byte-identical to the pre-fix commit"
root_cause: "A guard has two independent failure modes — a wrong condition (its body) and no execution (its call site). Happy-path tests exercise neither when the subject is absent, and a green suite cannot distinguish 'checked and approved' from 'never ran'."
resolution_type: test_fix
plan_id: ai-course-prep-pipeline-b3b-course-generation
applies_when:
  - "A fix or a review round adds a guard, predicate, or invariant test"
  - "Closing a finding on the strength of a green suite"
  - "Reviewing a diff that adds a check which is not obviously reached"
tags:
  - dead-guard
  - falsifiability
  - mutation-check
  - green-suite-blindness
  - review-discipline
related_components:
  - ai_content_gate
  - knowledge_model
  - render_pages
---

# A guard that never runs: four shapes, and the cheap proof that kills them

## Problem

Review rounds kept approving guards that could not fail — either because nothing called them, or because
their condition could never be true — and a green suite reported the same colour in both cases.

## Symptoms

- A suite is green, every gate layer passes, and the defect the new guard was written to catch is still
  present. Nothing in the output distinguishes "the guard checked and approved" from "the guard never ran".
- Concretely, in one branch: four predicates (`_banner_violations`, `_textbook_claim_offenders`,
  `_absolute_no_ai_offenders`, `_missing_chapter_offenders`) were **defined and never called** — each name
  appeared exactly once in the repository, on its own `def` line. Three reviewed findings therefore had no
  executable enforcement at all while the suite stayed green.
- In the same iteration, another test asserted `x in y + x` — a tautology that passes for every possible
  value of the guard and proves nothing about it.

## What Didn't Work

- **Reading the test names.** The suite contained tests whose *names* described the exact rule that was not
  enforced. Name-level review is what let the first wave of review approve them.
- **Trusting the fixer's self-report.** A residual was closed on the strength of "the agent says it is
  fixed"; the re-review showed the test body was byte-identical to the pre-fix commit. The closure had to be
  retracted and re-closed on code evidence.
- **Adding predicates without call sites.** The predicates were correct and non-tautological when executed by
  hand — they were simply unwired. Correctness of a guard's body says nothing about whether anything calls it.

## Solution

Prove, for each guard, that **neutralising the subject makes it fire** — and prefer a proof that survives the
guard being deleted:

1. **AST / grep call-node check.** Walk the module's AST for `Call` nodes and confirm each predicate name has
   at least one call site outside its own `def`. A name with one occurrence is dead. (This is how the four
   dead predicates were found, after grep alone was ambiguous.)
2. **Positive control per predicate.** A test that neutralises one predicate's subject and asserts *that
   predicate's own test* fails. Without it, a suite cannot tell a weakened predicate from a working one — one
   round had 16 tests passing blind until each predicate was neutralised in turn.
3. **Red-before-green on the new regression tests, verified by reverting the fix.** Do not accept "the test is
   red before the fix" as a claim; restore the pre-fix sources (`git checkout <base> -- <files>`) and run the
   new tests. In B3b all four new tests failed on the pre-fix tree and passed after — a 3-second check that
   converts a self-report into evidence.
4. **Re-review the fix delta, not the report.** The seats re-read the changed hunks and re-ran their own
   probes; the fact that the fix commit touched exactly the six in-scope files and none of the artefacts was
   itself part of the verdict.
5. **Keep the reviewed SHA reviewable.** After the seats approved `7361409`, a one-line documentation nit was
   committed as a **new** commit rather than amending — amending would have invalidated every seat's line
   anchors. Record that reasoning, so a later reader does not "clean up" history and silently void the review.

## Why This Works

A guard has two independent failure modes: a **wrong condition** (the body) and **no execution** (the call
site). Happy-path tests exercise neither when the subject is absent, and the suite's green colour is
indistinguishable in both cases. The proofs above target the wiring, and the red-before-green revert targets
the body, so between them the guard's *existence*, its *reachability* and its *discriminating power* are each
independently falsifiable.

Pair this with the complementary convention in the conventions/ category — *Gates must re-derive, and every
AI block must land on a page* — which covers guards that run but verify nothing because their condition can
never be true (name/path mismatch, scope that switches itself off, counts that survive substitution).
Together: **a check must be reachable, and its condition must be able to be false.**

## Prevention

- When a diff adds a predicate, require the reviewer to point at its call site (not its definition).
- When a finding is closed, close it on code: the call site, the red-before-green revert, or the neutralised
  predicate. A report is an input, never the proof.
- Keep mutation/positive-control tests as the default shape for invariant tests, and run the red-before-green
  check yourself whenever a fix round claims it.
