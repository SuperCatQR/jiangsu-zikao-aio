# sources/jiangsu 布局契约（P2）

> 单一真相源：本文件 + `major-slugs.json`。禁止再引入第三套 sources 树。

## 顶层

```text
sources/jiangsu/
├── public-official/     # 可公开官方 PDF（LFS）
│   ├── major-plans/     # 专业考试计划
│   ├── policies/        # 政策通知
│   ├── syllabi/         # 考纲 PDF
│   ├── textbooks/       # 教材计划表等
│   └── past-papers/     # 若有公开真题原件（通常极少）
├── processed/           # 机器抽取产物（可公开）
│   ├── major-source/    # 按专业计划抽取（历史数字目录可并存，新建用 code-slug）
│   ├── policies/
│   ├── syllabus/
│   ├── textbooks/
│   ├── documents/
│   └── source-records/  # manifest / 报告
└── manifests/           # 迁移与批处理清单
```

## 命名

| 类型 | 公开 PDF 路径 | 抽取产物 |
| --- | --- | --- |
| 专业计划 | `public-official/major-plans/{code}-{slug}.pdf` 或保留原名 + manifest | `processed/major-source/{code}-{slug}/` |
| 考纲 | `public-official/syllabi/{code}-*.pdf` | `processed/syllabus/{code}-*/` |
| 政策 | `public-official/policies/{id}.pdf` | `processed/policies/{id}/` |

专业 slug 字典：`ops/jiangsu/major-slugs.json`（中文名 → english-slug）。

## 与 content 的边界

- **content/** 只放可渲染 Markdown。
- 抽取副产物（`plan.raw.xml` / `plan.extracted.md` 等）可暂存于 `content/.../sources/` 以便审核，长期应优先落在 `sources/.../processed/`。
- 工作流脚本读写路径须与本契约一致；`bootstrap-province` 生成新省时使用同一 `public-official` + `processed` 树。

## 过期路径（勿再写）

- `sources/jiangsu/major-plans-2024/`（已迁 public-official）
- bootstrap 旧树 `syllabi/ + exam-schedules/ + machine-output/`（已废弃）
