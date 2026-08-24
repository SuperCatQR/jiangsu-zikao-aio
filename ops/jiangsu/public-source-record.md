# 公开来源记录契约

公开课程页（`content/jiangsu/courses/<code>/sources.md` 等）记录官方证据时使用本表。私有 `materials://` 路径、PDF 正文、题文、内部抽取稿不得写入本契约字段。

PDF 只记录 URL + 标题 + 已声明日期；**永不拷贝 PDF 正文**。

第三方网页只能标 `discovery-lead`，不能支撑已发布结论。

## 必填列

| 列 | 说明 | 取值 |
| --- | --- | --- |
| 官方 URL | 可离线抽取的 Markdown 链接或裸 `https://...`，且位于含 `IN_SCOPE_SECTION_KEYWORDS` 的标题下 | 江苏省教育考试院、主考学校或其他明确官方机构 URL |
| 标题 | 页面或文件标题 | 原文标题；不明则写 `未声明` 不得编造 |
| 发布/适用日期 | 来源已声明的发布日或适用考期 | `YYYY-MM-DD` 或其它来源原文日期；未声明则写 `未声明` |
| 课程代码/名称匹配 | 来源上的代码与课名是否与本课一致 | `match` / `mismatch` / `unverified` |
| 核验日期 | 人工或机器核验当天 | `YYYY-MM-DD` |
| 支撑字段 | 该来源实际支撑的公开元数据 | 例如考纲版本、课名、代码；不得推断未出现的 ISBN/范围 |
| 状态 | 该条证据的公开状态 | `verified-metadata` / `missing-source` / `needs-review` / `discovery-lead` |

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `verified-metadata` | 官方 URL 已核验，且仅据此填写元数据 |
| `missing-source` | 仍缺官方公开 URL |
| `needs-review` | 有线索但匹配或日期未核完 |
| `discovery-lead` | 第三方或非官方线索，不得作为发布依据 |

## 抽取约束

`scripts/check-source-links.py` 只抽取范围内标题下的 Markdown `[text](https://...)` 或裸 `https://...`。当前 `## 来源清单` 因含「来源」而在范围内。
