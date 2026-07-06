"""单元测试：validate-materials-policy.py 核心函数。"""
import importlib.util
from pathlib import Path


def _load_module():
    script = Path(__file__).parents[1] / "scripts" / "validate-materials-policy.py"
    spec = importlib.util.spec_from_file_location("validate_materials_policy", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_check_ref_allows_documented_placeholders():
    mod = _load_module()

    assert mod.check_ref("...") is None
    assert mod.check_ref("...`，不得写") is None
    assert mod.check_ref("<path>") is None


def test_check_ref_rejects_escape_and_sensitive_names():
    mod = _load_module()

    assert mod.check_ref("../private.pdf") == "bad materials path"
    assert mod.check_ref(r"e-books\secret.pdf") == "bad materials path"
    assert mod.check_ref("e-books/jiangsu/password.pdf") == "sensitive word in path"



def test_bad_pattern_catches_documented_private_dirs():
    mod = _load_module()
    for text in ("past-papers/jiangsu/a.pdf", "syllabus/jiangsu/a.pdf", "official-packages/jiangsu/a.zip"):
        assert mod.BAD.search(text)
