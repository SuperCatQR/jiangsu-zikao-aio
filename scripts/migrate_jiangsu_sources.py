from pathlib import Path
import csv
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sources" / "jiangsu"

MAJOR_SLUGS = {
    "机械制造及自动化": "mechanical-manufacturing", "机电一体化技术": "mechatronics", "中药学": "chinese-medicine",
    "工商企业管理": "business-admin", "市场营销": "marketing", "电子商务": "e-commerce", "学前教育": "preschool-education",
    "小学教育": "primary-education", "心理健康教育": "mental-health", "人力资源管理": "human-resource", "行政管理": "administration",
    "金融学": "finance", "国际经济与贸易": "international-trade", "法学": "law", "汉语言文学": "chinese-language",
    "秘书学": "secretarial-science", "英语": "english", "商务英语": "business-english", "新闻学": "journalism", "广告学": "advertising",
    "机械设计制造及其自动化": "mechanical-design", "汽车服务工程": "automotive-service", "计算机科学与技术": "computer-science", "消防工程": "fire-engineering",
}

def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()

def slug(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"\d+[\.、_-]*", "", stem)
    for zh, en in MAJOR_SLUGS.items():
        if zh in stem:
            return en
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "source"

def classify_pdf(p: Path) -> str:
    s = p.as_posix(); name = p.name
    if "major-plans" in s or "考试计划" in name or "plan-handbook" in name:
        return "public-official/major-plans"
    if "course-adjustment" in name or "directory" in name or "code-mapping" in name:
        return "public-official/policies"
    if "exam" in name or "notice" in name or "报名" in name or "考试" in name:
        return "public-official/exam-notices"
    return "public-official/syllabi"

def plan_moves():
    rows = []
    for p in sorted(SRC.rglob("*")):
        if not p.is_file() or "manifests" in p.parts:
            continue
        old = rel(p)
        if "/public-official/" in old or "/processed/" in old:
            continue
        if p.suffix.lower() == ".pdf":
            folder = classify_pdf(p)
            new = f"sources/jiangsu/{folder}/{slug(p.name)}/{p.name}"
            kind = "official-pdf"
        else:
            folder = "processed/major-plans" if "major-plans" in old else "processed/source-records"
            new = f"sources/jiangsu/{folder}/{p.name}"
            kind = "processed"
        rows.append((old, new, kind, "public-official" if kind == "official-pdf" else "derived", "mechanical migration"))
    return rows

def write_manifest(rows):
    out = SRC / "manifests" / "migration-map.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["old_path", "new_path", "kind", "public_status", "notes"]); w.writerows(rows)

def apply(rows, dry_run=True):
    write_manifest(rows)
    if dry_run:
        return
    for old, new, *_ in rows:
        src = ROOT / old; dst = ROOT / new
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    for d in sorted(SRC.rglob("*"), reverse=True):
        if d.is_dir():
            try: d.rmdir()
            except OSError: pass

if __name__ == "__main__":
    rows = plan_moves()
    apply(rows, dry_run="--apply" not in __import__("sys").argv)
    print(f"planned {len(rows)} moves")
