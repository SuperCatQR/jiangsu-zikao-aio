#!/usr/bin/env python3
"""课程内容流水线入口（kebab-case，对齐 `run-gates.py`）。

当前子命令：

  evidence <code>   写 `sources/jiangsu/courses/<code>/evidence.json` 并打印放行等级
  evidence --all    现有 18 门课程页课码各写一份（spec AC4）

`resolve` / `model` / `generate` / `render` 等后续阶段随各自 task 接入（plan § Target-state module map）；
本入口不做占位子命令。默认离线：只读仓内抽取件与只读基线（GC8 / GC14 / GC15）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.course_pipeline import evidence as evidence_mod  # noqa: E402

CODE_RE = re.compile(r"\d{5}")


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jiangsu self-study course content pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evidence = subparsers.add_parser("evidence", help="写 sources/jiangsu/courses/<code>/evidence.json")
    evidence.add_argument("code", nargs="?", help="5 位课码")
    evidence.add_argument("--all", action="store_true", help="现有 18 门课程页课码")

    args = parser.parse_args(argv)

    if args.all:
        codes = evidence_mod.course_codes(ROOT)
    elif args.code:
        if not CODE_RE.fullmatch(args.code):
            parser.error(f"课码必须是 5 位数字：{args.code!r}")
        codes = [args.code]
    else:
        parser.error("evidence 需要 <code> 或 --all")
    return run_evidence(codes)


if __name__ == "__main__":
    raise SystemExit(main())
