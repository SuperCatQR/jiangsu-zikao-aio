from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BAD = re.compile(r"https://github\.com/.+/(zikao-materials/.+|raw|download)|(?:^|[\s(])(?:\.\./)?(?:materials|e-books|papers|official-archives)/[^\s)]+\.(?:pdf|zip|rar)\b", re.I)
MAT = re.compile(r"materials://([^\s)>'\"]+)")


def check_ref(ref: str) -> str | None:
    ref = ref.rstrip("`。，；,.;:")
    if ref.startswith("...") or ref in {"<path>", "<relative-path-without-extension-or-sensitive-name>"}:
        return None
    if ".." in ref or "\\" in ref:
        return "bad materials path"
    if re.search(r"(secret|token|key|password)", ref, re.I):
        return "sensitive word in path"
    return None


def main() -> int:
    errors = []
    for p in (ROOT / "content").rglob("*.md"):
        s = p.read_text(encoding="utf-8", errors="ignore")
        for m in MAT.finditer(s):
            err = check_ref(m.group(1))
            if err:
                errors.append(f"{p.relative_to(ROOT)}: {err}: {m.group(0)}")
        for line_no, line in enumerate(s.splitlines(), 1):
            if "materials://" in line:
                continue
            if BAD.search(line) and "jseea.cn" not in line:
                errors.append(f"{p.relative_to(ROOT)}:{line_no}: possible private/raw file leak")
    if errors:
        print("materials policy violations:")
        print("\n".join(errors))
        return 1
    print("materials policy ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
