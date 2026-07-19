"""Shared mdutil helpers (formerly in build-course-pages)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from lib.mdutil import code_for_source, parse_heading_title, parse_meta_table, route_for_source, split_frontmatter


def test_split_frontmatter_empty():
    text = "# 标题\n\n内容"
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body == text


def test_split_frontmatter_valid():
    text = """---
title: 测试课程
code: "12345"
---

# 内容
"""
    fm, body = split_frontmatter(text)
    assert fm["title"] == "测试课程"
    assert fm["code"] == "12345"
    assert body.strip().startswith("# 内容")


def test_parse_meta_table():
    body = """
| 字段 | 内容 |
|---|---|
| 课程代码 | 12345 |
| 课程名称 | 测试课程 |
| 学分 | 4 |

其他内容
"""
    meta = parse_meta_table(body)
    assert meta["课程代码"] == "12345"
    assert meta["课程名称"] == "测试课程"
    assert meta["学分"] == "4"


def test_parse_heading_title():
    body = """
## 副标题

# 主标题

内容
"""
    assert parse_heading_title(body) == "主标题"


def test_code_and_route():
    p1 = Path("content/jiangsu/courses/12345/index.md")
    assert code_for_source(p1) == "12345"
    assert route_for_source(p1) == "/courses/12345/"
    p2 = Path("content/jiangsu/courses/67890.md")
    assert code_for_source(p2) == "67890"
