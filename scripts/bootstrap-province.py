#!/usr/bin/env python3
"""省份扩展脚手架：一键生成新省份的目录骨架和模板文件。

用法：
    python scripts/bootstrap-province.py guangdong

生成结构：
    content/{province}/
        courses/index.md
        majors/index.md
        index.md
    sources/{province}/
        README.md
    ops/{province}/
        README.md
        source-links.baseline.json
        course-review-checklist.md
"""

import argparse
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]


def validate_province_code(code: str) -> bool:
    """验证省份代码：小写拼音，2-15 字符。"""
    return code.islower() and code.isalpha() and 2 <= len(code) <= 15


def create_structure(province: str) -> dict[Path, str]:
    """返回需创建的文件路径和内容。"""
    files: dict[Path, str] = {}
    
    # content/{province}/
    content_base = ROOT / "content" / province
    files[content_base / "courses" / "index.md"] = dedent(f"""\
        # {province.capitalize()} 自考课程索引
        
        此页面自动生成，列出所有课程。
        
        ## 课程列表
        
        建设中...
    """)
    
    files[content_base / "majors" / "index.md"] = dedent(f"""\
        # {province.capitalize()} 自考专业计划
        
        | 专业代码 | 专业名称 | 层次 | 状态 |
        |---------|---------|------|------|
        | - | 建设中 | - | - |
    """)
    
    files[content_base / "index.md"] = dedent(f"""\
        # {province.capitalize()} 自学考试
        
        > {province.capitalize()} 省自学考试资料库
        
        ## 快速导航
        
        - [课程索引](courses/)
        - [专业计划](majors/)
        
        ## 数据来源
        
        - [{province.capitalize()} 省教育考试院](https://example.com)  <!-- 请更新为实际链接 -->
    """)
    
    # sources/{province}/
    sources_base = ROOT / "sources" / province
    files[sources_base / "README.md"] = dedent(f"""\
        # {province.capitalize()} 原始资料与机器产物
        
        存放考试院 PDF、OCR 文本、抽取清单等。
        
        ## 目录结构
        
        ```text
        sources/{province}/
        ├── syllabi/           # 考纲 PDF 原件
        ├── exam-schedules/    # 考试计划表
        ├── machine-output/    # OCR/PDF 解析产物
        └── reports/           # 抽取报告
        ```
        
        ## 注意事项
        
        - PDF 文件应使用 Git LFS 管理
        - 文件命名遵循 `{{type}}-{{date}}-{{desc}}.pdf` 格式
    """)
    
    # ops/{province}/
    ops_base = ROOT / "ops" / province
    files[ops_base / "README.md"] = dedent(f"""\
        # {province.capitalize()} 元文档
        
        内部规范、检查清单、工作流、外链基线等。
        
        ## 文件说明
        
        - `source-links.baseline.json`: 外链监控基线（由 check-source-links.py 生成）
        - `course-review-checklist.md`: 课程页发布前检查清单
    """)
    
    files[ops_base / "source-links.baseline.json"] = dedent("""\
        {
          "_meta": {
            "description": "外链监控基线，由 scripts/check-source-links.py 生成",
            "last_update": "待首次运行"
          },
          "urls": {}
        }
    """)
    
    files[ops_base / "course-review-checklist.md"] = dedent(f"""\
        # {province.capitalize()} 课程页发布前检查清单
        
        课程页提交前必须通过以下检查：
        
        ## 元数据完整性
        
        - [ ] 课程代码、名称、学分、考试形式填写完整
        - [ ] 版本年/教材信息准确（与考试院公告一致）
        
        ## 外链可用性
        
        - [ ] 考纲链接可访问
        - [ ] 教材购买链接有效
        - [ ] 真题来源链接可访问
        
        ## 格式规范
        
        - [ ] Markdown 语法正确（无残留标记）
        - [ ] 表格对齐、无空单元格
        - [ ] 代码块有语言标识
        
        ## 内容质量
        
        - [ ] 无错别字
        - [ ] 专业术语准确
        - [ ] 链接描述清晰（避免"点击这里"）
    """)
    
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip())
    ap.add_argument("province", help="省份代码（小写拼音，如 guangdong）")
    ap.add_argument("--dry-run", action="store_true", help="仅显示将创建的文件，不实际写入")
    args = ap.parse_args()
    
    province = args.province.strip().lower()
    
    if not validate_province_code(province):
        print(f"错误: 无效的省份代码 '{province}'（需小写拼音，2-15字符）", file=sys.stderr)
        sys.exit(1)
    
    files = create_structure(province)
    
    if args.dry_run:
        print(f"[DRY RUN] 将创建以下 {len(files)} 个文件:\n")
        for path in sorted(files.keys()):
            print(f"  {path.relative_to(ROOT)}")
        return
    
    created = []
    for path, content in files.items():
        if path.exists():
            print(f"⚠  跳过已存在: {path.relative_to(ROOT)}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
        print(f"✓  创建: {path.relative_to(ROOT)}")
    
    print(f"\n成功创建 {len(created)}/{len(files)} 个文件")
    print(f"\n下一步:")
    print(f"  1. 更新 content/{province}/index.md 中的考试院链接")
    print(f"  2. 编辑 build.toml 添加 {province} 相关路径（如需单独配置）")
    print(f"  3. 运行 scripts/check-source-links.py 生成外链基线")


if __name__ == "__main__":
    main()
