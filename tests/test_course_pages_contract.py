"""Course multipage + frontmatter schema contract."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lib.course_pages_contract import check_course_dir, check_frontmatter, load_schema
from lib.mdutil import split_frontmatter


def test_load_schema_has_lifecycle(tmp_path=None):
    root = Path(__file__).parents[1]
    schema = load_schema(root)
    assert "lifecycle" in schema.get("frontmatter", {}).get("required", [])


def test_missing_lifecycle_errors(tmp_path):
    root = tmp_path
    course = root / "content" / "jiangsu" / "courses" / "12345"
    course.mkdir(parents=True)
    (course / "index.md").write_text(
        "---\ncompleteness: metadata-only\n---\n# t\n\n## 页面导航\nsources.md practice.md plan.md\n",
        encoding="utf-8",
    )
    for name, marker in [
        ("sources.md", "来源 核验"),
        ("practice.md", "真题"),
        ("plan.md", "阶段目标"),
    ]:
        (course / name).write_text(marker + "\n", encoding="utf-8")
    schema = {
        "required_files": ["index.md", "sources.md", "practice.md", "plan.md"],
        "page_markers": {
            "index.md": ["页面导航", "sources.md", "practice.md", "plan.md"],
            "sources.md": ["来源", "核验"],
            "practice.md": ["真题"],
            "plan.md": ["阶段目标"],
        },
        "frontmatter": {
            "required": ["lifecycle", "completeness"],
            "lifecycle_values": ["draft", "machine_ready", "in_review", "publishable"],
            "completeness_values": ["complete", "metadata-only", "missing-source", "needs-review"],
        },
    }
    errors = check_course_dir(root, course, schema)
    assert any("lifecycle" in e for e in errors)


def test_valid_frontmatter_ok(tmp_path):
    p = tmp_path / "index.md"
    p.write_text(
        "---\nlifecycle: draft\ncompleteness: metadata-only\n---\n# t\n",
        encoding="utf-8",
    )
    schema = {
        "frontmatter": {
            "required": ["lifecycle", "completeness"],
            "lifecycle_values": ["draft", "machine_ready", "in_review", "publishable"],
            "completeness_values": ["complete", "metadata-only", "missing-source", "needs-review"],
        }
    }
    assert check_frontmatter(tmp_path, p, schema) == []


def test_disallowed_frontmatter_key_errors(tmp_path):
    p = tmp_path / "index.md"
    p.write_text(
        "---\nlifecycle: draft\ncompleteness: metadata-only\ncanonical: /courses/04747/\n---\n# t\n",
        encoding="utf-8",
    )
    schema = {
        "frontmatter": {
            "required": ["lifecycle", "completeness"],
            "lifecycle_values": ["draft", "machine_ready", "in_review", "publishable"],
            "completeness_values": ["complete", "metadata-only", "missing-source", "needs-review"],
            "disallowed": {"route": "archived SSG routing input", "canonical": "MkDocs emits it"},
        }
    }
    errors = check_frontmatter(tmp_path, p, schema)
    assert any("canonical" in e and "disallowed" in e for e in errors)


def test_course_indexes_carry_no_hand_written_route_metadata():
    """`route`/`canonical` were inputs to the archived hand-written SSG.

    MkDocs derives page URLs and the canonical link from `site_url` plus the
    file path, so a hand-written copy can only drift: those values still said
    `/courses/<code>/` long after the pages moved to `/jiangsu/courses/<code>/`.
    """
    root = Path(__file__).parents[1]
    schema = load_schema(root)
    disallowed = list((schema.get("frontmatter") or {}).get("disallowed") or {})
    assert disallowed, "schema must declare disallowed frontmatter keys"

    offenders = [
        f"{index.parent.name}:{key}"
        for index in sorted((root / "content" / "jiangsu" / "courses").glob("*/index.md"))
        for key in disallowed
        if key in split_frontmatter(index.read_text(encoding="utf-8"))[0]
    ]
    assert not offenders, f"vestigial routing metadata: {offenders}"
