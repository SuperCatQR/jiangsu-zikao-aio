"""答案分布守卫的**可证伪**证据（compass R4 / T4；plan § Data contracts 1/2，design-notes § 2）。

本模块只做一件事：把「守卫真的会触发、且触发的是它自己那条判据」变成可运行的检查。B2a 的 `W-1` 与
B3b 的三个谓词都是**定义在源码里、没有任何调用点**的死守卫（`test-failures/dead-guards-need-a-fire-proof.md`），
所以每个谓词都要过三关：**AST call-node**（有人调）+ **变异**（条件会真）+ **修前红**（在改动前失败）。

分工：判据边界与解析口径用**纯函数**测（`answer_distribution()`，无 I/O，可直接变异）；
作用域信号与报告通道用**闸门级**测试（`run_ai_content_gate()` + `capsys`）。
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SOURCE = ROOT / "scripts" / "lib" / "ai_content_gate.py"

# 实测的 `answer_md` 首行排布（plan § Data contracts 2 / design-notes § 2.3）：
# 单选三种（前缀 + 该行是否结束的差别**只在同一行内**）+ 判断题四种。
SINGLE_CHOICE_SHAPES = {
    "① 该行仅含答案": "正确答案：A",
    "② 该行后接解释": "正确答案：B\n解析：B 项符合题干。",
    "③ 压缩形态（前缀不同、解释同段）": "答案：C。C 项是官方口径。",
}
JUDGEMENT_SHAPES = {
    "① 句号结尾": "参考答案：错误。",
    "② 也是句号结尾": "参考答案：正确。",
    "③ 逗号后接解释": "参考答案：错误，有三处错误。",
    "④ 句号后接解释": "参考答案：正确。连接池的核心就是复用连接。",
}

# 多选答案的五种写法（QC-2：qc1 F-2 与 qc2 S-1 双席独立发现）。旧式 `([A-D])\b` 里 `\b` 在 `、`/`,`/`，`/
# 空格之前**成立**（都是非词字符），于是前四种被静默计成首字母 `A`（错值进分子），而第五种 `AB` 又因 `\b`
# 不成立失败关闭 —— 同一批多选答案两种相反行为。五种现在必须**一致**进入 `unparseable`。
MULTI_ANSWER_SHAPES = {
    "顿号分隔": "答案：A、B",
    "半角逗号分隔": "答案：A,B",
    "全角逗号分隔": "答案：A，B",
    "空格分隔": "答案：A B",
    "连写": "正确答案：AB",
}

# 单答案形态的**正向控制**（QC-2 的另一半：收紧多选判定不得动摇既有解析面，plan § Data contracts 2）。
# `(维度, 期望答案)`：前三行是单选三形态的实测值，末行是 `00898` 的第 4 种判断题真值排布。
SINGLE_ANSWER_SHAPES = {
    "答案 前缀": ("单项选择题", "答案：A", "single_choice", "A"),
    "正确答案 前缀": ("单项选择题", "正确答案：A", "single_choice", "A"),
    "答案后接解释": ("单项选择题", "答案：A。解析：A 项符合题干。", "single_choice", "A"),
    "真值后接解释": ("判断改错题", "参考答案：错误，有三处错误。", "judgement", "错误"),
}


def _drill(point_id: str, question_type: str, answer_md: str) -> dict:
    """最小可用的 drill 块（守卫只读 `kind` / `question_type` / `answer_md` / `point_id`）。"""
    return {
        "block_id": f"b-{point_id}",
        "kind": "drill",
        "point_id": point_id,
        "question_type": question_type,
        "answer_md": answer_md,
    }


def _content(*blocks: dict) -> dict:
    return {"blocks": list(blocks)}


def _fresh_root(tmp_path: Path, name: str) -> Path:
    """一份仓内产物树的副本（sources / ops / content），**不带 git 索引** = 未跟踪 = 新课。

    与既有 `tests/test_ai_content_gate.py` 的 fixture 同形；跟踪状态由各用例自己按需 `git add`。
    """
    root = tmp_path / name / "repo"
    shutil.copytree(ROOT / "sources", root / "sources")
    shutil.copytree(ROOT / "ops", root / "ops")
    shutil.copytree(ROOT / "content", root / "content")
    return root


def _git_track(root: Path, *rel_paths: str) -> None:
    """把给定相对路径登记进 fixture 根**自己的**索引（只 `git add`：跟踪状态读的就是索引）。"""
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "-f", "--", *rel_paths], check=True, capture_output=True
    )


def _content_path(root: Path, code: str) -> Path:
    return root / "sources" / "jiangsu" / "courses" / code / "content.json"


def _rewrite_single_choice_answers(path: Path, answer_md: str) -> int:
    """把该课**全部单选题**的答案改写成 `answer_md`，返回改写的块数（0 会让变异用例空洞通过）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for block in data["blocks"]:
        if block.get("kind") == "drill" and "选择" in str(block.get("question_type") or ""):
            block["answer_md"] = answer_md
            changed += 1
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return changed


def _biased_errors(errors: list[str], code: str) -> list[str]:
    """点名某门课的偏置错误（只按**守卫自己那条判据**筛，不靠「错误非空」蒙混）。"""
    return [e for e in errors if f"course {code}" in e and "答案分布" in e and "verdict=biased" in e]


def _unparseable_errors(errors: list[str], code: str) -> list[str]:
    """点名某门课的**解析覆盖缺口**错误（QC-1 的判据面：作用域收敛只该影响这一条，不影响别的检查）。"""
    return [e for e in errors if f"course {code}" in e and "答案分布" in e and "无法解析出答案" in e]


# --------------------------------------------------------------------------------------
# AC1：解析口径 —— 不锚行尾，一次覆盖全部实测形态；不可解析即失败关闭
# --------------------------------------------------------------------------------------

def test_single_choice_parser_covers_every_measured_shape():
    """三种排布都进同一个样本口径（把任一种漏在外面 = compass B4-R5 的漏检形态）。"""
    from lib.ai_content_gate import answer_distribution

    dist = answer_distribution(
        _content(*(_drill(f"p{i}", "单项选择题", text) for i, text in enumerate(SINGLE_CHOICE_SHAPES.values())))
    )
    single = dist["single_choice"]
    assert single["n"] == 3, f"三种形态都必须进样本: {single}"
    assert single["counts"] == {"A": 1, "B": 1, "C": 1, "D": 0}, single["counts"]
    assert dist["unparseable"] == [], dist["unparseable"]
    # 逐条点名：形态②③ 的差别只在「首行是否以行尾结束」，锚了 `$` 就只剩 1 道。
    for text in SINGLE_CHOICE_SHAPES.values():
        assert answer_distribution(_content(_drill("p", "单项选择题", text)))["single_choice"]["n"] == 1, text


def test_multi_letter_answers_never_contribute_a_first_letter():
    """QC-2：多选答案的**每一种**写法都必须进 `unparseable`，不得把首字母当单选样本。

    旧式 `\\b` 下 `答案：A、B` / `A,B` / `A，B` / `A B` 静默计成 `A`：进的是**错值**（不是缺值），
    守卫自己的分子被污染，且不产生任何 `unparseable` 记录。五种写法现在必须同形。
    """
    from lib.ai_content_gate import answer_distribution

    for label, text in MULTI_ANSWER_SHAPES.items():
        dist = answer_distribution(_content(_drill("p1", "单项选择题", text)))
        counts = dist["single_choice"]["counts"]
        assert dist["single_choice"]["n"] == 0, (
            f"多选写法「{label}」（{text}）不得贡献单选样本: {dist['single_choice']}"
        )
        assert counts == {"A": 0, "B": 0, "C": 0, "D": 0}, f"多选写法「{label}」污染了计数: {counts}"
        assert len(dist["unparseable"]) == 1 and "p1" in dist["unparseable"][0], (
            f"多选写法「{label}」（{text}）必须失败关闭为不可解析: {dist['unparseable']}"
        )


def test_single_letter_answers_still_parse_exactly_as_before():
    """QC-2 的**正向控制**：收紧多选判定不得动摇既有的单答案 / 真值形态（基线表的解析面）。

    与上一条同时成立才说明修的是「多选被误读」这一条，而不是把解析器整体收窄。
    """
    from lib.ai_content_gate import answer_distribution

    for label, (question_type, text, dimension, expected) in SINGLE_ANSWER_SHAPES.items():
        dist = answer_distribution(_content(_drill("p1", question_type, text)))
        assert dist[dimension]["n"] == 1, f"「{label}」（{text}）必须照旧进样本: {dist[dimension]}"
        assert dist[dimension]["counts"][expected] == 1, f"「{label}」（{text}）: {dist[dimension]['counts']}"
        assert dist["unparseable"] == [], f"「{label}」（{text}）不得被误判为不可解析: {dist['unparseable']}"


def test_judgement_parser_covers_every_measured_shape():
    """`00898` 实测的四种真值首行（含第 4 种「句号后接解释」）都要被解析。"""
    from lib.ai_content_gate import answer_distribution

    dist = answer_distribution(
        _content(*(_drill(f"p{i}", "判断改错题", text) for i, text in enumerate(JUDGEMENT_SHAPES.values())))
    )
    judgement = dist["judgement"]
    assert judgement["n"] == 4, f"四种形态都必须进样本: {judgement}"
    assert judgement["counts"] == {"正确": 2, "错误": 2}, judgement["counts"]
    assert dist["unparseable"] == [], dist["unparseable"]


def test_unparseable_answer_in_a_letter_family_fails_closed():
    """落在题型族内却提不出答案 = 该块的答案没进任何分布 → 必须报错，不得静默记为「无偏置」。"""
    from lib.ai_content_gate import answer_distribution

    dist = answer_distribution(
        _content(
            _drill("p1", "单项选择题", "正确答案：A"),
            _drill("p2", "单项选择题", "（出题模型没有按要求给出答案）"),
        )
    )
    assert dist["single_choice"]["n"] == 1, dist["single_choice"]
    assert len(dist["unparseable"]) == 1 and "p2" in dist["unparseable"][0], dist["unparseable"]


def test_non_letter_question_types_are_out_of_scope_without_failing_closed(tmp_path: Path):
    """简答题 / 材料题等文字型答案是**有意排除**，不是「不可解析」——实测 582 个此类 drill。

    这条是反向控制：若把「提不出字母」一律当不可解析，五门既有课会整片飘红。
    """
    from lib.ai_content_gate import answer_distribution, run_ai_content_gate

    dist = answer_distribution(
        _content(
            _drill("p1", "简答题", "参考答案：（1）马克思主义的直接理论来源有三个……"),
            _drill("p2", "材料题", "答案要点：\n- 第一点\n- 第二点"),
            _drill("p3", "名词解释题", "参考答案："),
        )
    )
    assert dist["single_choice"]["n"] == 0 and dist["judgement"]["n"] == 0
    assert dist["unparseable"] == [], f"文字型答案不得被当成不可解析: {dist['unparseable']}"

    # 仓内真产物上同样不得出现这类错误（否则既有课会被误伤）
    root = _fresh_root(tmp_path, "text-types")
    errors = run_ai_content_gate(root)
    assert not any("无法解析出答案" in e for e in errors), errors


# --------------------------------------------------------------------------------------
# AC3：判据边界（样本下界 10 / 单选 > 40% / 判断 > 80%）
# --------------------------------------------------------------------------------------

def test_ratio_criteria_boundaries_are_strict():
    """`> 40%` / `> 80%` 是**严格**大于，且样本下界按 10（=10 时仍判占比）。"""
    from lib.ai_content_gate import answer_distribution

    def verdict(answers: list[str], question_type: str = "单项选择题") -> str:
        dist = answer_distribution(
            _content(
                *(
                    _drill(f"p{i}", question_type, f"正确答案：{answer}")
                    for i, answer in enumerate(answers)
                )
            )
        )
        return dist["single_choice" if question_type == "单项选择题" else "judgement"]["verdict"]

    # 单选：n=10 时 4/10 = 40% 不算偏置，5/10 = 50% 算；n=9 一律样本不足（不判占比）
    assert verdict(list("AAAABCDBCD")) == "ok", "恰好 40% 不得判偏置"
    assert verdict(list("AAAAABCBCD")) == "biased", "50% 必须判偏置"
    assert verdict(list("AAAAAAAAA")) == "insufficient-sample", "n=9 < 10 → 样本不足"
    # 判断题：n=10 时 8/10 = 80% 不算，9/10 = 90% 算
    assert verdict(["正确"] * 8 + ["错误"] * 2, "判断改错题") == "ok", "恰好 80% 不得判偏置"
    assert verdict(["正确"] * 9 + ["错误"], "判断改错题") == "biased", "90% 必须判偏置"
    assert verdict(["正确"] * 3, "判断改错题") == "insufficient-sample", "n=3 < 10 → 样本不足"


# --------------------------------------------------------------------------------------
# AC2 / AC6：作用域信号 = git 跟踪状态；两个方向各一次
# --------------------------------------------------------------------------------------

def test_scope_signal_reads_git_tracking_two_states(tmp_path: Path):
    """同一棵树里两态并存：已跟踪 ⇒ `True`，未跟踪 ⇒ `False`（信号取自索引，不取自产物自述）。"""
    from lib.ai_content_gate import content_tracking_state

    root = _fresh_root(tmp_path, "two-states")
    rel = "sources/jiangsu/courses/15040/content.json"
    _git_track(root, rel)

    assert content_tracking_state(root, _content_path(root, "15040")) is True, "已 git add ⇒ 既有课"
    assert content_tracking_state(root, _content_path(root, "15043")) is False, "未 git add ⇒ 新课"


def test_undetermined_tracking_state_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """`tracked=None`（git 不可用 / 判定失败）⇒ 按新课处理：**照样报错**且报告写明方向。"""
    from lib.ai_content_gate import _answer_distribution_problems, answer_distribution

    errors: list[str] = []
    content = _content(*(_drill(f"p{i}", "单项选择题", "正确答案：A") for i in range(12)))
    _answer_distribution_problems("99999", answer_distribution(content), None, errors)

    out = capsys.readouterr().out
    assert _biased_errors(errors, "99999"), f"判定失败必须 fail-closed，不得降级为只报告: {errors}"
    assert "enforced=true" in out and "按新课处理" in out, out


def test_tracking_probe_returns_none_when_git_cannot_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """探针的「无法判定」两态：`git` 不可执行（`OSError`）与 fatal 退出码（实测 128 = 不是工作树）。

    两者都必须返回 `None`（而非 `False`）—— `False` 会被读成「确定未跟踪」，从而丢掉「按新课处理」
    这条报告口径；返回码语义见 `content_tracking_state()` 的 docstring（1 = pathspec 未命中）。
    """
    from lib import ai_content_gate

    root = tmp_path / "root"
    content_path = root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    content_path.parent.mkdir(parents=True)
    content_path.write_text("{}", encoding="utf-8")

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("git 不在 PATH 上")

    monkeypatch.setattr(ai_content_gate.subprocess, "run", _raise)
    assert ai_content_gate.content_tracking_state(root, content_path) is None, "git 不可用 ⇒ 无法判定"

    class _Fatal:
        returncode = 128  # 实测：`fatal: not a git repository` 走这个码

    monkeypatch.setattr(ai_content_gate.subprocess, "run", lambda *_a, **_k: _Fatal())
    assert ai_content_gate.content_tracking_state(root, content_path) is None, "fatal 退出码 ⇒ 无法判定"

    class _Untracked:
        returncode = 1  # 实测：`pathspec ... did not match any file(s) known to git`

    monkeypatch.setattr(ai_content_gate.subprocess, "run", lambda *_a, **_k: _Untracked())
    assert ai_content_gate.content_tracking_state(root, content_path) is False, "退出码 1 ⇒ 确定未跟踪"


def test_tracking_probe_is_bounded_and_degrades_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """QC-4（qc3 F-2）：探针给 `git` 子进程一个有界 `timeout=`，且**超时**也必须降级为 `None`。

    `subprocess.TimeoutExpired` 继承 `SubprocessError` 而**不是** `OSError`：只补 `timeout=` 会让超时
    异常穿透 `run_ai_content_gate()`，把整层闸门打崩而不是按新课处理。两条一起钉住：
    kwargs 里有有界的 `timeout`，且 `TimeoutExpired` / 其余 `SubprocessError` 都返回 `None`。
    """
    from lib import ai_content_gate

    root = tmp_path / "root"
    content_path = root / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
    content_path.parent.mkdir(parents=True)
    content_path.write_text("{}", encoding="utf-8")

    seen: list[dict] = []

    def _timeout(*_args, **kwargs):
        seen.append(kwargs)
        raise subprocess.TimeoutExpired(cmd="git", timeout=kwargs.get("timeout") or 0)

    monkeypatch.setattr(ai_content_gate.subprocess, "run", _timeout)
    assert ai_content_gate.content_tracking_state(root, content_path) is None, "超时必须降级为「无法判定」"
    assert seen, "探针必须真的调用 subprocess.run（否则 timeout 断言空转）"
    timeout = seen[0].get("timeout")
    assert isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and 0 < timeout <= 60, (
        f"探针必须给 git 子进程一个有界 timeout=（实测 kwargs: {seen[0]}）"
    )

    def _hard_failure(*_args, **_kwargs):
        raise subprocess.SubprocessError("索引损坏等非超时失败")

    monkeypatch.setattr(ai_content_gate.subprocess, "run", _hard_failure)
    assert ai_content_gate.content_tracking_state(root, content_path) is None, (
        "其余 SubprocessError 同样不得穿透闸门（捕获面必须放宽）"
    )


def test_unparseable_is_scope_gated_exactly_like_biased(capsys: pytest.CaptureFixture[str]):
    """QC-1（qc1 F-1 + qc2 F-1，双席独立发现）：解析缺口与偏置受**同一个** `enforced` 约束。

    方向一 —— `tracked=True`（既有课）：缺口仍必须**打印**（条数 + 首个块的 id，可 grep），但**不得**进
    `errors`（Clarify C3 / compass D5）。方向二/三 —— `False`（新课）与 `None`（无法判定）：照旧失败关闭。
    """
    from lib.ai_content_gate import _answer_distribution_problems, answer_distribution

    content = _content(
        *(_drill(f"p{i}", "单项选择题", "正确答案：A") for i in range(11)),
        _drill("p-bad", "单项选择题", "（出题模型没有按要求给出答案）"),
    )
    dist = answer_distribution(content)
    assert dist["unparseable"] == ["p-bad（单项选择题）"], dist["unparseable"]

    # 方向一：已跟踪的既有课 —— 同一份产物（既有偏置 + 解析缺口）只报告
    tracked_errors: list[str] = []
    _answer_distribution_problems("99999", dist, True, tracked_errors)
    out_tracked = capsys.readouterr().out
    assert tracked_errors == [], f"既有课不得被解析缺口阻断（C3/D5）: {tracked_errors}"
    assert "unparseable(n=1 first=p-bad（单项选择题）)" in out_tracked, (
        f"既有课的缺口必须打印条数与首个块 id（非静默）: {out_tracked}"
    )
    assert "enforced=false" in out_tracked, out_tracked

    # 方向二/三：未跟踪（新课）与无法判定 —— 都必须失败关闭
    for tracked in (False, None):
        errors: list[str] = []
        _answer_distribution_problems("99999", dist, tracked, errors)
        capsys.readouterr()
        assert _unparseable_errors(errors, "99999"), f"tracked={tracked} 必须失败关闭: {errors}"


def _make_single_choice_answers_unparseable(path: Path, limit: int) -> list[str]:
    """把该课**前 `limit` 道**单选题的答案改写成无法解析的文本，返回被改写的 `point_id`（空列表 = 变异空洞）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = [
        block
        for block in data["blocks"]
        if block.get("kind") == "drill" and "选择" in str(block.get("question_type") or "")
    ][:limit]
    for block in targets:
        block["answer_md"] = "（出题模型没有按要求给出答案）"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return [str(block.get("point_id")) for block in targets]


def test_gate_blocks_unparseable_on_a_new_course_and_only_reports_on_a_tracked_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """QC-1 的**闸门级**双向证明：同一棵树只改跟踪状态 ⇒ 同一份不可解析产物从报错变成只报告。

    走真实入口（`run_ai_content_gate()` + 真实 `git ls-files` 探针），证明作用域收敛在端到端路径上成立，
    而不只是在 `_answer_distribution_problems()` 的单测里成立。两个方向都断言**那一条判据**，
    不用「错误非空 / 为空」蒙混（同一条树上其他课仍可能因偏置报错，那是另一个方向的事）。
    """
    from lib.ai_content_gate import content_tracking_state, run_ai_content_gate

    root = _fresh_root(tmp_path, "unparseable-scope")
    broken = _make_single_choice_answers_unparseable(_content_path(root, "15044"), 2)
    assert len(broken) == 2, "对照前提：该课确实有单选题可改写（否则变异空洞通过）"

    # 方向一：未跟踪（新课）⇒ 解析缺口失败关闭
    errors_new = run_ai_content_gate(root)
    out_new = capsys.readouterr().out
    assert _unparseable_errors(errors_new, "15044"), f"新课的解析缺口必须失败关闭: {errors_new}"
    assert "unparseable(n=2" in out_new and broken[0] in out_new, out_new

    # 方向二：同一棵树，只把该课登记进索引 ⇒ 同一份产物只报告、不进 errors
    _git_track(root, "sources/jiangsu/courses/15044/content.json")
    assert content_tracking_state(root, _content_path(root, "15044")) is True
    errors_tracked = run_ai_content_gate(root)
    out_tracked = capsys.readouterr().out
    assert _unparseable_errors(errors_tracked, "15044") == [], f"既有课不得被解析缺口阻断: {errors_tracked}"
    line_15044 = next(line for line in out_tracked.splitlines() if "course=15044" in line)
    assert "unparseable(n=2" in line_15044 and broken[0] in line_15044, line_15044
    assert "enforced=false" in line_15044 and "QC-1" in line_15044, line_15044


def test_new_course_bias_errors_and_tracked_course_only_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """**变异双向证明**：同一份「所有单选答案都是 A」的产物，未跟踪时守卫报错、被跟踪后只报告。

    只证明一个方向不足以区分「守卫正确报告」与「守卫从不 enforce」，故两侧都在这里钉住，
    并在同一轮里保留 `15040` 这条**仍在 enforce** 的对照（证明守卫整体没被关掉）。
    """
    from lib.ai_content_gate import content_tracking_state, run_ai_content_gate

    root = _fresh_root(tmp_path, "all-a")
    changed = _rewrite_single_choice_answers(_content_path(root, "15043"), "正确答案：A")
    assert changed > 0, "对照前提：该课确实有单选题可改写（否则变异空洞通过）"

    # 方向一：未跟踪（新课）⇒ 偏置必须失败关闭
    errors_new = run_ai_content_gate(root)
    out_new = capsys.readouterr().out
    biased_new = _biased_errors(errors_new, "15043")
    assert biased_new, f"未跟踪的新课必须因 100% 偏置报错: {errors_new}"
    assert "100.0%" in biased_new[0] and "40%" in biased_new[0], biased_new[0]
    assert "course=15043" in out_new and "enforced=true" in out_new, out_new

    # 方向二：同一棵树，只把该课登记进索引 ⇒ 同一份偏置只报告、不进 errors
    _git_track(root, "sources/jiangsu/courses/15043/content.json")
    assert content_tracking_state(root, _content_path(root, "15043")) is True
    errors_tracked = run_ai_content_gate(root)
    out_tracked = capsys.readouterr().out
    assert _biased_errors(errors_tracked, "15043") == [], f"既有课不得被阻断: {errors_tracked}"
    # 同一轮里的对照：仍在未跟踪状态的 15040 照旧 enforce（守卫没被整体关掉）
    assert _biased_errors(errors_tracked, "15040"), f"对照前提：15040 仍在 enforce: {errors_tracked}"
    # 方向二的报告面：既有课的偏置必须可见，且点名跟踪它的 residual
    line_15043 = next(line for line in out_tracked.splitlines() if "course=15043" in line)
    assert "verdict=biased" in line_15043 and "enforced=false" in line_15043, line_15043
    assert "R15/R33" in line_15043, line_15043


# --------------------------------------------------------------------------------------
# AC4 / AC5：报告通道（非静默）与既有 5 门课的基线复现
# --------------------------------------------------------------------------------------

def test_insufficient_sample_is_reported_and_never_returned_as_an_error(capsys: pytest.CaptureFixture[str]):
    """双向断言：stdout **有** `insufficient-sample`（未静默通过）且返回值**无**该字面量（未误报为错误）。

    用仓内真实产物取证：`00898`/`02333`/`15040`/`15043`/`15044` 的判断题样本均为 0 或 10，
    其中 4 门 n=0 → 样本不足；而它们同时是**已跟踪**的既有课，故 `errors` 必须为空。
    """
    from lib.ai_content_gate import run_ai_content_gate

    errors = run_ai_content_gate(ROOT)
    out = capsys.readouterr().out

    assert "insufficient-sample" in out, f"样本不足必须出现在报告通道: {out}"
    assert not any("insufficient-sample" in e for e in errors), errors
    assert errors == [], f"既有 5 门课不得因偏置或小样本变红: {errors}"


def test_family_not_matched_is_a_distinct_report_only_marker(capsys: pytest.CaptureFixture[str]):
    """QC-3（qc1 F-3）：有 drill 而两族题型标记都没命中 ⇒ 打印**独立**的 `family-not-matched` 覆盖标记。

    否则「整门课脱出分布判定」与「样本确实不足」是同一个 `insufficient-sample` 字面量（该 verdict 按契约
    永不进 `errors`），一门题型写作「单选」「客观题」的课会整门零覆盖而只留一行报告。标记只走报告通道。
    """
    from lib.ai_content_gate import _answer_distribution_problems, answer_distribution

    # 反向控制：族命中（哪怕样本不足）不得带这个标记 —— 标记只能表示「守卫没看见题」
    matched = answer_distribution(_content(_drill("p1", "单项选择题", "正确答案：A")))
    matched_errors: list[str] = []
    _answer_distribution_problems("99999", matched, False, matched_errors)
    out_matched = capsys.readouterr().out
    assert "insufficient-sample" in out_matched, out_matched
    assert "family-not-matched" not in out_matched, f"族命中时不得出现覆盖标记: {out_matched}"

    # 族未命中：文字型题型（简答 / 材料）⇒ 整门课的答案都没进分布判定
    unmatched = answer_distribution(
        _content(
            _drill("p1", "简答题", "参考答案：（1）马克思主义的直接理论来源有三个……"),
            _drill("p2", "材料题", "答案要点：\n- 第一点"),
        )
    )
    assert unmatched["families"] == {"single_choice": 0, "judgement": 0, "drills": 2}, unmatched["families"]
    errors: list[str] = []
    _answer_distribution_problems("99999", unmatched, False, errors)
    out = capsys.readouterr().out
    assert "coverage=family-not-matched drills=2" in out, f"覆盖缺口必须有独立标记: {out}"
    assert errors == [], f"覆盖标记只报告，绝不进 errors: {errors}"

    # 第三个方向：族**已命中**、只是答案不可解析 ⇒ 缺口由 `unparseable` 发声，不得记成「题型没匹配上」
    broken = answer_distribution(_content(_drill("p1", "单项选择题", "（没有答案）")))
    broken_errors: list[str] = []
    _answer_distribution_problems("99999", broken, False, broken_errors)
    out_broken = capsys.readouterr().out
    assert "family-not-matched" not in out_broken, f"族已命中（解析失败）不得报覆盖标记: {out_broken}"
    assert "unparseable(n=1 first=p1（单项选择题）)" in out_broken, out_broken
    assert _unparseable_errors(broken_errors, "99999"), broken_errors


def test_existing_courses_reproduce_the_measured_baseline(capsys: pytest.CaptureFixture[str]):
    """AC5：既有 5 门课的实测分布与 plan § Data contracts 2 的基线表逐字一致（报告口径）。

    期望值来自 PM 复现并已被第 2 席独立复算的表；本用例是那份表的可运行版本 ——
    解析口径一旦漂移（例如锚了行尾、漏掉一整类形态），这里的 `n` 与计数会立刻不符。
    """
    from lib.ai_content_gate import run_ai_content_gate

    run_ai_content_gate(ROOT)
    out = capsys.readouterr().out
    lines = {code: next(l for l in out.splitlines() if f"course={code} " in l) for code in
             ("15040", "15043", "15044", "00898", "02333")}

    expected = {
        "15040": "single(n=194 counts=A105/B70/C17/D2 max_share=54.1% verdict=biased)",
        "15043": "single(n=173 counts=A129/B39/C4/D1 max_share=74.6% verdict=biased)",
        "15044": "single(n=147 counts=A24/B42/C41/D40 max_share=28.6% verdict=ok)",
        "00898": "single(n=137 counts=A35/B37/C37/D28 max_share=27.0% verdict=ok)",
        "02333": "single(n=68 counts=A12/B21/C17/D18 max_share=30.9% verdict=ok)",
    }
    for code, fragment in expected.items():
        assert fragment in lines[code], f"{code} 实测分布与基线表不符:\n  {lines[code]}\n  缺 {fragment}"
    assert "judgement(n=10 counts=正确4/错误6 max_share=60.0% verdict=ok)" in lines["00898"], lines["00898"]
    # 唯一超 40% 的既有课是 15043（74.6%）—— 只报告，不阻断
    assert "enforced=false" in lines["15043"], lines["15043"]


# --------------------------------------------------------------------------------------
# AC6：AST call-node —— 前两次死守卫的教训（谓词定义在源码里、没人调用）
# --------------------------------------------------------------------------------------

def _call_lines_outside_own_def(tree: ast.Module, name: str) -> list[int]:
    """`name` 的调用行号，且**排除**它自己 `def` 行区间内的一切（自调用不算调用点）。"""
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    own = functions.get(name)
    assert own is not None, f"{name} 在模块顶层没有定义"
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        callee_name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
        if callee_name != name:
            continue
        if own.lineno <= node.lineno <= (own.end_lineno or own.lineno):
            continue
        lines.append(node.lineno)
    return lines


def test_distribution_predicates_have_call_sites_inside_the_gate():
    """三个谓词都必须被 `run_ai_content_gate()` **调用**（定义在别处、没人调 = 死守卫）。"""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    gate = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_ai_content_gate"
    )
    for name in ("answer_distribution", "content_tracking_state", "_answer_distribution_problems"):
        sites = _call_lines_outside_own_def(tree, name)
        assert sites, f"{name} 只有 `def`、没有调用点 —— 这正是 B3b 四个死谓词的形态"
        assert any(gate.lineno <= line <= (gate.end_lineno or gate.lineno) for line in sites), (
            f"{name} 的调用点不在 run_ai_content_gate() 内（调用链没接进闸门主循环）: {sites}"
        )


def test_scope_signal_is_not_a_hardcoded_course_list():
    """作用域信号不得退化成硬编码课码清单或 mtime / `generated_at`（Clarify C3 明令禁止的旧缺陷类）。

    按 **AST** 检查（标识符与字符串字面量），不是文本匹配 —— 文档里提到这些名字是允许的，
    把它们**用作判据**才是缺陷。
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    probe = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "content_tracking_state"
    )
    identifiers = {n.id for n in ast.walk(probe) if isinstance(n, ast.Name)}
    identifiers |= {n.attr for n in ast.walk(probe) if isinstance(n, ast.Attribute)}
    for forbidden in ("st_mtime", "getmtime", "generated_at"):
        assert forbidden not in identifiers, f"禁止用 {forbidden} 做作用域信号（replay 会回放旧日期）"

    literals = [n.value for n in ast.walk(probe) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    joined = "\n".join(literals)
    for code in ("15040", "15043", "15044", "00898", "02333"):
        assert code not in joined, f"跟踪判定里出现硬编码课码 {code}"
    assert "ls-files" in literals and "--error-unmatch" in literals, (
        f"跟踪判定必须走 git 索引: {literals}"
    )
