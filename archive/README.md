# 归档区

存放不在正式发布树、但要保留可追溯的历史资料。

- `design-proposals/` — CHO-94 站点设计选型阶段的 4 套风格原型和 IA 文档。
- `scripts/build-course-pages.py` + `scripts/templates/` — 已退役的手写 SSG（P0 / Issue #52）。**生产构建改为 MkDocs**；发布闸门逻辑已抽到 `scripts/lib/publish_gate.py` 与 `scripts/validate-publish-gate.py`。
- `track-b-backend-contract.md` — 后端交付契约初稿，随原型一起归档。

归档区不参与 `mkdocs build` / `site/` 发布。
