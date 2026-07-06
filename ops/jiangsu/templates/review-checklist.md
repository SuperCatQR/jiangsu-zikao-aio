# {{页面名称}} 审查清单

## 结构

- [ ] 标题、代码、名称、层次/学分齐全。
- [ ] 日期使用 `YYYY-MM-DD`。
- [ ] 课程代码保留 5 位前导 0。
- [ ] 资料状态为 `complete` / `metadata-only` / `missing-source` / `needs-review`。

## 来源

- [ ] 官方链接或公开本地来源已列出。
- [ ] private 资料只写 `materials://...`。
- [ ] 不确定信息写 `待核验`，无猜测。

## 发布

- [ ] `python scripts/validate-content.py`
- [ ] `python scripts/build-course-pages.py --base /jiangsu-zikao-aio/`
- [ ] `python scripts/check-source-links.py --offline`
- [ ] `pytest`
