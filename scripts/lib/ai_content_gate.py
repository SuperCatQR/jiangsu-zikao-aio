"""AI Content Gate: validates AI prep layer contracts (Issue #55 / Task 6).

覆盖对象 = **存在 `content.json` 的课程**，外加一条**反向失败关闭**（F-QC3-2 / X2）：渲染页上已有带 AI
横幅的 AI 页面、而 `content.json` 缺失时同样报错 —— 作用域键不得替自己关闸，否则删掉真值源就能让
整层 AI 页面照常发布。既无 `content.json` 又无 AI 页面的课程保持全绿（其余 16 门课）。六类校验：

1. **标注四件套**（`validate_content_doc`）：`blocks[]` / `stage_plan[]` / `review_schedule` 及其 `plans[]`；
2. **8-gram 抄袭守卫**：语料取自 `evidence.json` 的 `syllabus.path`，并**校验 `sha256`**（QC1 F-5：
   旧实现按目录 glob 找语料、空即**静默跳过**，等于把闸门交给文件命名）；
3. **页面标记**：页面分类与标记字符串一律取自 `course.schema.json` 的 `generated_page_markers`
   （QC1 F-4 / QC3-003 / R9：schema 是唯一真源，同一规则不写两遍 —— 章页模式也由
   `_chapter_page_patterns()` 从该键派生，模块内不再自带 `knowledge/*.md` 字面量）；
   另有**未闭合注释的 fail-closed**（R20 / NEW-R3）：`<!--` 少了闭合记号时其后内容对读者不可见，
   而 `_blank_comments()` 只剥配对注释、谓词与计数仍把那些标题当证据 → 闸门全绿而页面已残缺。
   判据取「未闭合注释是否真的隐藏了内容」（见 `_comment_hides_content()`），故 Y2 的未闭合示例注释
   仍不报错（它没隐藏任何可见内容）；
4. **答案分布守卫**（compass R4 / T4）：按 `answer_md` 统计每门课的 drill 答案分布，判据 = 样本下界 10 /
   单选任一字母 > 40% / 判断题同类真值 > 80%。作用域信号是**该课 `content.json` 的 git 跟踪状态**
   （`git ls-files --error-unmatch`）：未跟踪 ⇒ 新课，偏置失败关闭；已跟踪 ⇒ 既有课，只报告；
   无法判定 ⇒ 按新课处理（fail-closed）。分布取证走**独立报告通道**（stdout），不进 `errors`；
   落在两族题型内却提不出答案的块**同受该作用域约束**（新课失败关闭；既有课只报告 —— QC-1 裁定，
   见 `_answer_distribution_problems()`）。**不做**硬编码课码清单，也**不用** mtime/`generated_at`
   （replay 会回放旧日期，不可复现）—— 那是 `conventions/gate-fail-closed-and-page-reach.md` 的旧缺陷类。
5. **AI 块必须真正落到页面**（QC3-001 / C2-004 / W1 / B2a N-1 / F-QC2-1 / F-QC3-1 / Y2）：对账口径 = **4 个
   block kind（`explain` / `memorize` / `drill` / `exam_strategy`）+ 2 个课程级顶层产物（`stage_plan` /
   `review_schedule`）**：`explain` / `memorize` 按**逐考核点锚点**对账（`### 考点精讲：<point_id>`
   小节内必须有对应 H4 小节、**且其正文非空**、且该 H4 标题是**读者可见的**——既不在代码围栏内，
   也不在 HTML 注释内），并保留**可见行**里的全局小节计数（精确相等）作**次级**页级界限；
   `practice.md` 的 drill 数、`plan.md` 的五阶段与
   `## 应试策略`、`review.md` 的排程，逐项与 `content.json` 对账；
   课程存在 `content.json` 而渲染页目录不存在时**失败关闭**，不静默跳过整门课。
   这一条缺失正是「AI 备考层从未被渲染」能过关的原因：先只覆盖 3/4 个 kind（`exam_strategy` 整块删掉仍两层全绿），
   后又是 `explain` / `memorize` 无对账 + 目录缺失静默 `continue`。
6. **反向失败关闭**（F-QC3-2 / X2 / Y1）：渲染页存在带 AI 横幅的页面而真值源不在 → 报错。作用域键取
   **源侧 ∪ 产物侧**的课码并集 —— 「产物存在」蕴含「源存在」，而不是以源的单个文件为前提：
   X2 只认 `content.json` 单文件缺失，于是**删掉整个源目录**时源侧迭代器里已经没有这门课，
   整门课连同 16 个渲染页一起逃出作用域（Y1）；把产物侧的课码并进来后，这一形态同样报错。
   产物侧课码**按 `^[0-9]{5}$` 设界**（R21 / Y1-a）：暂存残留的隐藏兄弟目录不是课程，
   放进作用域只会产生噪声错误（见 `_rendered_course_dirs()`）。

**为什么主判据是逐点锚点、而不是全局精确计数**（X3，更正此前写反的理由）：精确相等**并不能**防住
padding —— 删掉一个 `point_id` 的 `#### 要点梳理`、再在别处补一条同名标题，255 == 255 依旧全绿。
计数只回答「渲染了几个」，回答不了「渲染了哪几个」；`drill` 那样的下界同理。只有**按 `point_id` 锚点**
对账才防得住丢块，计数因此降级为次级页级界限（总量兜底）。

`rendered_course_dir` / `course_code` 让 `build` 的 `gate` 阶段校验**暂存区**页面而不是仓内既有页面。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from lib import course_pages_contract
from lib.course_pipeline.generate_content import (
    plagiarism_violations,
    validate_content_doc,
)

# 8-gram 之外的文本边界（plan § Data contracts 5 / design-notes §2 invariant 5）：`>` 引用块 ≤ 80 字符。
MAX_BLOCKQUOTE_CHARS = 80
QUESTION_TEXT_RE = re.compile(r"(选择题|填空题|简答题|材料题|下列.*正确)")

# `explain` / `memorize` 的唯一落点 = 渲染器的章页（`out_dir/knowledge/<NN>-<slug>.md`：
# `render_pages.py:881-882` 建目录、`:927-936` 逐章写入）。两个小节标题是**契约字面量**：
# `#### 记忆辅助` 由渲染器产出（`:807`）；`#### 要点梳理` 来自提示词常量
# （`generate_content.py:54` 的 `EXPLAIN_SUMMARY_HEADING`，由 `validate_content_doc()` 强制每个 explain
# 块必含），经 `_clean_explain_headings()`（`:141-155`）由 H3 降为 H4。判定一律按 H4 精确整行、
# **且只看代码围栏之外的行**（F-QC3-1(c)）。章页模式不自带字面量：见 `_chapter_page_patterns()`（R9/W-2）。
EXPLAIN_SUMMARY_HEADING = "#### 要点梳理"
MEMORIZE_AID_HEADING = "#### 记忆辅助"
# 裸行匹配仅供测试表达「全局计数」这一对照前提（`tests/test_ai_content_gate.py`）；闸门本身不用它们判定 ——
# 裸行匹配会把代码围栏内的同名行也算作渲染证据，那正是 F-QC3-1(c) 的漏洞。
EXPLAIN_SUMMARY_RE = re.compile(rf"(?m)^{re.escape(EXPLAIN_SUMMARY_HEADING)}$")
MEMORIZE_AID_RE = re.compile(rf"(?m)^{re.escape(MEMORIZE_AID_HEADING)}$")

# `explain` / `memorize` 的**逐考核点**锚点：渲染器在 `### 考点精讲：{point_id}（{requirement}）`
# 之下、紧挨着写出 explain 正文（`#### 要点梳理` 为其中一节）与 memorize 正文（`#### 记忆辅助`），
# 见 `render_pages.py:798-809`。H3 切分（`^### `）与 `drill` 的 `^### ` 小节口径一致；
# 该锚点同时是 MkDocs 目录里的稳定定位符，随页面重建而重建。
POINT_ANCHOR_RE = re.compile(r"^### 考点精讲：(?P<point_id>[^\s（]+)（")

# 答案分布守卫（plan § Data contracts 1/2；design-notes § 2.3/§ 2.4）的两条**单行**正则。
# 单选式有**两条互相独立**的约束，缺任一条都会给出错值：
# ① **不锚定行尾**：实测三种单选排布（`正确答案：A` 独占一行 / 该行后接解释 / `答案：A。…` 压缩形态）
#    与四种判断真值排布（`参考答案：错误。` / `…正确。` / `…错误，…` / `…正确。…`）的差别**只在同一行内**，
#    故一次覆盖即可。按「三种形态」分别匹配会系统性漏掉一整类（`15040` 的 31 道「前缀后接解释」曾因此被排除在样本外）。
# ② **捕获的字母必须是答案的终点**（QC-2 = qc1 F-2 + qc2 S-1，双席独立发现）：`\b` 在 `、` / `,` / `，` /
#    空格之前**成立**（它们都是非词字符），于是 `答案：A、B` / `答案：A,B` / `答案：A，B` / `答案：A B`
#    被静默记成 `A` —— 把**错值**灌进守卫自己的分子，比漏掉一个样本更糟；而同一批答案里的 `正确答案：AB`
#    又因 `\b` 不成立而失败关闭，两种多选写法行为相反。改为负向先行断言 `(?![\s、,，/]*[A-D])`：捕获字母之后
#    （允许空白与分隔符）**不得**再出现答案字母，五种多选形态因此一致进入 `unparseable`。
#    `答案：A。解析：…` 这类「解释紧跟」的形态不受影响 —— `。` 不是分隔符，解释文字也不以 A–D 开头。
ANSWER_SINGLE_CHOICE_RE = re.compile(
    r"^\s*[*#\s]*(?:正确)?答案[*\s]*[:：]\s*\**\s*([A-D])(?![\s、,，/]*[A-D])"
)
ANSWER_JUDGEMENT_RE = re.compile(r"^\s*[*#\s]*(?:参考|正确)?答案[*\s]*[:：]\s*\**\s*(正确|错误)")

# 题型**家族子串**：`question_type` 是考纲抽取出的自由文本（`knowledge_model.py` 读考纲「考试命题的
# 主要题型」段落），不是闭集枚举，故按家族子串分桶，而不是在这里写第二份题型白名单。未落入两族的题型
# （简答题 / 材料题 / 论述题 / 名词解释题 / 综合应用题）的答案本就是文字型，不参与分布判定；
# 实测五门课共 582 个此类 drill，全部无字母 / 真值答案，因此它们**不得**被当成「不可解析」报错。
SINGLE_CHOICE_TYPE_MARKER = "选择"
JUDGEMENT_TYPE_MARKER = "判断"

# Clarify C2 判据：样本下界 10；单选任一字母 > 40%；判断题同类真值 > 80%。百分比用整数比较，
# 边界不引入浮点误差（`n=10, count=4` 恰好 40% 不算偏置）。
MIN_ANSWER_SAMPLES = 10
MAX_SINGLE_CHOICE_SHARE_PERCENT = 40
MAX_JUDGEMENT_SHARE_PERCENT = 80

# 既有课的答案键偏置本轮**不回修**（Clarify C4），缺口由这两条 residual 跟踪。报告里点名它们，
# 读者才分得清「报告出来的既有偏置」与「新出现的问题」。
ANSWER_BIAS_RESIDUALS = "R15/R33"

# 作用域探针（`git ls-files`）的**上界**（QC-4 / qc3 F-2）：`ai-content` 层在 7 层闸门的关键路径上，
# 探针挂起（索引锁竞争、网络文件系统、`safe.directory` 类等待）会无诊断地阻塞整层。有界之后超时落进
# `content_tracking_state()` 的「无法判定 ⇒ 按新课处理」通道，而不是把闸门打崩。
GIT_TRACKING_PROBE_TIMEOUT_SECONDS = 10

# Markdown 代码围栏（``` / ~~~）：闭合需**同一字符**且不短于开启长度；围栏内的行不是渲染证据。
_FENCE_LINE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_HEADING_LINE_RE = re.compile(r"^#{1,6} ")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _blank_comments(text: str) -> str:
    """把 HTML 注释的**内容**换成空行（保留行数，行结构不变）—— 注释里的行不是渲染证据（Y2）。

    注释剥离必须发生在**标题扫描之前**。旧实现只在 `_heading_body()` 取到的**正文切片**里剥注释
    （`_is_empty_body`），于是两种形状的判定不对称：

    - 标题在注释**之外**、正文被注释包裹 → 正文切片内剥离后为空 → **能**抓到（QC3 的对照形状）；
    - `<!--` 开在标题行**之前**、`-->` 收在正文之后（标题 + 正文整段被包住）→ `<!--` 落在切片之外，
      切片里只剩注释的尾巴与脚注，剥完仍非空 → 判「已到达」，**0 错误**。

    对读者而言两种形状完全等价（该节都不可见），判定必须同形。与 `_unfenced_lines()` 同一手法：
    **不是渲染证据的行不参与判定**。

    只剥**配对完整**的注释。围栏里的 `<!--` 示例若按「直到文末」处理，会把其后真正的标题一并吞掉、
    反过来制造误报；两门课实测跨行注释 0 处（`<!-- generated … -->` / `<!-- ai-block … -->` 均单行闭合），
    故这一层只拦对抗路径、不动既有产物。
    """
    return _COMMENT_RE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def _unclosed_comment_line(text: str) -> int | None:
    """第一个**未闭合** `<!--` 所在的行号（0 基）；注释全部配平时返回 `None`。

    扫描口径与 `_blank_comments()` 用的 `_COMMENT_RE`（`<!--.*?-->`，非贪婪）**一致**：每个 `<!--`
    与其后最近的一个 `-->` 配对，游标跳过后继续找；找不到配对的那个即「未闭合」，其后的正文对读者
    全部不可见（HTML 注释的语义就是「直到闭合记号为止」）。

    裸 `-->`（前面没有开记号）**不**算未闭合：浏览器忽略它，它不隐藏任何内容，故不得报错。
    这也正是本判据不用「`<!--` 与 `-->` 计数不相等」的理由 —— 计数法会把一条无害的裸闭合记号判成缺陷。
    """
    cursor = 0
    while True:
        start = text.find("<!--", cursor)
        if start < 0:
            return None
        end = text.find("-->", start + 4)
        if end < 0:
            return text.count("\n", 0, start)
        cursor = end + 3


def _comment_hides_content(text: str) -> bool:
    """未闭合的 `<!--` 之后是否还有**非空行**（有则 fail-closed，R20）。

    背景（R20 / B2b QC3 NEW-R3）：`_blank_comments()` 只剥**配对**注释，未闭合的开记号原样留在文本里，
    于是 `_heading_body()` / `_count_visible_headings()` 仍把它后面的标题当成**已渲染证据** ——
    谓词与计数双双看不到「这些标题对读者不可见」，闸门在页面残缺时保持全绿。

    **口径（R20 要求的「未闭合如何 fail-closed 而不误伤」）**：以「未闭合注释**是否真的隐藏了内容**」
    为判据，而不是「记号计数是否配平」——
    - 开记号**之后还有非空行** → 那些行读者看不见 → 报错（末章页尾部被吞掉的形态）；
    - 开记号是全文最后一个非空行（其后只有空行，含 Y2 反向控制用例的形状）
      → 读者没有丢失任何可见内容 → **不报错**；
    - 开记号**自身那一行的剩余文本**不计入：`<!-- 未闭合的示例注释` 这种单行尾巴只丢半行，
      与「整段标题消失」不同量级，判它会误伤示例注释（Y2 反向控制用例已钉住这一侧不得报错）。

    围栏内的 `<!--` 示例同判：围栏里的记号不参与渲染，对读者不隐藏任何东西，故不报错 ——
    与 `_blank_comments()` 只剥配对注释同一立场。

    **记号定位与尾巴切片用两个不同的视图**（R42 更正 R20 的写法）。二者回答的是两个不同的问题：

    - 「这个 `<!--` 是不是注释」只能在**围栏视图**里问 —— 围栏内的记号不是注释（上一段）；
    - 「它后面是否还有内容」必须在**原文视图**里量 —— 未闭合注释吞掉其后的一切，**包括围栏记号本身**。
      若尾巴仍在围栏视图里取，一个**开在记号之后**的未闭合围栏就会把整段尾巴删掉，谓词反过来判
      「没隐藏任何内容」：`<!--` + ``` + `#### 要点梳理` + 正文 曾因此返回 `False`，而读者什么都看不见。

    两个视图靠 `_unfenced_indexed_lines()` 的原文行号对齐，而不是各切各的 —— 围栏出现在记号**之前**时，
    裸用围栏视图的行号去切原文会切错位置，把「确实隐藏了标题」误判成不报错（R20 的 (d) 形状）。
    """
    indexed = _unfenced_indexed_lines(text)
    start = _unclosed_comment_line("\n".join(line for _, line in indexed))
    if start is None:
        return False
    marker_line = indexed[start][0]
    return any(line.strip() for line in text.splitlines()[marker_line + 1 :])


def _unfenced_lines(text: str) -> list[str]:
    """`text` 中**不在代码围栏内**的行（围栏行本身也一并丢弃）。

    F-QC3-1(c)：`^#### 要点梳理$` 是纯行匹配，代码块里塞一条同名行即可满足它。判定必须只看围栏外的行，
    否则「删掉真标题、在围栏里补一条」就能让闸门放行。渲染器从不产出围栏（两门课实测围栏行均为 0），
    所以这一层只拦对抗路径、不动既有产物。
    """
    return [line for _, line in _unfenced_indexed_lines(text)]


def _unfenced_indexed_lines(text: str) -> list[tuple[int, str]]:
    """`_unfenced_lines()` 的**带原文行号**版本：`(0 基原文行号, 行内容)`，围栏内的行（含围栏行）不返回。

    行号是「围栏视图 ↔ 原文视图」之间唯一的对齐手段：围栏行被丢掉后行号不再相同，谁要跨视图取位置
    （`_comment_hides_content()` 的尾巴切片）就必须换回原文行号，否则切到的是错位区间。
    """
    lines: list[tuple[int, str]] = []
    fence: str | None = None
    for index, line in enumerate(text.splitlines()):
        match = _FENCE_LINE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group("fence")
                continue
            lines.append((index, line))
        elif match and match.group("fence")[0] == fence[0] and len(match.group("fence")) >= len(fence):
            fence = None
    return lines


def _evidence_lines(text: str) -> list[str]:
    """**读者可见的行** = 先剥 HTML 注释（Y2）、再看代码围栏之外（F-QC3-1(c)）的行。

    两层同形：注释与围栏里的内容都不是渲染证据，因而标题扫描、正文切片、小节计数一律走这一个入口 ——
    三个判定若各写一套剥离顺序，正是 Y2 那个「一半修好」缺口的来源。
    先剥注释再看围栏：注释里的 ``` 不会凭空开出围栏；围栏里的配对注释被剥掉也不影响围栏闭合判定
    （围栏内的内容本就不作证据）。
    """
    return _unfenced_lines(_blank_comments(text))


def _heading_body(section: str, heading: str) -> str | None:
    """`heading` 整行之后、到下一个标题行之前的正文（只看可见行）；标题不存在时返回 `None`。

    `None` 与空串是**两件事**，对应两种必须分别报错的规避（F-QC3-1）：
    (c) 标题在围栏里 → `None`（该标题根本没渲染到页面）；(a) 标题在、正文被清空 → `""`（渲染了空壳）。
    Y2 之后 (c) 扩为「标题不是渲染证据」：围栏**内**、或注释**内**（含注释包住标题整段的形状）都是 `None`。
    """
    lines = _evidence_lines(section)
    for index, line in enumerate(lines):
        if line != heading:
            continue
        body: list[str] = []
        for following in lines[index + 1 :]:
            if _HEADING_LINE_RE.match(following):
                break
            body.append(following)
        return "\n".join(body)
    return None


def _is_empty_body(body: str) -> bool:
    """正文去掉 HTML 注释后是否为空（`<!-- ai-block ... -->` 脚注不是正文，不能拿它充数）。

    `body` 来自 `_heading_body()`，注释在那之前已被 `_evidence_lines()` 换成空行，故剥注释这一步在此
    已是幂等的兜底（契约不变，单独调用本函数同样成立）。
    """
    return not _COMMENT_RE.sub("", body).strip()


def _count_visible_headings(text: str, heading: str) -> int:
    """**可见行**里 `heading` 的精确整行计数（**次级**页级界限；主判据是逐点锚点）。

    注释内的同名标题不计入（Y2）：计数回答的是「渲染到页面上几条」，而注释里的行读者看不见。
    """
    return sum(1 for line in _evidence_lines(text) if line == heading)


def _chapter_page_patterns(markers: dict) -> set[str]:
    """章页模式 = schema `generated_page_markers.ai_pages` 里的**子目录**模式（即 `knowledge/*.md`）。

    R9/W-2：本模块不再自带第二份 `knowledge/*.md` 字面量 —— 页面分类的唯一真源是 schema
    （模块 docstring 第 3 条），经 `course_pages_contract.generated_page_markers()` 读取（schema 缺键时
    该访问器自己回落到同一份默认值）。章页与课程级 AI 页（`plan.md` / `practice.md` / `review.md`）的
    区别是**目录层级**：章页在 `knowledge/` 之下，故取含 `/` 的模式；一个都没有时退回全部 AI 页
    （只会让次级计数更宽，主判据仍是逐点锚点）。
    """
    chapter = {str(pattern) for pattern in markers["ai_pages"] if "/" in str(pattern)}
    return chapter or {str(pattern) for pattern in markers["ai_pages"]}


def _syllabus_text(root: Path, code: str, rel_content: str, errors: list[str]) -> str:
    """考纲语料 = `evidence.json.syllabus.path` 的内容，且 `sha256` 必须与记录一致（缺失即失败关闭）。"""
    evidence_path = root / "sources" / "jiangsu" / "courses" / code / "evidence.json"
    if not evidence_path.is_file():
        errors.append(f"course {code}: content.json 存在但 evidence.json 缺失（无考纲语料可校验）")
        return ""
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    syllabus = evidence.get("syllabus") or {}
    rel_path = syllabus.get("path")
    if syllabus.get("status") != "extracted" or not rel_path:
        errors.append(f"course {code}: 考纲未 extracted（{rel_content} 的 8-gram 语料缺失，禁止静默跳过）")
        return ""
    document = root / rel_path
    if not document.is_file():
        errors.append(f"course {code}: evidence.json 指向的考纲抽取件不存在: {rel_path}")
        return ""
    recorded = syllabus.get("sha256")
    actual = hashlib.sha256(document.read_bytes()).hexdigest()
    if recorded != actual:
        errors.append(f"course {code}: 考纲抽取件 sha256 与 evidence.json 不一致（{rel_path}）")
        return ""
    return document.read_text(encoding="utf-8")


def _page_problems(rel_md: str, text: str, markers: dict, errors: list[str], *, label: str | None = None) -> None:
    """单页标记与文本边界（横幅双向断言 + generated 注释 + 生成页的引用块上限）。

    引用块上限只作用于**渲染器产出**的页面：`official_only` 页面（`index.md` / `syllabus.md` /
    `sources.md`）的正文是手写官方事实页，渲染器不得改写（QC3-002 / QC3-006 / C2-011）。
    对它们套用「≤ 80 字符」等于要求「删掉手写正文的引用块」，而那正是被判定的 Critical 缺陷本身。

    未闭合注释的 fail-closed（R20）放在最前、且**不**区分 official / AI 页：它是一条页面完整性守卫
    （页面尾部被吞掉），不是 AI 层对账，故与页面的 `official_only` 分类无关。

    `rel_md` 是相对课程目录的路径（页面分类用），`label` 是报错前缀。
    """
    where = label or rel_md
    if _comment_hides_content(text):
        errors.append(
            f"{where}: 存在未闭合的 `<!--`，其后内容对读者不可见"
            f"（读者看到的页面已残缺，禁止静默通过）"
        )
    if markers["any"] not in text:
        errors.append(f"{where}: 缺少生成标识注释 <!-- generated by ... -->")

    is_official = course_pages_contract.matches_page(rel_md, markers["official_only"])
    is_ai = course_pages_contract.matches_page(rel_md, markers["ai_pages"])
    if is_official and markers["ai_banner"] in text:
        errors.append(f"{where}: 官方页面意外包含 AI 横幅 banner（{markers['ai_banner']}）")
    elif is_ai and markers["ai_banner"] not in text:
        errors.append(f"{where}: AI 页面缺少 AI 横幅 banner（{markers['ai_banner']}）")

    if is_official:
        return
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith(">"):
            continue
        quote = stripped.lstrip(">").strip()
        if len(quote) > MAX_BLOCKQUOTE_CHARS:
            errors.append(f"{where}: 引用块超过 {MAX_BLOCKQUOTE_CHARS} 字符（{len(quote)}）: {quote[:40]}...")
        if QUESTION_TEXT_RE.search(quote):
            errors.append(f"{where}: 引用块出现题文特征: {quote[:40]}...")


def _chapter_page_sections(page_text: dict[str, str], chapter_patterns: set[str]) -> tuple[str, dict[str, str]]:
    """章页正文拼接 + `### 考点精讲：<point_id>` 锚点小节索引（H4 标题留在自己的小节内）。

    以 `^### ` 切分：章页上每个 H3 都是渲染器的**契约标题**（`### {章标题}` / `### 考点精讲：<point_id>`
    / `### 练习题：<point_id>`，见 `render_pages.py:798,827`），H4 小节因而必定落在其所属锚点小节之内。
    切分**只看可见行**（`_evidence_lines()`：剥 HTML 注释 + 跳过围栏，F-QC3-1(c) / Y2）：围栏里的
    `### ` 不是渲染器的 H3，不能拿来凭空造一个锚点小节，
    否则「真小节删掉、围栏里补一个假锚点」就能让逐点对账误判为已到达；注释包住整段的 `### ` 同理
    （那些行读者看不见）。页面顺序在两门课内**唯一**
    （`render_pages.py:881-882,927-936` 逐章写一个文件）；真出现重复时后者覆盖
    前者，`rendered != expected` 的页级计数会兜住。
    """
    chapters: list[str] = []
    sections: dict[str, str] = {}
    for rel_md, text in page_text.items():
        if not course_pages_contract.matches_page(rel_md, chapter_patterns):
            continue
        chapters.append(text)
        # 按「围栏外的 `^### ` 行」切分（与 `^### ` 正则 split 同形：`### ` 前缀由下面的 `section` 补回）。
        # `chunk` 每项 = 一个 H3 的标题行 + 其正文，正好一节；不能再两两配对（那会把相邻小节拼进来
        # —— 邻节的 H4 会掩盖本节的缺失）。切分口径 = `_evidence_lines()`（剥注释 + 跳过围栏），
        # 注释包住整段的 H3 不再凭空造出锚点小节（Y2）。
        current: list[str] = []
        chunks: list[str] = []
        for line in _evidence_lines(text):
            if line.startswith("### "):
                if current:
                    chunks.append("\n".join(current))
                current = [line[4:]]
            else:
                current.append(line)
        if current:
            chunks.append("\n".join(current))
        for chunk in chunks:
            section = "### " + chunk
            match = POINT_ANCHOR_RE.match(section)
            if match:
                sections[match.group("point_id")] = section
    return "".join(chapters), sections


def _per_point_reached_problems(
    code: str, content: dict, sections: dict[str, str], errors: list[str]
) -> None:
    """逐 `point_id` 对账：块是「真值」，它指名的考核点必须在章页上**有自己那一节**（F-QC2-1）。

    口径 = 锚点小节**内**的 H4 小节：`explain` 块要求 `### 考点精讲：<point_id>` 小节内出现
    可见的 `#### 要点梳理` **且其正文非空**；`memorize` 块同理要求 `#### 记忆辅助`。因此
    「删掉某点的整节、再在别处补一条同名标题」不再能蒙混过关（全局计数不变、相邻小节的同名 H4 也不会
    被误算进来，但该 `point_id` 的锚点/小节确实没了），错误文案**点名缺失的 `point_id`**，
    与 `drill` 的锚点对账（`practice.md`）同一形态。
    F-QC3-1 / Y2 的三种剩余规避也在此闭合（判定一律走 `_evidence_lines()`：剥注释 + 跳过围栏）：
    - (a) **标题在、正文被清空** → 空壳不算到达（`_is_empty_body`；AI 块脚注不算正文）；
    - (c) **标题被塞进代码围栏** → 围栏内的行不是渲染证据，等价于「标题不存在」；
    - Y2 **标题被 HTML 注释包住**（`<!--` 开在标题行之前）→ 该节对读者不可见，同样等价于「标题不存在」；
      与之对称的「正文被注释、标题在注释外」本就被 `_is_empty_body()` 判为空壳 —— 两种形状现在同形。
    调用顺序上逐点在前、全局计数在后：计数不匹配只是次级「页级界限」，块级真相优先（否则「丢一节 + 别处补一条」
    只会报成模糊的计数不符）。有块却无锚点的考核点算失败；没有块的考核点不在此列（无块即无诉求）。
    """
    for kind, heading in (
        ("explain", EXPLAIN_SUMMARY_HEADING),
        ("memorize", MEMORIZE_AID_HEADING),
    ):
        block_points = [
            str(block["point_id"])
            for block in content.get("blocks") or []
            if block.get("kind") == kind and block.get("point_id")
        ]
        missing_anchor: list[str] = []
        missing_heading: list[str] = []
        empty_body: list[str] = []
        for point_id in block_points:
            section = sections.get(point_id)
            if section is None:
                missing_anchor.append(point_id)
                continue
            body = _heading_body(section, heading)
            if body is None:
                missing_heading.append(point_id)
            elif _is_empty_body(body):
                empty_body.append(point_id)
        if missing_anchor:
            errors.append(
                f"course {code}: 章页缺少 {len(missing_anchor)} 个考核点的 `### 考点精讲：<point_id>` 锚点"
                f"（首个 {missing_anchor[0]}）—— 该 point_id 的 {kind} 块未渲染到章页"
            )
        if missing_heading:
            errors.append(
                f"course {code}: 章页有 {len(missing_heading)} 个考核点的锚点小节内缺少 `{heading}`"
                f"（首个 {missing_heading[0]}）—— 该 point_id 的 {kind} 块未渲染到章页"
            )
        if empty_body:
            errors.append(
                f"course {code}: 章页有 {len(empty_body)} 个考核点的 `{heading}` 小节正文为空"
                f"（首个 {empty_body[0]}）—— 该 point_id 的 {kind} 块未渲染到章页"
            )


def _page_reached_problems(
    code: str, content: dict, page_text: dict[str, str], markers: dict, errors: list[str]
) -> None:
    """每个 AI 产物块都必须真的落到页面上（QC3-001 / C2-004 / W1 / B2a N-1：闸门只看页面装饰，看不出整层丢失）。

    对账口径按 kind —— **4 个 block kind + 2 个课程级顶层产物，一个都不能漏**：
    - `explain` → 逐 `point_id`：该点在章页上有 `### 考点精讲：<point_id>` 锚点，且锚点小节内有
      `#### 要点梳理` **且正文非空**；**再**以可见行里的全局标题计数**精确相等**作次级页级界限；
    - `memorize` → 同样的逐点锚点口径（`#### 记忆辅助`）+ 同样的次级计数；
    - `drill` → `practice.md` 的 `###` 小节数 + 逐 `point_id` 的练习小节锚点；
    - `stage_plan[]`（恰 5 条）→ `plan.md` 逐阶段名 + `done_when`；
    - `exam_strategy`（课程级块）→ `plan.md` 的 `## 应试策略` 区块内的 `text_md`；
    - `review_schedule` → `review.md` 的三档排程或命名缺口。

    `exam_strategy` 这一条是 W1：它曾经既不在渲染器里、也不在本函数里，于是删掉整块
    （1180 → 1179）两层闸门全绿。`explain` / `memorize` 是 B2a 的 N-1：两者有写入者（章页）却无对账，
    于是删掉章页的 `#### 要点梳理` + `#### 记忆辅助`、乃至删掉整个 `knowledge/` 目录都仍然全绿。
    主判据因此是**逐点锚点**（`_per_point_reached_problems`）：块是「真值」，每个有块的 `point_id` 都要在
    章页上存在自己的 `### 考点精讲：<point_id>` 小节，且该小节内有对应 H4 标题、且其正文非空；错误文案
    点名缺失的 `point_id`，与 `drill` 的锚点对账同一形态。注意 F-QC2-1：**精确计数并不能防住 padding** ——
    删掉 `15043-ch01-s1-p1` 的 `#### 要点梳理` 小节、再在别的章页补一条同名标题，255 == 255 依旧全绿，
    因为全局计数只回答「渲染了几个」，回答不了「渲染了哪几个」；`drill` 那样的下界（`rendered < len(drills)`）
    同理。所以计数降级为**次级页级界限**（总量兜底：整页/整目录级丢失、以及多写一条标题），
    逐点锚点才是主判据。`blocks[]` 里没有写入者的 kind 由
    `validate_content_doc()`（`BLOCK_KINDS` 枚举）拦下，所以这里只需覆盖「有写入者的 kind」。
    """
    chapters_text, sections = _chapter_page_sections(page_text, _chapter_page_patterns(markers))

    # 主判据：逐考核点（F-QC2-1 —— 能点名是哪个 point_id 丢了）。
    _per_point_reached_problems(code, content, sections, errors)

    # 次级界限：可见行里的全局小节计数精确相等（页级总量兜底，message 措辞保持稳定以兼容既有测试）。
    for kind, heading in (
        ("explain", EXPLAIN_SUMMARY_HEADING),
        ("memorize", MEMORIZE_AID_HEADING),
    ):
        expected = len([b for b in content.get("blocks") or [] if b.get("kind") == kind])
        rendered = _count_visible_headings(chapters_text, heading)
        if rendered != expected:
            errors.append(
                f"course {code}: 章页的 `{heading}` 小节数 {rendered} 与 content.json 的 {kind} 块数 {expected} "
                f"不一致（{kind} 块未渲染到章页）"
            )

    practice = page_text.get("practice.md", "")
    drills = [block for block in content.get("blocks") or [] if block.get("kind") == "drill"]
    if drills:
        rendered = len(re.findall(r"(?m)^### ", practice))
        if rendered < len(drills):
            errors.append(
                f"course {code}: practice.md 的 AI 练习小节数 {rendered} 少于 content.json 的 drill 块数 {len(drills)}"
                "（AI 块未渲染到页面）"
            )
        missing_ids = [b["point_id"] for b in drills if b.get("point_id") and b["point_id"] not in practice]
        if missing_ids:
            errors.append(
                f"course {code}: practice.md 缺少 {len(missing_ids)} 个 drill 的考核点锚点（首个 {missing_ids[0]}）"
            )
        if not re.search(r"(?m)^<details>|^<details ", practice):
            errors.append(f"course {code}: practice.md 的 AI 练习答案未折叠（缺 <details>）")

    plan = page_text.get("plan.md", "")
    stages = content.get("stage_plan") or []
    rendered_stages = re.findall(r"(?m)^### 阶段：(.+?)\s*$", plan)
    expected_names = [str(stage.get("stage")) for stage in stages if stage.get("stage")]
    if rendered_stages != expected_names:
        errors.append(
            f"course {code}: plan.md 的 `### 阶段：` 小节 {rendered_stages} 与 stage_plan 的五阶段 {expected_names} 不一致"
            "（stage_plan 未渲染到页面）"
        )
    for stage in stages:
        name = stage.get("stage")
        done_when = stage.get("done_when")
        if done_when and done_when not in plan:
            errors.append(f"course {code}: plan.md 缺少阶段「{name}」的完成标准（done_when 未渲染）")
        for key, label in (("goal", "目标"), ("inputs", "输入"), ("how", "做法"), ("outputs", "输出物")):
            values = [str(item) for item in stage.get(key) or []] if isinstance(stage.get(key), list) else [stage.get(key)]
            if any(value and value not in plan for value in values):
                errors.append(f"course {code}: plan.md 缺少阶段「{name}」的{label}（stage_plan 未完整渲染）")

    # 课程级 `exam_strategy`（W1）：必须落在 `plan.md` 的 `## 应试策略` 区块**之内**，
    # 而不是碰巧出现在页面别处（与 review 的命名缺口同一口径）。
    strategies = [block for block in content.get("blocks") or [] if block.get("kind") == "exam_strategy"]
    for block in strategies:
        block_id = block.get("block_id")
        section = re.search(r"(?ms)^## 应试策略\s*$(.*?)(?=^## |\Z)", plan)
        if section is None:
            errors.append(
                f"course {code}: plan.md 缺少 `## 应试策略` 区块（AI 课程级块 {block_id} 未渲染到页面）"
            )
            continue
        text = str(block.get("text_md") or "").strip()
        if text and text not in section.group(1):
            errors.append(
                f"course {code}: plan.md 的 `## 应试策略` 区块缺少 {block_id} 的 text_md（exam_strategy 未渲染）"
            )

    review = page_text.get("review.md", "")
    schedule = content.get("review_schedule") or {}
    if schedule.get("status") == "named_gap":
        # 缺口必须**在命名缺口区块内**呈现，而不是碰巧出现在页面别处
        block = re.search(r"(?ms)^## 命名缺口\s*$(.*?)(?=^## |\Z)", review)
        if block is None:
            errors.append(f"course {code}: review.md 缺少 `## 命名缺口` 区块（排程缺口未渲染）")
        else:
            for key, label in (("gap_impact", "缺口影响"), ("next_evidence", "下一份需要的证据")):
                value = schedule.get(key)
                if value and value not in block.group(1):
                    errors.append(
                        f"course {code}: review.md 的命名缺口区块缺少 {label}（{key} 未渲染）"
                    )
    else:
        for plan_entry in schedule.get("plans") or []:
            tier = plan_entry.get("tier")
            if tier and f"（{tier}）" not in review:
                errors.append(f"course {code}: review.md 缺少排程档位 {tier}（review_schedule 未渲染）")


def _rendered_ai_pages(rendered_dir: Path, markers: dict) -> list[str]:
    """`rendered_dir` 下带 **AI 横幅**的 AI 分类页面（相对路径排序）—— 「这页是 AI 生成物」的判据。

    判据取 schema 声明的两个标记（`ai_pages` 分类 + `ai_banner` 横幅，`_page_problems()` 用的同一对），
    不猜「看起来像不像 AI 写的」：横幅是渲染器写进 AI 页的契约字面量，非 AI 页带横幅本身就被
    `_page_problems()` 判错。因此这一层不会把「有页面但没有 AI 内容」的课程误判成 AI 产物。
    """
    pages: list[str] = []
    if not rendered_dir.is_dir():
        return pages
    for md_file in sorted(rendered_dir.rglob("*.md")):
        rel_md = md_file.relative_to(rendered_dir).as_posix()
        if not course_pages_contract.matches_page(rel_md, markers["ai_pages"]):
            continue
        if markers["ai_banner"] in md_file.read_text(encoding="utf-8"):
            pages.append(rel_md)
    return pages


def _rendered_course_dirs(root: Path) -> dict[str, Path]:
    """产物侧的作用域键：`content/jiangsu/courses/<code>/` 目录（课码 → 目录）。

    与源侧同样只取目录（`content/jiangsu/courses/` 下还有一个 `index.md` 文件，天然被排除）。
    **课码须匹配 `^[0-9]{5}$`**（R21 / Y1-a）：`build` 的暂存目录名在 `mkdtemp` → `os.replace` 窗口内
    被 SIGKILL 时会残留（如 `.15043.promote.abc123`），这类隐藏兄弟目录不是课程，若不设边界就会进
    作用域并命中「AI 产物在、真值源不在」的反向判定、报出与内容无关的噪声错误。判据复用
    `course_pages_contract.CODE`（同一语义：目录名即课码；schema 的 `directory_pattern` 亦为此式），
    不在此另写字面量。真实形态（课码目录在、源侧缺失）不受影响 —— 其课码本就匹配该式。
    """
    courses_dir = root / "content" / "jiangsu" / "courses"
    if not courses_dir.is_dir():
        return {}
    return {
        entry.name: entry
        for entry in sorted(courses_dir.iterdir())
        if entry.is_dir() and course_pages_contract.CODE.fullmatch(entry.name)
    }


def _missing_source_problem(root: Path, code: str, rendered_dir: Path, markers: dict) -> str | None:
    """「AI 产物在、真值源不在」的失败关闭报文；无 AI 产物时返回 `None`（该课只是没有 AI 层）。

    报错文案点名缺失的源路径：源目录整份不存在时报目录（Y1 的形态），只缺 `content.json` 时报该文件
    （X2 的形态）。两种形态共用同一条判定，因此不存在「删得更彻底反而更安全」的阶梯。
    """
    orphans = _rendered_ai_pages(rendered_dir, markers)
    if not orphans:
        return None
    source_dir = root / "sources" / "jiangsu" / "courses" / code
    missing = (
        f"{source_dir.relative_to(root).as_posix()}/content.json"
        if source_dir.is_dir()
        else f"{source_dir.relative_to(root).as_posix()}/（整个源目录缺失）"
    )
    rel_rendered = (
        rendered_dir.relative_to(root).as_posix() if rendered_dir.is_relative_to(root) else rendered_dir.as_posix()
    )
    return (
        f"course {code}: 渲染页 {rel_rendered} 存在 {len(orphans)} 个 AI 生成页面"
        f"（首个 {orphans[0]}）但真值源缺失: {missing}"
        "（AI 备考层无来源可校验，禁止静默跳过）"
    )


def _answer_verdict(n: int, top_count: int, limit_percent: int) -> str:
    """单维度的三元判定：`ok` / `biased` / `insufficient-sample`（Clarify C2）。

    样本不足时**跳过占比判定**（不产生 `biased`），但调用方必须把 `insufficient-sample` 送进报告通道 ——
    「跳过判定」不等于「静默通过」，这正是本守卫不走 `errors` 也要发声的那一半（§ Data contracts 1）。
    """
    if n < MIN_ANSWER_SAMPLES:
        return "insufficient-sample"
    return "biased" if top_count * 100 > limit_percent * n else "ok"


def _answer_dimension(counts: dict[str, int], limit_percent: int) -> dict:
    """一组答案计数的分布摘要（`n` / `counts` / 众数 / 占比 / `verdict`）—— 报告字段的唯一来源。

    众数并列时按答案标签取最大者（`A`–`D` / `错误`），使同一份 `content.json` 的报告**逐字节可复现**；
    占比只在 `n > 0` 时存在，`n == 0` 时显式留 `None`（报告层渲染成 `n/a`，不是 `0%`）。
    """
    n = sum(counts.values())
    top_label, top_count = max(counts.items(), key=lambda item: (item[1], item[0]))
    return {
        "n": n,
        "counts": counts,
        "top": top_label if n else None,
        "top_count": top_count if n else 0,
        "max_share": (top_count / n) if n else None,
        "limit_percent": limit_percent,
        "verdict": _answer_verdict(n, top_count, limit_percent),
    }


def answer_distribution(content: dict) -> dict:
    """`content.json` 里 drill 块的答案分布（**纯函数**：无 I/O、无副作用、可直接被单测变异）。

    分桶按 `question_type` 的家族子串（见 `SINGLE_CHOICE_TYPE_MARKER`），提取按两条不锚行尾的正则。
    **不可解析即失败关闭**：落在两族内却提不出答案的块进 `unparseable`（调用方据此报错），
    绝不静默计入 `n=0` —— 那会把「解析器覆盖不到」伪装成「无偏置」，即 compass B4-R5 的漏检形态。
    判断题真值只存在于 `answer_md` 文本中（`generate_content.py:300-304` 的 drill 只有
    `question_type` / `answer_md` / `source_kind`），没有独立字段可回退，故这一条对它尤其关键。

    已知边界（有意为之，不是缺口）：家族子串命中但答案形如多选（`AB`，含 `A、B` / `A,B` / `A，B` / `A B`
    等分隔符写法）的题型一律判为**不可解析**，而不是把首字母当成单选的样本 —— 失败关闭优先于凑出一份错的
    分布（QC-2：`\b` 曾让分隔符写法静默计成首字母，与 `AB` 的失败关闭方向相反，同一批答案两种行为；
    改写为「字母之后不得再接答案字母」的负向先行断言后，五种多选写法同形）。

    返回的 `families` 是**已分桶 / 未分桶**的块数对照（qc1 F-3 / QC-3）：两族命中数都为 0 而本课确有 drill
    ⇒ 整门课的答案都没进入分布判定，调用方据此打印 `family-not-matched` 覆盖标记（报告通道，非 `errors`）。
    判据取**家族命中数**而非答案计数：一个家族内全是不可解析块的课，族是命中的（缺口由 `unparseable` 发声），
    不得再被记成「题型没匹配上」。
    """
    single = {letter: 0 for letter in "ABCD"}
    judgement = {"正确": 0, "错误": 0}
    unparseable: list[str] = []
    families = {"single_choice": 0, "judgement": 0, "drills": 0}
    for block in content.get("blocks") or []:
        if block.get("kind") != "drill":
            continue
        families["drills"] += 1
        question_type = str(block.get("question_type") or "")
        # 判定只看**首行**：三种排布与四种真值排布的差别都在首行内，解释可能在后续行。
        first_line = str(block.get("answer_md") or "").split("\n", 1)[0]
        where = str(block.get("point_id") or block.get("block_id") or "?")
        if SINGLE_CHOICE_TYPE_MARKER in question_type:
            families["single_choice"] += 1
            match = ANSWER_SINGLE_CHOICE_RE.match(first_line)
            if match is None:
                unparseable.append(f"{where}（{question_type}）")
                continue
            single[match.group(1)] += 1
        elif JUDGEMENT_TYPE_MARKER in question_type:
            families["judgement"] += 1
            match = ANSWER_JUDGEMENT_RE.match(first_line)
            if match is None:
                unparseable.append(f"{where}（{question_type}）")
                continue
            judgement[match.group(1)] += 1
    return {
        "single_choice": _answer_dimension(single, MAX_SINGLE_CHOICE_SHARE_PERCENT),
        "judgement": _answer_dimension(judgement, MAX_JUDGEMENT_SHARE_PERCENT),
        "unparseable": unparseable,
        "families": families,
    }


def content_tracking_state(root: Path, content_path: Path) -> bool | None:
    """该课 `content.json` 的 git 跟踪状态：`True` 已跟踪（既有课）/ `False` 未跟踪（新课）/ `None` 无法判定。

    作用域信号的权威在**产物侧的 git 索引**，不在产物自己的声明里（Clarify C3 / § Data contracts 1）：
    硬编码课码清单与 mtime/`generated_at` 都是被明确否掉的旧缺陷类。调用方对 `None` 取失败关闭方向
    （按新课处理）—— 见 `_answer_distribution_problems()`。

    退出码语义（实测，非猜测）：`0` = 路径在索引中；`1` = `pathspec ... did not match any file(s)
    known to git`（未跟踪）；`128` = `fatal: not a git repository ...`（不是工作树，无从判定）。
    `git` 可执行文件本身缺失（`OSError`）同归「无法判定」。把「非 1 的非零码」整体当无法判定，
    而不是只认 128：git 的其他致命码（索引损坏、权限）同样不该被读成「这门课是新的」。

    探针**有界**（QC-4 / qc3 F-2）：`subprocess.run(..., timeout=GIT_TRACKING_PROBE_TIMEOUT_SECONDS)`
    挂起即降级。捕获必须放宽到 `(OSError, subprocess.SubprocessError)` —— `TimeoutExpired` 继承
    `SubprocessError` 而**不是** `OSError`，只补 `timeout=` 会让超时异常穿透 `run_ai_content_gate()`，
    与这里承诺的「`None` = 无法判定」相反（闸门整层崩掉，而不是按新课处理）。
    """
    try:
        rel_path = content_path.relative_to(root).as_posix()
    except ValueError:
        return None
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TRACKING_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode == 0:
        return True
    return False if probe.returncode == 1 else None


def _counts_text(counts: dict[str, int]) -> str:
    """`{'A': 105, ...}` → `A105/B70/...`（固定标签顺序，报告行可逐字比对）。"""
    return "/".join(f"{label}{count}" for label, count in counts.items())


def _max_share_text(dimension: dict) -> str:
    """占比文本：`n == 0` 时为 `n/a`（没有样本就没有占比，不得渲染成 `0.0%`）。"""
    share = dimension["max_share"]
    return "n/a" if share is None else f"{share:.1%}"


def _answer_distribution_problems(code: str, dist: dict, tracked: bool | None, errors: list[str]) -> None:
    """报告一门课的答案分布，并只在**新课**（或判定失败）时把偏置与解析缺口失败关闭（Clarify C3 / D5）。

    报告通道契约（§ Data contracts 1）：分布取证**不是** `content.json` 的新字段，而是 stdout 上的
    独立输出通道 —— `verdict ∈ {ok, insufficient-sample}` **不得**进 `errors`（否则既有小样本课变红，
    与 D5 冲突），但**必须**打印且含固定字面量 `insufficient-sample`。两个方向都要能断言，
    才排除「既不报错也不报告」的静默通过。

    `enforced` 三态 → 两个方向：`tracked is True`（既有课）只报告；`False`（新课）与 `None`
    （无法判定）都失败关闭 —— 判定失败的降级方向是**按新课处理**，绝不静默降级为「只报告」。

    **`unparseable` 与 `biased` 受同一个 `enforced` 约束**（QC-1 裁定 = qc1 F-1 + qc2 F-1，双席独立发现）：
    已跟踪的既有课即使出现解析覆盖缺口也**只报告** —— 缺口仍逐课打印（条数 + 首个块的 id，绝不静默），
    未跟踪 / 无法判定才失败关闭。此前该分支无条件 `errors.append`，与 C3/D5「既有课只报告」冲突：
    一条解析覆盖面缺口就足以让既有课永久报红，正是「守卫变成噪声」的旧失败形态。§ Data contracts 2 的
    「不可解析即失败关闭」与该作用域条款只在**已跟踪课**上相撞，按 PM 裁定以 D5（用户裁定）为准；
    「新课」方向不受影响，故守卫不因此变盲（plan QC 合并报告 § PM adjudications 1）。

    覆盖缺口另有**独立标记**（qc1 F-3 / QC-3）：有 drill 而两族题型标记都没命中时打印
    `coverage=family-not-matched` —— 否则整门课脱出分布判定只会呈现为一行 `insufficient-sample`，
    与「样本确实不足」无法区分（该 verdict 按契约永不进 `errors`）。标记只走报告通道。
    """
    single, judgement = dist["single_choice"], dist["judgement"]
    unparseable = dist["unparseable"]
    families = dist["families"]
    if tracked is True:
        scope = "enforced=false（git 已跟踪 content.json：既有课，只报告）"
    elif tracked is False:
        scope = "enforced=true（content.json 未跟踪：新生成课，失败关闭）"
    else:
        scope = "enforced=true（无法判定 git 跟踪状态，按新课处理）"
    enforced = tracked is not True

    biased = [dim for dim in (single, judgement) if dim["verdict"] == "biased"]
    family_not_matched = bool(families["drills"]) and not families["single_choice"] and not families["judgement"]

    # 解析覆盖缺口与覆盖标记都落在**报告行**上：条数与首个块的 id 一律可见（`unparseable(n=…)`），
    # 标记与「样本不足」区分开。报告行始终带 `unparseable(n=…)` 字段，两个方向都可逐字断言。
    coverage = [
        f"unparseable(n={len(unparseable)}" + (f" first={unparseable[0]}" if unparseable else "") + ")"
    ]
    if family_not_matched:
        coverage.append(f"coverage=family-not-matched drills={families['drills']}")

    notes: list[str] = []
    if biased and not enforced:
        notes.append(f"历史偏置由 {ANSWER_BIAS_RESIDUALS} 跟踪（本轮不回修）")
    if unparseable and not enforced:
        notes.append("既有课的解析覆盖缺口只报告、不阻断闸门（QC-1 作用域裁定）")

    print(
        f"[ai-content 答案分布] course={code}"
        f" single(n={single['n']} counts={_counts_text(single['counts'])}"
        f" max_share={_max_share_text(single)} verdict={single['verdict']})"
        f" judgement(n={judgement['n']} counts={_counts_text(judgement['counts'])}"
        f" max_share={_max_share_text(judgement)} verdict={judgement['verdict']})"
        f" {' '.join(coverage)}"
        f" {scope}" + "".join(f" {note}" for note in notes)
    )

    # 解析覆盖缺口（QC-1）：与 `biased` **同一**作用域口径 —— 既有课只报告（上面的报告行已点名条数与首个块），
    # 新课 / 判定失败才失败关闭。不可解析不得静默记为「无偏置」（§ Data contracts 2 的新课方向）。
    if unparseable and enforced:
        errors.append(
            f"course {code} 答案分布: {len(unparseable)} 个 drill 的 answer_md 无法解析出答案"
            f"（首个 {unparseable[0]}）—— 不可解析不得静默记为「无偏置」"
        )

    for label, dimension in (("单选", single), ("判断题", judgement)):
        if dimension["verdict"] != "biased" or not enforced:
            continue
        errors.append(
            f"course {code} 答案分布: {label} verdict=biased"
            f"（{dimension['top']} {dimension['top_count']}/{dimension['n']}"
            f" = {dimension['max_share']:.1%} > {dimension['limit_percent']}%）"
            "—— 新生成课的答案键必须打散（禁止静默通过）"
        )


def run_ai_content_gate(
    root: Path,
    *,
    rendered_course_dir: Path | None = None,
    course_code: str | None = None,
) -> list[str]:
    """校验 AI 备考层产物（默认校仓内页面；给定 `rendered_course_dir` 时校该目录，供暂存区复用）。

    作用域规则 = **源侧 ∪ 产物侧**的课码并集（F-QC3-2 / X2 / Y1）：源侧是
    `sources/jiangsu/courses/<code>/`，产物侧是 `content/jiangsu/courses/<code>/`。两者取并集而不是
    以源侧为准，是因为**作用域键不得自我关闭**：只要渲染页上**确实带着 AI 横幅**（= AI 产物已在仓内）
    而真值源不在，那正是「真值源缺失、AI 页面照样发布」的形态，必须**报错**而不是被作用域规则静默跳过 ——
    否则删掉 `content.json`（X2）乃至删掉整个源目录（Y1）都能让 7 层闸门全绿、16 个 AI 页面照常部署。
    反向判定只认 schema 声明的 AI 横幅，因此**没有任何 AI 页面的课程仍然完全静默**（其余 16 门课既无
    `content.json` 也无横幅 → 0 错误），作用域规则对它们的原意不变。

    `rendered_course_dir` 给定时为暂存区形态（只校一门课）：作用域键由 `course_code` 收窄，
    此路径下产物侧目录可能尚不存在，故并集退化为源侧单键。
    """
    errors: list[str] = []
    courses_dir = root / "sources" / "jiangsu" / "courses"
    if not courses_dir.is_dir() and not (root / "content" / "jiangsu" / "courses").is_dir():
        return errors

    markers = course_pages_contract.generated_page_markers(course_pages_contract.load_schema(root))

    source_dirs = (
        {entry.name: entry for entry in sorted(courses_dir.iterdir()) if entry.is_dir()}
        if courses_dir.is_dir()
        else {}
    )
    rendered_dirs = {} if rendered_course_dir is not None else _rendered_course_dirs(root)

    for code in sorted(set(source_dirs) | set(rendered_dirs)):
        if course_code is not None and code != course_code:
            continue

        course_dir = source_dirs.get(code)
        rendered_dir = rendered_course_dir if rendered_course_dir is not None else (
            root / "content" / "jiangsu" / "courses" / code
        )

        content_path = course_dir / "content.json" if course_dir is not None else None
        if content_path is None or not content_path.is_file():
            # X2 / Y1 反向判定：AI 产物在页面上，真值源却不在 —— 作用域键不能替自己关闸。
            problem = _missing_source_problem(root, code, rendered_dir, markers)
            if problem is not None:
                errors.append(problem)
            continue

        rel_content = content_path.relative_to(root).as_posix()

        try:
            content = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{rel_content}: JSON decode error: {exc}")
            continue

        model_path = course_dir / "knowledge-model.json"
        if not model_path.is_file():
            errors.append(f"course {code}: content.json exists but knowledge-model.json missing")
            continue

        try:
            model = json.loads(model_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"course {code} knowledge-model.json: JSON decode error: {exc}")
            continue

        # 1. `stage_plan[]` 恰 5 条（错误文案需点名「5」）
        stage_plan = content.get("stage_plan")
        if not isinstance(stage_plan, list) or len(stage_plan) != 5:
            n_stages = len(stage_plan) if isinstance(stage_plan, list) else "non-list"
            errors.append(f"course {code} stage_plan: 必须恰为 5 个阶段 (found {n_stages})")

        # 2. 标注四件套 / 块归属 / drill 字段
        for p in validate_content_doc(content, model):
            errors.append(f"course {code}: {p}")

        # 3. 8-gram 与考纲语料重合率（语料 = evidence.json 指针 + sha256，缺失即失败关闭）
        syl_text = _syllabus_text(root, code, rel_content, errors)
        if syl_text:
            for p in plagiarism_violations(content, syl_text, threshold=0.20):
                errors.append(f"course {code} 8-gram overlap: {p}")

        # 4. 答案分布（Clarify C2/C3）：确定性判据 + 独立报告通道；作用域信号 = 该课 content.json 的
        #    git 跟踪状态。放在页面校验**之前**，好让「页面缺失」的课也照样拿到分布报告（非静默）。
        _answer_distribution_problems(
            code,
            answer_distribution(content),
            content_tracking_state(root, content_path),
            errors,
        )

        # 5. 渲染页标记 + 文本边界 + AI 块是否真的落到页面
        if not rendered_dir.is_dir():
            # 有 `content.json` 却没有渲染页目录 = 「AI 块从未被渲染」的极端形态（B2a N-1）：
            # 旧实现在这里静默 `continue`，于是删掉整个课程页目录也全绿。
            errors.append(
                f"course {code}: 存在 {rel_content} 但渲染页目录不存在: {rendered_dir}"
                "（AI 备考层未渲染到页面）"
            )
            continue
        page_text: dict[str, str] = {}
        for md_file in sorted(rendered_dir.rglob("*.md")):
            rel_md = md_file.relative_to(rendered_dir).as_posix()
            text = md_file.read_text(encoding="utf-8")
            page_text[rel_md] = text
            # 页面分类按**相对路径**判定，报错文案才带课程前缀（前缀会破坏 glob 匹配）
            _page_problems(rel_md, text, markers, errors, label=f"course {code} {rel_md}")
        _page_reached_problems(code, content, page_text, markers, errors)

    return errors
