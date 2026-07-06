# 江苏公开来源目录

本目录只放可公开归档的官方材料、处理产物和清单；教材电子书、第三方真题全文、答案解析等版权材料不得进入本仓，应放在私有 `zikao-materials` 并以 `materials://...` 引用。

## 目标分层

```text
sources/jiangsu/
├─ public-official/   # 新增官方公开原件优先放这里
├─ processed/         # PDF/XML/TXT/Markdown 等机器处理产物
├─ manifests/         # 清单、报告、批处理记录
├─ syllabus/          # 既有考纲归档；后续可逐步迁入 public-official/syllabus
├─ textbooks/         # 既有公开教材计划；不是教材电子书
├─ past-papers/       # 仅允许官方公开真题或索引，不放第三方全文
└─ major-plans-2024/  # 既有专业计划归档
```

ponytail: 为避免一次性移动破坏现有内容引用，当前先确立新目录与规则；后续按 PR 小批量迁移并同步引用。
