"""`R53` 排程排序不变量（`INV-R53`）：**先把前提证伪，再把不变量钉成可证伪的回归测试**。

`R53`（B3b 计划 QC 三席 Suggestion，PM 升格为 open）称 `_tier()` 的日程条目“按单元序排序”，
于是「章概览」会排在其自身编号子节（`1.1` / `1.2`）之后。B4a Task 2 的 Step 1 在**已交付产物上
实测不可复现**，本文件把该结论钉成可核的三条：

1. `INV-R53`（`test_inv_r53_tier_order_equals_canonical_order`，按**全部**已交付模型参数化）：
   `_tier()` 的条目序 == `order_blocks()` 的规范序。跨课参数化 —— 新课程接入后自动进入守护范围。
2. **守卫会响**（`test_inv_r53_guard_fires_on_mutated_model_ordinal_out_of_order`）：构造一份
   「非首个附录 `ordinal` 置 0」的模型副本，`INV-R53` 必须变红，且报错含首个分歧位置 + 两侧四元组键。
   没有这条正向控制，`INV-R53` 就是「条件永真」的守卫（本项目已两次踩到：B2a `W-1`、B3b 三谓词）。
3. **证伪边界**（`test_inv_r53_premise_section_reordering_is_invisible_to_the_key`）：节级倒序对
   `INV-R53` **完全不可见** —— `_tier()` 与 `_point_order()` 都取 `enumerate(unit["sections"])` 的
   **列表位置**，两侧同步翻转。故 `R53` 描述的「章概览排在其编号子节之后」在内核上不可达：
   要复现它必须存在一条**按 `section.index` 字典序排序**的代码路径，全仓不存在该路径。

`R53` 的**重开触发条件**（与 register 的 `closure_note` 同口径，任一失守即须重开）：
`test_inv_r53_premises_hold_over_delivered_models` 的三条前提 —— 交付模型数下界、
模型自带 `section.index` 且不带 `.`（`knowledge_model.SECTION_RE` 只认 `^(\\d+)\\.`，
故 `1.1` 形态在**模型格式上**不可表达）、以及每门课都有非空嵌套序。

排程须**现场驱动**生产函数才谈得上可观测：既有 5 门课的 `review_schedule` 全是 `named_gap`
（`plans == []`），仓内没有任何已发布排程可读，故本文件的考期入参是合成的（不落盘）。
"""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from lib.course_pipeline import generate_content as gc

ROOT = Path(__file__).resolve().parents[1]
MODELS = sorted((ROOT / "sources" / "jiangsu" / "courses").glob("*/knowledge-model.json"))

# 合成考期入参：只为把 `_tier()` 驱动起来（`_exam_inputs()` 要求 exam_date + weekly_hours > 0）。
# 本文件不写任何文件，合成值不进仓内产物。
SYNTHETIC_EXAM_DATE = date(2026, 12, 19)
SYNTHETIC_WEEKLY_HOURS = 6.0
SYNTHETIC_GENERATOR = {
    "backend": "cli",
    "model": "inv-r53-probe",
    "prompt_id": "stage_plan",
    "prompt_version": "v1",
    "generated_at": "2026-09-18T00:00:00Z",
}
# `R53` 点名的是 30 天档（`_tier()` 的条目序与档位无关，仍按点名档驱动一次）。
HORIZON_DAYS = gc.HORIZONS[0]

# 序短于对方时的哨兵值：长度不一致同样是分歧（`_point_order()` 是 dict，重复 point id 会静默塌缩）。
MISSING = "<序更短：无此位置>"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tier_order_ids(model: dict) -> list[str]:
    """`_tier()` 构造条目所用的嵌套序（`_units()` 阅读序 → `sections` 列表序 → `points` 列表序）。"""
    return [
        point["id"]
        for unit in gc._units(model)
        for section in unit["sections"]
        for point in section["points"]
    ]


def _scheduled_ids(model: dict) -> list[str]:
    """**真实** `_tier()` 输出的点序（按 `plans[].items[].point_ids` 展平，含分档切片层）。"""
    plan = gc._tier(
        model, HORIZON_DAYS, SYNTHETIC_EXAM_DATE, SYNTHETIC_WEEKLY_HOURS, SYNTHETIC_GENERATOR
    )
    return [point_id for item in plan["items"] for point_id in item["point_ids"]]


def _canonical_ids(model: dict) -> list[str]:
    """`order_blocks()` 的规范序（design-notes § 3.1 的 `order_blocks_canonical_order(M)`）。"""
    order = gc._point_order(model)
    return sorted(order, key=order.get)


def _first_divergence(actual_ids: list[str], canonical_ids: list[str]) -> tuple[int, str, str]:
    for position in range(max(len(actual_ids), len(canonical_ids))):
        actual = actual_ids[position] if position < len(actual_ids) else MISSING
        expected = canonical_ids[position] if position < len(canonical_ids) else MISSING
        if actual != expected:
            return position, actual, expected
    raise AssertionError("两条序逐位相同，无分歧可报（调用方不应在无分歧时询问首个分歧位置）")


def _divergence_report(
    model: dict, actual_ids: list[str], canonical_ids: list[str], *, actual_label: str = "_tier order"
) -> str:
    """design-notes § 3.2 的失败信息形态：首个分歧位置 + 两侧四元组键。

    只报「序不同」无法定位是 `unit_class` 错（附录插错位置）、`ordinal` 错（单元序）还是
    `section_index` / `point_index` 错，故四元组键是失败信息的一部分而不是调试辅助。
    """
    position, actual, expected = _first_divergence(actual_ids, canonical_ids)
    order = gc._point_order(model)
    return (
        f"R53 invariant violated: {model.get('course_code')}\n"
        f"  first divergence at position {position}:\n"
        f"    {actual_label:<17} -> {actual}\n"
        f"    canonical order   -> {expected}\n"
        f"  unit_class/ordinal/section_index/point_index of each: "
        f"{order.get(actual)} vs {order.get(expected)}"
    )


def _assert_same_order(
    model: dict, actual_ids: list[str], *, actual_label: str = "_tier order"
) -> None:
    assert actual_ids == _canonical_ids(model), _divergence_report(
        model, actual_ids, _canonical_ids(model), actual_label=actual_label
    )


def assert_tier_order_is_canonical(model: dict) -> None:
    """`INV-R53`：`point_ids(_tier_order(M)) == point_ids(canonical_order(M))`。"""
    _assert_same_order(model, _tier_order_ids(model))


def _appendix_bearing_model() -> tuple[Path, dict]:
    """带附录的交付模型（附录是 `R53` 唯一可能撞车的位置：附录 `ordinal` 与章同域）。"""
    for path in MODELS:
        model = _load(path)
        if model.get("appendices"):
            return path, model
    pytest.fail("对照前提：已交付模型里必须至少有一门带附录的课，否则本文件的变异控制失去作用对象")


def _multi_section_model() -> tuple[Path, dict]:
    """含**多节单元**的交付模型（节级倒序必须真能改变嵌套序，才谈得上「对键不可见」）。"""
    for path in MODELS:
        model = _load(path)
        if any(len(unit["sections"]) >= 2 for unit in gc._units(model)):
            return path, model
    pytest.fail("对照前提：已交付模型里必须至少有一门课带多节单元，否则节级倒序是空操作")


def test_inv_r53_premises_hold_over_delivered_models() -> None:
    """`R53` 的三条前提（= 重开触发条件）：任一失守都说明「不可复现」的结论必须重核。

    ① 交付模型数下界（**不**硬编码课码清单 —— 那是 C3 明令禁止的旧缺陷类，改为从目录推导的基数）；
    ② 每门课都有非空嵌套序（否则本文件退化为空集合上的恒真检查）；
    ③ `section.index` 是整数串、**不带 `.`**：`knowledge_model.SECTION_RE` 只认 `^(\\d+)\\.`，
    `（N）` 版式经 `_chinese_number()` 也归约成整数，故 `R53` 举例的 `1.1` 子节在**模型格式上**
    不可表达 —— 它若出现，说明模型契约变了，`R53` 的前提须重新评估。
    """
    assert len(MODELS) >= 5, f"对照前提：交付模型数不得少于 5（实际 {len(MODELS)}：{MODELS}）"
    for path in MODELS:
        model = _load(path)
        code = model["course_code"]
        assert model["chapters"], f"{code}: 模型必须自带 chapters"
        assert _tier_order_ids(model), f"{code}: 嵌套序不得为空"
        dotted = [
            section["index"]
            for unit in gc._units(model)
            for section in unit["sections"]
            if "." in section["index"]
        ]
        assert not dotted, (
            f"{code}: `R53` 举例的编号子节形态（`1.1`）在模型格式上不可表达，"
            f"实测却出现 {dotted} —— `R53` 的前提须重新评估"
        )


@pytest.mark.parametrize("model_path", MODELS, ids=lambda path: path.parent.name)
def test_inv_r53_tier_order_equals_canonical_order(model_path: Path) -> None:
    """`INV-R53` 跨**全部**已交付模型成立（不只两门新课，含唯一带附录的课）。

    两条腿各测一层：嵌套序 == 规范序（design-notes § 3.1 的断言形态），以及**真实** `_tier()`
    产物展平后的点序 == 规范序（多覆盖 `items[]` 的分档切片层）。
    """
    model = _load(model_path)
    assert_tier_order_is_canonical(model)
    _assert_same_order(model, _scheduled_ids(model), actual_label="_tier() items")


def test_inv_r53_guard_fires_on_mutated_model_ordinal_out_of_order() -> None:
    """变异 / 正向控制：模型副本「非首个附录 `ordinal` 置 0」后，`INV-R53` 必须**变红**。

    只证明「不变式在真实模型上为绿」不足以证明它是守卫：谓词条件写错（永真）时会同样为绿。
    本控制的变异点选在**单元级** `ordinal`：`_point_order()` 按 `(unit_class, ordinal, …)` 排序，
    而 `_tier()` 按 `_units()` 的列表序 —— 两者的意见只在**单元级**才会分叉。

    实测口径（同一变异在 02333 上量过）：
    - 把**非首个**附录的 `ordinal` 置 0 → 红（本用例）；
    - 把**首个**附录或**全部**附录的 `ordinal` 置 0 → **绿**（`unit_class` 前缀 + 稳定排序下同序），
      故本用例显式钉住「作用对象必须是列表里非首个的那个」，否则变异是惰性的。
    """
    path, model = _appendix_bearing_model()
    appendices = model["appendices"]
    assert len(appendices) >= 2, (
        f"{path}: 对照前提：附录必须至少 2 个，否则「非首个附录」的变异无作用对象"
    )
    assert appendices[0]["ordinal"] != appendices[-1]["ordinal"], (
        f"{path}: 对照前提：首个与末个附录的 ordinal 必须不同，否则置 0 不产生分歧"
    )

    mutated = copy.deepcopy(model)
    mutated["appendices"][-1]["ordinal"] = 0
    mutated_code = mutated["course_code"]
    assert _tier_order_ids(mutated) != _canonical_ids(mutated), (
        f"{mutated_code}: 对照前提：该变异必须真的让两条序分叉，否则本控制测不到守卫会不会响"
    )

    with pytest.raises(AssertionError) as excinfo:
        assert_tier_order_is_canonical(mutated)

    message = str(excinfo.value)
    position, actual, expected = _first_divergence(_tier_order_ids(mutated), _canonical_ids(mutated))
    order = gc._point_order(mutated)
    assert f"R53 invariant violated: {mutated_code}" in message, message
    assert f"first divergence at position {position}" in message, message
    assert f"-> {actual}" in message and f"-> {expected}" in message, message
    assert f"{order.get(actual)} vs {order.get(expected)}" in message, (
        f"失败信息必须含两侧四元组键（design-notes § 3.2）：{message}"
    )


def test_inv_r53_premise_section_reordering_is_invisible_to_the_key() -> None:
    """`R53` 前提的**证伪**（实测）：节级倒序对 `INV-R53` 完全不可见。

    变异方案「把 `sections` 列表倒序」**不会**让本不变量变红：`_tier()`（嵌套列表序）与
    `_point_order()`（`enumerate(unit["sections"])`）取的是**同一个列表位置**，两侧同步翻转，
    故不变量仍绿 —— 这不是守卫失灵，而是 `R53` 的复现边界：即使某份模型把「章概览」排在编号
    子节之后，排程也只是**忠实照抄**模型声明的阅读序，排序键本身没有任何节级意见；
    要产生 `R53` 描述的错序，必须存在一条按 `section.index` 字典序排序的代码路径，全仓不存在。

    控制：先断言变异**确实**改变了嵌套序，否则「绿」可能只是变异没落上
    （`02333` 正是这种情形：它的单元只有 0–1 个节，节级倒序在该课上是**空操作**；
    这也一并说明 `R53` 的前提在模型形状上无处安放 —— 该课连「章概览 vs 编号子节」的对子都不存在）。
    """
    _path, model = _multi_section_model()
    mutated = copy.deepcopy(model)
    for unit in gc._units(mutated):
        unit["sections"].reverse()

    assert _tier_order_ids(mutated) != _tier_order_ids(model), (
        "对照前提：节级倒序必须真的改变嵌套序，否则本用例测不出「不可见」"
    )
    assert_tier_order_is_canonical(mutated)
    _assert_same_order(mutated, _scheduled_ids(mutated), actual_label="_tier() items")
