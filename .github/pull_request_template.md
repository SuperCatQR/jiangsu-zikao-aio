## 类型

- [ ] 课程页
- [ ] 专业页
- [ ] 资料索引
- [ ] 流程/模板
- [ ] 脚本/CI

## 来源

- 官方链接：
- 内部资料路径：`materials://`
- 公开本地来源：`sources/jiangsu/...`

## 检查

- [ ] 未提交 private 原件、教材电子书或第三方真题全文
- [ ] 符合 `ops/jiangsu/content-standard.md`
- [ ] `python scripts/validate-content.py`
- [ ] `python scripts/build-course-pages.py --base /jiangsu-zikao-aio/`
- [ ] `python scripts/check-source-links.py --offline`
- [ ] `pytest`

## 备注

