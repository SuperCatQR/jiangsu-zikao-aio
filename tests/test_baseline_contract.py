"""B2-D4 语义断言的**可失败性**与契约覆盖（反向验证的可运行形式）。

plan Task 3 Step 4 要求证明新的语义断言没有退化成恒真检查：人为改 baseline 一个字节 →
断言必须报错；还原后必须重新通过。本文件把那一步固化为**长期用例**（而不是只在
task report 里贴一次命令输出），并补齐 helper 各分支的覆盖。
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from tests.baseline_contract import (
    BASELINE_PATH,
    CATALOG_PATH,
    SNAPSHOT_PATH,
    assert_contract,
    assert_contract_can_fail,
    assert_unwritten,
    coherence_problems,
    contract_problems,
    official_set_problems,
    official_urls,
)


def _probe_root(tmp_path: Path) -> Path:
    """把契约涉及的三个文件复制进一个可安全变异的假根。"""
    root = tmp_path / "root"
    for rel in (BASELINE_PATH, SNAPSHOT_PATH, CATALOG_PATH):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] / rel, target)
    return root


def test_committed_baseline_and_snapshot_satisfy_the_contract():
    """committed 树上契约**当下即为绿**（断言不得要求先改 baseline，GC14）。"""
    assert_contract()


def test_contract_detects_official_url_byte_mutation():
    """反向验证：官方 URL 改一个字节 → 官方集合断言必须失败（证明检查能失败）。"""
    assert_contract_can_fail()


@pytest.mark.parametrize(
    "mutate, expect",
    [
        # 官方主机被改掉 → 官方集合与快照不再相等（语义判定，不是字节规范化）。
        (lambda doc: doc["urls"].pop(next(u for u in doc["urls"] if "jseea" in u)), "not official"),
        # 状态与码位配对被破坏。
        (
            lambda doc: next(
                it for it in doc["urls"].values() if it["status"] == "ok"
            ).update({"http_code": 503}),
            "status=ok",
        ),
        # 非权威条目带上内容指纹（writer 从不这么产出）。
        (
            lambda doc: next(
                it for it in doc["urls"].values() if not it["authoritative"]
            ).update({"content_hash": "0" * 64}),
            "non-authoritative",
        ),
        # 课码脱离目录真源（GC11）。
        (
            lambda doc: doc["urls"][next(iter(doc["urls"]))].update({"course_codes": ["99999"]}),
            "catalog",
        ),
        # 逐条键缺失。
        (
            lambda doc: doc["urls"][next(iter(doc["urls"]))].pop("sections"),
            "entry keys",
        ),
    ],
)
def test_coherence_check_rejects_mutations(tmp_path, mutate, expect):
    """契约的每一条实质分支都能**真的失败**（逐条反向验证，避免「有断言但不生效」）。"""
    root = _probe_root(tmp_path)
    baseline = root / BASELINE_PATH
    doc = json.loads(baseline.read_text(encoding="utf-8"))
    mutate(doc)
    baseline.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    problems = coherence_problems(root) + official_set_problems(root)
    assert any(expect in problem for problem in problems), (
        f"expected a problem mentioning {expect!r}, got: {problems}"
    )


def test_mutated_snapshot_is_detected(tmp_path):
    """快照侧漂移（在线 URL 集合里多一条 / 少一条）必须报错。"""
    root = _probe_root(tmp_path)
    snapshot = root / SNAPSHOT_PATH
    doc = json.loads(snapshot.read_text(encoding="utf-8"))
    doc["urls"] = doc["urls"][:-1]  # 丢掉一条官方 URL
    doc["count"] = len(doc["urls"])
    snapshot.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    problems = official_set_problems(root)
    assert problems, "a snapshot missing an official URL must fail the contract"
    assert any("missing from snapshot" in problem for problem in problems), problems


def test_helper_does_not_write_the_committed_baseline():
    """反向验证本身**不得**改到仓内 baseline（GC14：文件零字节改动）。"""
    baseline = Path(__file__).resolve().parents[1] / BASELINE_PATH
    before = baseline.read_bytes()
    assert_contract_can_fail()
    assert baseline.read_bytes() == before


def test_scratch_dirs_are_cleaned_up():
    """`assert_contract_can_fail` 在临时目录内工作，不留残渣在仓内。"""
    root = Path(__file__).resolve().parents[1]
    before = sorted(p.name for p in root.iterdir())
    with tempfile.TemporaryDirectory(prefix="baseline-contract-") as scratch:
        assert_contract_can_fail(scratch=Path(scratch))
    assert sorted(p.name for p in root.iterdir()) == before


def test_missing_files_are_reported_not_raised(tmp_path):
    """文件缺失必须**报错**（返回违规清单），不得抛 `FileNotFoundError` 让上层失去可读诊断。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert any("missing" in p for p in coherence_problems(empty))
    assert any("missing" in p for p in official_set_problems(empty))
    assert contract_problems(empty), "an empty root must not silently pass"


def test_official_set_predicate_matches_the_producer():
    """N-3（T3 复审）+ R7/F-QC3-6（B2a QC wave 1）：官方判据只有**一处定义**，且守护测试真的调用它。

    本用例的存在理由：I-1 的修复（`554a816`）只改谓词、**未加测试**，而 committed 数据上旧/新谓词
    给出**同一个** 10 元素集合 —— 即回退该修复后整套件仍然全绿，修复没有耐久守护。
    上一轮又只把合取式在 `baseline_contract.py` 内**复述**了一遍，于是仍有**三处**定义
    （生产者 / `official_source.is_official_url()` / 本模块），而守护测试只测第三处、从不调用生产者。

    现在 `official_urls()` **委托**生产者 `snapshot-official-sources.py:is_official()`，
    本用例按合成输入把二者钉在一起：包括 `www.jseea.com.cn`（在 writer 的 `AUTHORITATIVE_HOSTS` 里、
    但**不是** `jseea.cn` 子域）、真子域、`authoritative=false`、以及 `eviljseea.cn` 这种后缀陷阱。

    **分歧方向（QC3 F-QC3-6 的校准）**：生产者用裸 `host.endswith("jseea.cn")`，因此对
    `eviljseea.cn` + `authoritative=true` 判为官方；`official_source.is_official_url()`（精确 host 或
    `.jseea.cn` 子域）判为非官方。guard 现在**跟生产者** —— 这正是单一真源的意义：guard 断言
    「官方集合 == 快照集合」，而快照由该谓词产出，换任何别的定义都会让合法刷新无法满足断言。
    生产者的宽松 `endswith` 是**生产者侧**的已知弱点（其模块 docstring 自陈），且在 writer 路径上不可达：
    `eviljseea.cn` 不在 `check-source-links.py` 的 `AUTHORITATIVE_HOSTS` 里，writer 永远不会为它写出
    `authoritative: true`。收紧生产者本身不在本轮范围内。
    """
    from tests.baseline_contract import PRODUCER_IS_OFFICIAL

    cases: list[tuple[str, dict, bool]] = [
        # 域名对 + authoritative → 官方
        ("https://www.jseea.cn/a.html", {"authoritative": True}, True),
        # 子域 + authoritative → 官方
        ("https://zsb.jseea.cn/sub.html", {"authoritative": True}, True),
        # 裸域 → 官方
        ("https://jseea.cn/x", {"authoritative": True}, True),
        # 域名对但非权威 → 不是官方
        ("https://www.jseea.cn/b.html", {"authoritative": False}, False),
        # `www.jseea.com.cn` 在 writer 的 AUTHORITATIVE_HOSTS 里，但**不是** jseea.cn 子域 → 不是官方
        ("https://www.jseea.com.cn/c.html", {"authoritative": True}, False),
        # 后缀陷阱：生产者的裸 `endswith("jseea.cn")` **接受** `eviljseea.cn`（生产者侧已知弱点）
        ("https://eviljseea.cn/d.html", {"authoritative": True}, True),
        # 非官方域 → 不是官方
        ("https://example.com/e.html", {"authoritative": True}, False),
        # authoritative 缺失 → 不是官方
        ("https://www.jseea.cn/f.html", {}, False),
    ]

    for url, item, expected in cases:
        assert bool(PRODUCER_IS_OFFICIAL(url, item)) is expected, (
            f"对照前提：生产者的判据对 {url} / {item} 应为 {expected}"
        )
        baseline = {"urls": {url: item}}
        assert (official_urls(baseline) == {url}) is expected, (
            f"guard 的判据与生产者分歧：{url} / {item}（期望官方={expected}）"
        )

    # 汇总口径：合成 baseline 上的集合必须与「逐条调用生产者」的结果**逐元素相等**
    baseline = {"urls": {url: item for url, item, _ in cases}}
    assert official_urls(baseline) == {
        url for url, item, _ in cases if PRODUCER_IS_OFFICIAL(url, item)
    }, "guard 必须与生产者逐元素一致（单一真源）"


def test_official_set_predicate_divergence_would_be_caught():
    """R7 反向验证：guard 必须跟**生产者**，而不是退回本模块自行复述的合取式。

    两处历史判定在 `eviljseea.cn` 上分歧：生产者（裸 `endswith`）**接受**它，
    `official_source.is_official_url()`（精确 host / `.jseea.cn` 子域）**拒绝**它。
    guard 现在跟生产者；若有人把 guard 改回「合取 `authoritative` 且 `is_official_url`」的旧实现，
    本用例必须变红 —— 那正是 QC3 记录下来的「三处定义」形态。
    """
    from lib.course_pipeline.official_source import is_official_url
    from tests.baseline_contract import PRODUCER_IS_OFFICIAL

    trap = "https://eviljseea.cn/d.html"
    item = {"authoritative": True}

    # 对照前提：两处谓词在这一点上**确实**分歧（否则本用例证明不了什么）
    assert is_official_url(trap) is False, "对照前提：域名判据拒绝 eviljseea.cn"
    assert PRODUCER_IS_OFFICIAL(trap, item) is True, "对照前提：生产者接受 eviljseea.cn（裸 endswith）"

    # guard 现在跟的是生产者 → 接受该 URL
    assert official_urls({"urls": {trap: item}}) == {trap}
    # 而复述旧合取式的实现会拒绝它 —— 本用例因此能挡住那次回退
    old_predicate_set = {
        url for url, entry in {trap: item}.items() if entry.get("authoritative") and is_official_url(url)
    }
    assert old_predicate_set == set(), "对照前提：旧实现确实会拒绝该 URL（分歧可复现）"
    assert official_urls({"urls": {trap: item}}) != old_predicate_set, "guard 不得退回旧合取式"


# --------------------------------------------------------------------------------------
# R13：`assert_unwritten` 的守护测试（M-1 修复此前无测试，且措辞不准）
# --------------------------------------------------------------------------------------

def test_assert_unwritten_passes_when_the_block_writes_nothing(tmp_path: Path):
    """正向：块内不写 → 通过。"""
    target = tmp_path / "untouched.json"
    target.write_text("original\n", encoding="utf-8")

    with assert_unwritten([target]):
        target.read_text(encoding="utf-8")

    assert target.read_text(encoding="utf-8") == "original\n"


def test_assert_unwritten_fails_when_the_block_writes(tmp_path: Path):
    """M-1 核心：块内写入 → 必须失败（无 `finally` 的旧实现只在正常退出时检查，写后抛即可逃逸）。"""
    target = tmp_path / "written.json"
    target.write_text("original\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="was written by the code path under test"):
        with assert_unwritten([target]):
            target.write_text("mutated\n", encoding="utf-8")


def test_assert_unwritten_fails_on_write_then_raise(tmp_path: Path):
    """M-1 逃逸路径：**先写后抛**也必须被抓到；原始异常只作为 `__context__` 保留（R13 措辞更正）。

    旧实现（无 `try/finally`）在块内抛异常时直接跳过比对，写入逃逸。
    现实现于 `finally` 中比对：`raise` 会**替换**正在传播的异常 —— 调用方看到的是 `AssertionError`，
    被替换的原始异常挂在 `__context__` 上（Python 隐式异常链），**不是**「原始异常优先传播」。
    """
    target = tmp_path / "write-then-raise.json"
    target.write_text("original\n", encoding="utf-8")

    class Boom(RuntimeError):
        pass

    with pytest.raises(AssertionError, match="was written by the code path under test") as caught:
        with assert_unwritten([target]):
            target.write_text("mutated\n", encoding="utf-8")
            raise Boom("original failure")

    # 措辞更正所依据的事实：原异常不在 `__cause__` 上（那需要 `raise ... from`），而在 `__context__` 上
    assert isinstance(caught.value.__context__, Boom), (
        f"原始异常应作为 __context__ 保留，实际 {caught.value.__context__!r}"
    )
    assert caught.value.__cause__ is None, "`finally` 里的 raise 不带 `from`，故 __cause__ 为空"


def test_assert_unwritten_is_not_tautological(tmp_path: Path):
    """反向对照：同一 path 列表在「不写」与「写」两种块下必须给出不同结果（用例本身可失败）。"""
    target = tmp_path / "config.json"
    target.write_text("{}\n", encoding="utf-8")

    with assert_unwritten([target]):
        pass

    with pytest.raises(AssertionError):
        with assert_unwritten([target]):
            target.write_bytes(b"{}\n\n")
