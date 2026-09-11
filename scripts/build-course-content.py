#!/usr/bin/env python3
"""课程内容流水线入口（kebab-case，对齐 `run-gates.py`）。

当前子命令：

  evidence <code>   写 `sources/jiangsu/courses/<code>/evidence.json` 并打印放行等级
  evidence --all    现有 18 门课程页课码各写一份（spec AC4）
  model <code>      写 `sources/jiangsu/courses/<code>/knowledge-model.json` 并打印章数与覆盖率
  generate <code>   写 `sources/jiangsu/courses/<code>/content.json`（AI 备考层，三后端可选）

放行等级非 `L1` 的课程在 `model` / `generate` 阶段**跳过且不视为失败**（exit 0、零 AI 产物，plan § 阶段语义）；
`generate` 的 `--backend` 三值见 GC8：`cli`（OpenAI 兼容 API）/ `agent`（无 key 环境，harness agent 回填
`.agent-task/*.result.json`）/ `replay`（CI 离线读录制 fixture，缺一条即报错、不套模板）；
`--record-fixtures` 把本次响应落到 `tests/fixtures/course_pipeline/llm/`；`--chapters` 限定章范围（分批生成，
取值见 `generate_content.select_chapters()`：章 `slug` / 章序标签 / `ordinal`）；`resolve` / `render` 等后续阶段
随各自 task 接入（plan § Target-state module map）；本入口不做占位子命令。
默认离线：只读仓内抽取件与只读基线（GC8 / GC14 / GC15）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.course_pipeline import evidence as evidence_mod  # noqa: E402
from lib.course_pipeline import generate_content as generate_content_mod  # noqa: E402
from lib.course_pipeline import knowledge_model as knowledge_model_mod  # noqa: E402
from lib.course_pipeline import llm_client  # noqa: E402

CODE_RE = re.compile(r"\d{5}")
CHAPTER_SPLIT_RE = re.compile(r"[,，]")


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


def run_generate(code: str, *, backend: str, chapters: list[str], record_fixtures: bool) -> int:
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
    model_file = knowledge_model_mod.knowledge_model_path(ROOT, code)
    if not model_file.is_file():
        print(
            f"stage=generate missing: {model_file.relative_to(ROOT).as_posix()}（先跑 model 阶段）",
            file=sys.stderr,
        )
        return 2
    model = json.loads(model_file.read_text(encoding="utf-8"))
    if chapters:
        model = generate_content_mod.select_chapters(model, chapters)
    llm_client.RECORD_FIXTURES = record_fixtures
    try:
        doc = generate_content_mod.generate_course_content(ROOT, model, backend=backend)
    except llm_client.AgentTasksPendingError as exc:
        print(f"stage=generate missing: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        # 失败关闭：缺 fixture / schema 连失 / 自检不过一律不写盘（plan § 失败与「无半成品」约定）。
        print(f"stage=generate failed: {exc}", file=sys.stderr)
        return 1
    path = generate_content_mod.content_path(ROOT, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_content_mod.serialize(doc), encoding="utf-8")
    counts = Counter(block["kind"] for block in doc["blocks"])
    breakdown = " ".join(f"{kind}={counts[kind]}" for kind in sorted(counts))
    print(
        f"{code}: backend={backend} blocks={len(doc['blocks'])} {breakdown} "
        f"schedule={doc['review_schedule']['status']} -> {path.relative_to(ROOT).as_posix()}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jiangsu self-study course content pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evidence = subparsers.add_parser("evidence", help="写 sources/jiangsu/courses/<code>/evidence.json")
    evidence.add_argument("code", nargs="?", help="5 位课码")
    evidence.add_argument("--all", action="store_true", help="现有 18 门课程页课码")

    model = subparsers.add_parser("model", help="写 sources/jiangsu/courses/<code>/knowledge-model.json")
    model.add_argument("code", help="5 位课码")

    generate = subparsers.add_parser("generate", help="写 sources/jiangsu/courses/<code>/content.json")
    generate.add_argument("code", help="5 位课码")
    generate.add_argument("--backend", choices=llm_client.BACKENDS, default="cli", help="生成执行体（默认 cli）")
    generate.add_argument("--chapters", help="只生成这些章（逗号分隔的 slug / 章序标签 / ordinal）")
    generate.add_argument("--record-fixtures", action="store_true", help="把本次响应录到 tests/fixtures/course_pipeline/llm/")

    args = parser.parse_args(argv)

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
        args.code, backend=args.backend, chapters=chapters, record_fixtures=args.record_fixtures
    )


if __name__ == "__main__":
    raise SystemExit(main())
