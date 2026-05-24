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

用户表达练题、出题、下一题或专项训练意图时使用：

- "来一道建筑实务选择题"
- "按防水工程考我"
- "根据我刚才错的点再出一题"
- "下一题"
- "给我 3 道案例小题"
- "围绕危大工程专项方案出个变式题"

如果用户已经提交答案并要求判分，转给 `construction-mcq-grading` 或 `construction-case-grading`。

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

1. **识别训练目标**
   - 优先读取本轮用户指定的考点、题型、难度和数量。
   - 若用户说"根据刚才错的点"，使用上一轮 grading result 的 `next_task_signal`。
   - 若没有明确目标，默认生成 1 道建筑实务高频选择题。

2. **绑定来源约束**
   - 有题库同考点题时，优先出同考点/同错因变式题。
   - 涉及精确规范、年份政策、数值门槛时，必须依赖 RAG 或题库来源。
   - 来源不足时降低到概念辨析题，不编造条文号。

3. **调用 `deep_question`**
   - 明确 topic、question_type、difficulty、num_questions。
   - 建筑实务默认 `zh`。
   - 多题生成时每题必须有稳定题号和独立选项。

4. **应用显隐策略**
   - 默认输出题干和选项。
   - 内部可保留 answer key 供后续阅卷绑定。
   - 用户明确"带答案/带解析"时才展示答案或解析。

5. **输出练题对象**
   - 输出应包含可追踪的临时 question id、考点、题型、来源说明、answer hidden 标记。
   - 不从 Markdown 反解析答案；服务实现应保留结构化对象。

## 用户可见输出

默认只输出：

1. **题目**
2. **选项**（如为选择题）
3. **作答提示**：一句话说明如何回复，例如"直接回复 A/B/C/D"或"按采分点分条作答"。

不要默认输出：

- 标准答案
- 解析
- 采分点
- 评分规则
- 用户薄弱画像

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
- 根据模糊主题自由编造规范条文、考试政策、年份数字或题库来源。
- 生成题后把答案写进用户可见正文，导致后续阅卷场景失效。
- 用本 Skill 的自然语言描述代替 `deep_question` capability 或题库审核流程。

## Trace Fields

- `question_lifecycle_scene=practice_generation`
- `skill_stack`
- `loader_source`
- `question_supply_mode`
- `answer_visibility`
- `source_constraints`
