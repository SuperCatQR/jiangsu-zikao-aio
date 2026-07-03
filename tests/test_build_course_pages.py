"""单元测试：build-course-pages.py 核心函数。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import pytest


def test_split_frontmatter_empty():
    """空 frontmatter 应返回空字典和原文本。"""
    from build_course_pages import split_frontmatter
    
    text = "# 标题\n\n内容"
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body == text


def test_split_frontmatter_valid():
    """有效 frontmatter 应解析为字典。"""
    from build_course_pages import split_frontmatter
    
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
    """元数据表格应解析为字典。"""
    from build_course_pages import parse_meta_table
    
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
    """提取一级标题。"""
    from build_course_pages import parse_heading_title
    
    body = """
## 副标题

# 主标题

内容
"""
    title = parse_heading_title(body)
    assert title == "主标题"


def test_code_for_source():
    """从路径推断课程代码。"""
    from build_course_pages import code_for_source
    
    # 文件夹格式
    p1 = Path("content/jiangsu/courses/12345/index.md")
    assert code_for_source(p1) == "12345"
    
    # 文件名格式
    p2 = Path("content/jiangsu/courses/67890.md")
    assert code_for_source(p2) == "67890"


def test_route_for_source():
    """路由生成。"""
    from build_course_pages import route_for_source
    
    p = Path("content/jiangsu/courses/12345/index.md")
    assert route_for_source(p) == "/courses/12345/"
