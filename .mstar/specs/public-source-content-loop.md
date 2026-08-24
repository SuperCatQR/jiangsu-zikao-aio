---
spec_id: jiangsu-public-source-content-loop
status: locked
created_at: 2026-08-24
owner: project-manager
---

# Jiangsu Public-Source Content Loop

This document is the **locked** long-term spec for this iteration. Iteration-local notes remain in `.mstar/iterations/jiangsu-public-source-loop-2026-08-24/`.

## Intent

Build a repeatable public-source workflow for Jiangsu self-study course pages. The first delivery slice covers P0 courses **15043 中国近现代史纲要** and **15044 马克思主义基本原理** and keeps every claim tied to an official public source or an explicit unresolved gap.

## Reader outcome

For each course, a reader can identify the publicly supported examination-outline scope, scan a bounded syllabus index and paraphrased orientation, and follow an executable study sequence. The page also makes unavailable evidence useful by naming the gap, its reader-facing consequence, and the next evidence needed; it never fills the gap with private or inferred material.

## Locked decisions

- Publishable evidence comes from Jiangsu Education Examination Authority pages/files, host-school official pages, or another clearly official institution. Third-party pages may identify leads but cannot support a public conclusion.
- Each source record carries the official URL, page/file title, publication or applicability date when stated, course-code/name match, verification date, and the fields it supports.
- Public pages may contain metadata, indexes, paraphrased summaries, and study plans. They must not contain textbook or past-paper originals, copied question text, private raw URLs, or unverified exam claims.
- Course state advances per course only when its evidence supports the target state. The iteration may advance a course to `machine_ready`; it must not synthesize human review or set `publishable`.
- Missing official evidence remains a visible gap. A dry-run backlog is stored in the repository; the iteration does not create or update remote GitHub issues automatically.
- The public maturity projection and gap summary must be deterministic and must reject drift between the generator's current lifecycle/completeness rows and the checked-in public view.
- Public source evidence is stored as Markdown/YAML the existing extractors already read. Official URLs must appear as Markdown links or bare `http(s)` URLs under headings that match `scripts/check-source-links.py` `IN_SCOPE_SECTION_KEYWORDS` (substring match: `来源`, `来源与引用`, `考纲与教材`, `官方来源`, `真题`, `真题索引`). Table cells that omit a real URL are not extracted.
- Official PDF/page provenance is URL, title, stated publication/applicability date, course-code/name match, verification date, and supported fields. Public pages must not copy PDF body text, processed `document.extracted.md` body, or private archive contents.
- Plan 2 is blocked until Plan 1 has landed the per-course evidence/status contract (`lifecycle`/`completeness` plus the source record). Plan 2 may project those rows; it must not invent evidence or lifecycle semantics.

## Scope

### In scope

- `content/jiangsu/courses/15043/` and `content/jiangsu/courses/15044/` source, syllabus, study-plan, and related status fields.
- Official 2025-02-25 examination-outline **index pages** on `www.jseea.cn` and the same-day linked official PDFs, with code/name/version verification. Full lead URLs are recorded in the iteration direction lock; Execute must re-verify before publishing claims.
- A minimal public evidence schema (`ops/jiangsu/public-source-record.md`, introduced by Plan 1 Task 1) and the existing `sources.md` / `ops/jiangsu/schemas/course.schema.json` page contract.
- `content/jiangsu/gaps/page-maturity.md`, its summary, and the repository-only dry-run gap view (`ops/jiangsu/issues/course-gap-issues.dry-run.md`; Plan 1 owns the 15043/15044 records).
- Focused tests and the non-mutating release-gate check needed to detect public projection drift.

### Out of scope

- Private `zikao-materials` files, credentials, private raw URLs, or local private archives.
- Reproducing textbook PDFs, examination papers, copyrighted question text, or third-party answer content.
- Automatic lifecycle promotion to `in_review` or `publishable`, reviewer impersonation, or legal sign-off.
- The remaining P0 courses 00023, 13000, and 15040.
- GitHub issue creation, Actions SHA pinning, and the repository-wide Ruff/mypy/coverage contract.

## Acceptance criteria

1. Both course pages link to the official examination-outline page/PDF and record the source evidence required to reproduce the code/name/version decision.
2. Both courses have public syllabus indexes, bounded paraphrased summaries, and executable study plans whose claims are traceable to public evidence or marked as gaps.
3. No public file contains private raw material, copied protected text, or an unsupported publishable claim; the materials policy and content gates pass.
4. Each course's `lifecycle` and `completeness` reflect its actual evidence state, with no automatic `reviewed: true`, `reviewer`, or `publishable` transition; `machine_ready` is the maximum automated target.
5. The checked-in maturity page and gap summary are generated from or checked against the same deterministic rows as the operational report; drift fails before site publication.
6. Focused tests, the repository gate sequence, offline source extraction, and strict MkDocs build pass in the normal Execute phase.
7. A reviewer can verify from the rendered course pages that each course has the reader outcome above, and each missing official field is visibly labeled with its evidence boundary and impact rather than silently omitted.

## Roadmap

- **Batch 1 (this iteration)**: 15043/15044 evidence and reader-facing content, then deterministic maturity/gap projection.
- **Batch 2 trigger**: extend the same contract to 00023, 13000, and 15040 only after each candidate has a verified official source record with course-code/name and applicability/version evidence, or an explicitly triaged public gap that can be shown to readers; owner is the content maintainer.
- **Batch 2 definition of done**: each candidate has the same reader outcome, measurable evidence fields, deterministic status row, and honest gap behavior as Batch 1.
- **Final target**: every included Jiangsu course has an auditable public-source record, useful reader content, truthful lifecycle/completeness state, and a human-controlled publish gate.
