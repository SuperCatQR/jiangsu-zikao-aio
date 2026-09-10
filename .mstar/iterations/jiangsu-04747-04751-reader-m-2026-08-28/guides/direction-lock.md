# Direction Lock — 04747 + 04751 Reader Paths

## Autonomous input and ranking

No free-text direction was supplied. The loop therefore used the requested code-first research default and ranked candidates against the repository evidence, previous iteration roadmaps, product completeness, and blast radius.

### Selected direction

Deliver official-syllabus reader paths for **04747 Java 语言程序设计（一）** and **04751 计算机网络安全**. Both course directories are still migration skeletons, but both already have an authoritative jseea.cn syllabus record and a local machine extraction that can support a names-only chapter index.

### Evidence matrix

| Course | Existing official URL evidence | Local extraction | Current gap |
|---|---|---|---|
| 04747 | `content/jiangsu/courses/04747/sources.md:13` → `https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285133106820943872.html`; baseline entry is authoritative for `04747` | `sources/jiangsu/processed/syllabus/04747-java-programming-1-gaogang-4067/document.extracted.md`; `高纲 4067`, 13 chapter headings: 9 assessed (1–6, 8–10) and 4 non-assessed (7, 11, 12, 13) with verbatim `（本章内容不作考核要求）` qualifier | `syllabus.md:11` still says official syllabus missing; `plan.md:24-32` is a generic 30-day schedule |
| 04751 | `content/jiangsu/courses/04751/sources.md:13` → existing jseea.cn HTML and PDF records; baseline associates the HTML with `04751` and `13017` | `sources/jiangsu/processed/syllabus/04751-computer-network-security-gaogang-4389/document.extracted.md`; `高纲 4389`, 13 chapter headings: 10 assessed (1–10) and 3 non-assessed (11, 12, 13) with verbatim `（本章内容不作考核要求）` qualifier | `syllabus.md:11` still says official syllabus missing; `plan.md:24-32` is a generic 30-day schedule |

### Alternatives kept out

- **13017** has official source and textbook metadata but no local syllabus extraction; it also needs a clear explanation of its 2026-10 choice relationship with 04751.
- **13000** remains the documented next candidate only after an official source record or an explicitly triaged public gap; current `sources.md` still marks the official syllabus missing.
- **13003/13180** remain broader discovery candidates without equivalent local extraction evidence in this survey.

## Locked constraints

- Publish chapter names and chapter-level non-assessment qualifiers (`（本章内容不作考核要求）`) only; do not copy syllabus body prose or 04747 code samples.
- Reuse only URLs already recorded in each course source page and the source-link baseline. Never invent a PDF/page URL from a filename or a URL date.
- Preserve missing textbook, true-paper, ISBN/physical-book, applicability, and human-review evidence boundaries.
- Keep lifecycle/completeness at the current machine-safe state; never write `reviewed`, `publishable`, or `reviewer`.
- Plan count is exactly two business plans (`04747-official-syllabus-reader-path` and `04751-official-syllabus-reader-path`), satisfying the `M` budget. Review, SDD, QC, QA, close, PR, and other harness activities are mandatory but do not consume the budget.
