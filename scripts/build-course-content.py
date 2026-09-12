#!/usr/bin/env python3
"""课程内容流水线入口（kebab-case，对齐 `run-gates.py`）。

子命令：
  build <query>     依次跑 resolve -> acquire -> evidence -> model -> generate -> render -> gate 七阶段
  resolve <query>   只跑目录解析，打印 status / code / name / matched_by
  evidence <code>   写 `sources/jiangsu/courses/<code>/evidence.json` 并打印放行等级
  evidence --all    现有 18 门课程页课码各写一份（spec AC4）
  model <code>      写 `sources/jiangsu/courses/<code>/knowledge-model.json` 并打印章数与覆盖率
  generate <code>   写 `sources/jiangsu/courses/<code>/content.json`（AI 备考层，三后端可选）
  render <code>     只渲染，产出 content/jiangsu/courses/<code>/ 六页 + 18 章页
  fetch-source <url> 抓官方来源快照（B1 提示属 B2 并 exit 2）

阶段开关：--stages resolve,acquire,evidence,model,generate,render,gate（默认全部，按序执行）
运行模式：--backend cli|agent|replay（默认 cli）| --offline | --dry-run | --force | --record-fixtures
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import course_pages_contract  # noqa: E402
from lib.course_pipeline import course_catalog as catalog_mod  # noqa: E402
from lib.course_pipeline import evidence as evidence_mod  # noqa: E402
from lib.course_pipeline import generate_content as generate_content_mod  # noqa: E402
from lib.course_pipeline import knowledge_model as knowledge_model_mod  # noqa: E402
from lib.course_pipeline import llm_client  # noqa: E402
from lib.course_pipeline import render_pages as render_pages_mod  # noqa: E402

CODE_RE = re.compile(r"\d{5}")
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


def run_render(code: str, *, target_dir: Path | None = None) -> int:
    try:
        written = render_pages_mod.render_course_pages(ROOT, code, target_dir=target_dir)
        print(f"render ok: {code} wrote {len(written)} pages")
        return 0
    except Exception as exc:
        print(f"stage=render failed: {exc}", file=sys.stderr)
        return 1


def _validate_staging_gates(root: Path, stage_dir: Path, code: str) -> list[str]:
    errors: list[str] = []
    schema = course_pages_contract.load_schema(root)
    # Check course contract
    contract_errors = course_pages_contract.check_course_dir(stage_dir.parent, stage_dir, schema)
    errors.extend(contract_errors)

    # Check generated page markers
    gen_markers = schema.get("generated_page_markers", {})
    any_marker = gen_markers.get("any")
    ai_banner = gen_markers.get("ai_banner", "本页由 AI 辅助生成")
    ai_pages = set(gen_markers.get("ai_pages", ["plan.md", "practice.md", "review.md", "knowledge/*.md"]))
    official_only = set(gen_markers.get("official_only", ["index.md", "syllabus.md", "sources.md"]))

    for md_path in stage_dir.rglob("*.md"):
        rel = md_path.relative_to(stage_dir).as_posix()
        text = md_path.read_text(encoding="utf-8")
        if any_marker and any_marker not in text:
            errors.append(f"{rel}: missing generated comment marker")

        is_ai_page = rel in ai_pages or rel.startswith("knowledge/")
        is_official = rel in official_only

        if is_ai_page and ai_banner not in text:
            errors.append(f"{rel}: missing AI statement banner")
        if is_official and ai_banner in text:
            errors.append(f"{rel}: leaked AI banner into official page")

        # Check blockquote length
        for line in text.splitlines():
            s = line.lstrip()
            if s.startswith(">"):
                quote = s.lstrip(">").strip()
                if len(quote) > 80:
                    errors.append(f"{rel}: blockquote exceeds 80 chars ({len(quote)}): {quote[:40]}...")
                if re.search(r"(选择题|填空题|简答题|材料题|下列.*正确)", quote):
                    errors.append(f"{rel}: leaked question text into quote: {quote[:40]}...")

    # Check practice.md canonical H1
    practice_md = stage_dir / "practice.md"
    if practice_md.is_file():
        lines = practice_md.read_text(encoding="utf-8").splitlines()
        if not lines or not re.match(r"^# .+（\d{5}）：练习与真题\s*$", lines[0]):
            errors.append("practice.md: first line is not canonical H1")

    return errors


def run_build(
    query: str,
    *,
    backend: str,
    stages: list[str],
    offline: bool,
    dry_run: bool,
    force: bool,
    record_fixtures: bool,
) -> int:
    # 1. stage=resolve
    code = query
    if "resolve" in stages:
        catalog = catalog_mod.build_catalog(ROOT)
        result = catalog_mod.resolve_course(catalog, query)
        if result.get("status") != "resolved":
            print(f"stage=resolve missing: query={query!r} status={result.get('status')}", file=sys.stderr)
            return 2
        code = result["code"]
        print(f"[resolve] ok: {code} ({result.get('name')})")

    # 2. stage=acquire
    if "acquire" in stages:
        # Check offline baseline/sources
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

    # 6. stage=render & 7. stage=gate (with atomic staging)
    needs_render = "render" in stages
    needs_gate = "gate" in stages

    if needs_render or needs_gate:
        stage_dir = Path(tempfile.mkdtemp(prefix=f"build_{code}_"))
        try:
            # Render into staging area
            written = render_pages_mod.render_course_pages(ROOT, code, target_dir=stage_dir)
            if "render" in stages:
                print(f"[render] ok: {code} staged {len(written)} pages")

            # Validate staging area
            if "gate" in stages:
                errors = _validate_staging_gates(ROOT, stage_dir, code)
                if errors:
                    for err in errors:
                        print(f"stage=gate failed: {err}", file=sys.stderr)
                    return 1
                print(f"[gate] ok: {code}")

            # If not dry-run, atomic promote from staging to content/jiangsu/courses/<code>
            if not dry_run:
                dest_dir = ROOT / "content" / "jiangsu" / "courses" / code
                dest_dir.mkdir(parents=True, exist_ok=True)
                for src_path in stage_dir.rglob("*"):
                    if src_path.is_file():
                        rel = src_path.relative_to(stage_dir)
                        target_file = dest_dir / rel
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_path, target_file)
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jiangsu self-study course content pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    build_p = subparsers.add_parser("build", help="端到端流水线")
    build_p.add_argument("query", help="课码或课名")
    build_p.add_argument("--backend", choices=llm_client.BACKENDS, default="cli", help="生成执行体（默认 cli）")
    build_p.add_argument("--stages", default=",".join(ALL_STAGES), help="执行阶段列表")
    build_p.add_argument("--offline", action="store_true", default=True, help="离线模式")
    build_p.add_argument("--dry-run", action="store_true", help="只演练不落盘")
    build_p.add_argument("--force", action="store_true", help="强制覆盖")
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
            offline=args.offline,
            dry_run=args.dry_run,
            force=args.force,
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
