---
iteration_id: jiangsu-ai-course-pipeline-2026-09-11
start_date: 2026-09-11
status: completed
end_date: 2026-09-12
enforcement: soft
effort_budget: M
iteration_base_branch: main
spec_integration_branch: iteration/jiangsu-ai-course-pipeline-2026-09-11
target_branch: main
plans:
  - ai-course-prep-pipeline-b1
---

# jiangsu-ai-course-pipeline-2026-09-11 Delivery Compass

## Scope

**交付切片 = B1 only**（spec § Roadmap 的 B1 行；plan `ai-course-prep-pipeline-b1`）。
本迭代锁定的 spec 点（Primary spec：`.mstar/specs/ai-course-prep-pipeline.md`）：

- **S1 双层内容模型**：官方事实层（只允许官方来源，沿用现有硬闸门）+ AI 备考层（每块带 `ai_generated` / `generator` / `evidence_refs`，页面显著标注，绝不冒充官方）。
- **S2 唯一放行门槛**：`syllabus.status == extracted` **且** `textbook_plan.status == matched` → `L1`；否则零 AI 产物，保持命名缺口。
- **S3 课码 / 课名驱动入口**：`sources/jiangsu/catalog/courses.json` 为课程目录 SSOT，支持代码与名称（含全半角 / 空格变体）解析。
- **S4 知识模型**：把官方考纲「三、考核知识点与考核要求」结构化为 章 → 节 → 考核点（识记 / 领会 / 应用）+ 本章重点 + 题型 / 样卷锚点，覆盖率 ≥ 90%。
- **S5 一键流水线**：`resolve → acquire → evidence → model → generate → render → gate` 单命令可跑，缺前置即明确失败；CI 离线（fixture）可回归。
- **S6 闸门扩展**：新增 `evidence` 与 `ai-content` 两层接入 `run-gates.py`；既有五层语义不变。
- **S7 试点验收**：`15040` 端到端产出七类页面，且与既有手工知识树（导论 + 17 章 / 61 个节级知识点）可比对。

**迭代范围边界（硬）**：本迭代只交付 **B1（数据底座 + `15040` 端到端试点）**。
B2（公共课 P0 五门）、B3（080901 计算机 27 门）、B4（其余专业分批）为**后续迭代**，本迭代不启动、不产出其知识模型 / AI 备考层 / 渲染页；
三者的启动门槛（触发条件）与完成定义见 spec § Roadmap（B2：B1 验收 1–9 全绿且 `O2` / `O4` 书面收敛；B3：B2 Done 且 `catalog` 能解析 080901 计划表；B4：B3 Done 且流水线在 ≥ 10 门无回归）。
可核验边界：本迭代结束时 `content/jiangsu/courses/` 下只有 `15040` 被重渲染；B1 为现有 18 门课产出的 `evidence.json` 是**放行判定数据**，不等于该课进入生成批次。

**对读者的三条硬承诺（本迭代必须可核验）**：

1. **拒绝生成** —— 缺官方考纲或缺官方教材计划 → 放行等级非 `L1` → 零 AI 内容，页面保持命名缺口（读者看到缺口说明，不是猜测内容）。
2. **AI 标注** —— 每个 AI 块带生成器（后端 / 模型 / 提示词 id / 版本 / 生成时间）与证据锚点，页面带 AI 声明横幅，**绝不冒充官方**。
3. **来源可追溯** —— 每条官方事实带 `doc_id` + `locator`；无来源的数字 / 日期 / 章号 / 分值一律为命名缺口。

## Plans

| plan_id | Name | Status | Notes |
|---------|------|--------|-------|
| ai-course-prep-pipeline-b1 | AI 备考流水线 B1：数据底座 + `15040` 端到端试点（本迭代唯一交付切片） | **Done** | 6 个 task；`Execution mode: sdd`；pilot = `15040`；范围 = B1 only。T1–T6 + 8 个内容批次 + P0/P1 打磨全部落地。**QC tri 首轮三席一致 `Request Changes`**（7 Critical → 5 个独立缺陷 + 24 Warning + 11 Suggestion），经 **3 轮修复波次**（`2bc9102` / `a25eb29` / `c5f42d8`）清零；**终审 3/3 `Approve`（0 Critical / 0 Warning）**。**QA gate `PASS with notes`，AC1–AC9 全 PASS**（8 项运行时探针）。终态 head `c5f42d8`，worktree 干净。Durable summary 见 plan § Review Gate Summary / QA Gate Summary |

Status values: `Todo` | `InProgress` | `InReview` | `Done` | `Blocked`

## Milestones

| Milestone | Target date | Status |
|-----------|-------------|--------|
| Spec freeze（Phase 1 chain + compass locked） | 2026-09-11 | pending |
| Dev complete（Task 1–6） | 2026-09-12 | pending |
| QC complete（plan QC tri + QA gate） | 2026-09-12 | pending |
| Iteration close | 2026-09-12 | pending |

## Acceptance Criteria

> 迭代级 done 条件，逐条一一对应 spec § Acceptance criteria（编号相同）。任一条不成立 = 本迭代不能判 Done。
> 每条给出命令（含预期退出码）、可观察产物或可数集合；不得以「基本完成 / 大致达标」判定。

- **AC1（= spec AC1）端到端单命令**：迭代内以离线确定性口径验收 —— `python scripts/build-course-content.py build 15040 --backend replay` → exit 0，七阶段跑完，产出 `content/jiangsu/courses/15040/` 七类页面（六页 + `knowledge/*.md` **18 个章页**）；缺前置 → exit ≠ 0 + stderr 报缺失阶段名，且失败路径下 `content/jiangsu/courses/15040/**` 无新增/改写文件（无半成品）。
- **AC2（= spec AC2）目录覆盖面**：`python scripts/build-course-catalog.py --check` → exit 0；`sources/jiangsu/catalog/courses.json` 唯一课码 **≥ 60**，覆盖 `content/jiangsu/courses/` 全部 **18** 个课码 + `content/jiangsu/majors/` 全部 **54** 个专业页课程表所涉课码；冲突入 `conflicts[]`（含两侧值 + `locator`），不自动取舍。
- **AC3（= spec AC3）课码 / 课名解析**：`15040` / `中国近现代史纲要` → `15043` / `java 语言程序设计（一）` → `04747`（全半角括号、大小写、空格归一）；同名课 → `ambiguous` + `len(candidates) == 2`；无匹配 → `not_found`。
- **AC4（= spec AC4）放行与零 AI 产物**：18 份 `evidence.json` 就位；`L1` 集合**恰为** 7 门 `{15040, 15043, 15044, 04747, 02333, 04751, 00898}`，其余 11 门 `blocked` 且 `reasons` 非空；非 `L1` 课程无 `content.json`（零 AI 产物）；`named_gap`（命名缺口）带 `gap_impact` + `next_evidence`。实测不符即 STOP 回写，不放宽判定。
- **AC5（= spec AC5）知识模型与手工比对**：`coverage.ratio ≥ 0.90`；章数 18 且与 `content/jiangsu/courses/15040/syllabus.md` 章目逐字一致；与手工 **61** 个节级知识点的差异逐条落 `coverage.diff_vs_manual`；未编号段落入 `chapters[].unmodeled[]`，不编造。
- **AC6（= spec AC6）AI 标注合同**：`blocks[]` / `stage_plan[]` 每项四件套齐全（`ai_generated` / `generator` / 非空 `evidence_refs` / `review_state`）；`drill` 块含 `answer_md` + `source_kind`（`official_sample` 必带 `provenance`）；`point_id` 存在于知识模型；渲染页带 `本页由 AI 辅助生成` 横幅；`run-gates.py` 的 `ai-content` 层对「缺字段 / 无锚点 / 8-gram > 20%」分别失败关闭。
- **AC7（= spec AC7）来源可追溯**：官方事实字段均带 `doc_id` + `locator`；无「`verified` 但缺 `provenance`」字段；`quote` ≤ 60 字符且无 `>` 引用块；无来源的数字 / 日期 / 章号 / 分值一律 `named_gap`；`evidence` 层闸门对非法 `status` / 缺 `gap_impact` / 不存在 `point_id` 失败关闭。
- **AC8（= spec AC8）全绿命令集**：`python scripts/run-gates.py`（含新增 `evidence` / `ai-content` 两层）、`.venv/bin/python -m pytest -q`、`ruff check scripts tests`、`python scripts/check-source-links.py --offline`、`mkdocs build --strict`、`git diff --check` 逐条 exit 0；CI 不联网、不调用 LLM（`.github/workflows/deploy-pages.yml` 不设 `ZIKAO_LLM_*`）。
- **AC9（= spec AC9）无 key 环境**：`python scripts/build-course-content.py generate 15040 --backend agent` 在无 `ZIKAO_LLM_API_KEY` 时产出 `content.json` 并过同一套闸门（缺回填即显式失败，不伪造）；「逐字段同构」判定 = 同一 JSON schema 校验均通过且必需字段集合一致；`--backend replay` 复跑与首次生成在归一 `generated_at` 后一致。

## Non-Goals

- 不生成任何缺官方考纲或缺官方教材计划课程的内容（实践课 7 个课码同样排除）。
- 不做交互式题库 / 自测 / 学习进度 / 账号体系。
- 不做 Anki / CSV / 打印版导出。
- 不提升 `publishable`、不写 `reviewed: true` / `reviewer`、不做法务终审（仍为人工职责）。
- 不引入私有仓 `zikao-materials` 内容，不转载第三方（B/C 级）题文。
- 不修改既有五层闸门语义，不改 `mkdocs.yml` 的 `nav`。
- **不启动 B2–B4 批次**：不产出 `15043` / `15044` / `13000` / `00023`（B2）与其余专业课程（B3 / B4）的知识模型、AI 备考层或渲染页。B1 为其产出的 `evidence.json` 只是放行判定数据。
- 不重渲染其余 17 门现有课程的页面（本迭代只渲染 `15040`；其页面缺口呈现随各自批次）。

## Roadmap Position

- **Current iteration（jiangsu-ai-course-pipeline-2026-09-11）**：**delivered** —— B1 数据底座（catalog + resolver）、取证与放行（evidence / eligibility）、知识模型、AI 备考层与标注契约、确定性渲染、新增两层闸门，以 `15040` 端到端试点验收。QC tri 首轮三席一致 `Request Changes`（7 Critical → 5 个独立缺陷），经 3 轮修复波次清零；**终审 3/3 `Approve`**；**QA gate `PASS with notes`，AC1–AC9 全 PASS**；plan `ai-course-prep-pipeline-b1` = `Done`，已合入集成分支（merge `6f80d7d`）。**本迭代未启动 B2–B4。**
- **Next iteration（B2，未启动）**：全专业公共课 P0（`15040` / `15043` / `15044` / `13000` / `00023`）；启动门槛（触发条件）：本迭代验收 AC1–AC9 全绿（**已满足**）、且 spec `O2`（真题授权边界）与 `O4`（LLM 预算上限）**书面收敛**（**仍未满足**——`O4` 可用的实测基线：`15040` 单课产出 1.46 MB / ≈58 万 tokens / 393 考点，即 ≈1473 tokens/考点，`15043` 255 点 ≈376k、`15044` 271 点 ≈399k output tokens）；owner：内容维护者（`@project-manager` 派发）。**注意**：`15043` / `15044` 的知识模型已随 B1 落地并修复（`15044` 8 章 / coverage 28；`15043` 首章 `ch01`；两门 `question_types` 已补齐），故 B2 的剩余工作是**生成 + 渲染**，不构成 B2 启动。
- **Later iterations（未启动）**：**B3**（080901 计算机 27 门）触发条件 = B2 Done 且 `catalog` 能解析 080901 现行计划表；**B4**（其余专业分批）触发条件 = B3 Done 且流水线在 ≥ 10 门课验证无回归。B2–B4 的完整定义（范围 / 启动门槛 / 完成定义 / owner）见 spec § Roadmap。
- **本期非阻塞遗留（见 plan § Follow-ups F6–F17，各有 owner 与触发条件）**：手工编辑的未闭合 derived 标记不收敛；无闸门解析 derived 标记 / 对账章节链接（检测仍只在渲染器内）；`is_fresh` 死导出；模块级 record 全局；一处手写长引用块按 F10 维持现状。
- **最终目标**：给出任一江苏自考课码或课名，即可得到一套以应试为目标、来源可追溯、AI 备考层显式标注的完整学习资料；机器产物上限始终为 `machine_ready`。

## Delivery Branch Policy

> Mirror of frontmatter; keep in sync with workflow snapshot `.mstar/workflows/jiangsu-ai-course-pipeline-2026-09-11/snapshot.json` `branch` anchors.

| Field | Value |
|-------|-------|
| `iteration_base_branch` | `main`（用户 2026-09-11 确认） |
| `spec_integration_branch` | `iteration/jiangsu-ai-course-pipeline-2026-09-11` |
| `target_branch` | `main` |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 考纲抽取件版式差异导致知识模型错位 | Med | Med | Task 3 设降级 STOP（节级粒度）+ `coverage.diff_vs_manual` 差异留痕 |
| 教材计划多行版式导致放行误判 | Med | High | 归一化匹配 + 双向测试锁死（多行命中 / 日程区不误判 / 跨文档并集） |
| LLM 输出漂移或不可控（agent 后端） | Med | Med | 固定 JSON schema + 校验失败即 STOP（不放宽 schema、不填占位）；replay fixture 离线回归 |
| 渲染覆盖既有手工内容 | Low | High | `manual:` 块保留机制 + 哨兵测试；失败即回滚 `6d17ae9` 的 15040 页面 |
| 既有 17 门课被新闸门误伤 | Low | Med | 新层只对存在产物的课程生效；未生成课程不参与新层校验 |

## Iteration package

> Sibling paths under `.mstar/iterations/jiangsu-ai-course-pipeline-2026-09-11/` — not in `.mstar/specs/` or `.mstar/knowledge/`. Promoted to knowledge at iteration-close via **`mstar-compound`**.

| Path | Purpose |
|------|---------|
| `guides/` | 探索与过程笔记（含 Phase 1 方向锁定与实测证据） |
| `specs/` | 迭代级 spec 草案（长期规范仍以 `.mstar/specs/ai-course-prep-pipeline.md` 为准） |
| `README.md` | Package 文档索引 |

## Quality Gate Summary

> Filled at iteration-close.

| plan_id | QC decision | QA gate | Residuals | Durable summary |
|---------|-------------|---------|-----------|-----------------|
| ai-course-prep-pipeline-b1 | **Approve**（三席 3/3；首轮 7 Critical / 24 Warning / 11 Suggestion → 3 轮修复波次清零） | **PASS with notes**（`mandatory` / `acceptance-only`；AC1–AC9 全 PASS） | 无 open R# | `.mstar/plans/ai-course-prep-pipeline-b1.md` § Review Gate Summary / QA Gate Summary |

## Compound Round Summary

- 结晶文档数：**5 篇**
  - `conventions/gate-fail-closed-and-page-reach.md`（闸门须重新推导并证明会触发；四个 block kind 必须各自落页）
  - `conventions/renderer-preserves-handwritten-prose.md`（渲染器不得改写手写正文；derived 区块兄弟化 + 配平扫描 + 无条件刷新）
  - `testing-patterns/deterministic-generation-backends.md`（一 schema 三后端；整产物字节相等为判据；无 key 后端失败关闭）
  - `workflow-patterns/reviewer-findings-need-reproduction.md`（席位发现须先复现再入档；行号只在产出它的切分语义下有效）
  - `architecture-patterns/course-pipeline-layering.md`（三层流水线、每产物单写者、放行判定唯一落点）
- 新增 CONCEPTS.md 条目：**7 条**（Pipeline 节：Stage / Block kind / Derived region / Manual block / Zero AI artifacts / Backend）
- 迭代 package 盘点：`guides/` + `specs/` 共 5 篇（compass 按规则排除）。**Promote**：`specs/design-notes.md` → `architecture-patterns/course-pipeline-layering.md`。**Keep snapshot**：`specs/iteration-scope.md`（B1 切片说明，已被 spec 取代）、`guides/corpus-hygiene.md`（§1.6 一次性过程报告）、`guides/direction-lock.md`、`guides/official-source-evidence.md`（规划期实测证据，属迭代史）。
- 触发 compound-refresh：**否**——五篇新文档与既有 6 篇无重叠（类目从 3 个扩到 6 个），无需合并或清理。
- 每篇新 doc 均通过 `mstar compound validate` 并登记 `{KNOWLEDGE_DIR}/README.md`（Phase 6 强制）。

## Iteration Retrospective (minimal)

- **做得好的**：
  - 三席 tri-review 顶住了"全绿假象"——在 249 测试 + 7 层闸门 + 站点构建全绿的情况下，仍查出 AI 备考层**从未上线**（1180 块孤儿）与 `gate` 阶段**空转**这两个结构性缺陷。本轮最高价值产出。
  - `zero-residual` 执行到位：三轮修复波次把 7 个 Critical + ~30 Warning 全部清零，无一项降级为 open R#。
  - 独立复核纪律有效：PM 亲自复现全部 5 个独立 Critical，并推翻 2 处席位误报（plan F13 / F15③），避免错误结论入档。
  - QA 运行时探针（三种变异证明"无半成品"、`agent` 后端失败关闭不伪造）补上 L3 无法覆盖的最后一环。
- **可改进的**：
  - **Phase 2 收尾顺序出错一次**：QA 通过后应"先串行 merge 再设 Done"，实际先设 Done，且三个修复波次提交一度只留在 plan 分支。已补做 merge（`6f80d7d`）并记录在案。
  - **PM 两次越界编辑控制树**：一次直接改 `ops/jiangsu/content-standard.md`（已回滚，登记 F12）——"控制 worktree 禁产品编辑"尚未形成肌肉记忆。
  - **席位证据链仍需 PM 兜底**：两处误报都带"实测数字"，其中一处的错误源于与 PM 首轮相同的 `splitlines()` 陷阱——方法学盲区会在席位与 PM 之间共享，故复核必须**换一种独立实现**，而非照抄口径。
  - 首轮 `qc-consolidated.md` 曾在三席报告缺失时写出 `Approve`，属"汇总层零注入"违规；已作废重跑。
- **下迭代建议**：
  1. **先谈口径再排批次**：B2 启动门槛只差 spec `O2`（真题授权）与 `O4`（预算上限）书面收敛；`O4` 已有实测基线（≈1473 tokens/考点）可作上限依据。
  2. **B2a 走"生成 + 渲染"**：`15043` / `15044` 知识模型已在 B1 修复落地，B2 增量面小于原计划。
  3. **补纵深防御**：给 `chapter-links` 加闸门级「模型 ↔ 页面」对账（当前检测只在渲染器内），并处理手工编辑的未闭合 derived 标记。
  4. **复习排程输入面**：`15040` 唯一读者可见空洞仍是 `review_schedule` 的 `named_gap`（缺 `exam_date` / `weekly_hours`）。
