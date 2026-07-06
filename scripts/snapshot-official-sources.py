#!/usr/bin/env python3
"""Snapshot authoritative Jiangsu official source URLs from source-link baseline."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "ops" / "jiangsu" / "source-links.baseline.json"
OUT_JSON = ROOT / "ops" / "jiangsu" / "official-source-snapshot.json"
OUT_MD = ROOT / "ops" / "jiangsu" / "official-source-snapshot.md"


def is_official(url: str, item: dict) -> bool:
    host = urlparse(url).hostname or ""
    return bool(item.get("authoritative")) and host.endswith("jseea.cn")


def main() -> int:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    rows = []
    for url, item in sorted(data.get("urls", {}).items()):
        if not is_official(url, item):
            continue
        rows.append({
            "url": url,
            "status": item.get("status"),
            "http_code": item.get("http_code"),
            "content_hash": item.get("content_hash"),
            "course_codes": item.get("course_codes", []),
            "sections": item.get("sections", []),
        })
    OUT_JSON.write_text(json.dumps({"source": str(BASELINE.relative_to(ROOT)), "count": len(rows), "urls": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 官方来源快照", "", f"来源：`{BASELINE.relative_to(ROOT).as_posix()}`", "", f"数量：{len(rows)}", "", "| URL | 状态 | 课程 | hash |", "| --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['url']} | {r['status']} {r['http_code'] or ''} | {', '.join(r['course_codes']) or '-'} | `{r['content_hash'] or '-'}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"official sources snapshot ok: {len(rows)} urls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
