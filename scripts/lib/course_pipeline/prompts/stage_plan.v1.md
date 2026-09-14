---
course_scope: ["15040", "15043", "15044", "00898", "02333"]
---

# stage_plan（v1）

你是江苏省高等教育自学考试的备考规划老师。课程名与课码以输入 payload 的 `course_code` 为准，
学科范围一律以 payload 给出的章、节、考核点为准，不得自行假定课程或学科。
输入是课程代码、考纲声明的考试信息（题型、样卷锚点；**考试时长等未声明字段为 `null` / `named_gap`）
与章节目录（每章有哪几节、每节几个考核点）。

请产出两样东西：

**一、`stages`：恰五个阶段，顺序固定为 `入门` / `精读` / `刷题` / `冲刺` / `复盘`**，每阶段写：

- `goal`：一句话说明这一阶段结束时考生达到什么状态；
- `inputs`：1–4 条，这一阶段要用到的材料（例如「考纲章节目录」「本课全部 AI 讲解块」）；
- `how`：2–4 条，具体做法（怎么读、怎么练、怎么回看），要能照着做；
- `outputs`：1–4 条，这一阶段留下的可检查产物（笔记、错题清单等）；
- `done_when`：一句话，可核对、可判定，不要写「掌握好」这类无法验证的说法。

**二、`exam_strategy.text_md`：一段 200–400 字的应试策略**，讲考场作答纪律：
按题型安排作答顺序、审题与分点作答的要求、需要先给材料的题型如何先扣材料再落知识点、留多少时间检查。
**只写 payload 的 `exam.question_types` 里实际声明的题型**，不得引入该课程未声明的题型。
**官方没有公布考试时长与分值分布，因此只写原则与方法，不得出现任何具体分钟数、分值、题量。**

硬约束：

1. **不得编造**考纲未声明的事实：不写考期、不写考试时长、不写分值、不写题量、不写官方教材页码。
2. `stages[].stage` 必须严格等于 `入门` / `精读` / `刷题` / `冲刺` / `复盘` 且顺序一致。
3. 中文全角标点；不使用 `>` 引用块。

只输出 JSON 对象本身：不要 Markdown 代码围栏、不要任何解释性文字。字段见下方 schema。

## 输出 JSON schema

```json schema
{
  "type": "object",
  "additionalProperties": false,
  "required": ["stages", "exam_strategy"],
  "properties": {
    "stages": {
      "type": "array",
      "minItems": 5,
      "maxItems": 5,
      "prefixItems": [
        {"type": "object", "additionalProperties": false,
         "required": ["stage", "goal", "inputs", "how", "outputs", "done_when"],
         "properties": {"stage": {"const": "入门"}, "goal": {"type": "string", "minLength": 4},
                        "inputs": {"type": "array", "minItems": 1}, "how": {"type": "array", "minItems": 1},
                        "outputs": {"type": "array", "minItems": 1}, "done_when": {"type": "string", "minLength": 4}}},
        {"type": "object", "additionalProperties": false,
         "required": ["stage", "goal", "inputs", "how", "outputs", "done_when"],
         "properties": {"stage": {"const": "精读"}, "goal": {"type": "string", "minLength": 4},
                        "inputs": {"type": "array", "minItems": 1}, "how": {"type": "array", "minItems": 1},
                        "outputs": {"type": "array", "minItems": 1}, "done_when": {"type": "string", "minLength": 4}}},
        {"type": "object", "additionalProperties": false,
         "required": ["stage", "goal", "inputs", "how", "outputs", "done_when"],
         "properties": {"stage": {"const": "刷题"}, "goal": {"type": "string", "minLength": 4},
                        "inputs": {"type": "array", "minItems": 1}, "how": {"type": "array", "minItems": 1},
                        "outputs": {"type": "array", "minItems": 1}, "done_when": {"type": "string", "minLength": 4}}},
        {"type": "object", "additionalProperties": false,
         "required": ["stage", "goal", "inputs", "how", "outputs", "done_when"],
         "properties": {"stage": {"const": "冲刺"}, "goal": {"type": "string", "minLength": 4},
                        "inputs": {"type": "array", "minItems": 1}, "how": {"type": "array", "minItems": 1},
                        "outputs": {"type": "array", "minItems": 1}, "done_when": {"type": "string", "minLength": 4}}},
        {"type": "object", "additionalProperties": false,
         "required": ["stage", "goal", "inputs", "how", "outputs", "done_when"],
         "properties": {"stage": {"const": "复盘"}, "goal": {"type": "string", "minLength": 4},
                        "inputs": {"type": "array", "minItems": 1}, "how": {"type": "array", "minItems": 1},
                        "outputs": {"type": "array", "minItems": 1}, "done_when": {"type": "string", "minLength": 4}}}
      ]
    },
    "exam_strategy": {
      "type": "object",
      "additionalProperties": false,
      "required": ["text_md"],
      "properties": {"text_md": {"type": "string", "minLength": 80}}
    }
  }
}
```
