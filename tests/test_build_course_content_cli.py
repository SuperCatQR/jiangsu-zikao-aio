"""`build-course-content.py` 的 CLI 契约：`--dry-run` 的 help 文案必须如实描述写盘范围（R55）。

背景：旧 help 写「只演练不落盘」，实现却只守 `:340` 的正式页提升 —— `evidence` / `generate`
阶段无条件执行，仍写 `sources/jiangsu/courses/<code>/` 下的产物并重戳 `generated_at`
（参见 `{KNOWLEDGE_DIR}/developer-experience/pipeline-cli-operator-traps.md`）。该文案会误导验收者
把「干净检出的 `git status` 为空」当作演练的证据，因此本模块把它锁住：**改回旧的失实文案即红**。

两个用例分别锁住文案本身与它所声称的代码行为：

1. `test_build_help_names_the_real_write_scope` —— 真实 `build --help` 输出（子进程调用，非 import），
   断言写盘范围被点名、旧的失实断言消失；
2. `test_dry_run_guards_promotion_only` —— help 里「evidence/generate 阶段仍会写」是一句**正向的
   代码行为断言**；用 AST 调用点证明它与 `run_build` 中 `if not dry_run:` 守卫的实际覆盖面对齐
   （对齐 plan GC3 的「守卫须可证伪」口径）。反向漂移（让 `--dry-run` 真的挡掉写盘）会让本用例变红，
   提醒作者同步改文案，而不是让文案悄悄失真。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "build-course-content.py"

# 旧文案：唯一被实现证伪的断言（`--dry-run` 从未阻止 `sources/` 下的写入）
STALE_CLAIM = "只演练不落盘"

# help 必须点名的两处写盘事实 + 一处它确实守住的边界
STILL_WRITTEN_SCOPE = "sources/jiangsu/courses"
RESTAMPED_FIELD = "generated_at"
GUARDED_DESTINATION = "content/jiangsu/courses"


def _build_help() -> str:
    """真实子进程取 `build --help`（argparse 的换行随 `COLUMNS` 变，断言前统一压平空白）。"""
    res = subprocess.run(
        [sys.executable, str(CLI), "build", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"build --help 必须成功退出：stdout={res.stdout} stderr={res.stderr}"
    return " ".join(res.stdout.split())


def test_build_help_names_the_real_write_scope() -> None:
    help_text = _build_help()

    # ① 如实点名「仍然会写」的范围：`sources/jiangsu/courses/<code>/` 下的产物
    assert STILL_WRITTEN_SCOPE in help_text, (
        f"`--dry-run` 的 help 必须点名 `{STILL_WRITTEN_SCOPE}` 下的产物仍会被写：{help_text}"
    )
    # ② 如实点名 `generated_at` 会被重戳（这是「演练留下 modified files」的根因）
    assert RESTAMPED_FIELD in help_text, f"help 必须点名 `{RESTAMPED_FIELD}` 被重戳：{help_text}"
    # ③ 同时说明它确实守住的边界，避免反向失真
    assert GUARDED_DESTINATION in help_text, (
        f"help 必须说明 `--dry-run` 守住的提升目标 `{GUARDED_DESTINATION}`：{help_text}"
    )
    # ④ 旧的失实断言不得回归（本模块的存在意义）
    assert STALE_CLAIM not in help_text, f"「{STALE_CLAIM}」是失实断言，实现只挡正式页提升：{help_text}"


def _calls_guarded_by_dry_run() -> set[str]:
    """`run_build` 中 `if not dry_run:` 守卫体内被调用的函数名（AST 调用点证明）。"""
    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    guarded: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name)
            and test.operand.id == "dry_run"
        ):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                guarded.add(inner.func.id)
    return guarded


def test_dry_run_guards_promotion_only() -> None:
    guarded = _calls_guarded_by_dry_run()

    assert "_promote_staging" in guarded, (
        "`--dry-run` 必须仍然守住正式页提升（`if not dry_run:` 内调用 `_promote_staging`），"
        f"否则 help 的 ③ 失效；实测守卫体调用={sorted(guarded)}"
    )
    for stage_call in ("run_evidence", "run_generate", "run_model"):
        assert stage_call not in guarded, (
            f"help 声称 evidence/generate 阶段仍会写盘，但 `{stage_call}` 已被 `--dry-run` 挡下 —— "
            "行为与文案不一致，须同步改 help"
        )
