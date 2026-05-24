---
name: construction-learning-evidence-story
description: "建筑实务学习证据叙事 Skill。用于把已存在的作答、批改、错因、复测和训练结果整理成学生可读的学习故事。只能读取 evidence_refs 指向的事实，不生成新学习事实。"
metadata: {"nanobot":{"emoji":"🧭"}}
upstream_inspiration:
  source: zhongweiv/hermes-edu-skills@v0.18.6
  skill: agent-mistake-review
  license: MIT
  derivation: pattern-only
always: false
---

# Construction Learning Evidence Story

这是建筑实务学习证据叙事 Skill，不是 learner state writer，也不是掌握度计算器。

核心定位：

- 把已存在的证据整理成学生能看懂的学习语言。
- 每个结论都必须能回到 `evidence_refs`。
- 缺证据时降级表达，不补脑、不编历史、不制造新事实。
- 输出给学情页、错题复盘、阶段总结或 TutorBot 解释层使用。

## 何时使用

用户或系统需要把学习记录讲清楚时使用：

- "我最近为什么总错这个点"
- "这周我有什么进步"
- "这个弱点是怎么判断出来的"
- "把我的错题记录讲成人话"
- 学情页需要展示一段证据链说明
- 错题复盘需要串起作答、错因、训练和复测结果

如果用户正在提交答案或请求判分，转给 grading skill。若用户要求下一步安排，转给 `construction-study-assistant`。

## Boundary with sibling skill

`construction-learning-evidence-story` 只叙述已经发生的事实和证据链。`construction-study-assistant` 才把这些事实转成一个下一步动作；本 Skill 不负责安排训练入口。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 学习证据 | evidence refs / learner evidence read model | 只读取并转述已存在证据 |
| 错因与采分点 | grading result / attempt detail | 用学生语言解释已有结论 |
| 训练动作 | training intent / practice history | 叙述已经发生的训练动作 |
| 复测结果 | verified attempt / review outcome | 在有证据时描述是否改善 |
| 长期画像 | learner-state read projection | 只引用投影结论，不自行计算 |

## Forbidden Authority

- 不写 learner state、错题本、学习报告或长期画像。
- 不根据单次聊天自行断言掌握度、薄弱点、学习风格或长期能力。
- 不读取或展示原始隐私字段、账号标识、手机号、真实姓名、openid 或 raw chat transcript。
- 不直接生成下一步训练计划；只可输出可供 study assistant 消费的 evidence summary。
- 不把缺少 evidence refs 的判断写成确定结论。

## 叙事流程

1. **收集证据引用**
   - 只使用输入中显式提供的 `evidence_refs`、attempt detail、grading result、review outcome。
   - 如果证据引用为空，输出 degraded claim 或不输出该结论。

2. **识别证据类型**
   - 作答证据：用户当时怎么答。
   - 批改证据：命中/漏掉哪些点。
   - 错因证据：错因标签或老师/系统解释。
   - 训练证据：做过哪些针对性训练。
   - 复测证据：同类题是否改善。

3. **组织学生语言**
   - 优先使用"你在什么题上暴露了什么问题"。
   - 再说明"后来系统安排了什么训练"。
   - 最后说明"有没有被复测证明改善"。

4. **处理缺口**
   - 只有作答和批改，没有训练：写"目前只看到问题证据，还没有看到训练闭环"。
   - 只有单次错误：写"这是一次观察，不足以说明长期薄弱"。
   - 没有复测：写"还需要同类题复测确认"。

## 用户可见输出

默认结构：

1. **观察到的学习现象**
2. **证据来自哪里**
3. **可能的错因或能力缺口**
4. **已经采取的训练动作**（若存在）
5. **复测或改善情况**（若存在）
6. **仍需确认的地方**

语气要像学习教练，不要像数据库报表。

## 内部结构化结果

```json
{
  "story_mode": "complete_loop | evidence_only | degraded",
  "evidence_refs": ["attempt:2026-05-24:q1", "grading:2026-05-24:g1"],
  "observed_pattern": "危大工程专项方案题中漏写专家论证",
  "training_action": "同考点变式训练",
  "verification_outcome": "复测仍待完成",
  "degraded_reasons": [],
  "trace": {
    "question_lifecycle_scene": "learning_evidence_story",
    "skill_stack": ["construction-learning-evidence-story"],
    "loader_source": "deeptutor_skill_registry"
  }
}
```

## Anti-Patterns

- 把一次错误写成"你长期掌握很差"，但没有历史证据或复测证据。
- 没有 `evidence_refs` 时仍然编造"最近多次出错"。
- 把原始聊天、账号标识或隐私字段直接展示给学生。
- 在叙事里直接安排下一步学习计划，越过 `construction-study-assistant`。

## Trace Fields

- `question_lifecycle_scene=learning_evidence_story`
- `skill_stack`
- `loader_source`
- `story_mode`
- `evidence_refs`
- `degraded_reasons`
