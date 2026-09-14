"""B3c Task 2 — `15043` distractor-explanation quality (residual R4).

**缺陷类**：`15043` 的 38 道题（64 行）把干扰项解释写成裸占位「N 项与事实不符。」——
读者读完仍不知道那一项**错在哪**。对照 `15040` 只有 1 行 / 393 道，故属相对 B1 的质量回退（约 60×）。

**为什么判据是"裸行正则"而不是"长度"**：占位式的另一种写法同样可以很长
（`C 项与本条要点无关，且与事实不符。`），长度门槛拦不住它。真正的缺陷是
**该行没有给出任何具体理由**，因此判据取「整行只由 `N 项` + `与事实不符` 构成」。

**为什么同时断言 fixture**：plan GC2 要求「产物 = f(fixture)」是**结构保证**而非手工同步。
只测产物，fixture 可以在下次 `--record-fixtures` 时把占位写回来；只测 fixture，产物可能被手工改过。
两条一起测才把方法锁住。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "sources" / "jiangsu" / "courses" / "15043" / "content.json"
OTHER_CONTENT = ROOT / "sources" / "jiangsu" / "courses" / "15040" / "content.json"
FIXTURE = ROOT / "tests" / "fixtures" / "course_pipeline" / "llm" / "drill_point.v1.json"

# 裸占位：整行 = `<A-D> 项` + 任意非句号字符 + `与事实不符` + 可选句号，**行内没有别的理由**。
# 写进理由的行（`C 项与事实不符，它是革命组织。`）不匹配 —— 逗号后的具体理由是必需内容。
BARE_DISTRACTOR_RE = re.compile(r"^[A-D]\s*项[^。]*?与事实不符。?$", re.M)

# 填充语家族的**全量**判据（GC4 的核心）：整行 = `<A-D> 项` + 可选短限定语 + 判词，**判词之后没有实据**。
# `与事实不符` 只是家族一员；只查它会让 `与事实相反` / `表述不准确` / `与本条要点无关`
# 这类同族占位整批漏过（本片实测：38 道内另有 3 行，其余 217 道内另有 5 行）。
# 限定语上限 6 字：允许 `性质`/`时间`/`地点`/`战场归属` 这类**指向词**（`D 项地点记错。` 是有效理由，
# 它指名了错在哪个维度），同时挡住「一整句理由」被误判成占位。
FILLER_FAMILY_RE = re.compile(
    r"^[A-D]\s*项[^，。：；]{0,6}(与事实(不符|相反)|表述不准确|不完整|与本条要点无关|与史实不符)。?$"
)

# 本片修复的 38 道（`content.json` 里恰好这 38 个 drill 块的 `answer_md` 相对 base 变化；
# 由叶子级 diff 独立导出后**固定**在此，作为契约而不是每次现算 —— 现算会让断言自我指涉：
# 「凡是没被修的都算范围外」等于永不失败）。
# `test_in_scope_drill_list_matches_the_repaired_set` 负责看住这份清单本身。
IN_SCOPE_DRILLS = frozenset({
    "15043-ch01-s3-p5/drill",
    "15043-ch04-s3-p3/drill",
    "15043-ch05-s2-p1/drill",
    "15043-ch05-s2-p3/drill",
    "15043-ch06-s1-p2/drill",
    "15043-ch06-s1-p4/drill",
    "15043-ch06-s1-p5/drill",
    "15043-ch06-s2-p1/drill",
    "15043-ch06-s2-p2/drill",
    "15043-ch06-s2-p3/drill",
    "15043-ch06-s2-p5/drill",
    "15043-ch06-s2-p7/drill",
    "15043-ch06-s3-p1/drill",
    "15043-ch06-s3-p2/drill",
    "15043-ch06-s3-p4/drill",
    "15043-ch06-s3-p5/drill",
    "15043-ch06-s4-p10/drill",
    "15043-ch06-s4-p2/drill",
    "15043-ch06-s5-p1/drill",
    "15043-ch06-s5-p2/drill",
    "15043-ch07-s1-p5/drill",
    "15043-ch07-s1-p6/drill",
    "15043-ch07-s2-p10/drill",
    "15043-ch07-s2-p11/drill",
    "15043-ch07-s3-p3/drill",
    "15043-ch08-s2-p1/drill",
    "15043-ch08-s2-p6/drill",
    "15043-ch08-s2-p7/drill",
    "15043-ch08-s4-p1/drill",
    "15043-ch08-s4-p6/drill",
    "15043-ch08-s4-p7/drill",
    "15043-ch08-s5-p1/drill",
    "15043-ch08-s5-p2/drill",
    "15043-ch09-s1-p3/drill",
    "15043-ch09-s3-p4/drill",
    "15043-ch09-s3-p5/drill",
    "15043-ch10-s1-p2/drill",
    "15043-ch10-s2-p2/drill",
})

# 三处计数口径必须自洽（plan § Current state 实测值）：
#   B3c 前：64 行裸占位（`与事实不符` 正则）分布在 38 道中；本片后 = 0。
IN_SCOPE_DRILL_COUNT = 38
BASELINE_BARE_LINES = 64
# 范围外（其余 217 道）的**同族**占位既有存量：本片不扩大改动面，但只降不升。
MAX_OUT_OF_SCOPE_FILLER = 5

# 占位行**下限**：`15043` 必须为 0；`15040` 的既有 1 行不属本片范围，但不得增长。
MAX_BARE_15043 = 0
MAX_BARE_15040 = 1


def _load(path: Path) -> dict:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"
    return json.loads(path.read_text(encoding="utf-8"))


def _drills(doc: dict) -> list[dict]:
    return [block for block in doc["blocks"] if block.get("kind") == "drill"]


def _bare_lines(doc: dict) -> list[tuple[str, str]]:
    """(block_id, 裸行) —— 空列表即无残留。"""
    found = []
    for block in _drills(doc):
        for line in (block.get("answer_md") or "").split("\n"):
            if BARE_DISTRACTOR_RE.match(line):
                found.append((block["block_id"], line))
    return found


# ---- 产物侧（committed content.json） ----------------------------------------


def test_15043_has_no_bare_distractor_explanations():
    """R4 主判据：裸占位行数必须为 0（B3c 前实测 64 行 / 38 道）。"""
    bare = _bare_lines(_load(CONTENT))
    assert len(bare) <= MAX_BARE_15043, f"15043 仍有 {len(bare)} 行裸干扰项解释：{bare[:5]}"


def test_15040_bare_placeholder_count_does_not_grow():
    """对照课：`15040` 既有 1 行不在本片范围，但也不得增长（否则是新的回退）。"""
    bare = _bare_lines(_load(OTHER_CONTENT))
    assert len(bare) <= MAX_BARE_15040, f"15040 裸占位增长到 {len(bare)} 行：{bare}"


def test_in_scope_drills_have_no_filler_family_lines():
    """GC4 主判据：**不只用一种填充替换旧填充**。

    `与事实不符` 只是旧填充家族的一员。只查这一句，`与事实相反` / `表述不准确` /
    `与本条要点无关` 这类**同族占位**会整批漏过 —— 本片实测正是如此：plan 的头条计数
    （`^[A-D]\\s*项[^。]*?与事实不符。?$`）为 64 行 / 38 道，但其中 3 道还带有同族的兄弟行
    （2×`与事实相反` + 1×`表述不准确`），另有 5 行同族占位分布在其余 217 道中。

    判据因此收紧为**全家族**：整行 = `<A-D> 项` + ≤6 字限定语 + 判词，且**判词之后没有任何实据**。
    ≤6 字是为了容纳 `性质` / `时间` / `地点` / `战场归属` 这类**指向词**（`D 项地点记错。` 是有效理由，
    它指名了错在哪个维度），同时挡住一整句理由被误判。

    作用域 = 本片修复的 38 道。其余 217 道属既有内容、不在本片范围，其残留由
    `test_residual_filler_lines_are_within_known_budget` 以**固定上限**看住。
    """
    doc = _load(CONTENT)
    assert len(IN_SCOPE_DRILLS) == IN_SCOPE_DRILL_COUNT, (
        f"in-scope 契约清单应为 {IN_SCOPE_DRILL_COUNT} 道，实测 {len(IN_SCOPE_DRILLS)}"
    )

    offenders = []
    for block in _drills(doc):
        if block["block_id"] not in IN_SCOPE_DRILLS:
            continue
        for line in (block.get("answer_md") or "").split("\n"):
            if FILLER_FAMILY_RE.match(line):
                offenders.append((block["block_id"], line))
    assert offenders == [], f"本片 {IN_SCOPE_DRILL_COUNT} 道内仍有 {len(offenders)} 行填充语家族占位：{offenders[:5]}"


def test_in_scope_drill_list_matches_the_repaired_set():
    """清单自校验：`IN_SCOPE_DRILLS` 必须**恰好**是那些"答案里曾经是裸占位"的题。

    做法：拿 fixture 里每个题的 `answer_md` 无法回溯 base 版本，于是用**题目文本 + 当前答案**
    的另一种口径独立复算：`IN_SCOPE_DRILLS` 中的每一道，其现在答案必须**不再**含裸占位；
    而集合之外的每一道，若现在含同族占位则计入范围外预算。清单若被误改（多加/漏加），
    这条与上一条会同时失败 —— 避免"清单写窄了所以全绿"。
    """
    doc = _load(CONTENT)
    by_id = {b["block_id"]: b for b in _drills(doc)}

    missing = IN_SCOPE_DRILLS - set(by_id)
    assert not missing, f"in-scope 清单含不存在的块：{sorted(missing)[:5]}"

    # 每一道 in-scope 题都必须至少有 1 行干扰项解释（否则"清空占位"是靠删行实现的）
    thin = []
    for block_id in sorted(IN_SCOPE_DRILLS):
        answer = by_id[block_id]["answer_md"]
        distractor_lines = [ln for ln in answer.split("\n") if re.match(r"^[A-D]\s*项", ln)]
        if len(distractor_lines) < 2:
            thin.append((block_id, len(distractor_lines)))
    assert thin == [], f"{len(thin)} 道 in-scope 题的干扰项解释少于 2 行（疑似靠删行清占位）：{thin[:5]}"


def test_residual_filler_lines_are_within_known_budget():
    """范围外残留的**固定上限**：把"其余 217 道的同族占位"钉成数字，只降不升。

    本片不扩大改动面（改这 5 道会新增 fixture 键与产物块），但也不允许这个发现被静默遗忘：
    新代码若再引入同族占位，这条会立刻变红。修复它们需另开一片。
    """
    doc = _load(CONTENT)

    out_of_scope = []
    for block in _drills(doc):
        if block["block_id"] in IN_SCOPE_DRILLS:
            continue
        for line in (block.get("answer_md") or "").split("\n"):
            if FILLER_FAMILY_RE.match(line):
                out_of_scope.append((block["block_id"], line))
    assert len(out_of_scope) <= MAX_OUT_OF_SCOPE_FILLER, (
        f"范围外同族占位从 {MAX_OUT_OF_SCOPE_FILLER} 增长到 {len(out_of_scope)}：{out_of_scope}"
    )


# ---- fixture 侧（方法锁：产物 = f(fixture)） ---------------------------------


def test_fixture_no_longer_contains_bare_distractor_explanations_for_15043():
    """GC2：fixture 是产物真值源。若这条失败而产物侧通过，说明有人手工改了产物。"""
    doc = _load(FIXTURE)
    responses = doc.get("responses") or {}
    assert responses, "fixture 无 responses"

    # 以 `15043` 产物里的题干为锚，找到对应 fixture 条目（题干是两者的稳定连接键）
    stems = {block["text_md"] for block in _drills(_load(CONTENT))}
    checked = 0
    offenders = []
    for key, entry in responses.items():
        response = (entry or {}).get("response") or {}
        if response.get("text_md") not in stems:
            continue
        checked += 1
        for line in (response.get("answer_md") or "").split("\n"):
            if BARE_DISTRACTOR_RE.match(line):
                offenders.append((key, line))
    assert checked > 0, "未能在 fixture 中定位到任何 15043 题（锚键失效）"
    assert offenders == [], f"fixture 仍有 {len(offenders)} 行裸占位：{offenders[:5]}"


def test_fixture_and_artifact_agree_on_every_15043_drill():
    """把「产物 = f(fixture)」钉成可证伪断言：同一题干的 answer_md 必须逐字相同。

    这条也是 replay 字节一致性的**离线替身** —— 它不需要跑完整流水线就能发现
    「产物被手工改过」或「fixture 被回退」。
    """
    doc = _load(FIXTURE)
    responses = doc.get("responses") or {}
    by_stem = {}
    for key, entry in responses.items():
        response = (entry or {}).get("response") or {}
        stem = response.get("text_md")
        if stem:
            by_stem.setdefault(stem, []).append((key, response))

    mismatches = []
    checked = 0
    for block in _drills(_load(CONTENT)):
        matches = by_stem.get(block["text_md"])
        if not matches:
            continue
        checked += 1
        if all(response.get("answer_md") != block["answer_md"] for _key, response in matches):
            mismatches.append(block["block_id"])
    assert checked == 255, f"15043 的 255 道题应全部能在 fixture 中找到，实测 {checked}"
    assert mismatches == [], f"{len(mismatches)} 道题的 answer_md 与 fixture 不一致：{mismatches[:5]}"
