from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import content_gate


def test_table_fields_extracts_basic_fields():
    fields = content_gate.table_fields(
        """| 字段 | 内容 |\n| --- | --- |\n| 课程代码 | 02333 |\n| 资料状态 | complete |\n"""
    )
    assert fields["课程代码"] == "02333"
    assert fields["资料状态"] == "complete"


def test_validator_rejects_private_raw_url(tmp_path):
    f = tmp_path / "index.md"
    f.write_text(
        "https://raw.githubusercontent.com/me/zikao-materials/main/a.pdf",
        encoding="utf-8",
    )
    errors = content_gate.validate_file(ROOT, f)
    assert any("private/raw" in e for e in errors)


def test_pdf_manifest_gate_rejects_missing_output(tmp_path):
    manifest = tmp_path / "pdf-processing-manifest.csv"
    manifest.write_text(
        '"type","source_pdf","raw_xml","raw_txt","raw_view_html","extracted_md","source_sha256","extraction_policy"\n'
        '"major-plan","missing.pdf","a.xml","a.txt","a.html","a.md","'
        + ("0" * 64)
        + '","full-text-draft"\n',
        encoding="utf-8-sig",
    )
    errors = content_gate.validate_pdf_manifest(tmp_path, manifest)
    assert any("不存在" in e for e in errors)
