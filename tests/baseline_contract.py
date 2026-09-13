"""`ops/jiangsu/source-links.baseline.json` 的共享语义契约（B2-D4 / GC14）。

B1 用「该文件不得有任何 `git diff`」把 baseline 钉死（B1 的 GC14）。但 baseline 本就是
**可合法更新**的文件 —— `.github/workflows/source-link-monitor.yml` 的 `refresh-baseline`
job（`workflow_dispatch(update_baseline=true)`）与 `scripts/check-source-links.py
--update-baseline / --init-baseline` 都会写回它。把「零 diff」当全局不变量与该合法路径直接冲突，
所以 B2-D4 把它降级为 **B1 专属不变量**，改为断言该文件的**实质契约**：

1. **自洽**（`coherence_problems`）—— 形态与 `scripts/check-source-links.py` 的
   `serialize_baseline()` 能重新产出的一致：三个顶层键、六个逐条键、状态 / 哈希 / 课码的取值域，
   以及 `json.dumps(..., ensure_ascii=False, indent=2) + "\\n"` 的**重新序列化**一致
   （R8/W-6：抓缩进 / 分隔符 / 尾随换行漂移，**不**抓键序变化 —— 见该处注释）。
2. **官方集合与派生快照一致**（`official_set_problems`）—— 生产者 `is_official()` 判定的官方 URL
   集合**逐元素等于** `ops/jiangsu/official-source-snapshot.json` 记录的集合。

**官方判定的单一真源（R7/W-5/F-QC3-6）**：官方 URL 的判据只有一处定义 ——
`scripts/snapshot-official-sources.py` 的 `is_official()`（生产者）。本模块的 `official_urls()`
**委托**给它，不再自行复述合取式，也不再把 `official_source.is_official_url()`（只管域名）当成等价物。

**刻意不断言 `content_hash` 相等**：它是每次抓取的内容指纹，合法刷新必然改变它；断言哈希相等
等于把 B2-D4 要拆掉的「任何 diff 即红」换个形式装回来。**跨刷新稳定**的那一层是「哪些来源算官方」
（集合身份），不是「它们当时的内容是什么」（哈希）。哈希只按 writer 可产出的**取值域**校验。

`course_codes` 以 `sources/jiangsu/catalog/courses.json` 为单一真源（GC11）。
本模块是**纯读者**：只读文件、不写任何产物。
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterator

# R7/F-QC3-6：官方判定不再从 `official_source.is_official_url()`（只管域名）复述 —— 单一真源 = 生产者，
# 见 `_producer_is_official()`。本模块的文档字符串第 2 条据此更正。

ROOT = Path(__file__).resolve().parents[1]

BASELINE_PATH = Path("ops/jiangsu/source-links.baseline.json")
SNAPSHOT_PATH = Path("ops/jiangsu/official-source-snapshot.json")
CATALOG_PATH = Path("sources/jiangsu/catalog/courses.json")

# `serialize_baseline()` 的产出形态：恰好三个顶层键。
TOP_KEYS = frozenset({"generated_at", "note", "urls"})
# 逐条 URL 记录恰好六个键（`serialize_baseline()` 的两条分支都写满这六个）。
ENTRY_KEYS = frozenset(
    {"status", "http_code", "authoritative", "content_hash", "course_codes", "sections"}
)
STATUS_VALUES = frozenset({"ok", "dead", "inconclusive"})

_GENERATED_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COURSE_CODE_RE = re.compile(r"\d{5}")


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline(root: Path = ROOT) -> dict:
    return _read_json(root / BASELINE_PATH)  # type: ignore[return-value]


def load_snapshot(root: Path = ROOT) -> dict:
    return _read_json(root / SNAPSHOT_PATH)  # type: ignore[return-value]


def _producer_is_official() -> Callable[[str, dict], bool]:
    """加载**生产者**的官方判据：`scripts/snapshot-official-sources.py:is_official()`。

    R7/W-5/F-QC3-6：该文件是连字符脚本，不是可 import 的模块，故按路径加载。加载失败即失败关闭 ——
    生产者被改名 / 挪走时必须报错，而不是悄悄退回本模块自己的复述（那正是「三处定义」的成因）。
    """
    script = ROOT / "scripts" / "snapshot-official-sources.py"
    if not script.is_file():
        raise AssertionError(f"producer predicate source missing: {script}")
    spec = importlib.util.spec_from_file_location("_snapshot_official_sources", script)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load producer predicate from {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predicate = getattr(module, "is_official", None)
    if not callable(predicate):
        raise AssertionError(f"{script} no longer exports is_official()")
    return predicate


PRODUCER_IS_OFFICIAL = _producer_is_official()


def official_urls(baseline: dict) -> set[str]:
    """baseline 里的官方 URL 集合，判据 = **生产者本人**（`is_official()`，R7 单一真源）。

    **I-1（T3 评审，2026-09-12）**：原实现只判 `is_official_url(url)`（域名为 `jseea.cn` 或其子域），
    而生产者要求 `item["authoritative"] and host.endswith("jseea.cn")`。二者不一致时，一条
    `authoritative=false` 的 jseea URL 会被本函数算作官方、却被生产者排除 →
    **合法刷新永远无法满足断言**（正是 B2-D4 要消除的形态）。

    **R7 / F-QC3-6（B2a QC wave 1）**：上一轮把合取式在**本模块内**复述了一遍，于是判定仍有**三处**
    独立定义（生产者 / `official_source.is_official_url()` / 本模块），而守护测试只测第三处、
    从不调用生产者 —— 分歧因此抓不到。现改为**直接委托生产者**：本模块不再自带任何判定逻辑，
    `test_official_set_predicate_matches_the_producer()` 另按合成输入逐例比对二者。
    """
    predicate = PRODUCER_IS_OFFICIAL
    items = baseline.get("urls") or {}
    return {
        url
        for url, item in items.items()
        if isinstance(item, dict) and predicate(url, item)
    }


def coherence_problems(root: Path = ROOT) -> list[str]:
    """baseline 是否能被 `serialize_baseline()` 重新产出（形态 + 取值域）。返回违规清单（空 = 合规）。"""
    path = root / BASELINE_PATH
    if not path.is_file():
        return [f"{BASELINE_PATH}: missing"]

    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{BASELINE_PATH}: not valid JSON: {exc}"]

    if not isinstance(doc, dict):
        return [f"{BASELINE_PATH}: top level must be an object"]

    if set(doc) != TOP_KEYS:
        problems.append(f"{BASELINE_PATH}: top-level keys {sorted(doc)} != {sorted(TOP_KEYS)}")
    if not isinstance(doc.get("generated_at"), str) or not _GENERATED_AT_RE.fullmatch(
        doc.get("generated_at") or ""
    ):
        problems.append(f"{BASELINE_PATH}: generated_at {doc.get('generated_at')!r} is not %Y-%m-%dT%H:%M:%SZ")
    if not isinstance(doc.get("note"), str) or not doc.get("note"):
        problems.append(f"{BASELINE_PATH}: note must be a non-empty string")

    entries = doc.get("urls")
    if not isinstance(entries, dict) or not entries:
        return problems + [f"{BASELINE_PATH}: urls must be a non-empty object"]

    catalog = {c["code"] for c in _read_json(root / CATALOG_PATH)["courses"]}  # type: ignore[index]

    for url, entry in entries.items():
        where = f"{BASELINE_PATH}: {url}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: entry must be an object")
            continue
        if set(entry) != ENTRY_KEYS:
            problems.append(f"{where}: entry keys {sorted(entry)} != {sorted(ENTRY_KEYS)}")
            continue

        status, http_code = entry["status"], entry["http_code"]
        authoritative, content_hash = entry["authoritative"], entry["content_hash"]
        course_codes, sections = entry["course_codes"], entry["sections"]

        if status not in STATUS_VALUES:
            problems.append(f"{where}: status {status!r} not in {sorted(STATUS_VALUES)}")
        # 三条 writer 可产出的状态 / 码位配对（`probe()` 的三条返回路径）。
        if status == "ok" and not (isinstance(http_code, int) and 200 <= http_code < 400):
            problems.append(f"{where}: status=ok requires a 2xx/3xx http_code, got {http_code!r}")
        if status == "dead" and not (isinstance(http_code, int) and 400 <= http_code < 600):
            problems.append(f"{where}: status=dead requires a 4xx/5xx http_code, got {http_code!r}")
        if status == "inconclusive" and http_code is not None:
            problems.append(f"{where}: status=inconclusive must not carry http_code, got {http_code!r}")

        if not isinstance(authoritative, bool):
            problems.append(f"{where}: authoritative must be a bool, got {authoritative!r}")
        elif not authoritative:
            # 非权威主机只探活（HEAD），writer 从不为其取内容指纹。
            if content_hash is not None:
                problems.append(f"{where}: non-authoritative entry must have content_hash null")
        elif status == "ok" and not (
            isinstance(content_hash, str) and _SHA256_RE.fullmatch(content_hash)
        ):
            # `probe()` 对 2xx 的权威主机必然读出正文并现算 sha256。
            problems.append(f"{where}: ok authoritative entry needs a sha256 content_hash, got {content_hash!r}")
        elif content_hash is not None and not (
            isinstance(content_hash, str) and _SHA256_RE.fullmatch(content_hash)
        ):
            problems.append(f"{where}: content_hash must be null or sha256 hex, got {content_hash!r}")

        if not isinstance(sections, list) or not sections or not all(
            isinstance(s, str) and s for s in sections
        ):
            problems.append(f"{where}: sections must be a non-empty list of non-empty strings")
        if not isinstance(course_codes, list) or not all(
            isinstance(c, str) and _COURSE_CODE_RE.fullmatch(c) for c in course_codes
        ):
            problems.append(f"{where}: course_codes must be a list of 5-digit codes")
        else:
            unknown = sorted(set(course_codes) - catalog)
            if unknown:
                problems.append(f"{where}: course_codes {unknown} are not in {CATALOG_PATH} (GC11)")

    # R8/W-6：这里的判据是「文本 == `json.dumps(..., indent=2)` 的重新序列化结果」。
    # 它抓得到**缩进 / 分隔符 / 尾随换行 / 转义风格**这类漂移，但**抓不到键序变化** ——
    # Python 的 `json.loads` 保留插入顺序，而重排后的 `doc` 重新 dump 会得到与重排文本相同的字节，
    # 于是 `text == canonical` 成立（QC3 已用键序变异探针实测 0 problems）。
    # 这是**有意的**：`serialize_baseline()` 按 `sorted(findings.items())` 落盘，键序本就是它产出的形态之一，
    # 断言「键序不得变」等于把 B2-D4 要拆掉的「任何 diff 即红」换个形式装回来。
    # 真正跨刷新稳定的是「哪些来源算官方」这一层集合身份（见 `official_set_problems`），不是字节布局。
    canonical = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if text != canonical:
        problems.append(f"{BASELINE_PATH}: not canonical serialize_baseline() output (byte-level drift)")

    return problems


def official_set_problems(root: Path = ROOT) -> list[str]:
    """官方 URL 集合必须与 `official-source-snapshot.json` 逐元素一致（plan Data contracts 6）。"""
    if not (root / SNAPSHOT_PATH).is_file():
        return [f"{SNAPSHOT_PATH}: missing (regenerate with scripts/snapshot-official-sources.py)"]
    if not (root / BASELINE_PATH).is_file():
        return [f"{BASELINE_PATH}: missing"]

    baseline = load_baseline(root)
    snapshot = load_snapshot(root)
    problems: list[str] = []

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("urls"), list):
        return [f"{SNAPSHOT_PATH}: missing or malformed (expected {{count, source, urls[]}})"]
    if snapshot.get("count") != len(snapshot["urls"]):
        problems.append(f"{SNAPSHOT_PATH}: count {snapshot.get('count')!r} != len(urls) {len(snapshot['urls'])}")
    if snapshot.get("source") != BASELINE_PATH.as_posix():
        problems.append(
            f"{SNAPSHOT_PATH}: source {snapshot.get('source')!r} != {BASELINE_PATH.as_posix()!r}"
        )

    recorded = {row.get("url") for row in snapshot["urls"] if isinstance(row, dict)}
    derived = official_urls(baseline)
    for url in sorted(derived - recorded):
        problems.append(f"{SNAPSHOT_PATH}: official URL {url} missing from snapshot")
    for url in sorted(recorded - derived):
        problems.append(f"{SNAPSHOT_PATH}: recorded URL {url} is not official in {BASELINE_PATH}")
    if problems:
        problems.append(f"{SNAPSHOT_PATH}: regenerate with scripts/snapshot-official-sources.py")
    return problems


def contract_problems(root: Path = ROOT) -> list[str]:
    """baseline 的全部实质契约（自洽 + 官方集合）。空 = 合规。"""
    return coherence_problems(root) + official_set_problems(root)


def assert_contract(root: Path = ROOT) -> None:
    """断言 baseline 满足实质契约；违规时把**全部**违规一次报出（便于定位）。"""
    problems = contract_problems(root)
    assert not problems, (
        f"{BASELINE_PATH} violates its semantic contract (B2-D4) — "
        f"{len(problems)} problem(s):\n  - " + "\n  - ".join(problems)
    )


@contextlib.contextmanager
def assert_unwritten(paths: "list[Path]") -> Iterator[None]:
    """块内代码**不得**改动 `paths` 的任何一个字节（写自由 / write-freedom）。

    **M-1（T3 评审，2026-09-12）**：原实现无 `try/finally` —— 块内抛异常时会跳过检查，
    「先写后抛」即可逃逸（评审已复现）。改为 `finally` 中比对：无论正常退出还是异常，
    写入都会被断言抓到。

    **R13 措辞更正**：`finally` 里 `raise` 会**替换**正在传播的异常，原异常只是作为
    `__context__` 挂在新异常上（Python 的隐式异常链），并**不是**「异常优先传播 / 不掩盖原始失败」。
    因此「先写后抛」时调用方看到的是 `AssertionError`，原始异常要靠 `__context__` 才能取回 ——
    这正是测试 `test_assert_unwritten_fails_on_write_then_raise` 锁定的行为。
    """
    before = {path: path.read_bytes() for path in paths}
    try:
        yield
    finally:
        for path, original in before.items():
            if path.read_bytes() != original:
                raise AssertionError(f"{path} was written by the code path under test")


def baseline_contract_work(reader: "Callable[[], object]", root: Path = ROOT) -> "Callable[[], object]":
    """把「只读页面」的 work 包成**真正触碰 baseline 路径区**的 work（R7/F-QC3-6 第二半）。

    `assert_page_work_keeps_baseline_intact` 的写自由半边断言「`work()` 不得写 baseline」。
    若 `work` 只是 `path.read_text()`，那半边是**空转**的：纯读函数本来就不可能写 baseline，
    断言虽然为真却证明不了任何事（QC3 指出 7 处调用点里有 2 处正是这个形态）。

    本包装让 `work()` 在读完页面之后再走一遍 **baseline 契约读取器**（`coherence_problems` +
    `official_set_problems`）—— 它们真的解析并读取 `source-links.baseline.json`、
    `official-source-snapshot.json` 与课程目录。于是「写自由」不再是对 no-op 断言：
    这条代码路径里的任何一次写入（含将来把读取器改写成读取即回写的回归）都会被 `assert_unwritten` 抓到。
    语义半边（`assert_contract`）仍由 `assert_page_work_keeps_baseline_intact` 在块后另行执行。
    """
    def _work() -> object:
        result = reader()
        problems = coherence_problems(root) + official_set_problems(root)
        assert not problems, f"baseline contract violated inside the code path under test: {problems}"
        return result

    return _work


def assert_page_work_keeps_baseline_intact(work: "Callable[[], object]", root: Path = ROOT) -> None:
    """站点共用的替代断言（plan Data contracts 6 / B2-D4）。

    原断言是「baseline 与 git 索引零差异」，它把**两件事**捆在一起：
    (a) 被测的页面工作**没有写** baseline（写自由）；(b) baseline 与**已提交**状态相同。
    B2-D4 只解禁 (b) —— baseline 可被 `--update-baseline` / `refresh-baseline` job 合法刷新。
    于是这里逐字保留 (a)：`work()` 执行前后 baseline 字节必须不变；再叠加语义契约
    （自洽 + 官方集合与快照一致），使「被写坏」与「内容不自洽」两种真实故障都仍然报错。

    `work` 传该站点自己的页面读取动作（读 `plan.md` / 章页等），签名保持每个站点一行调用。
    """
    with assert_unwritten([root / BASELINE_PATH]):
        work()
    assert_contract(root)


def assert_contract_can_fail(root: Path = ROOT, scratch: Path | None = None) -> None:
    """反向验证：契约断言**能失败**，即它不是一个恒真检查。

    在临时副本上做三件事（先立对照前提，再变异，最后还原）：

    1. 原样副本 → 契约必须**通过**（否则下面的「失败」证明不了什么）；
    2. 改副本里**一个官方 URL 的 1 个字节**（`jseea.cn` → `jseea.cm`）→ 契约必须**报错**
       （官方集合与快照不再逐元素相等）；
    3. 把该字节改回 → 契约必须**重新通过**。

    只动副本，不动仓内 baseline（GC14）。
    """
    baseline_src = root / BASELINE_PATH
    snapshot_src = root / SNAPSHOT_PATH
    catalog_src = root / CATALOG_PATH

    scratch = Path(scratch) if scratch is not None else Path(tempfile.mkdtemp(prefix="baseline-contract-"))
    probe_root = scratch / "root"
    for rel in (BASELINE_PATH, SNAPSHOT_PATH, CATALOG_PATH):
        (probe_root / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(baseline_src, probe_root / BASELINE_PATH)
    shutil.copyfile(snapshot_src, probe_root / SNAPSHOT_PATH)
    shutil.copyfile(catalog_src, probe_root / CATALOG_PATH)

    # 1) 对照前提：未变异的副本必须合规。
    assert contract_problems(probe_root) == [], (
        "control premise failed: an unmutated copy already violates the contract, "
        "so a mutation failure would prove nothing"
    )

    probe_path = probe_root / BASELINE_PATH
    original = probe_path.read_bytes()
    assert b"jseea.cn" in original, "no official host literal to mutate"
    mutated = original.replace(b"jseea.cn", b"jseea.cm", 1)
    assert mutated != original, "mutation must change exactly the host byte(s)"
    probe_path.write_bytes(mutated)

    # 2) 变异必须被**语义**判定抓到（不是靠字节规范化这种形式检查）。
    reasons = contract_problems(probe_root)
    assert reasons, "contract accepted a 1-byte mutation of an official URL: the check is tautological"
    assert any("official URL" in r or "not official" in r for r in reasons), (
        f"mutation was rejected, but not by the official-set check: {reasons}"
    )

    # 3) 还原后必须重新合规。
    probe_path.write_bytes(original)
    assert contract_problems(probe_root) == [], "restored copy must pass again"
