---
name: construction-question-supply
description: "建筑实务练题供给 Skill。用于一建/二建建筑实务出题、来一道、下一题、专项训练、薄弱点训练、变式题生成。默认只展示题目，不主动公布答案或解析。"
metadata: {"nanobot":{"emoji":"🧩"}}
upstream_inspiration:
  source: zhongweiv/hermes-edu-skills@v0.18.6
  skill: adult-vocational-certificate
  license: MIT
  derivation: pattern-only
always: false
---

# Construction Question Supply

这是建筑实务练题供给 Skill，不是阅卷 Skill，也不是错题画像 Skill。

核心定位：

- 以 `deep_question` 为题目生成 authority。
- 以当前训练意图、考点、错因信号和题库/RAG 作为输入约束。
- 默认隐藏答案和解析，直到用户提交答案或明确要求公布。
- 生成题只进入本轮练习，不自动写入正式题库或 learner state。

## 何时使用

用户表达练题、出题、下一题或专项训练意图时使用："来一道建筑实务选择题""按防水工程考我""根据我刚才错的点再出一题""下一题""给我 3 道案例小题""围绕危大工程专项方案出个变式题"。

边界（可判定规则）：消息的主诉求是**得到新题** → 本 Skill；主诉求是**围绕已有题讲解/追问** → `construction-question-review`；用户已提交答案要求判分 → `construction-mcq-grading` / `construction-case-grading`。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 出题能力 | `deep_question` capability | 组织调用参数、题型、难度、主题和输出约束 |
| 训练意图 | `training_intent` / 当前 turn context | 选择本轮题目目标，不自行改写长期计划 |
| 知识依据 | `questions_bank` / `rag` / 题库 taxonomy | 约束题目来源和考点，不编造规范细节 |
| 答案显隐 | `answer_reveal_policy` | 默认隐藏答案和解析 |
| 正式题库 | 题库导入与审核流程 | 本 Skill 只生成练习题候选，不写正式题库 |
| 学习证据 | `LearnerStateService` | 不写 learner state，只输出可被后续阅卷消费的题目对象 |

## Forbidden Authority

- 不做用户答案判分、估分或错因诊断。
- 不直接写学习证据 ledger、错题本、学习报告或学习计划。
- 不决定 TutorBot 路由；只在已经被选中为练题供给场景后工作。
- 不把生成题自动升级为正式题库题目。
- 不在用户答题前主动展示标准答案、解析、采分点或得分口径。

## 出题流程

1. **识别训练目标**：优先读本轮用户指定的考点、题型、难度、数量；"根据刚才错的点"用上一轮 grading result 的 `next_task_signal`；无明确目标时默认 1 道建筑实务高频选择题。
2. **绑定来源约束**：有题库同考点题时优先出同考点/同错因变式题；涉及精确规范、年份政策、数值门槛必须依赖 RAG 或题库来源；来源不足时降级为概念辨析题，不编条文号。
3. **调用 `deep_question`**：明确 topic、question_type、difficulty、num_questions；建筑实务默认 `zh`；多题生成时每题有稳定题号和独立选项。
4. **质量自检**（见下）后再输出；自检不过则重新生成或降一档题型，不把残次题推给用户。
5. **应用显隐策略并输出练题对象**：默认只输出题干和选项，内部保留 answer key 供后续阅卷绑定；输出含临时 question id、考点、题型、来源说明、answer hidden 标记；不从 Markdown 反解析答案。

## 难度阶梯与训练意图对齐

| 训练意图 | 默认难度 | 规则 |
| --- | --- | --- |
| 新考点首练 / 零基础 | easy | 单一考点、无复合陷阱，先建立判定词 |
| 常规练习（默认） | medium | 一个主考点 + 一个常见干扰维度 |
| 错题变式（next_task_signal） | 与原题同档 | 同考点换情境；连续答对 2 次同考点再升一档 |
| 薄弱点专项 | 先 easy 后 medium | 先验证基础判定，再加干扰项 |
| 冲刺期 / 用户点名"来道难的" | hard | 复合考点、贴近真题陷阱密度 |

难度只在上表规则内调整；不要因为"显得专业"而擅自升档。

## 题目质量自检清单

输出前逐项过：

- **题干完整**：单独可读，不依赖未给出的图表/背景；问法明确（选"正确"还是"不正确"要醒目）。
- **选项互斥**：选择题选项之间无包含/同义关系；长度和句式大致均衡，不让正确项一眼可辨。
- **答案唯一**：单选有且仅有一个可辩护的正确项；多选每个正确项都能独立成立；存在争议口径时弃用该题。
- **考点对齐**：题目确实考用户要求的考点，干扰项来自相邻易混考点。
- **无泄漏**：题干和选项文本不包含暗示答案的表述；用户可见正文无答案、解析、采分点。

## Answer reveal 各档位表达模板

| 档位 | 触发 | 用户可见表达 |
| --- | --- | --- |
| hidden（默认） | 出题时 | 题目 + 选项 + 一句作答提示（"直接回复 A/B/C/D"或"按采分点分条作答"） |
| 用户索答（未作答） | "直接告诉我答案" | 默认不公布：回一句"先试着作答，答错也有判分和解析；实在没思路可以说『放弃，直接讲』"。用户明确认输/放弃后才公布并转入讲解 |
| 用户点名带答案出题 | "出一道带答案的" | 题目 + 答案 + 简析一起给，并标注该题不再用于本轮作答练习 |
| 已作答 | 用户提交答案 | 移交 grading skill；判分后答案与解析由 review/grading 链路展示 |

## 内部结构化结果

```json
{
  "question_supply_mode": "generated | variant | retrieved",
  "question_type": "single_choice | multi_choice | case_short_answer",
  "topic": "危大工程专项施工方案",
  "difficulty": "medium",
  "answer_visibility": "hidden",
  "source_constraints": ["questions_bank", "rag"],
  "next_task_signal_used": true,
  "runtime_question": {
    "id": "runtime-q-001",
    "stem": "...",
    "options": [{"key": "A", "text": "..."}],
    "correct_answer_hidden": true
  },
  "trace": {
    "question_lifecycle_scene": "practice_generation",
    "skill_stack": ["construction-question-supply", "deep-question"],
    "loader_source": "deeptutor_skill_registry"
  }
}
```

## Anti-Patterns

- 用户说"下一题"，直接暴露上一题答案或解析。
- 用户未作答就索要答案，立即公布而不是先引导作答（除非用户明确认输或点名"带答案出题"）。
- 根据模糊主题自由编造规范条文、考试政策、年份数字或题库来源。
- 生成题后把答案写进用户可见正文，导致后续阅卷场景失效。
- 用本 Skill 的自然语言描述代替 `deep_question` capability 或题库审核流程。
- 把"错题变式"出成原题换字面（选项顺序一换就完事），考点和陷阱没有迁移。

## Trace Fields

- `question_lifecycle_scene=practice_generation`
- `skill_stack`
- `loader_source`
- `question_supply_mode`
- `answer_visibility`
- `source_constraints`
