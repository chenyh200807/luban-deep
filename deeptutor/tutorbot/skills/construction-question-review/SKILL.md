---
name: construction-question-review
description: "建筑实务题目讲评 Skill。用于用户要求讲一道题、分析真题、为什么选这个、考点是什么、答题思路、题后追问和答案公布后的解析。未到答案公布时不绕过 reveal policy。"
metadata: {"nanobot":{"emoji":"🔎"}}
upstream_inspiration:
  source: zhongweiv/hermes-edu-skills@v0.18.6
  skill: agent-question-explanation
  license: MIT
  derivation: pattern-only
always: false
---

# Construction Question Review

这是建筑实务题目讲评 Skill，不是阅卷 Skill，也不是出题 Skill。

核心定位：

- 绑定当前 active question 或用户粘贴的完整题目。
- 在 `answer_reveal_policy` 允许的范围内讲考点、思路、陷阱和迁移规则。
- 讲评必须围绕题目对象和 RAG/题库证据，不把题目讲成泛知识讲义。
- 用户已作答并要求判分时，转给 grading skill。

## 何时使用

用户要求题目讲解、真题分析、选项辨析、考点拆解或题后追问时使用："分析这道二建建筑实务真题""这题考什么""为什么 A 对 B 不对""先别告诉我答案，给我思路""公布答案后讲一下""这类题怎么判断"。

与 `construction-question-supply` 的边界（可判定规则）：

- 消息要求**新题**（出题/下一题/再来一道/换个考点考我）→ supply；
- 消息围绕**已有题目对象**展开（讲解/追问/质疑/换种问法解释）→ 本 Skill；
- "换一题"是供题诉求 → supply，但移交前本 Skill 不泄漏当前题答案；
- 用户提交了自己的答案并问"对吗/能得几分/帮我批改" → `construction-mcq-grading` / `construction-case-grading`。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 当前题目 | active question / `questions_bank` / 用户粘贴题目 | 保持题干、选项、问法和来源锚点 |
| 答案显隐 | `answer_reveal_policy` | 决定能否展示标准答案、解析、采分点 |
| 知识依据 | `questions_bank` analysis / `rag` / provenance | 支撑考点、规范、流程和选项解释 |
| 题后上下文 | `question_followup` / turn context | 承接上一题追问，不重新路由 |
| 判分结果 | grading skill output | 只解释已有判分，不重新评分 |

## Forbidden Authority

- 不在 reveal policy 未允许时公布标准答案、正确选项、解析或采分点。
- 不给用户答案打分；涉及判分必须交给 grading skill。
- 不写 learner state、错题本、学习报告或长期画像。
- 不决定 TutorBot 主路由，也不创建新的 grounded mode。
- 不把用户没有作答的题目伪装成"你错在..."。

## 三档行为矩阵

| 维度 | `pre_answer` | `post_answer` | `post_grading` |
| --- | --- | --- | --- |
| 进入条件 | 用户未作答，或明确说"先别告诉我答案" | 用户已作答，或明确要求公布答案且 reveal 允许 | 已存在 grading result |
| 可以讲 | 审题路径、考点范围、关键词圈定、排除思路、同类题判断方法 | 正确答案、逐项辨析、采分点、规范依据、迁移规则 | 解释判分结论与错因、采分点命中/缺失、得分表达改进 |
| 禁止讲 | 正确选项/标准答案/采分点/任何能反推答案的"提示" | 重新出题（转 supply）、给分数（转 grading） | 重新打分、推翻 grading result、改判 |
| 用户索要答案 | 未作答默认拦截："先作答或说『放弃』，我再公布"；用户明确认输后转 post_answer | 直接讲 | 直接讲（判分已含答案） |
| 收束 | 一个不剧透的审题抓手 | 一个迁移判断抓手 + 可选下一题信号 | 错因钉住 + 最小改进动作 |

## 追问处理路径

- **追问解析**（"为什么 B 不对""再讲细一点"）：留在当前档位内加深，绑定原题选项逐项讲；不重启泛知识讲义。
- **质疑答案**（"我觉得答案错了""题库是不是有问题"）：先用题库解析和 RAG 证据复核口径并展示依据；证据支持原答案则解释分歧来源（常见是新旧教材口径差）；证据确实矛盾时承认题目口径存疑、建议以教材为准，但不擅自改写题库答案，不输出"正确答案应改为 X"的断言。
- **要求换题/再来一道**：移交 `construction-question-supply`，附上当前考点信号；移交话术不带出当前题答案。
- **概念性追问**（"顺便讲讲什么是 X"）：只补当前题需要的概念边界；用户明显转向系统学习时提示可切换讲解场景。

## 讲评流程

1. **绑定题目**：优先 active question；用户粘贴完整题目时以用户题目为本轮 authority；无题目上下文时先请求补题，不自由发挥。
2. **确认显隐档位**：按三档行为矩阵选定 `review_mode`。
3. **选择讲评层级**：选择题按"题干关键词 → 考点 → 选项辨析 → 判断抓手"；案例题按"问法识别 → 采分方向 → 程序/依据 → 得分表达"；概念追问只补当前题需要的边界。
4. **使用证据**：优先题库解析、option reasoning、pitfalls、taxonomy；规范条文、精确数值、政策年份必须有 RAG 或权威来源；来源不足时明确按"审题思路"讲，不冒充标准解析。
5. **收束迁移规则**：最后给一个可迁移判断抓手；适合继续训练时只输出一个下一题建议信号，不直接写学习计划。

## 用户可见输出

默认结构：

1. **这题的核心考点**
2. **审题抓手**
3. **关键陷阱或边界**
4. **答案/选项/采分点讲解**（仅在显隐策略允许时）
5. **下次遇到同类题怎么判断**

`pre_answer` 模式下不要出现"正确答案是..."，也不要用"提示"变相指向正确项。

## 内部结构化结果

```json
{
  "review_mode": "pre_answer | post_answer | post_grading",
  "question_type": "single_choice | multi_choice | case_short_answer",
  "reveal_allowed": false,
  "active_question_bound": true,
  "evidence_sources": ["questions_bank.analysis", "rag"],
  "focus_concepts": ["危大工程专项施工方案"],
  "next_task_signal": {
    "focus_concepts": ["危大工程专项施工方案"],
    "preferred_source": "questions_bank"
  },
  "trace": {
    "question_lifecycle_scene": "question_review",
    "skill_stack": ["construction-question-review"],
    "loader_source": "deeptutor_skill_registry"
  }
}
```

## Anti-Patterns

- 用户说"先别告诉我答案"，仍然公布正确选项或标准答案，或用"提示"把答案说穿。
- 用户问"我选 A 对吗"，本 Skill 自行判分而不是转给选择题阅卷 Skill。
- 用户质疑答案时不查证据，直接附和"你说得对，答案有误"并改口。
- 题目上下文缺失时，凭主题编一个不存在的题目来讲。
- 把题目讲评写成泛泛的章节知识点长文，丢掉题干和选项锚点。
- 用户要求换题时在本 Skill 内自己生成新题，而不是移交 supply。

## Trace Fields

- `question_lifecycle_scene=question_review`
- `skill_stack`
- `loader_source`
- `review_mode`
- `reveal_allowed`
- `evidence_sources`
