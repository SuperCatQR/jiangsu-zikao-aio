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
    """N-3（T3 复审，2026-09-12）：`official_urls` 的判据必须与**生产者逐字一致**（合取：
    `authoritative` **且** 域名是 `jseea.cn` 或其子域），否则合法刷新永远无法满足断言。

    本用例的存在理由：I-1 的修复（`554a816`）只改谓词、**未加测试**，而 committed 数据上旧/新谓词
    给出**同一个** 10 元素集合 —— 即回退该修复后整套件仍然全绿，修复没有耐久守护。此用例用
    **合成 baseline**（不依赖 committed 数据）把谓词钉住：构造一条 `jseea.cn` 但
    `authoritative=False` 的 URL，旧实现会把它算作官方、生产者不会 —— 本断言必须失败。
    """
    baseline = {
        "urls": {
            "https://www.jseea.cn/a.html": {"authoritative": True},
            "https://zsb.jseea.cn/sub.html": {"authoritative": True},   # 子域 + authoritative → 官方
            "https://www.jseea.cn/b.html": {"authoritative": False},    # 域名对但非权威 → **不是**官方
            "https://eviljseea.cn/c.html": {"authoritative": True},      # 权威标记但域名不符 → **不是**官方
            "https://example.com/d.html": {"authoritative": True},       # 非官方域 → **不是**官方
        }
    }
    assert official_urls(baseline) == {
        "https://www.jseea.cn/a.html",
        "https://zsb.jseea.cn/sub.html",
    }
