## 类型

- [ ] 课程页
- [ ] 专业页
- [ ] 资料索引
- [ ] 流程/模板
- [ ] 脚本/CI
- [ ] 批量迁移

## 来源与版权边界

- 官方公开链接：
- 公开仓来源：`sources/jiangsu/public-official/...`
- 派生索引/摘要：`sources/jiangsu/processed/...`
- 非公开资料引用：`materials://...`

## 状态

- 资料状态：`complete` / `metadata-only` / `missing-source` / `needs-review`
- 页面成熟度：`red` / `yellow` / `green`

## 检查

- [ ] 未提交教材电子书、第三方真题全文、答案解析或机构讲义
- [ ] 公开仓仅含官方公开来源、索引、摘要
- [ ] 符合 `ops/jiangsu/content-standard.md`
- [ ] `python scripts/run-gates.py`（7 层；含 `ai-content` —— `validate-content.py` **只**跑 content 层，不覆盖 `ai-content` 的页面到达性与 R20/R21）
- [ ] `python scripts/validate-content.py`
- [ ] `python scripts/check-source-links.py --offline`
- [ ] `pytest -q`
- [ ] `mkdocs build --strict`

## 备注
