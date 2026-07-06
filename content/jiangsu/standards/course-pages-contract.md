# 江苏自考课程页多页模板契约

课程目录固定为 `content/jiangsu/courses/<5位课程代码>/`，公开仓只放官方公开来源、索引、摘要；私有原件一律写 `materials://`。

## 必备页面
| 文件 | 作用 | 必备区块 |
| --- | --- | --- |
| `index.md` | 课程总览与导航 | 课程元信息、资料状态、页面导航、学习路径摘要 |
| `sources.md` | 来源链与核验 | 官方来源、materials 索引、缺口、最后核验日期 |
| `practice.md` | 真题/练习索引 | 真题覆盖状态、公开来源、materials 索引、空态说明 |
| `plan.md` | 学习计划 | 阶段目标、周计划、复习节奏、下一步 |

## 状态枚举
- `complete`：官方来源、教材/考纲、真题索引、计划均已核验。
- `metadata-only`：仅课程基础信息可靠。
- `missing-source`：关键官方来源或 materials 索引缺失。
- `needs-review`：机器生成或迁移稿，待人工复核。

## 链接约束
- 页面间必须互链：总览至少链接 `sources.md`、`practice.md`、`plan.md`。
- PDF/ZIP/RAR 私有资料不得使用公网或本机路径；只写 `materials://...`。
- 第三方网页只能作线索，不能作官方依据。

ponytail: 当前只校验结构与关键字；待页面稳定后再校验 frontmatter schema 与 MkDocs nav。


---

源文件：`ops/jiangsu/course-pages-contract.md`。
