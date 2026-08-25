"""单元测试：check-source-links.py 核心函数。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))



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

    # Sibling course pages under a 5-digit folder
    p4 = Path("content/jiangsu/courses/12345/sources.md")
    assert course_code_for(p4) == "12345"
    p5 = Path("content/jiangsu/courses/12345/syllabus.md")
    assert course_code_for(p5) == "12345"


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


def test_expand_env_vars_uses_default_and_env(monkeypatch):
    """build.toml env fallback: ${VAR:default}."""
    from check_source_links import expand_env_vars

    monkeypatch.delenv("ZIKAO_REPORT", raising=False)
    assert expand_env_vars("${ZIKAO_REPORT:site/source-link-report.md}") == "site/source-link-report.md"

    monkeypatch.setenv("ZIKAO_REPORT", "tmp/report.md")
    assert expand_env_vars("${ZIKAO_REPORT:site/source-link-report.md}") == "tmp/report.md"


def test_iter_source_files_includes_nested_major_pages(tmp_path, monkeypatch):
    """source-link monitor scans all major/course markdown, not only index.md."""
    import check_source_links as mod

    courses = tmp_path / "courses"
    majors = tmp_path / "majors"
    target = majors / "080901" / "past-paper-index.md"
    target.parent.mkdir(parents=True)
    target.write_text("## 真题索引\nhttps://www.jseea.cn/webfile/", encoding="utf-8")
    courses.mkdir()

    monkeypatch.setattr(mod, "COURSES_DIR", courses)
    monkeypatch.setattr(mod, "MAJORS_DIR", majors)

    assert target in list(mod.iter_source_files())



def test_bulk_rot_is_separate_from_actionable_gate():
    from check_source_links import UrlFinding, ProbeResult, STATUS_DEAD, build_report

    findings = {}
    for i in range(3):
        f = UrlFinding(url=f"https://rot.example/{i}", host="rot.example", authoritative=False)
        f.probe = ProbeResult(f.url, STATUS_DEAD)
        f.change = "went_dead"
        findings[f.url] = f

    _, summary = build_report(findings, {"rot.example": {"total": 3, "dead": 3, "dead_urls": sorted(findings)}})
    assert summary["actionable_count"] == 0
    assert summary["bulk_rot_count"] == 1
    assert len(summary["bulk_actionable"]) == 3


def test_normalize_url_fullwidth_semicolon():
    """全角分号（；）作为 CJK 列表分隔符应被剥离。"""
    from check_source_links import normalize_url

    # trailing fullwidth semicolon
    assert normalize_url("https://example.com/a.html；") == "https://example.com/a.html"
    # trailing fullwidth comma still stripped
    assert normalize_url("https://example.com/a.html，") == "https://example.com/a.html"


def test_bare_url_split_on_fullwidth_semicolon():
    """BARE_URL_RE 不得把全角分号连接的两个 URL 合并为一个。"""
    from check_source_links import BARE_URL_RE

    line = (
        "| 考纲 | https://www.jseea.cn/webfile/a/1.html；"
        "https://www.jseea.cn/webfile/upload/2025/06-19/14-59-1607281034810553.pdf |"
    )
    urls = [m.group(0) for m in BARE_URL_RE.finditer(line)]
    assert urls == [
        "https://www.jseea.cn/webfile/a/1.html",
        "https://www.jseea.cn/webfile/upload/2025/06-19/14-59-1607281034810553.pdf",
    ], urls
