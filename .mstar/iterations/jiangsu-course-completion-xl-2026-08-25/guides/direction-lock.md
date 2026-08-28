# Direction Lock

## Direction

Improve the course pages of five Jiangsu 080901 计算机科学与技术 courses — **02324 离散数学, 02333 软件工程, 00898 互联网软件应用与开发, 13015 计算机系统原理, 04735 数据库系统原理** — using only **existing verified sources** in this repository. This applies the reader-path pattern proven in `jiangsu-15043-15044-deepen-2026-08-24` (start-here block, symmetric cross-links, chapter-name index where an official syllabus extraction exists, executable study sequence) to the five courses. The long-term spec `.mstar/specs/public-source-content-loop.md` stays **locked**; this iteration extends the reader-facing outcome only.

## Evidence policy (unchanged from prior iterations)

- Official-public-only: a public claim is backed by a jseea.cn (or host-school) URL already recorded in the course `sources.md` and `ops/jiangsu/source-links.baseline.json`, or by a local extraction artifact of such a document. **Never invent official URLs.**
- Missing evidence stays a **named gap** with reader-facing consequence; never fill with inferred or private material.
- Internal material references use `materials://...` only; no private raw URLs.
- Lifecycle never exceeds `machine_ready`; no `publishable` / `reviewed: true` / `reviewer`.
- Chapter indexes publish **names only** from the official gaogang extraction artifacts; never body text, never pasted PDF prose.
- PR policy: open a PR to `main` at Phase 4 and merge after user confirmation (standing policy). Branch: `main` -> `iteration/jiangsu-course-completion-xl` -> `main`.

## Course source matrix (verified snapshot, 2026-08-25)

Evidence read from each course's `content/jiangsu/courses/<code>/sources.md`, the local extraction artifacts, `ops/jiangsu/source-links.baseline.json`, and the refreshed gap backlog `ops/jiangsu/issues/course-gap-issues.json`.

| Course | Textbook-plan row | Official syllabus URL | Local syllabus extraction | Current page state | Gap-backlog row |
|--------|-------------------|-----------------------|---------------------------|--------------------|-----------------|
| 02324 离散数学 | `verified-metadata` — `023241 离散数学(附大纲)` 辛运帏, 机械工业出版社, 2014 (`sources/jiangsu/processed/textbooks/jiangsu-2026-10-2027-01-schedule-textbooks/document.extracted.md`) | **missing-source** (named gap) | none | draft / metadata-only | P1: 官方考纲 URL/抽取件, 真题, 教材实物/ISBN 核验 |
| 02333 软件工程 | **missing-source** (named gap: 教材计划元数据) | `official-url-ok` — `https://www.jseea.cn/webfile/selflearning_jcdg/2025-01-15/7285132780508286976.html` | `sources/jiangsu/processed/syllabus/02333-software-engineering-gaogang-4068/document.extracted.md` (高纲 4068) | draft / metadata-only | P1: 教材计划元数据, 真题, 教材实物核验 |
| 00898 互联网软件应用与开发 | **missing-source** (named gap: 教材计划元数据) | `official-url-ok` — `https://www.jseea.cn/webfile/selflearning_jcdg/2024-07-05/7214792761239670784.html` | `sources/jiangsu/processed/syllabus/00898-internet-software-development-gaogang-4295/document.extracted.md` (高纲 4295) | draft / metadata-only | P1: 教材计划元数据, 真题, 教材实物核验 |
| 13015 计算机系统原理 | `verified-metadata` — `130151 计算机系统原理(附大纲)` 袁春风, 机械工业出版社, 2023 (same textbook-plan artifact) | **missing-source** (named gap) | none | draft / metadata-only | P1: 官方考纲 URL/抽取件, 真题, 教材实物/ISBN 核验 |
| 04735 数据库系统原理 | `verified-metadata` — `047351 数据库系统原理(附大纲)` 黄靖, 机械工业出版社, 2018 (same textbook-plan artifact) | **missing-source** (named gap) | none official; local textbook outline already drove the delivered v2.1 knowledge tree | machine_ready draft v2.1, 78/78 知识点, 章节知识树 delivered | P0: 官方考纲 URL/抽取件, 真题, 教材实物/ISBN 核验 |

The baseline JSON additionally records the two jseea.cn syllabus URLs as `authoritative: true` with content hashes and `course_codes` (`00898`, `02333` respectively) — those are the **only** official URLs in this iteration's evidence boundary.

## Per-course verified facts usable in plans

- **02333 (gaogang 4068, machine-draft extraction — verify against artifact at Execute)**: structure = 第一篇 面向过程的软件工程 (第1章 概论, 第2章 分析阶段, 第3章 总体设计, 第4章 详细设计, 第5章 编码及测试, 第6章 软件维护及软件再工程), 第二篇 面向对象的软件工程 (第7章 面向对象方法学, 第8章 面向对象分析, 第9章 面向对象设计, 第 10 章 面向对象实现), 第三篇 软件工程管理及开发实例 (第 11 章 软件工程标准化和软件文档, 第 12 章 软件工程质量, 第 13 章 软件工程项目管理, 第 14 章 简单的人事管理系统设计与开发（本章内容不作考核要求）), plus 附录一–七 (可行性研究报告, 需求规格说明书, 总体设计说明书, 详细设计说明书, 软件测试的需求规格说明书, 软件维护手册, UML 的模型及图示表示). The earlier snapshot ("11 章, 第 10 章 possibly missing") under-counted — the artifact does contain 第 10 章; counts must be re-verified line-by-line before publishing and any residual discrepancy surfaced as a named gap, not guessed. 第 14 章 carries a verbatim chapter-level non-assessment qualifier (index row keeps it; excluded from the assessed study sequence). Publish **names only**.
- **00898 (gaogang 4295, machine-draft extraction — verify at Execute)**: flat structure, no 篇 grouping. 第1章 JSP 与 Web 技术概论, 第2章 JSP 的开发和运行环境, 第3章 JSP 基本语法, 第4章 JSP 内置对象, 第5章 Cookie 及会话追踪, 第6章 JavaBean 和表单处理, 第7章 JSP 中的文件操作, 第8章 应用 JDBC 进行数据库开发, 第9章 JDBC 与 JavaBean 应用实例（本章内容不作考核要求）, 第 10 章 Servlet 基础, 第 11 章使用 Servlet 过滤器和监听器, 第 12 章 JSTL 标准标签库（本章内容不作考核要求）, 第 13 章 自定义标签库（本章内容不作考核要求）, 第 14 章 网上书店（本章内容不作考核要求）, 第 15 章 调查问卷管理系统（本章内容不作考核要求）, 第 16 章 Web 应用开发实践（本章内容不作考核要求）— i.e. **16 章**, not 9; the earlier snapshot stopped at 第9章. Chapter-level `（…不作考核要求）` qualifiers are themselves syllabus facts and are published verbatim with the chapter row (assessed set: 第1–8章, 第10–11章). Publish **names only**.
- **02324 / 13015**: no official syllabus URL or extraction exists → chapter index is a **named gap**; `plan.md` sequences key off the verified textbook-plan metadata (title/author/publisher/year, 附大纲) without chapter claims.
- **04735**: the delivered v2.1 `index.md` knowledge tree (第一章 数据库系统概述 … per the local 2018 textbook 附自学考试大纲) is existing verified-repo content; Plan 5 **traces** it (per-block source rows) and does not regenerate it.

## Plan-to-evidence mapping

| plan_id | Evidence consumed | Named gaps preserved |
|---------|-------------------|----------------------|
| 02324-reader-path | textbook-plan extracted row (2014, 附大纲) | official syllabus URL/抽取件; 真题; ISBN/实物 |
| 02333-official-syllabus-reader-path | jseea.cn URL (2025-01-15) + gaogang-4068 extraction | 教材计划元数据; 真题; 教材实物 |
| 00898-official-syllabus-reader-path | jseea.cn URL (2024-07-05) + gaogang-4295 extraction | 教材计划元数据; 真题; 教材实物 |
| 13015-reader-path | textbook-plan extracted row (2023, 附大纲) | official syllabus URL/抽取件; 真题; ISBN/实物 |
| 04735-source-trace-reader-path | textbook-plan extracted row (2018) + local textbook outline (already published as v2.1 tree) + existing `materials://` index | official syllabus URL; 真题; ISBN 核验 |

## Decisions recorded

- Five plans exactly as the plan_ids above; serial SDD execution on one integration branch.
- Hub (`content/jiangsu/courses/index.md`) already lists all five courses — out of scope for all plans (no dual ownership).
- Phase 1 is planning-only: no `content/**` edits, no commits, no branch changes in this phase.
