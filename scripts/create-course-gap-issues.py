from __future__ import annotations
from pathlib import Path
import argparse, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ops/jiangsu/issues/course-gap-issues.json"


def issue_body(item: dict) -> str:
    gaps = "、".join(item["gaps"])
    return f"""课程：`{item['code']}` {item['title']}

缺口：{gaps}
优先级：{item['priority']}
materials线索：{item['materials_hint']}

核验路径：
- `content/jiangsu/courses/{item['code']}/sources.md`
- `content/jiangsu/courses/{item['code']}/plan.md`
- `materials://` 私仓按课程代码检索
- `ops/jiangsu/source-links.baseline.json` 官方来源

验收：
- 教材状态明确为 `verified` / `missing-source` / `needs-review`
- 学习计划不再是弱占位；至少给出阶段目标与复习节奏
- 公开仓不出现私仓原件或下载链接
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Create course gap issues from dry-run manifest.")
    ap.add_argument("--apply", action="store_true", help="actually call gh issue create")
    ap.add_argument("--limit", type=int, default=0, help="max issues; 0 means all")
    args = ap.parse_args()
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.limit:
        items = items[: args.limit]
    for item in items:
        title = f"[course-gap] {item['code']} {item['title']}：{'、'.join(item['gaps'])}"
        labels = ["course-gap", item["priority"].lower(), "materials-needed"]
        if not args.apply:
            print(f"DRY-RUN: {title} [{', '.join(labels)}]")
            continue
        cmd = ["gh", "issue", "create", "--title", title, "--body", issue_body(item)]
        for label in labels:
            cmd += ["--label", label]
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
