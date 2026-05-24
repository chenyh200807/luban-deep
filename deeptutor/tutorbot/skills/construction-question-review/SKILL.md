---
name: construction-question-review
description: "建筑实务题目复盘讲解 Skill。用于未作答的真题分析、当前题为什么这样答、逐项解析。题干在前，结论在后；不冒充已验证的学习进展。"
metadata: {"nanobot":{"emoji":"🔍"}}
always: false
---

# Construction Question Review

这是建筑实务**题目复盘讲解** Skill。用于学员尚未提交答案、或在批改后追问"这题为什么"时的题目级讲解。

## 何时使用

学员触发题目复盘意图时使用：

- 未作答场景：
  - "分析一道验槽方法真题"
  - "讲一下这道选择题"
  - "这题怎么做"
  - "这道案例题怎么答"
- 作答后追问场景（与 grading scene 串联使用）：
  - "为什么 B 不对"
  - "再解释一下这题"
  - "为什么我只得 6 分"（与 case_grading rubric_breakdown 联用）

仅在 ChatOrchestrator 已将本轮 scene 判定为 `question_review` 时加载本 Skill。"再出 3 题"等供给场景不在本 Skill 职责范围。

## 单一 Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 题目资产 | `questions_bank` / `active_object` / 用户粘贴题干 | 复述与解释 |
| 历史系统解析 | 既有历史模块 assistant 解释（通过 `attempt_detail_read_model` 还原） | 优先复用，不重新生成口号化结论 |
| 选项 / 采分点解释 | `option_reasoning` / `pitfalls` / `grading_rubric` / `analysis` | 逐项讲解 |
| 学习进展事实 | `LearnerStateService` `learning_evidence` event | **不写入**；本 Skill 是 read-only 讲解 |
| Grading 评分明细 | `construction_grading_result.rubric_breakdown` | 作答后场景透传；本 Skill 引用，不重新打分 |

## 输出顺序硬约束（题干在前，结论在后）

1. **先重建题目**：题干 / 背景资料 / 选项 / 设问。学员必须先看到讨论的是哪道题。
2. **再给结论**：正确答案 / 标准要点（仅当本轮 reveal_answers=True 或学员已作答）。
3. **逐项 / 逐采分点解释**：
   - MCQ：为什么所选项对 / 错；正确选项为什么成立；其他干扰项为什么不对（仅当 option data 存在）
   - 案例题：采分点期望（仅当 `grading_rubric` 或 `projected_rubric` evidence 存在）
4. **关联知识 / 易错点**：扣回考点和 pitfalls。

未作答场景的 `reveal_answers` 默认遵循请求 config。本 Skill 不私自打开答案揭示。

## 历史系统解析优先

学员追问同一道题时：

- 优先调用 `attempt_detail_read_model` 还原同 turn / session 的历史 assistant 完整系统解析
- 历史解析作为教学材料引用，**但不能改写为"已掌握 / 已练熟 / 验证学习进展"** —— 那是 `learner_memory_events.learning_evidence` 的权威，只有真实 attempt 才写
- 历史 assistant 内容必须通过 `_sanitize_history_text` 去除 `[History Context]` 等内部标识和 PII

参见 docs/plan/2026-05-23-luban-learning-history-evidence-closed-loop-plan.md。

## 作答后追问 (post-grading) 场景

学员说 "为什么我只得 6 分"、"为什么 B 不对"：

- 本 Skill 上下文必须包含 `construction_grading_result.rubric_breakdown` / `option_results` / 最近一次 attempt detail
- 必须 cite 至少一条 rubric line / option result，**禁止**虚构分数或采分理由
- 如果 `rubric_breakdown=None`（open_skill 模式），用 "我无法定位评分明细" hedge，**不**编造数字
- 参见 plan §6.5 v2-7

## 用户可见输出

按这个顺序：

1. **题号 + 题型**：`q1 · 单选 · 验槽方法`
2. **题干 / 背景资料**：复述
3. **选项 / 设问**：列出
4. **正确答案 / 标准要点**（若 reveal）
5. **逐项 / 逐采分点解释**：每条绑定具体选项 / 采分点
6. **易错点 / 抓手**：一句话
7. **下一步建议**：可选；若给，限一个最小动作

## Anti-Patterns

### ❌ "分析一道真题" 直接抛出 "答案是 A" 不先重建题干
Ground: plan §6.5 (v1 失败模式)
Why wrong: 学员看不到讨论的是哪道题，无法验证讲解的针对性。
Correct shape: 输出顺序硬约束 §1 — 先题干 / 选项，再结论。

### ❌ 案例题追问 "为什么我得 6 分" 时虚构具体采分点扣分
Ground: plan §6.5 v2-7
Why wrong: 必须 cite 真实 `rubric_breakdown`；缺失 payload 时只能 hedge，不能编。
Correct shape: 上下文检查 `rubric_breakdown`；缺失 → "我无法定位评分明细"；存在 → 引用 rubric_item_id / criterion 原文。

### ❌ 历史模块本已有完整解析，本 Skill 重新生成口号化结论 "加强管理 严格检查"
Ground: plan §6.5 (v1 失败模式) + 2026-05-23 历史证据闭环
Why wrong: 历史 assistant 解析比新生成的口号化文本更具体；学员体感是"系统在重复说相同的废话"。
Correct shape: 优先 `attempt_detail_read_model` 还原历史完整解析；只在历史不存在时才新生成讲解。

### ❌ 未作答场景把本 Skill 当成"已验证掌握"的写回信号
Ground: plan §6.1 + AGENTS §5.7 single authority
Why wrong: 讲解 ≠ 学习证据；只有真实 attempt + grading 才能写 `learning_evidence`。
Correct shape: 本 Skill read-only；不调用任何 `LearnerStateService.write_*`。
