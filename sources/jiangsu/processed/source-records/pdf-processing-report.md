# PDF 批处理报告

| 字段 | 内容 |
| --- | --- |
| 处理时间 | 2026-07-06 12:29:51 +08:00 |
| 专业计划 PDF | 31 |
| 共享 PDF | 26 |
| Manifest | sources/jiangsu/processed/source-records/pdf-processing-manifest.csv |

## 输出规则

- 专业计划 PDF：content/jiangsu/majors/<major>/sources/
- 共享 PDF：sources/jiangsu/processed/<category>/<document>/

## 数据状态

本次输出为机器初稿，已完成 raw XML/TXT、Raw View HTML、Markdown 草稿和转换记录；manifest 记录 SHA256 与抽取策略。教材/真题默认不写入全文草稿，课程表级语义化抽取仍需后续人工校对或规则增强。