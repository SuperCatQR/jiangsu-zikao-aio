"""major-slugs.json is the single slug dictionary."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.major_slugs import load_major_slugs, slug_for_major_name


def test_json_has_computer_science():
    data = json.loads((ROOT / "ops/jiangsu/major-slugs.json").read_text(encoding="utf-8"))
    assert data["slugs"]["计算机科学与技术"] == "computer-science-and-technology"


def test_loader_matches_json():
    slugs = load_major_slugs(ROOT)
    assert slug_for_major_name(ROOT, "法学") == "law"
    assert "计算机科学与技术" in slugs
