"""Deprecated: former SSG unit tests.

Helpers now live in lib.mdutil; see tests/test_mdutil.py.
This file remains as a thin redirect so old pytest paths still resolve.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))


def test_helpers_moved_to_mdutil():
    from lib.mdutil import split_frontmatter, parse_meta_table, code_for_source

    fm, body = split_frontmatter("---\nx: 1\n---\n# t\n")
    assert fm["x"] == "1"
    assert parse_meta_table("| 字段 | 内容 |\n|---|---|\n| a | b |\n")["a"] == "b"
    assert code_for_source(Path("content/jiangsu/courses/12345/index.md")) == "12345"
