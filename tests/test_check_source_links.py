"""单元测试：check-source-links.py 核心函数。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import pytest


def test_normalize_url():
    """URL 规范化：去除尾随标点。"""
    from check_source_links import normalize_url
    
    assert normalize_url("https://example.com/page。") == "https://example.com/page"
    assert normalize_url("https://example.com/page.") == "https://example.com/page"
    assert normalize_url("https://example.com/page)") == "https://example.com/page"
    assert normalize_url("https://example.com/page，") == "https://example.com/page"


def test_host_of():
    """提取域名。"""
    from check_source_links import host_of
    
    assert host_of("https://www.example.com/path?q=1") == "www.example.com"
    assert host_of("http://example.com") == "example.com"
    assert host_of("https://sub.domain.com:8080/page") == "sub.domain.com"


def test_section_in_scope():
    """判断章节是否需监控。"""
    from check_source_links import section_in_scope
    
    assert section_in_scope("来源与引用") is True
    assert section_in_scope("考纲与教材") is True
    assert section_in_scope("真题索引") is True
    assert section_in_scope("课程概述") is False
    assert section_in_scope("学习建议") is False


def test_course_code_for():
    """从路径推断课程代码。"""
    from check_source_links import course_code_for
    
    # 文件夹格式
    p1 = Path("content/jiangsu/courses/12345/index.md")
    assert course_code_for(p1) == "12345"
    
    # 文件名格式（5位数字）
    p2 = Path("content/jiangsu/courses/67890.md")
    assert course_code_for(p2) == "67890"
    
    # 非课程文件
    p3 = Path("content/jiangsu/majors/software/index.md")
    assert course_code_for(p3) is None


def test_url_ref_extraction():
    """测试 URL 引用提取逻辑（集成测试风格，依赖正则）。"""
    from check_source_links import MD_LINK_RE, BARE_URL_RE
    
    text = """
[江苏省教育考试院](https://www.jseea.cn)
官网：https://www.jseea.cn/webfile/
"""
    
    md_links = MD_LINK_RE.findall(text)
    assert "https://www.jseea.cn" in md_links
    
    bare_urls = BARE_URL_RE.findall(text)
    assert any("https://www.jseea.cn/webfile/" in u for u in bare_urls)
