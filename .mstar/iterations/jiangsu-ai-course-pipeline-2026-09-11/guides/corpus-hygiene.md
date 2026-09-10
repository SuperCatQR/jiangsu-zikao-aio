# 迭代语料卫生报告（Phase 1 §1.6 seat 3）

## 0. PM 处置（2026-09-11，Phase 1 锁 compass 前）

seat 3 抛出的 P1–P9 由 `@project-manager` 逐条处置（P8 属 PM 自有文件）：

| # | 处置 | 落点 |
| --- | --- | --- |
| P1 | **已修**：AC5 尾注改为指向 plan § Data contracts 3（去掉循环引用与「尚未列出」的陈旧表述） | `.mstar/specs/ai-course-prep-pipeline.md` AC5 尾注 |
| P2 | **已修**：D7 增「B1 例外」——baseline 只读、不落盘新快照，登记能力 B2 启用；同步 direction-lock D7 行与 `specs/iteration-scope.md` 交付物 2 | spec D7 / guides/direction-lock.md / specs/iteration-scope.md |
| P3 | **已修**：`080901/index.md` 课码计数改为**边界感知 98 token / 去重 25 门**（主表 `:39-63` 55 token），并写明 naive `\d{5}` 会得 108/26 且注入伪课码 `08090`；Task 1 测试断言同步 | plan § Current state / Task 1 Step 1 |
| P4 | **已修**：`manual_locator` 示例行号 `:520` → `:125`（手工知识树首条） | plan § Data contracts 3 |
| P5 | **已修**：`000151` 锚点 `:1435` → `:1436`（含 Task 2 反例测试与 § Follow-ups F3 两处） | plan Task 2 Step 1 / § Follow-ups |
| P6 | **已收紧**：AC6 的标注覆盖面加入 `review_schedule`（含 `plans[]` 每一档），与 plan Task 4 Step 1 的既有测试对齐 | spec AC6 |
| P7 | **已修**：删除 Task 2 Step 3 中对本 plan 早期草稿的自指（「旧的…写法已删除」） | plan Task 2 Step 3 |
| P8 | **已修**：snapshot plan 行 `metadata.iteration_refs` 补齐 `guides/official-source-evidence.md`、`specs/design-notes.md`、`guides/corpus-hygiene.md` | `{WORKFLOW_DIR}/jiangsu-ai-course-pipeline-2026-09-11/snapshot.json` |
| P9 | **已修**：`run-gates.py` 未知层 `exit 2` 行号 `:100-104` → `:100-105` | plan § Current state |

---

> **作者 / 时点**：`writing-specialist`（review-and-edit chain seat 3），2026-09-11。
> **范围**：本轮 `{SPECS_DIR}` corpus hygiene + 措辞/术语/索引/交叉引用/放置。
> **不含**：决策、验收编号、契约、接口签名、范围与 task step 的实质内容（只做措辞、结构、术语、放置）。
> **基准**：工作树（control worktree `/root/workspace/jiangsu-zikao-aio`，分支 `iteration/jiangsu-ai-course-pipeline-2026-09-11`）。
> 行号均为**本轮编辑后**的工作树行号。

---

## 1. 索引完整性（逐行核对）

核对方式：逐条抽取索引行内的链接目标并 `os.path.exists` / `os.path.isfile` 判定，并与同目录实际文件集合双向比对。

| 索引 | 行 → 目标 | 目标存在？ | 处置 |
| --- | --- | --- | --- |
| `.mstar/specs/README.md` | `ai-course-prep-pipeline.md` | 是 | **补行**（新 spec 原先未登记） |
| 同上 | `public-source-content-loop.md`（两处） | 是 | Status 改为 `locked (partially superseded)`，Scope 补一句「哪些条款继续有效」（描述准确性） |
| `.mstar/iterations/README.md` | 7 行 ↔ 磁盘 7 个迭代目录 | 全部存在 | **补 1 行**：`jiangsu-course-completion-xl-2026-08-25`（目录在、行缺失；状态 `completed` 取自其 compass frontmatter） |
| `.mstar/knowledge/README.md` | 6 行 ↔ 6 份文档 | 全部存在 | 无需改动（Description 与各文档 `plan_id` 一致） |
| `<iteration-id>/README.md`（package） | 原 4 行 ↔ 磁盘 5 个文件 | 原行均存在 | **补 1 行**：`specs/design-notes.md`（文件在、行缺失） |

双向比对结果（编辑后）：package 内 5 个文件全部有行、5 行全部有文件；`{ITERATION_DIR}` 7 个目录全部有行。

**knowledge 无新增**：`.mstar/knowledge/` 仍为 `README.md` + 6 份文档（7 个文件），本轮零新增、零删除。

## 2. 术语单形化（同一概念只留一种写法）

| 概念 | 改动前存在的写法 | 归一为 | 改动位置 |
| --- | --- | --- | --- |
| AI 备考层 | `AI 层`（13 处）、`AI 备考层`（28 处） | `AI 备考层` | spec / plan / compass / direction-lock / iteration-scope / design-notes |
| 官方事实层 | `事实层`（1 处裸用）、`官方事实层`（17 处） | `官方事实层` | plan GC4 |
| 机器产物上限 `machine_ready` | `机器上限`、`机器产物最高 machine_ready`、`` `machine_ready` 上限 `` | 机器产物上限 `machine_ready` | spec（`D9`、B4 行、§ Supersede）、plan GC6、direction-lock §二 |
| 命名缺口 / `named_gap` | `named gap`（英文带空格，1 处在范围内） | 概念写「命名缺口」、机器字段写 `named_gap` | direction-lock §五 |
| 证据锚点 | `锚点`（裸用，指 AI 块证据时） | `证据锚点` | spec Reader outcome 7 |
| 证据锚点（避免同名两义） | 用「证据锚点」指测试依据行 | 断言依据 | plan § Current state `00023/plan.md:13` 行 |
| 生成器（`generator`） | `生成器信息` | 生成器标注 | design-notes §2 |
| AI 声明横幅 | `AI 横幅`（7 处） | `AI 声明横幅` | plan Data contracts 5 / Task 5 |
| Harness 路径符号 | `{SPECS_DIR}` / `{ITERATION_DIR}` / `{KNOWLEDGE_DIR}` / `{PLAN_DIR}` / `{WORKFLOW_DIR}`（仓库无 `.mstar/AGENTS.md` 定义处，HEAD 不可解析） | 具体路径 `.mstar/specs/…` 等 | package README、compass、official-source-evidence |

保留不动的两种「看似同义」写法（不是同一概念，未归一）：
- **放行门槛**（`D8` 规则）与**放行等级**（`L1` 取值）——两个概念两个词，全文用法一致。
- **生成器**（中文叙述）与 `generator`（JSON 字段名）——中文散文 / 英文标识符的分工，符合「Chinese prose, English identifiers」。
- `.mstar/knowledge/**`（英文语料）沿用其自身既定形态 `named gap`；与本迭代中文语料的「命名缺口 + `named_gap`」不混写。

## 3. 放置（misplacement）

**结论：无错放，未移动任何文件。**

核对项：
- `{SPECS_DIR}` 两份 spec 均为跨迭代长期权威（新 spec 是 plan 的 `primary_spec`，冻结决策 D1–D10 / 验收 AC1–AC9 / 批次 roadmap）；其中「本迭代只交付 B1」「B1 的 In scope」是长期 spec 对批次的门禁绑定，不是迭代草稿。
- `{ITERATION_DIR}/<id>/` 内 5 份文档均为迭代级（compass / direction-lock / 官方证据索引 / 迭代范围切片 / 设计说明），`design-notes.md` 自述其边界且被 plan § Status 引用，留在 `specs/` 正确（不是应为 `guides/` 的探索笔记）。
- `{KNOWLEDGE_DIR}` 未新增（本节第 1 条）。
- 未发现「实施踩坑原文」堆在 `{SPECS_DIR}`：解析规则、实测反例均在 package `guides/` 或 plan 的 § Current state / Follow-ups。

## 4. 交叉引用与链接

命令（对 12 份在审文件 + 6 份 knowledge 文档，共 18 份）：

```bash
python3 - <<'PY'
# 抽取所有 markdown 相对链接（跳过 http/#/mailto），按文件目录归一后 os.path.exists
PY
# -> files checked: 18 | broken relative links: 0
```

**修正的引用（原引用不可解析或与实测不符）**：

| 位置 | 改前 | 改后 | 依据 |
| --- | --- | --- | --- |
| `guides/official-source-evidence.md` | `:190-197` 定义区间 | `:190-199`（`:192` 识记 / `:194` 领会 / `:197` 应用） | `document.extracted.md` 实测（三定义止于 `:199`），与 plan § Current state 锚点一致 |
| 同上 | 教材代号 token「`<code>` 与 `<code>0` / `<code>1`」 | `^<code>\d{1,3}$`（后缀不限于 `0`/`1`） | plan § Current state 实测 + Task 2 `test_textbook_token_pattern` |
| 同上 + `guides/direction-lock.md` | 「`04747` 仅前两份文档」 | 「`04747` 命中第 1、3 份（`jiangsu-2025-04-07` / `jiangsu-2026-04-07`）」 | 逐份 `grep -c 047470`: 1 / 0 / 1 / 0 |
| `specs/design-notes.md` | `run-gates.py` import 区 `:26-30`；`runners` 字典 `:105-112` | `:26-29`；`:107-114` | 实文件行号核对，与 plan Task 6 一致 |
| package README / compass / official-source-evidence | `{SPECS_DIR}` 等 harness 符号 | `.mstar/specs/…` 等具体路径 | HEAD 可解析性（仓库无 `.mstar/AGENTS.md` 定义这些符号） |

**指向仓库之外的引用**：无（全部为仓内相对路径或官方 URL）。

## 5. 陈旧 AC5 复核（**按指派只报告、不修改**）

**spec AC5 尾括号原文**（`.mstar/specs/ai-course-prep-pipeline.md:186`）：

> （`coverage.diff_vs_manual` 的字段名以 plan Task 3 Step 1 测试为准；plan Data contracts 3 的示例 JSON 尚未列出该字段。）

**结论：该括号**已陈旧（stale）**。** 反证（plan 现文本）：

- `plan:292` —— Data contracts 3 的示例 JSON **已列出** `"diff_vs_manual": [...]`，且给出元素字段 `manual_locator` / `manual_title` / `model_point_id` / `kind` / `note`；
- `plan:312` —— 写入时机与元素形状的规则（`每次生成都写`；`manual_only` 必须逐条留痕）；
- `plan:503` —— `test_coverage_ratio_and_diff` 断言 `diff_vs_manual` 为列表且元素键集合固定。

**若 PM 决定修正**，正确表述应为：

> （`coverage.diff_vs_manual` 的字段名与元素形状见 `.mstar/plans/ai-course-prep-pipeline-b1.md` § Data contracts 3；本条只要求「手工侧 locator + 模型侧 `point_id`」的逐条留痕。）

同时注意两处**次级不一致**（同属 AC5，需 PM 一并裁决）：
1. 现值指引方向相反：AC5 说「字段名以 plan 测试为准」，plan:312 说「字段名与 spec AC5 第 3 句对齐」——互相指认对方为权威，形成循环。
2. AC5 写「模型侧 `point_id` **或 `named_gap`**」，plan 的元素形状是 `model_point_id: str|null` + `kind ∈ {matched, model_only, manual_only}`（缺模型侧时为 `null`，无 `named_gap` 取值）。

## 6. 留待 PM 处置（seat 3 不改）

| # | 位置 | 现象 | 建议 |
| --- | --- | --- | --- |
| P1 | spec:186 + plan:292/312/503 | AC5 尾括号陈旧 + 权威指引循环（见 §5） | 按 §5 给的建议句修正 AC5 尾括号（AC 号与要求本身不动） |
| P2 | spec:105（`D7`）、direction-lock:34、`specs/iteration-scope.md:10` | 三处把**基线登记**写成流水线能力/交付物之一；plan GC14 与 Task 2 则规定 `ops/jiangsu/source-links.baseline.json` 本迭代**只读**（两个既有测试断言 `git diff` 为空） | 明确 `D7` 的「基线登记」是 B2+ 自动取证路径的能力，或写明 B1 只读；`iteration-scope.md` 交付物 2 删去「基线登记」四字 |
| P3 | plan:74、plan:408 | 「5 位课码 token 共 **108** 个」只在**全页朴素 `\d{5}` 扫描**下复现；按所写范围 `:41` 起为 98（带边界）/102（朴素），主表 `:39-63` 为 55。朴素扫描会多出 `08090`（`080901` 的子串）与 `20809`（`X2080901` 的子串）两个**伪课码** | 定稿口径：现行课程表主表 `:39-63`，用带边界的 5 位 token 扫描；数字与范围二选一改准 |
| P4 | plan:293 | Data contracts 3 示例的 `manual_locator: "content/jiangsu/courses/15040/index.md:520"`：该行为 `- [ ] 考纲链接可访问或本地 PDF 路径有效`；手工知识树首条在 `:125`（`#### 0.1 … — 🟢🟡🔴`），与示例的 `manual_title` 形状一致 | 示例 locator 改为 `:125`（或任一真实树行） |
| P5 | plan:83、451、688 | `000151` 的锚点写 `:1435`；实测 `:1435` 为空行，`000151` 在 `:1436`（`:1437` 课码行、`:1438` `000159` 均正确） | 三处 `:1435` → `:1436` |
| P6 | spec:70-72（reader outcome 6）vs spec:187-191（AC6） | 「三档 30/14/7 计划齐备 / 未给输入时 `status == named_gap`」这条读者承诺**未被任何验收条目点名**：AC6 只写 `stage_plan[]` 与 `blocks[]`（compass AC6 同）；design-notes §3 的 `ai-content` 层描述把 `review_schedule` 及其 `plans[]` 纳入了 | 二选一：AC6 补写 `review_schedule[.plans[]]`，或在 spec 注明该承诺由 plan Task 4 Step 1 的两条测试承接（现已有测试，故非无覆盖，仅层级未写明） |
| P7 | plan:467（Task 2 Step 3 内） | 「旧的『追加登记到 baseline』写法已删除」引用了本 plan 的旧草稿（HEAD 无从解析） | 若要保留只读结论，改写成约束句（理由 GC14 已自足） |
| P8 | `{WORKFLOW_DIR}/jiangsu-ai-course-pipeline-2026-09-11/snapshot.json` | 该 plan 行 `metadata.iteration_refs` 只登记 3 条（compass / direction-lock / iteration-scope），未含 `guides/official-source-evidence.md` 与 `specs/design-notes.md` | 运行时文件，非本 seat 可写；PM 按需补齐 |
| P9 | plan:58（§ Current state） | 「未知层返回 exit 2（`:100-104`）」：`return 2` 实际在 `:105` | 范围改 `:100-105`（或保持块描述不改也行） |

## 7. 实现波次须知

- **`AI 层` → `AI 备考层`、`AI 横幅` → `AI 声明横幅` 是纯改名**：契约字段名（`ai_generated` / `generator` / `evidence_refs` / `review_state` / `generated_page_markers`）未动，横幅断言的唯一字面量仍是 `本页由 AI 辅助生成`。
- 教材计划区匹配口径以 **plan Task 2 与 `guides/official-source-evidence.md` §二** 为准：区边界 → 归一化 → `^<code>\d{1,3}$` → ±2 行佐证 → 四份文档并集；**跨文档分布以「第 1、3 份 / 第 2、4 份」为准**（原「前两份 / 后两份」的说法已更正）。
- 考纲三定义锚点用 `:190-199`（`:192` / `:194` / `:197`）。
- P3 / P4 / P5 属**待 PM 裁决的锚点与计数**：实现前请按 P 编号确认，勿直接照抄本 plan 现值（plan § Drift check 第 1 条已要求逐行复核锚点）。
