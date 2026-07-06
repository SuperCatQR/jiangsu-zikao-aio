from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_content", ROOT / "scripts" / "validate-content.py")
validate_content = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_content)


def test_table_fields_extracts_basic_fields():
    fields = validate_content.table_fields("""| 字段 | 内容 |\n| --- | --- |\n| 课程代码 | 02333 |\n| 资料状态 | complete |\n""")
    assert fields["课程代码"] == "02333"
    assert fields["资料状态"] == "complete"


def test_validator_rejects_private_raw_url(tmp_path):
    f = tmp_path / "index.md"
    f.write_text("https://raw.githubusercontent.com/me/zikao-materials/main/a.pdf", encoding="utf-8")
    errors = validate_content.validate_file(f)
    assert any("private/raw" in e for e in errors)
