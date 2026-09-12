# 江苏自考一站式解决（jiangsu-zikao-aio）

江苏省自学考试资料库，提供课程信息、考纲、真题索引和学习资料。

## 目的

为江苏自考生提供：
- 🎯 **课程信息聚合**：专业计划、课程元数据、考纲链接
- 📚 **真题索引**：历年真题汇总与来源追溯
- 🔍 **外链监控**：自动检测考纲/官方资料链接可用性
- 📖 **静态站点发布**：Markdown → GitHub Pages 全流程

数据源优先级：江苏省教育考试院官方 > 主考学校 > 人工校对。

## 项目结构

```text
jiangsu-zikao-aio/
├── content/jiangsu/       # 发布内容：课程、专业、索引
│   ├── courses/           # 课程 Markdown（{code}/index.md 或 {code}.md）
│   ├── majors/            # 专业计划与来源
│   └── index.md           # 站点首页
├── sources/jiangsu/       # 原始 PDF、机器抽取产物、清单
├── ops/                   # 元文档：政策、工作流、检查清单、蓝图
│   └── jiangsu/           # 江苏专属元文档
├── scripts/               # 校验/闸门/巡检脚本
│   ├── run-gates.py               # 统一分层闸门入口（CI 主路径）
│   ├── check-materials-resolve.py # materials:// 跨仓存在性诊断
│   ├── validate-*.py              # 单层薄包装（兼容旧命令）
│   ├── check-source-links.py      # 外链监控
│   ├── bootstrap-province.py      # 省份扩展脚手架
│   └── lib/                       # 共享状态机与闸门实现
├── tests/                 # 单元测试
├── build.toml             # 路径 + 监控配置
├── .env.example           # 环境变量示例
└── .github/workflows/     # CI：Pages 部署 + 外链监控
```

**三分区语义**：
- **content/** 被渲染进 `site/`（发布内容）
- **sources/** 原始资料与机器产物（按省分层）
- **ops/** 元文档（内部规范，不进入站点）

## 基础建设文档

- `ops/jiangsu/content-standard.md`：公开课程页、专业页、学习计划、复习计划排版标准。
- `ops/jiangsu/workflow.md`：专业页与课程页生产流程。
- `ops/jiangsu/publish-gate-contract.md`：发布闸门契约。
- `ops/jiangsu/course-status.md`：lifecycle + completeness 状态机。
- `ops/jiangsu/templates/study-plan.md`：课程学习计划模板。

## 使用

### 安装依赖

```bash
# Python 依赖
pip install -r requirements-dev.txt

# PDF 处理工具（可选，仅处理 PDF 时需要）
# Windows:
winget install --id oschwartz10612.Poppler --accept-package-agreements --silent
# 或手动下载 Poppler 并添加到 PATH

# Git LFS（首次克隆后）
git lfs install
```

### 构建静态站点

生产构建以 **MkDocs Material** 为唯一路径（与 CI 一致）。手写 SSG 已归档到 `archive/scripts/`。

```bash
# 生产构建（GitHub Pages）
python scripts/run-gates.py
pytest -q
python scripts/check-source-links.py --offline
mkdocs build --strict

# 本地预览
mkdocs serve
```

### 分层质量门禁（Gates）

`scripts/run-gates.py` 统筹执行分层门禁（默认 7 层，失败关闭）：
- `content`：版权声明、生命周期与完整度枚举、课码格式、PDF 清单
- `materials`：`materials://` 跨仓引用有效性及私有路径防泄露
- `contract`：课程多页模式必选文件与关键锚点结构契约
- `publish`：`lifecycle=publishable` 发布资格硬门禁
- `maturity-check`：非变异的公开页面成熟度投影比对
- `evidence`：官方事实层（`evidence.json`）与知识模型（`knowledge-model.json`）覆盖率、断言状态校验
- `ai-content`：AI 备考层（`content.json`）四件套标注、知识点归属、8-gram 重合率及渲染页横幅校验

### 外链监控

```bash
# 离线快速统计（仅统计引用数量）
python scripts/check-source-links.py --offline

# 在线探测（检查可用性并比对基线）
python scripts/check-source-links.py
```

### 新增省份

使用脚手架快速生成骨架：

```bash
# 1. 生成目录结构
python scripts/bootstrap-province.py guangdong

# 2. 编辑首页
# 编辑 content/guangdong/index.md

# 3. 添加课程页
# 在 content/guangdong/courses/ 创建课程 Markdown

# 4. 更新配置
# 在 build.toml 中添加省份路径（若需自定义）

# 5. 构建验证
mkdocs build --strict
```

### 本地开发环境变量（可选）

复制 `.env.example` 为 `.env` 并按需修改路径：

```bash
cp .env.example .env
# 编辑 .env 配置自定义路径
```

### 运行测试

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest

# 指定测试文件
pytest tests/test_publish_gate.py tests/test_course_status.py
```

## 开发规范

### 目录职责

详见 [ops/project-folders-structure-blueprint.md](ops/project-folders-structure-blueprint.md)。

### Git 提交

遵循 [GIT_GUIDE.md](GIT_GUIDE.md) 和 Conventional Commits 规范：

```bash
feat(courses): 新增 12345 软件工程课程页
fix(scripts): 修复 URL 规范化尾随标点处理
docs(ops): 更新课程审查清单
```

### 课程页发布前检查

必过 [ops/jiangsu/course-review-checklist.md](ops/jiangsu/course-review-checklist.md) 所有项。

### 配置管理

- `build.toml`：路径和监控配置（支持环境变量回退）
- `.env.example`：可选环境变量模板（本地开发时复制为 `.env`）

## 贡献

欢迎提交 PR 或 Issue：
- 课程信息勘误
- 真题索引补充
- 外链更新通知
- 新省份扩展

---

站点地址：<https://supercatqr.github.io/jiangsu-zikao-aio/>
