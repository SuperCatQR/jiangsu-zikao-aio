# 课程状态机契约（P0）

> 关联：Issue #52。本文件是 **lifecycle + completeness** 两维状态的 source of truth。  
> Emoji（🔴🟡🟢）仅用于页面展示，**不得**作为机器闸门判断依据。

## 一、lifecycle（发布流水线位置）

| 值 | 含义 | 展示建议 | 机器行为 |
| --- | --- | --- | --- |
| `draft` | 建设中 / 骨架 | 🔴 建设中 | 闸门不阻断 |
| `machine_ready` | 机器初稿已齐，待审查 | 🟡 机器初稿 | 闸门不阻断；应保留 AI 提示横幅 |
| `in_review` | 人工审查进行中 | 🟡 审查中 | 闸门不阻断 |
| `publishable` | 声称可对外发布 | 🟢 可发布 | **触发** `validate-publish-gate.py` 硬阻断 |

Frontmatter 字段：`lifecycle: <上表>`。

兼容：历史字段 `status: yellow|draft|…` 由迁移脚本映射为 lifecycle；新页面只写 `lifecycle`。

## 二、completeness（资料/内容完备度）

| 值 | 含义 |
| --- | --- |
| `complete` | 官方来源、教材/考纲索引、真题索引、计划均已核验 |
| `metadata-only` | 仅课程基础信息可靠 |
| `missing-source` | 关键官方来源或 materials 索引缺失 |
| `needs-review` | 机器生成或迁移稿，待人工复核资料完备度 |

Frontmatter 字段：`completeness: <上表>`。  
页面表内「资料状态」列应与此字段一致，**禁止**再用 completeness 冒充 lifecycle。

## 三、不变量

1. **仅人工**（PR 审查 / 法务）可将 `lifecycle` 设为 `publishable`；自动化 agent 不得伪造 `reviewed: true`。
2. `publishable` 时必须同时满足：`reviewed: true`、`reviewer` 非空，且通过发布闸门（见 `publish-gate-contract.md`）。
3. 存量迁移：`draft`/缺省 → `draft`；`yellow` → `machine_ready`；**禁止**批量升为 `publishable`。
4. 页面成熟度（`compute-page-maturity.py`）读取两维组合，不再把孤立 `status: complete` 当作 green。

## 四、存量映射表

| 旧 frontmatter `status` | 新 `lifecycle` |
| --- | --- |
| （缺省） | `draft` |
| `draft` | `draft` |
| `yellow` | `machine_ready` |
| `red` | `draft` |
| `green` / 冒用 `complete` | 迁移时压为 `machine_ready`（须人工再升） |

## 五、命令

```bash
# 迁移（可先 --dry-run）
python scripts/migrate-course-status.py --dry-run
python scripts/migrate-course-status.py

# 发布闸门（仅 publishable 硬失败）
python scripts/validate-publish-gate.py

# 生产构建
python scripts/validate-content.py
python scripts/validate-publish-gate.py
pytest -q
python scripts/check-source-links.py --offline
mkdocs build --strict
```
