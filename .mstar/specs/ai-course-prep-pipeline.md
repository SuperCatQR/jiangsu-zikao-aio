---
spec_id: jiangsu-ai-course-prep-pipeline
status: locked
created_at: 2026-09-11
owner: project-manager
supersedes_partial: .mstar/specs/public-source-content-loop.md
---

# 江苏自考 AI 备考内容流水线（Spec）

## Intent

把项目主干从「人工逐课建档的官方元数据索引站」重构为「课码 / 课名驱动的 AI 备考内容流水线」。

输入一个课程代码或课程名称，产出一整套**以应试为目标**的学习资料：学习流程、分章知识点、
题型与考法、练习、复习排程；同时保住项目现有的来源可追溯、闸门与 CI 体系。

`.mstar/specs/public-source-content-loop.md` 中「只搬运官方证据、缺口显式、禁止推断」的部分**继续有效**；
本 spec 在其上新增**AI 备考层**，并定义两层之间的边界、标注与放行契约。两者冲突时，以本 spec 为准
（逐项清单见 § Supersede）。

**交付切片**：本 spec 是长期规范；**当前迭代 `jiangsu-ai-course-pipeline-2026-09-11` 只交付 B1**
（数据底座 + 取证放行 + 知识模型 + AI 备考层 + 确定性渲染 + 闸门两层，`15040` 端到端试点）。
B2–B4 是后续迭代的批次，各有独立触发条件，见 § Roadmap；本迭代不启动 B2–B4。

**对读者可见的三条硬承诺**（产品承诺，实现侧不得放宽）：

1. **拒绝生成** —— 缺官方考纲或缺官方教材计划 → 放行等级非 `L1` → **零 AI 内容**，页面保持命名缺口；
   不得用 AI 补章号、考点、年份、分值或考试时长。
2. **AI 标注** —— 每块 AI 内容在页面上显著标注生成器与证据锚点，**绝不冒充官方**。
3. **来源可追溯** —— 每条官方事实可回溯到来源（`doc_id` + `locator`）；
   无来源的数字 / 日期 / 章号 / 分值一律为命名缺口。

## Supersede（与 `public-source-content-loop.md` 的关系）

本 spec **部分取代** `.mstar/specs/public-source-content-loop.md`（后者仍为 `locked`，其正文不重写、历史记录不改动）：

- **继续有效**（本 spec 沿用，不重新定义）：只认官方来源、缺口显式、禁止推断的证据纪律；来源记录字段（官方 URL / 标题 /
  适用或发布日期 / 课码课名匹配 / 核验日期 / 支撑字段）；公开页不得转载受保护正文或第三方题文；
  机器产物上限 `machine_ready`，不得自动提升 `publishable`。
- **被本 spec 取代**：内容生产链路（人工逐课建档 → 流水线）；批次划分（旧 spec § Roadmap 的 Batch 1 / Batch 2
  由本 spec § Roadmap 的 B1–B4 取代，批次编号一律以本 spec 为准）；课程覆盖面（旧 spec 的 In scope 只覆盖
  `15043` / `15044`，本 spec 覆盖全量课程目录）。
- **本 spec 新增**（旧 spec 无对应条款）：双层内容模型与 AI 备考层（`D1`）、AI 标注合同、`evidence` / `ai-content` 两层闸门。
- **旧 spec 的验收条款**：其 AC1–AC7 是该批次（`15043` / `15044`）已交付的验收记录，作为历史结论继续有效；
  后续批次的验收一律以本 spec § Acceptance criteria 为准。
- **冲突时**：以本 spec 为准（同 § Intent 末句）。

## Reader outcome

读者给出课码（`15040`）或课名（`中国近现代史纲要`），在**已发布站点**上能连续读完下列内容。
每条同时给出**读者在站点上看到什么**与**可核验形态**（页面 / JSON 字段 / 命令），
使「读到」与「验到」一一对应；无法在站点上核验的表述不得写进本节。

1. **学习流程** —— 分阶段（入门 / 精读 / 刷题 / 冲刺 / 复盘）可执行序列，每阶段含输入、做法、输出物、完成标准。
   *站点*：`plan.md` 五阶段逐段呈现；其中 AI 生成段落按本节末「读者可见的 AI 标注与来源承诺」标注。
   *核验*：`sources/jiangsu/courses/15040/content.json` → `stage_plan[]` 恰 5 条，每条 `inputs` / `how` / `outputs` / `done_when` 非空且 `ai_generated: true`。
2. **知识树** —— 章 → 节 → 考核点，每个考核点带官方考纲的能力层次（识记 / 领会 / 应用）与本章重点；逐条可回溯到考纲原文位置。
   *站点*：`syllabus.md` 呈现章 → 节 → 考核点三级结构。
   *核验*：`knowledge-model.json` 的 `chapters` 章数 = 18（导论 + 17 章）且与 `syllabus.md` 章目逐字一致；每个 `points[]` 带 `locator` 且 `quote` ≤ 60 字符。
3. **知识点页** —— 分章展开的要点梳理、易错点、记忆法（**明确标注 AI 生成**）。
   *站点*：`knowledge/<NN>-<chapter-slug>.md`（`15040` 共 18 个章页），每页含 `本页由 AI 辅助生成` 横幅。
   *核验*：每页存在且章页可回链课程首页；内容块在 `content.json` 中可查到 `generator` + `evidence_refs` + `review_state`。
4. **题型与考法** —— 官方考纲声明的题型与其出处；考纲未声明的字段保持命名缺口，**不猜**。
   *站点*：`syllabus.md` / `index.md` 列出题型并给出考纲出处；未声明字段显示缺口说明。
   *核验*：`exam.question_types` + `exam.question_types_provenance` 就位；`duration_minutes` 等未声明字段为 `status: "named_gap"` 且带 `gap_impact`。
5. **练习** —— 官方公开样卷 / 真题原件（如有，按来源登记）+ AI 生成题（标注「AI 生成，非真题」、挂知识点 id、含答案与解析）。
   *站点*：`practice.md` 两种块分区呈现，AI 题带标注与折叠答案。
   *核验*：`blocks[]` 中 `kind == "drill"` 的块含 `answer_md` 与 `source_kind ∈ {"ai_generated","official_sample"}`；`official_sample` 必带 `provenance`；`point_id` 存在于知识模型。
6. **复习排程** —— 由考试日期与每周可投入学时生成的 30 / 14 / 7 天计划与间隔重复次序。
   *站点*：`review.md` 给出排程；**未提供考试日期或每周学时**时，该页显示命名缺口与缺口影响，不编造日期。
   *核验*：`review_schedule.plans` 非空（已提供输入时三档计划齐备）；未提供输入时 `review_schedule.status == "named_gap"` 且 `gap_impact` 非空。
7. **来源与核验** —— 每条官方事实的来源记录；每块 AI 内容的生成器、提示词版本、证据锚点。
   *站点*：`sources.md` 逐行列出官方事实来源；AI 块标注生成器与证据锚点。
   *核验*：官方事实字段带 `doc_id` + `locator`；AI 块带 `generator`（后端 / 模型 / 提示词 id / 版本 / 生成时间）与非空 `evidence_refs`。
8. **不可生成课程（放行等级非 `L1`）** —— 缺官方考纲或缺官方教材计划的课程**不生成任何 AI 内容**。
   *站点*：该课程页面保留命名缺口及其对读者的影响（缺口项 / 缺口影响 / 下一份需要的证据），页面上不出现任何 AI 备考层内容。
   *核验*：`sources/jiangsu/courses/<code>/content.json` **不存在**；`evidence.json` 的 `eligibility.level != "L1"` 且 `reasons` 非空。
   本迭代只在 `15040` 渲染七类页面，其余 17 门的页面级缺口呈现随各自批次接入渲染时生效；
   本迭代可核验的形态 = 「非 `L1` → 零 AI 产物」。

### 读者可见的 AI 标注与来源承诺（不可由实现侧放宽）

- 每个 AI 块在页面上带显著标注：AI 声明横幅 + 块级 `generator` / `evidence_refs` / `review_state`；
  `ai-content` 闸门对缺任一标注项**失败关闭**（不是警告）。
- AI 备考层与官方事实层在版面上**分区呈现**：AI 内容不得进入官方来源区，
  页面任何位置不得以「官方」字样修饰 AI 内容。
- 官方事实层每个字段均可回溯（`doc_id` + `locator`）；无来源的数字 / 日期 / 章号 / 分值一律为命名缺口
  （`gap_impact` + `next_evidence`），不得静默省略。
- 无官方考纲或无官方教材计划 → 放行等级非 `L1` → 零 AI 产物；读者看到的是缺口说明，不是猜测内容。

## Locked decisions（2026-09-11 clarify，用户逐项确认）

- **D1 双层内容模型。** 官方事实层（`official`）只允许官方来源，沿用现有硬闸门；AI 备考层（`ai`）为新增层，
  每块内容必须携带 `ai_generated: true` + `generator`（后端 / 模型 / 提示词 id / 提示词版本 / 生成时间）
  + `evidence_refs`（指向官方证据或知识模型节点），页面显著标注，**绝不冒充官方**。
- **D2 生成引擎。** 仓库内 Python CLI 为生产路径（OpenAI 兼容 API，提示词版本化、JSON schema 固定、CI 用录制 fixture 离线回归）；
  harness agent 为同一 JSON schema 的第二执行体（无 key 环境的兜底）。二者产出必须逐字段同构。
- **D3 产物形态。** MVP 为静态站页面（MkDocs），页面由 JSON **确定性渲染**，禁止手工双写正文；
  导出（Anki / CSV）与站内交互（自测、进度）不在本 spec 范围，留作后续批次。
- **D4 题目口径。** 官方公开样卷 / 真题原件可入库并转载题文（须登记来源与章节）；AI 生成题必须标注、挂知识点 id，
  并通过与源文档的 n-gram 抄袭检测；第三方（B/C 级）题文**永不**入库。
- **D5 覆盖批次。** 单门试点 → 全专业公共课 P0 → 计算机（080901）→ 其余专业分批。
- **D6 无考纲课程。** 一律拒绝生成（等同现状）：缺任一放行条件即保持命名缺口，不用 AI 补章号、考点、年份或分值。
- **D7 自动取证。** 流水线内置 jseea.cn 官方检索 / 快照 / 哈希入库 / 基线登记；域名白名单限定，CI 走离线 fixture。
  **B1 例外（PM 处置，2026-09-11）**：本迭代内 `ops/jiangsu/source-links.baseline.json` 保持**只读**（两个既有测试断言其 `git diff` 为空），
  且不在仓库内落盘新快照；「基线登记」与联网入库在 **B2** 首次真实取证时启用。
- **D8 放行门槛（唯一）。** `syllabus.status == extracted`（官方考纲原件已入库且抽取成功）
  **且** `textbook_plan.status == matched`（官方教材计划行匹配成功）→ `eligibility.level = L1`，允许全量生成。
  任一不满足 → `L1` 之外无其他可生成等级，页面保持缺口。
- **D9 生命周期上限。** 机器产物上限 `machine_ready`；不得写 `reviewed: true` / `reviewer` / `publishable`（沿用不变量）。
- **D10 单一真源。** 课程代码与名称以 `sources/jiangsu/catalog/courses.json` 为 SSOT；页面表格由该 JSON 渲染。

## Content model（两层与放行）

| 层 | 允许内容 | 来源要求 | 机器字段 | 生命周期上限 |
| --- | --- | --- | --- | --- |
| `official` 官方事实层 | 课码 / 课名 / 学分 / 考试方式 / 考纲章节目录 / 考核要求原文 / 题型声明 / 教材计划行 / 官方样卷题文 | 必须 jseea.cn 或其他明确官方机构；逐条记 URL 或仓内抽取件路径 + 定位 | `provenance`（doc_id / locator / sha256） | `machine_ready` |
| `ai` AI 备考层 | 讲解 / 要点梳理 / 易错点 / 记忆法 / 生成题与解析 / 学习流程细化 / 复习排程 | 必须挂 `evidence_refs`；不得声明官方立场 | `ai_generated` + `generator` + `review_state` | `machine_ready` |

放行判定（D8）在 `sources/jiangsu/courses/<code>/evidence.json` 内持久化，渲染与闸门都读它，禁止各处重复判断。

## Scope

### In scope

> 本迭代（`jiangsu-ai-course-pipeline-2026-09-11`）的 In scope = **B1 切片**，对应 plan
> `.mstar/plans/ai-course-prep-pipeline-b1.md`（6 个 task，`Execution mode: sdd`）。
> 课程范围：`15040` 单门端到端（七类页面）+ 现有 18 门课程的 `evidence.json` 放行判定数据。
> 其余 17 门课程的页面重渲染**不在本迭代**（随各自批次）。

- 课程目录数据底座（`sources/jiangsu/catalog/`）与课码 / 课名解析。
- 取证与放行判定（`evidence.json`）与 jseea.cn 自动取证。
- 考纲 → 知识模型（章 / 节 / 考核点 / 能力层次 / 本章重点 / 题型 / 样卷入口）的结构化抽取与覆盖率统计。
- AI 备考层生成、标注契约、抄袭检测、LLM 适配（CLI + agent 双后端）。
- JSON → Markdown 确定性渲染、分章页面、站点集成。
- 闸门新增 `evidence` / `ai-content` 两层；`run-gates.py`、CI、测试与 ops 文档同步。
- 试点课程端到端打通（`15040`），并以既有手工知识树为黄金参照比对。

### Out of scope

> 下列条目**本迭代一律不启动**；B2–B4 的触发条件见 § Roadmap。
> 注意区分：B1 为现有 18 门课产出的 `evidence.json` 是**放行判定数据**，
> 不等于该课已进入内容生成批次（`L1` 课程的 AI 备考层与渲染仍按批次推进）。

- B2（全专业公共课 P0：`15040` / `15043` / `15044` / `13000` / `00023`）、B3（080901 计算机 27 门）、B4（其余专业分批）三个批次本身：
  其知识模型、AI 备考层与渲染页不在本迭代产出。
- 其余 17 门现有课程页面的重渲染（本迭代只渲染 `15040` 一个课程目录）。
- 交互式题库、自测、学习进度与账号体系。
- Anki / CSV / 打印版导出。
- 实践课（`00899` / `02334` / `04736` / `04748` / `13004` / `13014` / `14976` 等）的生成路径；其依据是主考学校实践考核要求，需单独定义来源口径。
- 真人审核 / 法务终审 / `publishable` 提升（仍为人工职责）。
- 私有仓 `zikao-materials` 内容入库与 `materials://` 解析扩展。
- 第三方站点（自考365、自考生网、B 站等）内容转载。

## Acceptance criteria

每条验收均为**客观可判定**：给出命令（含预期退出码）、可观察产物或可数集合，不含「合理 / 完善 / 大致」类判断。
验收 1–9 与 plan task 的映射见 `.mstar/plans/ai-course-prep-pipeline-b1.md` § Plan self-review（编号不得重排）。

1. **一条命令端到端**：`python scripts/build-course-content.py build 15040 --backend replay` → **exit 0**，
   依次跑完 `resolve → acquire → evidence → model → generate → render → gate` 七阶段，
   产出 `content/jiangsu/courses/15040/` 的七类页面：六页 `index` / `syllabus` / `plan` / `practice` / `review` / `sources`
   + `knowledge/*.md` 共 **18 个章页**（导论 + 17 章）。
   缺任一前置条件时该命令 **exit ≠ 0**，stderr 报出缺失阶段名与原因，且**不产出半成品**
   （失败路径下 `content/jiangsu/courses/15040/**` 无新增或改写文件）。
   *命令形态以 plan § Target-state module map 的 CLI 契约为准（`build <query>` + `--backend`）。*
2. **目录覆盖面（可数）**：`python scripts/build-course-catalog.py --check` → exit 0（幂等）；
   `sources/jiangsu/catalog/courses.json` 的唯一课码 **≥ 60**，且覆盖
   `content/jiangsu/courses/` 下全部 **18** 个课码目录与 `content/jiangsu/majors/` 下全部 **54** 个专业页课程表所涉课码
   （`tests/test_course_catalog.py::test_catalog_covers_existing_pages`）；
   同名 / 同学分不一致**不自动取舍**，逐条写入 `conflicts[]`（含两侧值与来源 `locator`）。
3. **课码 / 课名解析**：`resolve_course()` 对 `15040` → `15040`、`中国近现代史纲要` → `15043`、
   `java 语言程序设计（一）` → `04747`（大小写 / 全角半角括号 / 空格归一）；
   构造两门同名课时返回 `status == "ambiguous"` 且 `len(candidates) == 2`；无匹配返回 `status == "not_found"`。
   证据：`tests/test_course_catalog.py::test_resolve_by_code_and_name` / `::test_resolve_ambiguous_returns_candidates`。
4. **放行与零 AI 产物**：`sources/jiangsu/courses/<code>/evidence.json` 覆盖现有 18 门课程页课码（**18 份**）；
   `eligibility.level == "L1"` 的集合**恰为** `{15040, 15043, 15044, 04747, 02333, 04751, 00898}`（**7 门**，plan Task 2 Step 5 的实测口径），
   其余 **11 门** `blocked` 且 `reasons` 非空；
   非 `L1` 课程**零 AI 产物**（`content.json` 不存在，`tests/test_course_evidence.py::test_blocked_course_has_no_generated_artifacts`）；
   每个 `named_gap`（命名缺口）字段含非空 `gap_impact` + `next_evidence`。
   实测与上述集合不符时**不得放宽判定**：按 STOP 回报并回写 plan。
   **实测留痕（2026-09-11，plan Task 2）**：`python scripts/build-course-content.py evidence --all` → exit 0，18 份
   `sources/jiangsu/courses/<code>/evidence.json`；`L1` 实测集合 = `{00898, 02333, 04747, 04751, 15040, 15043, 15044}`
   （**7 门**，与上式逐元素相等，未触发 STOP）；`blocked` **11 门** = `{00023, 02324, 03708, 03709, 04735, 13000, 13003,
   13013, 13015, 13017, 13180}`，`reasons` 恒为 `[syllabus:*, textbook_plan:*]` 有序二元组（逐门取值见 plan
   § Current state「双齐实测」行）；非 `L1` 课程零 AI 产物由
   `tests/test_course_evidence.py::test_blocked_course_has_no_generated_artifacts` 锁定。
   **口径说明（实测更正）**：`syllabus.status == "extracted"` 的判据 = 考纲抽取件内**能定位「考核知识点与考核要求」小节**；
   该小节序号随高纲批次不同（`15040` / `15043` / `15044` 为 `三、`，`00898` / `02333` / `04747` / `04751` 为 `二、`），
   因此判定取小节名稳定部分，命中标题逐字记入 `evidence.json` 的 `syllabus.requirements_heading` 以便复核；
   `textbook_plan` 的教材计划区 = **首个**含表头 `教材代号` 的行起至文档末尾（表头逐页重复），区之前的考试日程区课码出现不算教材行。
5. **知识模型覆盖率与手工比对**：`sources/jiangsu/courses/15040/knowledge-model.json` 的 `coverage.ratio ≥ 0.90`；
   章数 **18** 且章标题与 `content/jiangsu/courses/15040/syllabus.md` 章目**逐字一致**；
   `coverage.official_point_count` 与手工页 `content/jiangsu/courses/15040/index.md:549` 记录的 **61** 个节级知识点比对，
   差异**逐条**写入 `coverage.diff_vs_manual`（每条含手工侧 locator + 模型侧 `point_id` 或 `named_gap`）；
   未编号段落记入 `chapters[].unmodeled[]`，**不编造**章号 / 考点。
   （`coverage.diff_vs_manual` 的字段名与元素形状以 `.mstar/plans/ai-course-prep-pipeline-b1.md` § Data contracts 3 为准；本条只要求「手工侧 locator + 模型侧 `point_id` 或 `named_gap`」的逐条留痕。）
6. **AI 标注合同**：`stage_plan[]`、`blocks[]` 与 `review_schedule`（含其 `plans[]` 每一档）每一项均含
   `ai_generated: true` + `generator`（`backend` / `model` / `prompt_id` / `prompt_version` / `generated_at`）+ 非空 `evidence_refs` + `review_state`；
   `kind == "drill"` 的块含 `answer_md` 与 `source_kind ∈ {"ai_generated","official_sample"}`（`official_sample` 必带 `provenance`）；
   块内 `point_id` 均存在于知识模型；渲染页保留 AI 声明横幅（文本 `本页由 AI 辅助生成`）；
   `python scripts/run-gates.py` 的 `ai-content` 层对「缺字段 / 无锚点 / 8-gram 重合率 > 20%」三类坏数据**分别失败关闭**。
7. **来源可追溯**：`evidence.json` / `knowledge-model.json` 中每个官方事实字段带 `doc_id` + `locator`；
   官方原文 `quote` ≤ 60 字符且不使用 `>` 引用块；
   不存在「`status: "verified"` 但缺 `provenance`」的字段，无来源的数字 / 日期 / 章号 / 分值一律 `status: "named_gap"`；
   `evidence` 层闸门对非法 `status` / 缺 `gap_impact` / 不存在的 `point_id` 失败关闭。
8. **全绿命令集（逐条 exit 0）**：
   `python scripts/run-gates.py`（含新增 `evidence` / `ai-content` 两层）→
   `.venv/bin/python -m pytest -q` → `ruff check scripts tests` →
   `python scripts/check-source-links.py --offline` → `mkdocs build --strict` → `git diff --check`；
   且 CI 链路不联网、不调用 LLM：`.github/workflows/deploy-pages.yml` 不设置 `ZIKAO_LLM_*` 环境变量，
   LLM 交互一律走 `tests/fixtures/course_pipeline/` 录制 fixture。
9. **无 key 环境（agent 后端）**：`python scripts/build-course-content.py generate 15040 --backend agent` 在无 `ZIKAO_LLM_API_KEY` 时
   产出 `content.json` 并通过同一套闸门（缺回填结果即显式失败，**不伪造**）；
   「逐字段同构」的判定 = 两后端产出对同一 JSON schema 校验均通过（同一 `llm_client` 校验路径），
   且 `blocks[]` / `stage_plan[]` 的必需字段集合一致；
   `--backend replay` 复跑与首次生成在归一 `generated_at` 后一致（幂等）。

## Roadmap（批次 · Durable Roadmap Gate）

**迭代边界（硬）**：本迭代 `jiangsu-ai-course-pipeline-2026-09-11` 只交付 **B1**。
B2–B4 是**后续迭代**的批次，各自必须满足下表「启动门槛（触发条件）」才可启动；
任何文件、页面或汇报都不得写成「本迭代会做 B2–B4」。

| 批次 | 迭代归属 | 范围 | 启动门槛（触发条件） | 完成定义 | Owner |
| --- | --- | --- | --- | --- | --- |
| **B1** | **本迭代（唯一交付切片）** | 数据底座（catalog + resolver）、取证与放行、知识模型、AI 备考层与两层闸门、确定性渲染；**`15040` 端到端试点** | 无（基线 `6d17ae9`，spec 已锁） | 验收 1–9 全绿；`15040` 生成页与手工页可比对 | `.mstar/plans/ai-course-prep-pipeline-b1.md` |
| **B2** | 后续迭代（不在本迭代） | 全专业公共课 P0：`15040` / `15043` / `15044` / `13000` / `00023` | ① B1 验收 1–9 全绿（plan Done）；② `O2`（真题授权边界）与 `O4`（LLM 预算上限）书面收敛；③ 自动取证能拿到各课官方考纲 + 教材计划行，任一缺条件即停在命名缺口。**实测（2026-09-11）**：`15040` / `15043` / `15044` 已双齐；`13000` 教材行疑列错位、`00023` 考纲未入库 → 需先取证 | 五门课全部有知识模型与 AI 备考层，或显式记录为什么不能生成 | 内容维护者（`@project-manager` 派发） |
| **B3** | 后续迭代（不在本迭代） | 计算机（080901）27 门课程 | ① B2 Done；② `catalog` 能解析 080901 现行计划表 | 笔试课有知识模型；实践课显式排除并记录口径 | 内容维护者 |
| **B4** | 后续迭代（不在本迭代） | 其余专业按官方计划表分批 | ① B3 Done；② B1 流水线在 ≥ 10 门课上验证无回归 | 全量课程页由流水线产出，机器产物上限仍为 `machine_ready` | 内容维护者 |

B2–B4 未开始前不得宣称完成度；每批启动时若出现新约束，先回写本 spec 与对应 plan 再执行。
本迭代的产物边界可核验：`content/jiangsu/courses/` 下只有 `15040` 被重渲染；
B1 为现有 18 门课产出的 `evidence.json` 是**放行判定数据**，不构成该课所属批次的完成。

## Open items（未决，需后续 clarify）

> 下列四项**均不阻塞 B1**（验收 1–9 不依赖其中任何一项）。「阻塞的批次 / 收敛时点」是
> § Roadmap 启动门槛的一部分：未收敛即不得启动对应批次。

| id | 未决问题 | 对 B1 的影响 | 阻塞的批次 / 收敛时点 |
| --- | --- | --- | --- |
| **O1 实践课口径** | 实践考核课（无笔试考纲）是否引入「主考学校实践考核要求」作为独立来源类型 | 无 —— B1 只做 `15040` 试点 | 阻塞实践课的任何生成（`00899` / `02334` / `04736` / `04748` / `13004` / `13014` / `14976`）；决定前一律不生成，页面保持命名缺口 |
| **O2 真题授权** | 官方公开真题原件的版权边界与「可转载题文」范围 | 无 —— B1 只用考纲声明的样卷锚点，不转载题文 | 阻塞 **B2**；B2 启动前须与用户书面确认 |
| **O3 导出与交互** | Anki / CSV 导出与站内自测的批次位置（`D3` 的后续） | 无 | 不阻塞 B1–B4 的核心交付；归属批次由后续 clarify 决定 |
| **O4 LLM 预算** | 批量生成的费用上限与失败重试策略 | 无 —— B1 只生成 `15040` 一门 | 阻塞 **B2**；B2 启动前须给出上限值 |
