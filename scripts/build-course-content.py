#!/usr/bin/env python3
"""课程内容流水线入口（kebab-case，对齐 `run-gates.py`）。

子命令：
  build <query>     依次跑 resolve -> acquire -> evidence -> model -> generate -> render -> gate 七阶段
  resolve <query>   只跑目录解析，打印 status / code / name / matched_by
  evidence <code>   写 `sources/jiangsu/courses/<code>/evidence.json` 并打印放行等级
  evidence --all    现有 18 门课程页课码各写一份（spec AC4）
  model <code>      写 `sources/jiangsu/courses/<code>/knowledge-model.json` 并打印章数与覆盖率
  generate <code>   写 `sources/jiangsu/courses/<code>/content.json`（AI 备考层，三后端可选）
  render <code>     渲染并落盘 `content/jiangsu/courses/<code>/`（内部走 render → gate → 原子提升）
  fetch-source <url> 抓官方来源快照（B1 提示属 B2 并 exit 2）

阶段开关：--stages resolve,acquire,evidence,model,generate,render,gate（默认全部，按序执行）
运行模式：--backend cli|agent|replay（默认 cli）| --dry-run | --record-fixtures
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import course_pages_contract  # noqa: E402
from lib.ai_content_gate import run_ai_content_gate  # noqa: E402
from lib.course_pipeline import course_catalog as catalog_mod  # noqa: E402
from lib.course_pipeline import evidence as evidence_mod  # noqa: E402
from lib.course_pipeline import generate_content as generate_content_mod  # noqa: E402
from lib.course_pipeline import knowledge_model as knowledge_model_mod  # noqa: E402
from lib.course_pipeline import llm_client  # noqa: E402
from lib.course_pipeline import render_pages as render_pages_mod  # noqa: E402
from lib.evidence_gate import run_evidence_gate  # noqa: E402

CODE_RE = re.compile(r"\d{5}")


def _sync_roots() -> None:
    """把 `llm_client` 的三个根重新对齐到当前 `ROOT`（QC3-007 / C2-010）。

    `llm_client` 默认按 `__file__` 推导 fixture / 提示词 / `.agent-task` 根。入口脚本从**副本仓**
    运行时（失败关闭测试的装置），若不同步就会去读真实仓的 fixture —— 于是「缺前置 → 退出非 0」
    可能因为真实仓恰好可用而误绿，与被测那棵树的状态无关。每次进入阶段前同步，测试改 `ROOT` 后也生效。
    """
    llm_client.set_repo_root(ROOT)


CHAPTER_SPLIT_RE = re.compile(r"[,，]")
ALL_STAGES = ("resolve", "acquire", "evidence", "model", "generate", "render", "gate")


def run_resolve(query: str) -> int:
    catalog = catalog_mod.build_catalog(ROOT)
    result = catalog_mod.resolve_course(catalog, query)
    status = result.get("status")
    if status == "resolved":
        print(f"status=resolved code={result['code']} name={result['name']} matched_by={result.get('matched_by', 'exact')}")
    elif status == "ambiguous":
        candidates = result.get("candidates", [])
        c_str = ", ".join(f"{c.get('code')}:{c.get('name')}" for c in candidates)
        print(f"status=ambiguous query={query} candidates=[{c_str}]")
    else:
        print(f"status=not_found query={query}")
    return 0


def run_evidence(codes: list[str]) -> int:
    _sync_roots()
    if not codes:
        print("evidence: 没有可处理的课码（--all 需要 content/jiangsu/courses/<课码>/ 目录）", file=sys.stderr)
        return 2
    paths, documents = evidence_mod.write_evidence(ROOT, codes)
    for path, doc in zip(paths, documents):
        eligibility = doc["eligibility"]
        reasons = " ".join(eligibility["reasons"])
        print(f"{doc['course_code']}: {eligibility['level']} {reasons} -> {path.relative_to(ROOT).as_posix()}")
    return 0


def run_model(code: str) -> int:
    _sync_roots()
    evidence_file = evidence_mod.evidence_path(ROOT, code)
    if not evidence_file.is_file():
        print(
            f"stage=model missing: {evidence_file.relative_to(ROOT).as_posix()}（先跑 evidence 阶段）",
            file=sys.stderr,
        )
        return 2
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    eligibility = evidence.get("eligibility") or {}
    if eligibility.get("level") != "L1":
        reasons = " ".join(eligibility.get("reasons") or [])
        print(f"{code}: {eligibility.get('level', 'unknown')} {reasons} -> model 阶段跳过（非 L1，零 AI 产物）")
        return 0
    path, doc = knowledge_model_mod.write_knowledge_model(ROOT, code)
    coverage = doc["coverage"]
    print(f"{code}: chapters={len(doc['chapters'])} ratio={coverage['ratio']} -> {path.relative_to(ROOT).as_posix()}")
    return 0


def run_generate(code: str, *, backend: str, chapters: list[str], record_fixtures: bool, merge: bool) -> int:
    _sync_roots()
    evidence_file = evidence_mod.evidence_path(ROOT, code)
    if not evidence_file.is_file():
        print(
            f"stage=generate missing: {evidence_file.relative_to(ROOT).as_posix()}（先跑 evidence 阶段）",
            file=sys.stderr,
        )
        return 2
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    eligibility = evidence.get("eligibility") or {}
    if eligibility.get("level") != "L1":
        reasons = " ".join(eligibility.get("reasons") or [])
        print(f"{code}: {eligibility.get('level', 'unknown')} {reasons} -> generate 阶段跳过（非 L1，零 AI 产物）")
        return 0
    out_of_scope = generate_content_mod.out_of_scope_prompts(code)
    if out_of_scope:
        print(
            f"stage=generate missing: {code} 无提示词包（course_scope 不含该课码）: "
            f"{'、'.join(out_of_scope)}（不得用其它课程的模板生成内容）",
            file=sys.stderr,
        )
        return 2
    model_file = knowledge_model_mod.knowledge_model_path(ROOT, code)
    if not model_file.is_file():
        print(
            f"stage=generate missing: {model_file.relative_to(ROOT).as_posix()}（先跑 model 阶段）",
            file=sys.stderr,
        )
        return 2
    model = json.loads(model_file.read_text(encoding="utf-8"))
    scoped_model = generate_content_mod.select_chapters(model, chapters) if chapters else model
    llm_client.RECORD_FIXTURES = record_fixtures
    path = generate_content_mod.content_path(ROOT, code)
    try:
        doc = generate_content_mod.generate_course_content(ROOT, scoped_model, backend=backend)
        if merge:
            doc = generate_content_mod.merge_content_file(path, doc, model)
    except llm_client.AgentTasksPendingError as exc:
        print(f"stage=generate missing: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"stage=generate failed: {exc}", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_content_mod.serialize(doc), encoding="utf-8")
    counts = Counter(block["kind"] for block in doc["blocks"])
    breakdown = " ".join(f"{kind}={counts[kind]}" for kind in sorted(counts))
    merged_note = " merge=1" if merge else ""
    print(
        f"{code}: backend={backend}{merged_note} blocks={len(doc['blocks'])} {breakdown} "
        f"schedule={doc['review_schedule']['status']} -> {path.relative_to(ROOT).as_posix()}"
    )
    return 0


def run_render(code: str) -> int:
    """`render` 子命令 = `build` 的 render+gate+promote 三段（QC3-012）。

    旧实现直接写 `content/jiangsu/courses/<code>/`，是本流水线**唯一**能留下半套页面的路径
    （24 个文件逐个覆盖、无任何校验）。渲染入口不允许绕过暂存与闸门，因此这里只做 `build` 的阶段转发。
    """
    return run_build(code, backend="replay", stages=["resolve", "render", "gate"], dry_run=False, record_fixtures=False)


def _validate_staging_gates(root: Path, stage_dir: Path, code: str) -> list[str]:
    """`gate` 阶段对**暂存区**的校验（页面契约 + 暂存区自身的生成标记）。

    `stage_dir` 必须是**课码命名目录**（`<mkdtemp>/<code>/`），否则
    `course_pages_contract.check_course_dir()` 会在 `CODE.fullmatch(d.name)` 处静默早返回 `[]`，
    整页契约检查形同虚设（QC1 F-1 / QC2 C2-001 / QC3-003）。
    """
    errors: list[str] = []
    schema = course_pages_contract.load_schema(root)
    # 页面契约（必备文件 + page_markers + frontmatter）：以课码命名目录为根，契约检查才真正执行
    contract_errors = course_pages_contract.check_course_dir(stage_dir.parent, stage_dir, schema)
    errors.extend(contract_errors)

    # 生成标记：页面分类与标记字符串一律取自 schema 的 `generated_page_markers`（QC1 F-4 / QC3-003）
    markers = course_pages_contract.generated_page_markers(schema)
    ai_pages = set(markers["ai_pages"])
    official_only = set(markers["official_only"])

    for md_path in stage_dir.rglob("*.md"):
        rel = md_path.relative_to(stage_dir).as_posix()
        text = md_path.read_text(encoding="utf-8")
        if markers["any"] not in text:
            errors.append(f"{rel}: missing generated comment marker")

        is_ai_page = course_pages_contract.matches_page(rel, ai_pages)
        is_official = course_pages_contract.matches_page(rel, official_only)

        if is_ai_page and markers["ai_banner"] not in text:
            errors.append(f"{rel}: missing AI statement banner")
        if is_official and markers["ai_banner"] in text:
            errors.append(f"{rel}: leaked AI banner into official page")

    # Check practice.md canonical H1
    practice_md = stage_dir / "practice.md"
    if practice_md.is_file():
        lines = practice_md.read_text(encoding="utf-8").splitlines()
        if not lines or not re.match(r"^# .+（\d{5}）：练习与真题\s*$", lines[0]):
            errors.append("practice.md: first line is not canonical H1")

    return errors


def _promote_staging(stage_dir: Path, dest_dir: Path) -> list[str]:
    """暂存区 → 产物目录的**目录级替换**：拷贝到同盘兄弟暂存目录后 `os.replace`，并清除陈旧文件。

    逐文件 `copy2` 既不原子（中途失败留下半套页面），也不清陈旧文件（改 slug 后孤儿
    `knowledge/<NN>-<slug>.md` 会一直留在站点里）。`os.replace` 在同一文件系统上是原子操作，
    因此失败路径下产物目录零改动（spec AC1 第 3 句 / QC1 F-6 / QC3-003）。
    """
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest_dir.name}.promote.", dir=dest_dir.parent))
    try:
        shutil.copytree(stage_dir, staging, dirs_exist_ok=True)
        if dest_dir.exists():
            stale = Path(tempfile.mkdtemp(prefix=f".{dest_dir.name}.stale.", dir=dest_dir.parent))
            os.replace(dest_dir, stale)
            shutil.rmtree(stale, ignore_errors=True)
        os.replace(staging, dest_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return []


def run_build(
    query: str,
    *,
    backend: str,
    stages: list[str],
    dry_run: bool,
    record_fixtures: bool,
) -> int:
    _sync_roots()
    # 1. stage=resolve
    #
    # 课码在**任何**路径拼接之前就校验（C2-006）：`--stages evidence` 会跳过 `resolve`，
    # 旧实现于是把 `query` 原样当课码用，`evidence_path()` 的 `root / COURSES_DIR / code / …`
    # 可被 `../../..` 逃出仓根并写盘（实测 exit 0）。课码形态是 CLI 契约，不因阶段开关而放宽。
    code = query
    if "resolve" in stages:
        catalog = catalog_mod.build_catalog(ROOT)
        result = catalog_mod.resolve_course(catalog, query)
        if result.get("status") != "resolved":
            print(f"stage=resolve missing: query={query!r} status={result.get('status')}", file=sys.stderr)
            return 2
        code = result["code"]
        print(f"[resolve] ok: {code} ({result.get('name')})")
    if not CODE_RE.fullmatch(code):
        print(f"stage=resolve missing: 课码必须是 5 位数字：{code!r}", file=sys.stderr)
        return 2

    # 2. stage=acquire
    if "acquire" in stages:
        # 离线取证的输入基线；`acquire` 不做联网抓取（B1 不落盘官方快照，GC15）
        baseline = ROOT / "ops" / "jiangsu" / "source-links.baseline.json"
        if not baseline.is_file():
            print(f"stage=acquire missing: baseline file {baseline.as_posix()}", file=sys.stderr)
            return 2
        print(f"[acquire] ok: {code}")

    # 3. stage=evidence
    if "evidence" in stages:
        rc = run_evidence([code])
        if rc != 0:
            print(f"stage=evidence failed: exit code {rc}", file=sys.stderr)
            return rc
        print(f"[evidence] ok: {code}")

    # Check eligibility for downstream AI stages
    evidence_file = evidence_mod.evidence_path(ROOT, code)
    if not evidence_file.is_file():
        print(f"stage=evidence missing: {evidence_file.relative_to(ROOT).as_posix()}", file=sys.stderr)
        return 2
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    eligibility = evidence.get("eligibility") or {}
    level = eligibility.get("level")
    if level != "L1":
        print(f"{code}: level={level} -> skip model/generate/render (not L1, zero AI artifacts)")
        return 0

    # 4. stage=model
    if "model" in stages:
        rc = run_model(code)
        if rc != 0:
            print(f"stage=model failed: exit code {rc}", file=sys.stderr)
            return rc
        print(f"[model] ok: {code}")

    # 5. stage=generate
    if "generate" in stages:
        rc = run_generate(code, backend=backend, chapters=[], record_fixtures=record_fixtures, merge=False)
        if rc != 0:
            return rc
        print(f"[generate] ok: {code}")

    # 6. stage=render & 7. stage=gate（暂存 → 校验 → 目录级原子提升）
    needs_render = "render" in stages
    needs_gate = "gate" in stages

    if needs_render or needs_gate:
        # 暂存根 = mkdtemp()，其中**课码命名子目录**才是渲染目标：`check_course_dir` 依赖
        # 目录名匹配 `^[0-9]{5}$`，暂存目录名一旦不是课码，整页契约检查会静默早返回 `[]`。
        stage_root = Path(tempfile.mkdtemp(prefix=f"build_{code}_"))
        stage_dir = stage_root / code
        stage_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Render into staging area
            written = render_pages_mod.render_course_pages(ROOT, code, target_dir=stage_dir)
            if not written:
                print(f"stage=render failed: {code} 未产出任何页面", file=sys.stderr)
                return 1
            if "render" in stages:
                print(f"[render] ok: {code} staged {len(written)} pages")

            # Validate staging area
            if needs_gate:
                errors = _validate_staging_gates(ROOT, stage_dir, code)
                # 两个新层对**暂存区**的等价校验：evidence 层校 JSON 产物，
                # ai-content 层校本课程暂存页（含「每个 AI 块都落到页面」的失败关闭检查）
                errors.extend(run_evidence_gate(ROOT))
                errors.extend(run_ai_content_gate(ROOT, rendered_course_dir=stage_dir, course_code=code))
                if errors:
                    for err in errors:
                        print(f"stage=gate failed: {err}", file=sys.stderr)
                    return 1
                print(f"[gate] ok: {code}")

            # If not dry-run, promote staging to content/jiangsu/courses/<code>
            if not dry_run:
                dest_dir = ROOT / "content" / "jiangsu" / "courses" / code
                _promote_staging(stage_dir, dest_dir)
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jiangsu self-study course content pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    build_p = subparsers.add_parser("build", help="端到端流水线")
    build_p.add_argument("query", help="课码或课名")
    build_p.add_argument("--backend", choices=llm_client.BACKENDS, default="cli", help="生成执行体（默认 cli）")
    build_p.add_argument("--stages", default=",".join(ALL_STAGES), help="执行阶段列表")
    # R55：`--dry-run` 的唯一作用点是 `:340` 的提升守卫，`evidence` / `generate` 阶段无条件执行
    # 并写 `sources/jiangsu/courses/<code>/` 下的产物。旧文案「只演练不落盘」与实现不符
    # （会误导验收者以为演练不动工作区，实际留下 modified files）。
    build_p.add_argument(
        "--dry-run",
        action="store_true",
        help="不把渲染结果提升到 content/jiangsu/courses/<code>；"
        "evidence/generate 阶段仍会写 sources/jiangsu/courses/<code>/ 下的产物并重戳 generated_at",
    )
    build_p.add_argument("--record-fixtures", action="store_true", help="录制 fixture")

    # resolve
    resolve_p = subparsers.add_parser("resolve", help="目录课码解析")
    resolve_p.add_argument("query", help="课码或课名")

    # evidence
    evidence = subparsers.add_parser("evidence", help="写 sources/jiangsu/courses/<code>/evidence.json")
    evidence.add_argument("code", nargs="?", help="5 位课码")
    evidence.add_argument("--all", action="store_true", help="现有 18 门课程页课码")

    # model
    model = subparsers.add_parser("model", help="写 sources/jiangsu/courses/<code>/knowledge-model.json")
    model.add_argument("code", help="5 位课码")

    # generate
    generate = subparsers.add_parser("generate", help="写 sources/jiangsu/courses/<code>/content.json")
    generate.add_argument("code", help="5 位课码")
    generate.add_argument("--backend", choices=llm_client.BACKENDS, default="cli", help="生成执行体（默认 cli）")
    generate.add_argument("--chapters", help="只生成这些章（逗号分隔的 slug / 章序标签 / ordinal）")
    generate.add_argument("--merge", action="store_true", help="把本次结果合并进已有 content.json（逐批生成）")
    generate.add_argument("--record-fixtures", action="store_true", help="把本次响应录到 tests/fixtures/course_pipeline/llm/")

    # render
    render_p = subparsers.add_parser("render", help="渲染课程页面与知识章节")
    render_p.add_argument("code", help="5 位课码")

    # fetch-source
    fetch_p = subparsers.add_parser("fetch-source", help="抓取官方来源（B2 能力）")
    fetch_p.add_argument("url", help="官方来源 URL")

    args = parser.parse_args(argv)

    if args.command == "fetch-source":
        print("stage=fetch-source: capability belongs to B2 (spec D7 / Roadmap B2)", file=sys.stderr)
        return 2

    if args.command == "resolve":
        return run_resolve(args.query)

    if args.command == "render":
        if not CODE_RE.fullmatch(args.code):
            parser.error(f"课码必须是 5 位数字：{args.code!r}")
        return run_render(args.code)

    if args.command == "build":
        stages = [s.strip() for s in args.stages.split(",") if s.strip()]
        return run_build(
            args.query,
            backend=args.backend,
            stages=stages,
            dry_run=args.dry_run,
            record_fixtures=args.record_fixtures,
        )

    if args.command == "evidence":
        if args.all:
            codes = evidence_mod.course_codes(ROOT)
        elif args.code:
            if not CODE_RE.fullmatch(args.code):
                parser.error(f"课码必须是 5 位数字：{args.code!r}")
            codes = [args.code]
        else:
            parser.error("evidence 需要 <code> 或 --all")
        return run_evidence(codes)

    if args.command == "model":
        if not CODE_RE.fullmatch(args.code):
            parser.error(f"课码必须是 5 位数字：{args.code!r}")
        return run_model(args.code)

    if not CODE_RE.fullmatch(args.code):
        parser.error(f"课码必须是 5 位数字：{args.code!r}")
    chapters = [item for item in CHAPTER_SPLIT_RE.split(args.chapters or "") if item.strip()]
    return run_generate(
        args.code,
        backend=args.backend,
        chapters=chapters,
        record_fixtures=args.record_fixtures,
        merge=args.merge,
    )


if __name__ == "__main__":
    raise SystemExit(main())
