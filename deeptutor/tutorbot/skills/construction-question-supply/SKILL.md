---
name: construction-question-supply
description: "建筑实务题目供给 Skill。用于一建/二建建筑实务出题、继续练、摸底测试。只发布题面，不公开标准答案或解析，除非用户已作答或显式 reveal。"
metadata: {"nanobot":{"emoji":"📝"}}
always: false
---

# Construction Question Supply

这是建筑实务**题目供给** Skill，不是讲解 Skill、不是阅卷 Skill、不是推荐 Skill。

## 何时使用

学员触发题目生成意图时使用：

- "再出 3 题" / "继续练" / "下一题"
- "先做一次摸底测试" / "出几道选择题练手"
- 首页 / 学情页点击"开始练习"类训练入口
- 题型 hint：单选 / 多选 / 判断 / 案例题 / 综合训练

仅当 ChatOrchestrator 已将本轮 scene 判定为 `practice_generation` 时才加载本 Skill。任何"分析这道真题"、"为什么 B 不对"等场景不在本 Skill 职责范围。

## 单一 Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 公开题面 | `deep_question` 生成的 `QuestionArtifact.stem` / `options` / `case_prompt` | 仅输出可作答的题面 |
| 标准答案 | `QuestionArtifact.correct_answer` / `grading_key` | **服务端持有**，公开输出不得包含 |
| 评分规则 | `QuestionArtifact.rubric` / `grading_key` | 服务端持有，公开输出不得包含 |
| 题目知识依据 | `QuestionArtifact.knowledge_context` / `evidence_refs` | 服务端持有；不写入公开题面 |
| 题量 / 题型 / 难度 | 本轮 capability request config | 由 `deep_question` 解析，本 Skill 不再决定 |

## 公开输出规则

1. **题面公开范围**：
   - 单选 / 多选 / 判断题：题干 + 完整选项（不带正确性标注）
   - 案例题：背景资料 + 设问；不公开评分采分点和参考答案
2. **答案与解析默认隐藏**：
   - `reveal_answers=False`（默认）：公开输出中**禁止**出现"答案：X"、"正确选项是"、"解析"、"采分点"、"得分要点"、option marker（如"B ✓"）等任何答案泄露形式
   - `reveal_answers=True`（用户作答后或显式请求）：允许在批改 / 复盘阶段展示；但**仅限**`mcq_grading` / `case_grading` / `question_review` scene，不属于本 Skill 职责
3. **答案与解析独立分离**：`reveal_answers` 与 `reveal_explanations` 是两个独立 flag；解析揭示不暗示答案揭示，反之亦然
4. **服务端 QuestionArtifact 保留权威字段**：`correct_answer` / `grading_key` / `rubric` / `knowledge_context` / `evidence_refs` 必须在服务端持久化 / 透传给后续 grading scene；本 Skill 不允许 wrap 一层覆盖或丢弃

## 生成不是批改

题目供给阶段：

- 不写 `learning_evidence`
- 不写 `learner_memory_events`
- 不更新 `training_intent` / `study_plan`
- 不调用 `construction_grading`
- 不调用 `LearnerStateService.write_*`

学员作答后由 `mcq_grading` / `case_grading` scene 接管，本 Skill 完全交棒。

## 摸底测试 / Starter Assessment 路由

学员说"先做一次摸底测试"、"自测"、"小测"：

- 必须路由到既有 assessment 入口或 `deep_question` 的 supply 路径
- **禁止**降级为普通 TutorBot 自由文本聊天
- `home_personalization.learning_prompt_intent` 在 `_prepare_practice_request_context` 边界提升为 `learning_training_intent` 并交给 `deep_question`（参见 contracts/capability.md §硬约束 26）

## 用户可见输出

按这个顺序输出（精简）：

1. **题号 + 题型标签**：`q1 · 单选` / `q1 · 案例题`
2. **题干 / 背景资料**：原文（不预改写）
3. **选项 / 设问**：A/B/C/D 等纯选项文本；案例题列出 1/2/3 设问
4. **作答提示**：单行 "请直接回复 A/B/C/D"、"请按顺序作答 q1 q2 q3"

不要追加"答案"、"提示"、"解析"、"我可以告诉你正确答案是..."等任何形式。

## Anti-Patterns

### ❌ 公开题面包含 "答案：B" / "B ✓" / "正确选项 D"
Ground: plan §6.5 v2-1 / 历史 prompt 拼接 bug
Why wrong: 题目供给与答案揭示是两个独立 scene，answer reveal 默认 False。
Correct shape: 公开输出只含题干和选项；正确答案放服务端 hidden context。

### ❌ "答案与解析：A，因为……" — 答案 reveal 与 explanation reveal 被合并
Ground: plan §6.5 (v1 失败模式)
Why wrong: `reveal_answers` 与 `reveal_explanations` 是两个独立 flag；任何一个 True 都不能蕴含另一个。
Correct shape: 服务端 deterministic gate 控制两个 flag；本 Skill 不输出"答案与解析"合并标题。

### ❌ "请直接告诉我答案" / "答案给我看" 在 practice_generation 阶段被本 Skill 直接接受并给答案
Ground: plan §6.5 v2-8 + §10 Q9
Why wrong: user-explicit-reveal override 是 product code authority（`question_followup.detect_answer_reveal_preference`），允许仅在 `question_review` 作答后 OR 显式"我要跳过这题"意图。本 Skill 内出题阶段必须按策略回复："练习阶段不公开答案；作答或主动跳过后会展示解析"。
Correct shape: 本 Skill markdown 不得包含"如果用户要求看答案就给"的规则。

### ❌ 把"再出 3 题"识别为讲解 / 自由聊天，未走 deep_question 生成可作答题卡
Ground: plan §6.5 (v1 失败模式) + contracts/capability.md §硬约束 25
Why wrong: TutorBot runtime 自由文本不能产出 submit-able 题卡；submit-able 题卡必须来自 `deep_question` QuestionArtifact 主链路。
Correct shape: ChatOrchestrator 将 `practice_generation` scene 路由到 `deep_question`，本 Skill 仅在 `deep_question` 生成上下文内被激活。
