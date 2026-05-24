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

用户要求题目讲解、真题分析、选项辨析、考点拆解或题后追问时使用：

- "分析这道二建建筑实务真题"
- "这题考什么"
- "为什么 A 对 B 不对"
- "先别告诉我答案，给我思路"
- "公布答案后讲一下"
- "这类题怎么判断"

若用户提交了自己的答案并问"对吗/能得几分/帮我批改"，使用 `construction-mcq-grading` 或 `construction-case-grading`。

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

## 讲评流程

1. **绑定题目**
   - 优先使用 active question。
   - 用户粘贴完整题目时，以用户题目为本轮 authority。
   - 只有"讲一下这题"但无题目上下文时，先请求补题，不自由发挥。

2. **确认显隐状态**
   - `pre_answer`：用户未作答或明确要求不公布答案，只讲审题路径、考点范围、排除思路。
   - `post_answer`：用户已作答或明确要求公布答案，可讲正确答案、选项理由或采分点。
   - `post_grading`：已有 grading result，只解释判分和错因，不重新打分。

3. **选择讲评层级**
   - 选择题：题干关键词 -> 考点 -> 选项辨析 -> 判断抓手。
   - 案例题：问法识别 -> 采分方向 -> 程序/依据 -> 得分表达。
   - 概念追问：只补当前题需要的概念边界，不展开成整章讲义。

4. **使用证据**
   - 优先用题库解析、option reasoning、pitfalls、taxonomy。
   - 规范条文、精确数值、政策年份必须用 RAG 或权威来源支撑。
   - 来源不足时明确按"审题思路"讲，不冒充标准解析。

5. **收束迁移规则**
   - 最后给一个可迁移判断抓手。
   - 若适合继续训练，只输出一个下一题建议信号，不直接写学习计划。

## 用户可见输出

默认结构：

1. **这题的核心考点**
2. **审题抓手**
3. **关键陷阱或边界**
4. **答案/选项/采分点讲解**（仅在显隐策略允许时）
5. **下次遇到同类题怎么判断**

`pre_answer` 模式下不要出现"正确答案是..."。

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

- 用户说"先别告诉我答案"，仍然公布正确选项或标准答案。
- 用户问"我选 A 对吗"，本 Skill 自行判分而不是转给选择题阅卷 Skill。
- 题目上下文缺失时，凭主题编一个不存在的题目来讲。
- 把题目讲评写成泛泛的章节知识点长文，丢掉题干和选项锚点。

## Trace Fields

- `question_lifecycle_scene=question_review`
- `skill_stack`
- `loader_source`
- `review_mode`
- `reveal_allowed`
- `evidence_sources`
