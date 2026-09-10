# 迭代范围切片说明（iteration-scoped）

> 长期规范 = `.mstar/specs/ai-course-prep-pipeline.md`（本迭代解锁）。本文件只说明**本迭代交付哪一片**。

## 交付片：B1

| # | 交付物 | 说明 |
| --- | --- | --- |
| 1 | `scripts/lib/course_pipeline/course_catalog.py` + `sources/jiangsu/catalog/{courses,majors}.json` | 课程目录 SSOT + 课码 / 课名解析（含全半角与空格归一、歧义返回候选、冲突显式记录） |
| 2 | `scripts/lib/course_pipeline/evidence.py` + `official_source.py` + `sources/jiangsu/courses/<code>/evidence.json` | 官方取证与**唯一**放行判定（`L1` = 考纲 `extracted` 且教材计划 `matched`）；jseea.cn 白名单抓取（B1 内 `source-links.baseline.json` 只读、不落盘快照；登记在 B2 启用） |
| 3 | `scripts/lib/course_pipeline/knowledge_model.py` + `knowledge-model.json` | 考纲 → 章 / 节 / 考核点（识记 / 领会 / 应用）/ 本章重点 / 题型 / 样卷锚点 + 覆盖率 |
| 4 | `scripts/lib/course_pipeline/{llm_client,generate_content}.py` + `prompts/*.v1.md` + `content.json` | AI 备考层（讲解 / 记忆法 / 题 / 五阶段流程 / 复习排程）+ 标注契约 + 三后端（`cli` / `agent` / `replay`） |
| 5 | `scripts/lib/course_pipeline/render_pages.py` + `content/jiangsu/courses/15040/**` | JSON → 七类页面确定性渲染；`manual:` 块保留；新增 `knowledge/<NN>-<chapter>.md` 章页 |
| 6 | `scripts/lib/{evidence_gate,ai_content_gate}.py` + `run-gates.py` 接线 | 新增 `evidence` / `ai-content` 两层闸门；既有五层语义不变 |

## 不在本片

- B2（公共课 P0 五门）/ B3（080901 27 门）/ B4（其余专业）——后续迭代，见 spec § Roadmap。
- 交互式题库、Anki / CSV 导出、实践课口径、`publishable` 提升与法务终审。

## 交付顺序与依赖

`T1 catalog → T2 evidence（依赖 T1）→ T3 knowledge model（依赖 T2）→ T4 AI 备考层（依赖 T3）→ T5 渲染（依赖 T2/T3/T4）→ T6 闸门接线（依赖 T1–T5）`，同一 plan 内 **SDD 串行**。

## 无 key 环境的执行前提（用户 2026-09-11 确认）

Task 4 的真实生成走 **agent 后端为主**：由 harness agent 按版本化提示词回填与 CLI 同构的 JSON，
再用 `replay` fixture 做离线回归；两条路径产出必须逐字段同构并过同一套闸门。
