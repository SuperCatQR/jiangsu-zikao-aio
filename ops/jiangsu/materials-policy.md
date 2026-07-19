# materials:// 私仓引用政策

公开仓只保存“官方公开来源 + 索引 + 摘要”。教材、真题原件、扫描件、非公开资料一律只在 private `zikao-materials` 中保存，公开仓使用 `materials://` 引用。

## 可公开内容

- 官方 URL、标题、发布日期、发布机构。
- 教材书名、作者、出版社、ISBN、版本年。
- 资料存在状态：`ready` / `needs-review` / `need-procurement` / `blocked-license`。
- 内部引用：`materials://...`。

## 禁止内容

- PDF、图片、压缩包原件。
- private 仓 raw/download 链接。
- 扫描页截图、可还原原文的大段 OCR。
- 来源不明第三方网盘或转载 PDF 下载地址。

## 引用格式

```markdown
教材：《数据库系统原理》（2018年版）
ISBN: 9787040494938
资料状态：ready
内部路径：materials://e-books/jiangsu/04735
官方来源：https://www.jseea.cn/...
```

## 入库闭环

1. 在 `zikao-materials` 核验合法性与 LFS。
2. 记录元数据与状态。
3. 在 AIO 课程页 `sources.md` 写公开元数据和 `materials://`。
4. 若缺资料，开 `missing-source` issue；若待核验，标 `needs-review`。

## 解析与存在性（P2 / Issue #57）

机器侧实现：`scripts/lib/materials_resolve.py`。

- 私仓根目录：环境变量 `ZIKAO_MATERIALS_ROOT`，或与 AIO 同级的 sibling `zikao-materials/`。
- `materials://e-books/jiangsu/04735` 可前缀匹配私仓中以课程代码开头的教材文件。
- 私仓不可用时（CI 无 sibling）不阻断；本地有私仓时，`run-gates` materials 层会报告 missing。
- 诊断：`python scripts/check-materials-resolve.py`
- 关闭存在性检查：`ZIKAO_MATERIALS_RESOLVE=0`
