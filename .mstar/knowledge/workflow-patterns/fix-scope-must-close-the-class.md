---
module: jiangsu-ai-course-pipeline
date: 2026-09-13
problem_type: workflow_issue
category: workflow-patterns
severity: high
plan_id: ai-course-prep-pipeline-b2a-15043
applies_when:
  - "Closing a QC/QA finding of the form 'check X does not cover case Y'"
  - "A fix landed and the same reviewer seat is about to revalidate it"
  - "Deciding whether a partially-closed finding may be deferred as a residual"
tags:
  - fix-scope
  - half-fixed
  - revalidation
  - residual-discipline
  - evidence-discipline
last_updated: 2026-09-13
---

# A fix must close the class, not the named instance — four "half-fixed" findings in one plan

## Context

B2a (`15043` end-to-end) went through one plan QC tri-review, one fix round, a re-review, a second fix round and
a second re-review. Every blocking finding was **fixed** in the first round, and the re-review still returned
`Request Changes`: four findings had been closed **only for the shape the reviewer named**, leaving the same defect
alive in a sibling form.

| Finding | What the first fix covered | What it left open |
|---|---|---|
| False source attribution (F-1) | the `explain` block the reviewer quoted | the **`drill` block** of the same point carried the identical false citation |
| Gate scope key ("X2") | the course's `sources/jiangsu/courses/15043/content.json` **single file** missing | deleting the **whole source directory** still passed (the scope key was built from the source-side iterator) |
| Page-reach predicate | the **duplicate-pad** evasion | **body-emptied** (heading kept) and **code-fence-padded** headings still passed |
| Replay durability ("W-1") | the **replay** byte-identity test | the **render** byte-identity half had no test at all (`helpers` still bound to the other course) |

Three of the four were found by the **same seat** that raised the original finding, re-reading the diff rather than
re-running the fixer's evidence. The fourth was raised by a peer seat revalidating its own item.

## Guidance

- **Fix the class; say which class you fixed.** When a finding is "the check does not cover Y", the fix is
  incomplete until you can state the *general* predicate and show every input shape is covered. "I fixed the case
  the reviewer quoted" is not a closure. For the page-reach predicate above, the class was "the check must identify
  *which* item is present, not *how many*" — which forced a per-item identity anchor instead of a count.
- **Enumerate sibling shapes before writing the fix, not after.** Derive them mechanically from the predicate: if
  the check parses text, ask "what else can hide this token?" (whitespace, a code fence, an HTML comment, a
  different page). B2a's fixer closed the fence case and left the comment case, because the comment case was
  never enumerated.
- **A partially-closed finding is not a residual.** Deferring the open half lets a half-true statement ship: the
  register says "fixed", the reviewer's original wording says "fixed", and the defect is still live. In B2a the
  PM explicitly ruled that all four had to be closed **in the same round** rather than registered as residuals —
  the marginal cost is one commit and one replay verification, and the cost of the alternative is a record that
  misleads the next session.
- **The revalidating seat must re-read the diff, not the fixer's evidence.** A fixer's report is testimony. The
  four items above were all caught because the seat applied its own original predicate to the new revision. Treat
  "fixed" as a claim to falsify.
- **Watch for the fix that is silently a no-op.** B2a's first per-item anchor fix paired a split's `[1:]` with
  `[2:]` under a non-capturing group, which glued each section to its neighbour: the fix did not work, yet the test
  suite was green. Only the after-state reproduction (mutate, then the layer must exit non-zero) exposed it. A
  green suite is not evidence that a fix works.

## Why This Matters

The failure mode is asymmetric in cost. Fixing the class costs one more commit; fixing the instance costs a
permanent, authoritative-looking record that says a defect is closed while it is still reachable. Because the
register and the review reports are what the next session reads, the half-fix becomes *harder* to find than the
original defect — the original at least had an open finding attached to it.

There is also a schedule effect: each half-fix costs a full re-review round (dispatch, probes, report). B2a spent
two extra rounds on four items that one class-level pass would have closed together.

## When to Apply

- Closing any finding whose wording is "does not check", "does not cover", "only handles", or "misses".
- Before marking a QC round closed: for every finding, ask "what is the general predicate, and is every shape of
  input covered?"
- Before registering a partially-closed finding as a deferred residual — prefer closing it, or state explicitly
  in the register note that the closure is **limited to a named shape** (B2a's R14 does exactly this, and its
  sister item R18 records the open shape).
- When a fix touches a parser or a text predicate: reproduce the *before* state, make the change, and re-run the
  same mutation to prove the after state. Do not rely on the suite.

## Examples

### Before

Reviewer: "the reachability check is count-only, so a dropped block can be masked by a padded heading."
Fix: strip code fences before counting.
Re-review: "the fence variant is closed, but a heading with an **emptied body** still passes, and so does a floor
padding heading."

### After

The predicate was restated as an identity requirement: each point must own an anchor section that **contains its
heading with a non-empty body**, with comment- and fence-stripping applied **before** the heading scan through a
single shared entry point so the three judgements cannot diverge again. Every enumerated shape — duplicate-pad,
body-emptied, fence-pad, comment-wrapped, page-moved-out, and the compensated two-sided shrink — now fails closed,
and each has a mutation test. The PM recorded the closure per shape, and the one shape still open at a different
layer (an *unclosed* comment) was registered separately rather than folded into the "fixed" wording.
