#!/usr/bin/env python3
"""课程目录入口：写 / 校验 `sources/jiangsu/catalog/{courses,majors}.json`。

Usage:
  python scripts/build-course-catalog.py           # 写目录产物并打印唯一课码数 / 专业数 / 冲突数
  python scripts/build-course-catalog.py --check   # 重新生成并与磁盘逐字节比对（有差异 → exit 1）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.course_pipeline.course_catalog import check_catalog, write_catalog  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify the course catalog")
    parser.add_argument("--check", action="store_true", help="verify the on-disk catalog against a fresh build")
    args = parser.parse_args(argv)

    if args.check:
        problems = check_catalog(ROOT)
        for problem in problems:
            print(problem)
        if problems:
            print(f"catalog check failed: {len(problems)} file(s) differ")
            return 1
        print("catalog check ok")
        return 0

    paths, (catalog, majors) = write_catalog(ROOT)
    conflicts = sum(1 for course in catalog["courses"] if course["conflicts"])
    print(f"courses: {len(catalog['courses'])} unique codes, {conflicts} with conflicts")
    print(f"majors: {len(majors['majors'])}")
    for path in paths:
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
