# B1 设计说明（迭代级 design note）

> **位置与边界（先读）**：本文件属于本迭代 package —— `{ITERATION_DIR}/jiangsu-ai-course-pipeline-2026-09-11/specs/`，
> **不是**长期规范（`{SPECS_DIR}/ai-course-prep-pipeline.md`），**也不是** `{KNOWLEDGE_DIR}` 的知识文档。
> 长期规范与锁定决策（D1–D10）在 spec；本文件只说明 **B1 切片**的目标态模块图、分层规则、闸门语义与契约演进清单。
> iteration-close 时由 `mstar-compound` 决定其中哪部分值得提升为知识。
>
> - **作者 / 时点**：`architect`（Phase 1 review-and-edit chain，seat 2 / 3），2026-09-11。
> - **基准**：base commit `6d17ae924747899b3608d16b3424120fa4344e1c`（`main`）；所有锚点均在该 commit 上复核过。
> - **上游**：`.mstar/specs/ai-course-prep-pipeline.md`（`## Content model` / `## Locked decisions`）、
>   `.mstar/plans/ai-course-prep-pipeline-b1.md`（可执行 plan，接口与契约的 SSOT）、
>   `delivery-compass.md`（AC1–AC9）、`guides/official-source-evidence.md`（实测证据索引）。

---

## 1. 目标状态模块图（target state）

三层职责，**每个产物只有一个写入者**：

```text
                     ┌─────────────────────────── 数据底座层 ───────────────────────────┐
content/jiangsu/majors/*/sources/plan.raw.txt ─┐
content/jiangsu/majors/*/index.md（现行课程表）─┼─► course_catalog.py ─► sources/jiangsu/catalog/
sources/jiangsu/processed/major-source/**      ─┘                        {courses,majors}.json
                                                                          （课码 / 课名 SSOT）
                     ┌────────────────────── 取证与抽取层（确定性，无 LLM） ──────────────┐
sources/jiangsu/processed/syllabus/<code>-*/document.extracted.md ─┐
sources/jiangsu/processed/textbooks/*/document.raw.txt（4 份）     ─┼─► evidence.py ─► sources/jiangsu/courses/
ops/jiangsu/source-links.baseline.json（只读输入）                 ─┘   （evaluate_eligibility 唯一判定）
                                                                        <code>/evidence.json
考纲抽取件（三、考核知识点与考核要求）─► knowledge_model.py ─► <code>/knowledge-model.json
                     ┌──────────────────── AI 备考层（唯一允许 LLM 的层） ────────────────┐
knowledge-model.json ─► generate_content.py ─► llm_client.py ─► <code>/content.json
                        （五阶段 / explain / memorize / drill / review_schedule）
                        后端：cli（生产）· agent（无 key 兜底）· replay（CI 离线 fixture）
                     ┌──────────────────── 渲染与闸门层（确定性，不联网） ───────────────┐
三份 JSON ─► render_pages.py ─► content/jiangsu/courses/<code>/{index,syllabus,plan,practice,
                               review,sources}.md + knowledge/<NN>-<slug>.md（18）
                     └─► run-gates.py：content · materials · contract · publish · maturity-check
                                      + evidence · ai-content（新增两层，fail-closed）
```

**入口（唯一）**：`scripts/build-course-content.py`，子命令 `build | resolve | evidence | model | generate | render | fetch-source`，
阶段 `resolve → acquire → evidence → model → generate → render → gate`，`--backend cli|agent|replay`。
`scripts/build-course-catalog.py` 只是 spec AC2 固定命令 `--check` 的薄入口，**不是**第二个流水线入口。

**模块与所有权**（路径 → 唯一写入者）：

| 产物 | 唯一写入者 | 说明 |
| --- | --- | --- |
| `sources/jiangsu/catalog/{courses,majors}.json` | `course_catalog.py` | 课码 / 课名 SSOT；页面表格不得手工双写 |
| `sources/jiangsu/courses/<code>/evidence.json` | `evidence.py` | 放行判定唯一落点（`eligibility`） |
| `sources/jiangsu/courses/<code>/knowledge-model.json` | `knowledge_model.py` | 官方事实（考纲结构）唯一结构化形态；确定性、无 LLM |
| `sources/jiangsu/courses/<code>/content.json` | `generate_content.py` | AI 备考层唯一落点，四件套标注 |
| `content/jiangsu/courses/<code>/**` | `render_pages.py` | 由三份 JSON 确定性渲染；`manual:` 块原样保留 |
| `ops/jiangsu/source-links.baseline.json` | —（只读） | 既有基线；本迭代零改动（见 §4） |

**B1 不落地的东西**（接口预留，产物不产）：B2–B4 批次课程的知识模型 / AI 备考层 / 页面；真人审核与 `publishable` 提升；
Anki / CSV 导出；交互式题库；实践课生成路径；官方原件（PDF）入库。

---

## 2. 分层规则：官方事实层 vs AI 备考层

| | `official` 官方事实层 | `ai` AI 备考层 |
| --- | --- | --- |
| 允许内容 | 课码 / 课名 / 学分 / 考试方式 / 考纲章节与考核要求原文（≤ 60 字符引文）/ 题型声明 / 样卷锚点 / 教材计划行 / 来源记录 | 讲解 / 要点梳理 / 易错点 / 记忆法 / 生成题与解析 / 学习流程细化 / 复习排程 |
| 来源要求 | jseea.cn 或其他明确官方机构；逐条 `doc_id` + `locator`（+ 抽取件 `path` / `sha256`） | 必须挂非空 `evidence_refs`（指向官方证据或知识模型节点）；不得声明官方立场 |
| 机器字段 | `provenance`（`doc_id` / `locator` / `sha256`）、`status ∈ {verified, named_gap}` | `ai_generated: true` + `generator`（`backend` / `model` / `prompt_id` / `prompt_version` / `generated_at`）+ `review_state` + `evidence_refs` |
| 页面落点 | `index.md`、`syllabus.md`、`sources.md` | `plan.md`、`practice.md`、`review.md`、`knowledge/*.md` |
| 页面横幅 | **不得**出现 `本页由 AI 辅助生成` | **必须**出现该横幅（页面级）+ 块级 `generator` / `evidence_refs` / `review_state` 脚注 |
| 生命周期上限 | `machine_ready` | `machine_ready`（不得写 `reviewed: true` / `reviewer` / `publishable`） |
| 放行条件 | 始终产出（缺则写命名缺口） | 仅当 `eligibility.level == "L1"` 才产出；否则**零 AI 产物** |

**分层不变量（可测）**：

1. **分区呈现**：AI 块只出现在上表「AI 备考层页面落点」；`index.md` / `syllabus.md` / `sources.md` 只呈现官方事实。
   测试形态 = 横幅**存在**与**缺席**双向断言（`test_ai_banner_presence_and_absence`）。
2. **不冒充官方**：页面任何位置不得以「官方」修饰 AI 内容；`sources.md` 保持 100% 官方事实（AI 块的生成器标注写在 AI 块所在页面）。
3. **禁止手工双写**：官方事实只由 JSON 渲染；`manual:` 块只能承载非事实性正文（说明 / 方法 / 边界 / 通用节奏模板）。
4. **禁止推断**：无来源的数字 / 日期 / 章号 / 分值一律 `named_gap` + `gap_impact` + `next_evidence`。
5. **引文边界**：`quote` 字段任何情况下 ≤ 60 字符且逐字来自官方文本；`>` 引用块 ≤ 80 字符（`MAX_BLOCKQUOTE_CHARS`）。
   **B1 不产生 `official_sample` 块、不转载样卷 / 真题题文**（spec `O2` 未收敛）：只登记 `exam.sample_paper` 锚点，
   枚举值 `official_sample` 仅由测试构造校验。
6. **唯一放行门槛**：`syllabus.status == "extracted"` **且** `textbook_plan.status == "matched"` → `L1`；
   判定只写在 `evidence.json.eligibility`，渲染层与闸门层只读，不得各处重判。

---

## 3. 闸门语义（fail-closed）

新增两层接在既有五层之后（`DEFAULT_LAYERS` 末尾），**不改变既有五层语义**：

| 层 | 覆盖对象 | 失败关闭（`list[str]` 非空 → `run-gates.py` exit 1） |
| --- | --- | --- |
| `evidence` | 18 份 `evidence.json` + 1 份 `knowledge-model.json` | `facts[*].status` 非法；`verified` 缺 `provenance`；`named_gap` 缺 `gap_impact` / `next_evidence`；非 `L1` 课程存在 `content.json`；`quote` > 60 字符；point `id` 重复 / 格式不符；`coverage.ratio < 0.90`；`diff_vs_manual[].kind == "manual_only"` |
| `ai-content` | 仅**存在 `content.json`** 的课程 | 标注四件套缺失（`blocks[]` / `stage_plan[]` / `review_schedule` 及其 `plans[]`）；`point_id` 不存在于知识模型；`drill` 缺 `answer_md` / `source_kind`；`official_sample` 缺 `provenance`；`stage_plan[]` 非 5 条；8-gram 与考纲重合率 > 20%；AI 页缺横幅 / `official_only` 页出现横幅；缺 generated-by 注释 |

**作用域规则（硬）**：新层**只对存在产物的课程生效**。`evidence` 层校验全部 18 份 `evidence.json`（B1 会为现有 18 门课产出），
但目录缺 `evidence.json` 时不报错；`ai-content` 层以 `content.json` 存在为开关 —— 其余 17 门课在 B1 结束时**必须仍全绿**。

**「无半成品」语义（spec AC1 第 3 句）**：任一阶段失败 → exit ≠ 0 + stderr `stage=<name> missing: <reason>`；
渲染先写 `tempfile.mkdtemp()` 暂存区，`gate` 阶段对暂存区校验，全部通过后才 `shutil.move` 到 `content/jiangsu/courses/<code>/`
（逐文件 `os.replace`）；失败即清理暂存区 → 失败路径下页面目录零改动。

**AC → 闸门 / 命令的落点**（避免同一件事两处判定）：

| 验收 | 落点 |
| --- | --- |
| AC1 端到端 + 无半成品 | `build <query> --backend replay`（阶段 + 暂存区语义）；`test_failed_build_writes_nothing` |
| AC2 目录覆盖 | `build-course-catalog.py --check` + `tests/test_course_catalog.py` |
| AC3 课码 / 课名解析 | `resolve_course` + 同名歧义测试 |
| AC4 放行与零 AI 产物 | `evidence` 层 + Task 2 Step 5 的实测集合回写 |
| AC5 知识模型与手工比对 | `evidence` 层（`ratio` / `diff_vs_manual`）+ Task 3 比对步骤 |
| AC6 AI 标注合同 | `ai-content` 层（三类坏数据分别失败关闭）+ 渲染横幅测试 |
| AC7 来源可追溯 | `evidence` 层 + 渲染页来源区 |
| AC8 全绿命令集 | `run-gates.py`（7 层）→ `pytest -q` → `ruff` → `check-source-links.py --offline` → `mkdocs build --strict` → `git diff --check` |
| AC9 无 key 环境 | `generate --backend agent` + `replay` 幂等（fixture 必须覆盖全课） |

---

## 4. 本 plan 演进的契约清单（explicit）

`create` = 新增契约；`additive` = 只追加、不改变既有字段；`none` = 明确**不改**并给出理由。

| 契约 / 文件 | 处置 | 说明与执行者 |
| --- | --- | --- |
| `sources/jiangsu/catalog/{courses,majors}.json` | create | 课码 / 课名 / 专业覆盖 SSOT（plan Data contracts 1 / 1b），Task 1 |
| `sources/jiangsu/courses/<code>/evidence.json` | create | 放行判定唯一落点（Data contracts 2），Task 2 |
| `sources/jiangsu/courses/<code>/knowledge-model.json` | create | 章 `ordinal`/`slug`、point `id = <code>-<slug>-s<n>-p<m>`、`unmodeled[]`、`coverage.diff_vs_manual` + `manual_reference`（Data contracts 3），Task 3 |
| `sources/jiangsu/courses/<code>/content.json` | create | AI 备考层标注四件套 + `review_schedule.plans[]` 元素 schema + 三档 30/14/7 口径（Data contracts 4），Task 4 |
| `ops/jiangsu/schemas/course.schema.json` | additive | `optional_files` 增 `"knowledge/"`；新增键 `generated_page_markers`（`any` / 各 AI 页的横幅 / `official_only`）。**不改** `required_files` / `page_markers` / `frontmatter` —— 改它们会打红其余 17 门课。Task 5 |
| `scripts/lib/course_pages_contract.py` | **none** | `check_course_dir` 只校验 schema 的 `required_files` + `page_markers`（4 个必备文件），且只遍历课码目录一层；新页与横幅 marker 交给 `ai-content` 层按 `generated_page_markers` 校验。把 `knowledge/` 写进必备清单会破坏其余 17 门课 |
| `scripts/run-gates.py` | modify | 三处：`DEFAULT_LAYERS`（`:31`）追加 `"evidence","ai-content"`；import 区（`:26-29`）两行；`runners` 字典（`:107-114`）两项。既有五层顺序与语义不变。Task 6 |
| `tests/test_practice_index_framework.py` | **none** | 该文件锁 `practice.md` 首行 canonical H1、H2 恰为 4 个、`历年真题` 状态、引用块上限（18 门课共用）。渲染器**满足**它（generated-by 注释放 H1 之后、AI 练习块用 `###`），不放宽测试。Task 5 |
| `tests/test_site_integration.py` / `tests/test_15040_chapter_index.py` / `tests/test_chapter_index_study_plan.py` | **none** | 五页齐备 / 互链栏对称 / `## 开始学习` 四步 / 18 行章目 / 部次表 / 来源状态 / 不复述 PDF 正文 —— 全是渲染必须满足的冻结断言，Task 5 Step 4 一次全绿 |
| `ops/jiangsu/source-links.baseline.json` | **none（只读）** | 两个测试断言其 `git diff` 为空；离线投影仍由既有 `scripts/snapshot-official-sources.py` 负责。Task 2 已删除「追加登记 baseline」的旧写法 |
| `sources/jiangsu/public-official/**` + `pdf-processing-manifest.csv` | **none（不写入）** | `sources/**/*.pdf` 受 Git LFS 管辖（`.gitattributes:4`），manifest 行要求 `source_sha256` 与实文件一致；B1 已有仓内抽取件，联网抓取只在测试中以 `tmp_path` 覆盖。真实原件入库按 spec § Roadmap 的 B2 启动门槛③ |
| `mkdocs.yml` | **none** | `nav` 不含 `courses/**` 不触发 `--strict` 失败（`validation.nav.omitted_files = info`，mkdocs 1.6.1 实测默认值）；真正约束是 `validation.links.not_found = warn` → 渲染器必须保证每个相对链接指向存在的 `.md` |
| `ops/jiangsu/course-pages-contract.md`、`ops/jiangsu/content-standard.md`、`CONCEPTS.md`、`README.md` | modify（文档） | 新页契约 / 双层内容标准 / 新概念（官方事实层、AI 备考层、`L1`、`named_gap`）/ 流水线用法。Task 6 |
| `.github/workflows/deploy-pages.yml` | **none** | 既有步骤会自动带上新层；CI 不设 `ZIKAO_LLM_*`，LLM 交互全走 fixture |
| `.mstar/specs/ai-course-prep-pipeline.md` | **none（seat 2 范围内未改）** | `## Content model` 与 plan 逐条对齐，无漂移；spec AC5 关于「`coverage.diff_vs_manual` 尚未在 plan 列出」的括号说明在 plan 补齐契约后已过时，但 AC 文本由 seat 1 / 用户冻结，改动留待 PM（见 §5） |

---

## 5. 留给实现者 / PM 的边界事项

- **实现者**：plan 的每个 task 都带 In / Out / STOP；`--backend replay` 必须覆盖全课 61 个考核点（fixture 不全即 STOP，禁止兜底模板）。
- **实测回写**：Task 1 / 2 / 3 各自要求在完成时把实测数字（唯一课码数、`L1` 集合、章数与 `coverage`）回写 plan；`L1` 集合不符时按 spec AC4 停并回写，**不得**放宽判定。
- **PM / seat 1**：spec AC5 末尾括号「plan Data contracts 3 的示例 JSON 尚未列出该字段」已被本 seat 的 plan 编辑解决（`coverage.diff_vs_manual` 已入契约），该句可在下次 spec 编辑时清理；spec 的 Intent / Reader outcome / AC / Roadmap 措辞不在本 seat 的编辑范围。
- **不做什么**：本文件不设计 B2–B4 的批次内容（只保留 spec 已声明的接口影响），不引入导出 / 交互 / 账号等后续能力。
