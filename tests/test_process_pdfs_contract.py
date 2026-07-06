"""Static contract checks for scripts/process-pdfs.ps1."""
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "process-pdfs.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")


def test_manifest_records_hash_policy_and_raw_view():
    assert "source_sha256 = $outputs.SourceSha256" in TEXT
    assert "extraction_policy = $outputs.ExtractionPolicy" in TEXT
    assert "raw_view_html" in TEXT
    assert "source-records\\pdf-processing-manifest.csv" in TEXT


def test_shared_pdf_policy_avoids_copyright_fulltext_leak():
    assert 'if ($Type -in @("textbooks", "past-papers"))' in TEXT
    assert 'Policy = "metadata-only"' in TEXT
    assert "不写入全文" in TEXT


def test_raw_outputs_are_gated_and_not_mislabeled_normalized_html():
    assert "Assert-NonEmptyFile $raw.RawXml" in TEXT
    assert "Assert-NonEmptyFile $raw.RawTxt" in TEXT
    assert "New-RawViewHtml" in TEXT
    assert "NormalizedHtml" not in TEXT
    assert "规范化 HTML" not in TEXT


def test_shared_slugs_include_source_hash_when_filename_has_no_ascii_slug():
    assert "function Get-UniqueSlug" in TEXT
    assert 'return "document-$hash"' in TEXT


def test_major_code_missing_is_fail_fast():
    assert "Cannot extract major code" in TEXT
    assert '"unknown-$sequence"' not in TEXT


def test_report_lives_with_manifest_source_records():
    assert '$report = Join-Path $ProcessedDir "source-records\\pdf-processing-report.md"' in TEXT
    assert '$report = Join-Path $SourcesRoot "pdf-processing-report.md"' not in TEXT
