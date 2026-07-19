"""materials:// resolve adapter tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lib.materials_resolve import (
    parse_materials_uri,
    resolve_ref,
    MaterialsRef,
    find_materials_root,
)


def test_parse_strips_trailing_punct():
    ref = parse_materials_uri("materials://e-books/jiangsu/04735).")
    assert ref is not None
    assert ref.path == "e-books/jiangsu/04735"


def test_parse_rejects_placeholder():
    assert parse_materials_uri("materials://...") is None
    assert parse_materials_uri("materials://<path>") is None


def test_resolve_prefix_match(tmp_path):
    root = tmp_path / "mat"
    d = root / "e-books" / "jiangsu"
    d.mkdir(parents=True)
    pdf = d / "04735 数据库系统原理（2018年版）.pdf"
    pdf.write_bytes(b"%PDF")
    ref = MaterialsRef(raw="materials://e-books/jiangsu/04735", path="e-books/jiangsu/04735")
    result = resolve_ref(ref, root)
    assert result.exists
    assert result.reason == "ok-prefix"
    assert pdf in result.candidates


def test_resolve_missing(tmp_path):
    root = tmp_path / "mat"
    (root / "e-books" / "jiangsu").mkdir(parents=True)
    ref = MaterialsRef(raw="materials://e-books/jiangsu/99999", path="e-books/jiangsu/99999")
    result = resolve_ref(ref, root)
    assert not result.exists
    assert result.reason == "missing"


def test_resolve_no_root():
    ref = MaterialsRef(raw="materials://e-books/jiangsu/04735", path="e-books/jiangsu/04735")
    result = resolve_ref(ref, None)
    assert result.reason == "no-root"


def test_find_materials_root_sibling(tmp_path, monkeypatch):
    aio = tmp_path / "jiangsu-zikao-aio"
    mat = tmp_path / "zikao-materials"
    aio.mkdir()
    mat.mkdir()
    monkeypatch.delenv("ZIKAO_MATERIALS_ROOT", raising=False)
    found = find_materials_root(aio)
    assert found == mat.resolve()
