# 课程页 🟢 可发布闸门契约（P0）

> 关联：Issue #52。本文件锁定 `lifecycle: publishable` 时的机器闸门与人工前置条件。  
> **生产构建**：`mkdocs build --strict`（唯一）。  
> **发布闸门**：`python scripts/validate-publish-gate.py`（CI 在 MkDocs 之前强制执行）。  
> 状态语义：`draft` / `machine_ready` / `in_review` / `publishable`（见 `course-status.md`）。

## 一、机器闸门（`scripts/validate-publish-gate.py`）

仅当 frontmatter `lifecycle: publishable`（兼容旧写法 `status: publishable`）时触发硬阻断（`errors` → exit 1）：

| 闸门码 | 条件 |
| --- | --- |
| `HUMAN_REVIEW_REQUIRED` | 须有 `reviewed: true` 且 `reviewer: <姓名>` 非空 |
| `PUBLISH_PENDING_REQUIRED_DATA` | 元信息 `数据状态`/`发布日期` 不得含 `待校对`/`待统计`/`待收集`/`待核验`/`待确认`；`exam_source_status`/`exam_analysis_status` 同理；`replacement_confirmed` 须为 true/yes/confirmed/not_applicable |
| `REPLACEMENT_FREE_TEXT_BYPASS` | 「新旧课程顶替」不得同时存在 4 字段表与含「替代」的自由文本 blockquote |
| `EXAM_INDEX_SCOPE_MIXED` / `EXAM_INDEX_DUPLICATED_SCOPE` | 考期索引现行/历史不得混排、不得重复 |
| `CONTENT_REVISION_MISMATCH` | 若设置 `content_revision`，须匹配构建 HEAD commit |

> 闸门只在页面**声称 publishable** 时阻断；`draft` / `machine_ready` / `in_review` 不阻断构建。

## 二、人工前置

1. **内容审查背书**（PR 审查团队）：政策与时效、考纲、教材、知识树、真题索引口径、来源与引用、新旧顶替。
2. **法务合规**（如适用）：真题/教材版权、PII、AI 声明。
3. **背书可追溯**：`reviewed: true` + `reviewer` 须由人类在 PR/commit 中留下；**不得由自动化 agent 伪造**。

## 三、交付路径

1. 内容达到 `machine_ready` 后开 PR 审查 → `in_review`。
2. 审查与法务通过后，人类将 `lifecycle` 设为 `publishable` 并填写 `reviewed`/`reviewer`。
3. CI（`deploy-pages.yml`：`push: main` + `workflow_dispatch`，**不**在 PR 上运行）：**`run-gates.py`（7 层，含 `ai-content`）** → `pytest -q` → `ruff check scripts tests` → `check-source-links --offline` → **`mkdocs build --strict`**。
   **更正（2026-09-13）**：本文此前写作 `validate-content` → `validate-publish-gate` → `pytest` → …，与 CI 实际步骤**不符** ——
   实际入口是 `run-gates.py`；`validate-content.py` 只跑 content 层、`validate-publish-gate.py` 是发布门限校验，
   两者都**不**覆盖 `ai-content` 层的页面到达性与 R20/R21。人工预提交请用 `run-gates.py`。
4. 真题原件仍由 `zikao-materials` 链路负责；未入库时相关区块保持空态。

## 四、命令

```bash
python scripts/run-gates.py
pytest -q
python scripts/check-source-links.py --offline
mkdocs build --strict
```

单层兼容：`python scripts/validate-publish-gate.py` 仍可单独调用。

历史手写 SSG（`scripts/build-course-pages.py`）已归档至 `archive/scripts/`，**不再作为生产构建路径**。
