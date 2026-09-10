# jiangsu-ai-course-pipeline-2026-09-11 — Iteration Package

重构项目主干：从「人工逐课建档的官方元数据索引站」到「课码 / 课名驱动的 AI 备考内容流水线」。
本迭代只交付 **B1（数据底座 + `15040` 端到端试点）**。

## Package index

| Path | Purpose |
|------|---------|
| [`delivery-compass.md`](delivery-compass.md) | 迭代 compass（范围 / 验收 / 非目标 / 分支策略 / 风险），status SSOT |
| [`guides/direction-lock.md`](guides/direction-lock.md) | Phase 1 方向锁定与规划期实测证据（含踩坑记录） |
| [`guides/official-source-evidence.md`](guides/official-source-evidence.md) | 本迭代用到的官方来源与放行门槛实测明细 |
| [`guides/corpus-hygiene.md`](guides/corpus-hygiene.md) | §1.6 seat 3 语料卫生报告：索引完整性、术语归一、链接修正、陈旧 AC5 复核与 PM 待处置清单 |
| [`specs/iteration-scope.md`](specs/iteration-scope.md) | 迭代级范围切片说明（长期规范见 `.mstar/specs/ai-course-prep-pipeline.md`） |
| [`specs/design-notes.md`](specs/design-notes.md) | 迭代级 design note：B1 目标态模块图、分层规则、闸门语义、契约演进清单 |

## Long-term spec（不在本 package）

- `.mstar/specs/ai-course-prep-pipeline.md` — 目标状态、锁定决策 D1–D10、批次 roadmap B1–B4、开放项 O1–O4。

## Plan

| plan_id | File | Execution |
|---------|------|-----------|
| ai-course-prep-pipeline-b1 | `.mstar/plans/ai-course-prep-pipeline-b1.md` | `mstar-sdd`（6 tasks） |

## Promote at close

iteration-close（Phase 3）经 `mstar-compound` 把本 package 中可复用的实施约定提升到 `.mstar/knowledge/`；
本目录不直接写入 knowledge。
