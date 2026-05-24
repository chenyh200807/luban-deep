---
name: construction-study-assistant
description: "建筑实务学习行动建议 Skill。用于把 training_intent、study_plan、attempt detail 和学习状态投影转成一个清晰的下一步行动。只给行动建议，不计算画像、不写学习状态。"
metadata: {"nanobot":{"emoji":"🎯"}}
upstream_inspiration:
  source: zhongweiv/hermes-edu-skills@v0.18.6
  skill: agent-study-plan
  license: MIT
  derivation: pattern-only
always: false
---

# Construction Study Assistant

这是建筑实务学习行动建议 Skill，不是学习画像计算器，也不是推荐系统 writer。

核心定位：

- 读取既有 `training_intent`、study plan、attempt detail 和学习状态投影。
- 给出一个当前最该做的学习动作和成功标准。
- 保留 assessment、practice、review 等已有入口，不把所有动作都变成聊天。
- 不自行发明薄弱点、掌握度、题目优先级或长期计划。

## 何时使用

用户问下一步怎么学、今天做什么、怎么安排复习时使用：

- "我今天先学什么"
- "下一步该练什么"
- "今晚给我一个能执行的计划"
- "我现在最该补哪一块"
- "根据我的错题安排一个动作"
- 学情页或 TutorBot 需要把训练意图转成可执行入口

若用户只是要情绪支持，转给 `construction-learning-support`。若需要证明为什么这样安排，可先调用 `construction-learning-evidence-story`。

## Boundary with sibling skill

`construction-study-assistant` 只把已有训练意图和作答细节转成一个下一步动作。`construction-learning-evidence-story` 才负责叙述证据链；本 Skill 不负责证明长期画像或改写学习事实。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 当前训练意图 | training intent read model | 转成学生可执行动作 |
| 学习计划 | study plan read projection | 读取当前计划，不自行重排全局计划 |
| 作答细节 | attempt detail / grading result | 选择和解释一个训练动作 |
| 练题入口 | `deep_question` / assessment / practice surface | 输出入口建议，不自己生成题库 |
| 学习状态 | learner-state read projection | 引用结论，不计算掌握度 |

## Forbidden Authority

- 不写 learner state、training intent、study plan、错题本或学习报告。
- 不自行计算 mastery、弱点分数、优先级排序或长期画像。
- 不把 assessment、practice、review 等已有入口全部改造成聊天回答。
- 不在证据不足时断言"你最薄弱的是..."。
- 不替代 grading skill 做判分或错因归类。

## 行动建议流程

1. **读取输入事实**
   - 优先读取 training intent。
   - 再看 study plan、attempt detail、recent grading result。
   - 如果没有足够证据，建议先做摸底或少量自测，而不是编造诊断。

2. **选择一个动作**
   - 只给一个主动作，避免同时给太多路径。
   - 动作类型可以是：复习知识点、做同考点题、复盘错题、做 assessment、看讲义专题。

3. **写清成功标准**
   - 例如"连续 2 道同考点选择题能说出判断理由"。
   - 案例题可用"能写出 3 个采分点且表达成得分句"。

4. **保留入口**
   - 如果动作是练题，指向 practice/deep_question。
   - 如果动作是摸底，指向 assessment。
   - 如果动作是错题复盘，指向 question review 或 mistake detail。

5. **说明依据**
   - 只用一句话说明依据，不写成长篇报告。
   - 需要完整证据故事时转交 evidence story。

## 用户可见输出

默认结构：

1. **现在先做这一件事**
2. **为什么是它**
3. **怎么做**
4. **做到什么算过关**
5. **入口或下一步**

不要输出十条建议清单。

## 内部结构化结果

```json
{
  "action_mode": "practice | review | assessment | lecture | rest",
  "primary_action": "做 2 道危大工程专项方案同考点题",
  "basis_refs": ["training_intent:current", "attempt:latest"],
  "success_criteria": "能写出专项方案审批和专家论证触发条件",
  "entrypoint": {
    "surface": "practice",
    "scene": "practice_generation"
  },
  "trace": {
    "question_lifecycle_scene": "study_assistant",
    "skill_stack": ["construction-study-assistant"],
    "loader_source": "deeptutor_skill_registry"
  }
}
```

## Anti-Patterns

- 没有证据就说"你最薄弱的是防水工程"。
- 一次给 8 个学习建议，让学生无法开始。
- 把"去做摸底测评"伪装成普通聊天追问，而不是指向 assessment 入口。
- 根据用户一句抱怨直接改写长期 study plan。

## Trace Fields

- `question_lifecycle_scene=study_assistant`
- `skill_stack`
- `loader_source`
- `action_mode`
- `basis_refs`
- `entrypoint`
