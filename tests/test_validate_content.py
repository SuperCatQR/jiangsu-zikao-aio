from pathlib import Path
import hashlib
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


def _write_manifest(tmp_path, source_pdf: str, source_sha: str) -> Path:
    for name in ("a.xml", "a.txt", "a.html", "a.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    manifest = tmp_path / "pdf-processing-manifest.csv"
    manifest.write_text(
        '"type","source_pdf","raw_xml","raw_txt","raw_view_html","extracted_md","source_sha256","extraction_policy"\n'
        f'"major-plan","{source_pdf}","a.xml","a.txt","a.html","a.md","{source_sha}","full-text-draft"\n',
        encoding="utf-8-sig",
    )
    return manifest


def _write_lfs_pointer(tmp_path, name: str, oid: str) -> None:
    (tmp_path / name).write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{oid}\nsize 1234\n",
        encoding="utf-8",
    )


def test_pdf_manifest_gate_accepts_matching_lfs_pointer(tmp_path):
    _write_lfs_pointer(tmp_path, "doc.pdf", "a" * 64)
    manifest = _write_manifest(tmp_path, "doc.pdf", "a" * 64)
    assert content_gate.validate_pdf_manifest(tmp_path, manifest) == []


def test_pdf_manifest_gate_rejects_stale_lfs_pointer(tmp_path):
    _write_lfs_pointer(tmp_path, "doc.pdf", "b" * 64)
    manifest = _write_manifest(tmp_path, "doc.pdf", "a" * 64)
    errors = content_gate.validate_pdf_manifest(tmp_path, manifest)
    assert any("不一致" in e for e in errors)


def test_pdf_manifest_gate_hashes_real_pdf_bytes(tmp_path):
    payload = b"%PDF-1.4 real bytes"
    (tmp_path / "doc.pdf").write_bytes(payload)

    fresh = _write_manifest(tmp_path, "doc.pdf", hashlib.sha256(payload).hexdigest())
    assert content_gate.validate_pdf_manifest(tmp_path, fresh) == []

    stale = _write_manifest(tmp_path, "doc.pdf", "c" * 64)
    errors = content_gate.validate_pdf_manifest(tmp_path, stale)
    assert any("不一致" in e for e in errors)
