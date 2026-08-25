# 考纲/来源链接监控与基线刷新（CHO-14）

> 本文件是 `scripts/check-source-links.py` 与 `.github/workflows/source-link-monitor.yml` 的
> 维护标准。基线（`ops/jiangsu/source-links.baseline.json`）是死链/内容漂移检测的对照基准。

## 基线刷新节奏（Cadence）

- **触发时机**：任何课程页 `sources.md` / `syllabus.md` / `index.md` 的「来源与引用」「考纲与教材」「真题索引」章节
  发生链接增删改后，**立即刷新**；此外**至少每月刷新一次**（与每周自动检测错峰，防止基线陈旧导致误报/漏报）。
- **自动检测**（每周一 03:17 UTC）：只读探测 + 告警 issue，**不**写基线。
- **手动刷新**：`workflow_dispatch` 且 `update_baseline=true`（自动开 PR，人工确认后合并），
  或本地执行下述命令后提交。

## 本地刷新命令（精确）

```bash
# 在线探测全部监控 URL 并把结果写回基线（含 generated_at 时间戳）
python scripts/check-source-links.py --update-baseline \
  --timeout 20 --retries 2 \
  --report site/source-link-report.md --summary site/source-link-report.json
```

- `--update-baseline` 会把本次探测结果（含权威页内容哈希）固化到
  `ops/jiangsu/source-links.baseline.json`；`inconclusive` 探测**不覆盖**既有权威状态。
- 刷新后应检查报告：`actionable_count` 应为 0（否则先人工核验变更再提交），
  `bulk-rot` 提示站点改版时按 PRD §4.2 处理。
- 离线冒烟（不探测，仅验证提取逻辑）：`python scripts/check-source-links.py --offline`。

## 维护注意事项

- 课程页内两个裸 URL 之间用全角分号（`；`）分隔会被 `BARE_URL_RE` 拆分为两个独立 URL
  （2026-08-25 修复，见 `tests/test_check_source_links.py` 回归用例）；**不要**在 URL 内部使用全角标点。
- 权威考纲页（jseea.cn）做内容哈希漂移检测；页面动态内容可能导致 `content_changed`，
  人工核验后以刷新基线固化。
