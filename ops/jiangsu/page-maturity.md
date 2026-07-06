# 江苏自考页面成熟度规则

成熟度只描述页面可用程度，不等同资料完整度。

| 等级 | 条件 |
| --- | --- |
| red | 多页模板缺页，或 `status` 为 `missing-source`/`needs-review`，或来源页无核验说明 |
| yellow | 模板齐全但仍为 `draft`/`metadata-only`，允许空态与待补 |
| green | `status` 为 `complete`，四页齐全，来源/真题/计划均有非空说明 |

运行：`python scripts/compute-page-maturity.py` 生成 `ops/jiangsu/page-maturity.json` 与 `page-maturity.report.md`。
