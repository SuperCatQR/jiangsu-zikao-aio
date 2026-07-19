"""单元测试：materials_policy 核心函数。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lib import materials_policy as mod


def test_check_ref_allows_documented_placeholders():
    assert mod.check_ref("...") is None
    assert mod.check_ref("...`，不得写") is None
    assert mod.check_ref("<path>") is None


def test_check_ref_rejects_escape_and_sensitive_names():
    assert mod.check_ref("../private.pdf") == "bad materials path"
    assert mod.check_ref(r"e-books\secret.pdf") == "bad materials path"
    assert mod.check_ref("e-books/jiangsu/password.pdf") == "sensitive word in path"


def test_bad_pattern_catches_documented_private_dirs():
    for text in (
        "past-papers/jiangsu/a.pdf",
        "syllabus/jiangsu/a.pdf",
        "official-packages/jiangsu/a.zip",
    ):
        assert mod.BAD.search(text)
