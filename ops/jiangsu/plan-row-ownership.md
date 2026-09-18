# Plan 行归属元数据义务（worktree 回收的前置条件）

本文只登记**一条写入义务**：Morning Star harness 的 plan 行收口时，归属元数据必须并进同一次写入。
它不定义新 schema，也不复述 engine 内部实现 —— 细节读快照与 engine 契约即可。

Plan 行存放在 `.mstar/workflows/<workflow-id>/snapshot.json` 的 `plans[]` 中；`.mstar/` 是 harness 空间，
不是内容目录，其写入权限见下面的「本宿主」一节。

## 义务：`Done` + 删 lease + 落归属，必须在同一次 locked write 内

把 plan 行置为 `Done` 的那**一次** locked update，必须同时完成三件事：

- [ ] 状态置 `Done`。
- [ ] 删除该行的 `execution_lease`。
- [ ] 写入 `metadata.working_branch` 与 `metadata.worktree_path`
      （该 plan 的功能分支名，以及 plan worktree 的绝对路径）。

归属元数据**不是**收口之后另起一步补写的附属信息，而是 `Done` 这一次写入的组成部分。
拆成两次写会留下一个窗口：plan 已经 `Done`、lease 已经释放，归属信息却还是空的 ——
这正是 B3a / B3c 的形态。

## 为什么重要：缺字段时 Phase-6 清理会 fail-closed

Phase 6 回收 plan worktree 时，清理动作先读这两个字段，确认「该 worktree 归本次 lifecycle 所有」。
字段缺失 → 归属检查无法确认所有权 → 按契约拒绝清理，拒绝码：

```text
cleanup.refuse.foreign-worktree
```

后果不是「删错目录」，而是**该回收的 worktree 收不掉**（继续占盘），并且只能如实上报，
不得改用命名推断绕过归属检查。

## 本宿主上这条清单是 no-op（不要把它当成已生效的守卫）

**本宿主没有 engine CLI**，而快照的唯一合法写入者是 engine 的 plan 生命周期 verb：

```bash
$ which mstar mstar-harness
# 无输出，exit 1（2026-09-18 实测）

$ grep -rn "worktree_path\|working_branch" scripts/
# 无命中（exit 1）→ 仓内没有任何代码写这两个字段，写入者是 engine
```

因此：

- 上面那份清单**现在没有人执行**。它是写给「未来的写入者（engine verb）及其调用方」的义务说明，
  **不是**一条正在运行的守卫；本仓当前也没有任何脚本能代替它执行。
- 手工补写快照会制造**第二个写入者**，契约明令禁止
  （`.mstar/knowledge/architecture-patterns/course-pipeline-layering.md`：one writer per artefact；
  `.mstar/knowledge/conventions/gate-fail-closed-and-page-reach.md`：the writer set must be closed）。
- 所以本文**不能**用来声称「归属元数据已经得到保证」。一条看起来存在、却从不运行的守卫本身就是缺陷形态
  （`.mstar/knowledge/test-failures/dead-guards-need-a-fire-proof.md` 的症状表）。

**生效条件**：engine `plan complete` 在本宿主可用、且 plan 行的写入重新由该 verb 承担时，
这份清单才真正会运行。

## 既有缺口（登记为 R56，未回填）

B3 收口时（2026-09-14）的实测状态：

| plan 行 | `working_branch` / `worktree_path` | 后果 |
| --- | --- | --- |
| `ai-course-prep-pipeline-b3a-chapter-fallback` | 缺 | worktree 未回收 |
| `ai-course-prep-pipeline-b3b-course-generation` | 有 | worktree 已正常回收 |
| `ai-course-prep-pipeline-b3c-reader-gaps-and-quality` | 缺 | worktree 未回收 |

`b3b` 行有值 ⇒ 这两个字段**能被正常写入**，缺的只是**某些 Done 写入路径没带上** ——
所以问题不在 schema，而在写入路径。

同一快照中 B4a / B4b 两行尚未 `Done`（`InProgress` / `Todo`），因此也还没有这两个字段：
本义务要求的正是「它们在 Done 的那一次写入里出现」，而不是事后回填。
补齐 `b3a` / `b3c`（以及更早的 `b1` / `b2a-15043`）需要 engine 授权，已登记为 `R56`，
触发条件为 engine `plan complete` 在本宿主可用。

## 事后自检（engine 可用后确认字段确实落盘）

在 **control root 主 checkout** 执行 —— `.mstar/**` 是本地 harness 空间（`.gitignore` 第 44 行），
**不会**出现在 feature worktree 里，所以这条检查不能在 plan worktree 内跑：

```bash
cd /root/workspace/jiangsu-zikao-aio
python3 -c "import json;d=json.load(open('.mstar/workflows/<workflow-id>/snapshot.json'));print([(p['id'],p['status'],'working_branch' in p.get('metadata',{}),'worktree_path' in p.get('metadata',{})) for p in d['plans']])"
```

2026-09-18 实测输出（`<workflow-id>` = `jiangsu-ai-course-pipeline-b3-2026-09-13`）：

```text
[('ai-course-prep-pipeline-b3a-chapter-fallback', 'Done', False, False), ('ai-course-prep-pipeline-b3b-course-generation', 'Done', True, True), ('ai-course-prep-pipeline-b3c-reader-gaps-and-quality', 'Done', False, False)]
```

`Done` 的行应全部打印 `True, True`；出现 `False` 即说明该行的 Done 写入路径又漏带了归属元数据。
