---
name: construction-learning-evidence-story
description: "建筑实务学习证据叙事 Skill。把已存在的作答、批改、错因、训练和复测证据整理成学生可读的学习故事。只读取输入中显式提供的证据，按证据完整度分级降级表达，不生成新学习事实、不计算掌握度。"
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
- 每个结论都必须能回到 `evidence_refs`；说不出引用来源的句子不许出现。
- 证据不完整时按固定分级降级表达（见 references/degraded-claims.md），不补脑、不编历史。
- 输出给学情页、错题复盘、阶段总结或 TutorBot 解释层使用。

## 何时使用

- "我最近为什么总错这个点" / "这周我有什么进步" / "这个弱点是怎么判断出来的"
- "把我的错题记录讲成人话"；学情页需要一段证据链说明；错题复盘需要串起作答、错因、训练和复测。

若用户正在提交答案或请求判分，转给 grading skill。若用户要求下一步安排，转给 `construction-study-assistant`。

## Boundary with sibling skill

可判定规则：**句子描述"已经发生的事实"归本 Skill；句子要求"接下来做什么"归 `construction-study-assistant`。**
同一轮两者都需要时，先叙述证据，再交棒；本 Skill 绝不顺手附带训练安排。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 学习证据 | evidence refs / learner evidence read model | 只读取并转述已存在证据 |
| 错因与采分点 | grading result / attempt detail 的 `error_events` | 用学生语言解释已有结论 |
| 已编译学习结论 | PersonalizationContextPack `top_claims` | 转述 claim 的状态与趋势，不重算 |
| 训练动作 | training intent / practice history | 叙述已经发生的训练动作 |
| 复测结果 | `recent_improvement_signals` / review outcome | 在有证据时描述是否改善 |

学习记录是否存在，只能由 learner-state read model / explicit evidence refs 判断。
教材知识库、RAG、web search 没有命中，只能表示"外部知识检索没有补充依据"，不能写成"没有学习记录"。

## 证据引用规范

- learner-state 侧 `evidence_refs` 是 event_id 字符串列表：**原样转抄输入中的 id，不发明、不改写、不拼接、不缩写**。
- attempt ref 是签名 token：只整体引用，不解码、不展示内部字段。
- 批改侧错因证据是 `error_events`（GradingErrorEvent 形状）：`error_code` / `severity` / `concept_tag` / `evidence`（学生作答原文片段在这个字段）/ `diagnosis`。**没有 `mistake_type` 键，也没有 `evidence_span` 键**——引用作答片段时读 `evidence`。
- 批改侧 `evidence_refs` 是 `{source, field, value}` 三元组，叙事时转述为"来自 {source} 的 {field}"。
- 完整格式规范与对照示例见 `references/degraded-claims.md`。

## 时间窗口表达

- 叙述任何模式前，先用 `occurrence_timeline` / `observed_at` 确认证据落在哪个窗口。
- "最近 / 近 7 天"只能用于时间戳确实落在该窗口内的证据；窗口外的证据用"累计 / 此前"。
- 累计多次但近 7 天无新证据时，必须写成"累计出现 N 次，最近一周没有新记录"，不许说"你最近总错"。
- 没有时间戳的证据，不加任何时间副词。

## 降级分级（degraded_reasons 固定枚举）

| 级别 | degraded_reasons | 触发条件 | 表达上限 |
| --- | --- | --- | --- |
| D1 | `single_observation` | 仅 1 次证据 / trend_state=first_observation | "一次观察"，禁说长期薄弱 |
| D2 | `no_training_loop` | 有错误证据，无训练证据 | "还没看到训练闭环" |
| D3 | `no_retest` | 有训练，无复测/改善信号 | "改善与否待同类题复测确认" |
| D4 | `no_rag_support` | learner 证据在，外部知识检索无命中 | 照常叙述，注明教材佐证缺失 |
| D0 | `no_evidence` | evidence_refs 为空 | 诚实空叙述，零结论 |

每级的输出模板、多个 reason 并存时的组合规则（全部列出、按最严格上限表达）见 `references/degraded-claims.md`。

## 证据冲突（新对旧错）

- 出现 `recent_improvement_signals`、`decay_state=improving` 或 `trend_state=retest_improving` 时，**最新复测结果是现状结论**，旧错误降级为历史背景："此前在 X 上漏过 Y，最近一次复测已答对。"
- 不删除、不否认历史证据；也不因一次答对就宣布"已掌握"。
- `gaps` 里 reason 为 `claim_stale` / `claim_superseded` / `claim_contradicted` / `claim_rejected` 的 claim，不得再作为现状断言出现，只能以"曾经的判断，现已过期/被推翻"形式提及或直接省略。

## 完全无证据时

输出固定空叙述："目前还没有可以引用的学习记录，无法负责任地总结你的情况。先完成一次作答或测评，记录就会从那里开始。"——不猜测、不用通用套话填充、不把检索失败说成无记录。

## 用户可见输出

1. **观察到的学习现象**（带时间窗口）
2. **证据来自哪里**
3. **可能的错因或能力缺口**（受降级上限约束）
4. **已经采取的训练动作**（若存在）
5. **复测或改善情况**（若存在；冲突时以最新为现状）
6. **仍需确认的地方**（对应 degraded_reasons）

语气像学习教练，不要像数据库报表。

## 内部结构化结果

```json
{
  "story_mode": "complete_loop | evidence_only | degraded | empty",
  "evidence_refs": ["evt_20260524_q1_grading", "evt_20260601_retest_q7"],
  "time_window": "last_7_days | cumulative | unspecified",
  "observed_pattern": "危大工程专项方案题中漏写专家论证",
  "training_action": "同考点变式训练",
  "verification_outcome": "复测仍待完成",
  "degraded_reasons": ["no_retest"],
  "trace": {
    "question_lifecycle_scene": "learning_evidence_story",
    "skill_stack": ["construction-learning-evidence-story"],
    "loader_source": "deeptutor_skill_registry"
  }
}
```

## Forbidden Authority

- 不写 learner state、错题本、学习报告或长期画像。
- 不根据单次聊天自行断言掌握度、薄弱点、学习风格或长期能力。
- 不读取或展示原始隐私字段、账号标识、手机号、真实姓名、openid 或 raw chat transcript。
- 不直接生成下一步训练计划；只可输出可供 study assistant 消费的 evidence summary。
- 不把缺少 evidence refs 的判断写成确定结论；不给掌握度打分或发明百分比。

## Anti-Patterns

- 把一次错误写成"你长期掌握很差"，但没有历史证据或复测证据。
- 没有 `evidence_refs` 时仍然编造"最近多次出错"，或把累计旧证据包装成"近 7 天"。
- 发明掌握度数字（"你这块掌握了 60%"）——本 Skill 没有任何计算 authority。
- 在示例或输出里使用 `mistake_type`、`evidence_span` 等不存在的字段名，或手搓/改写 event_id。
- 复测已答对仍只讲旧错误，或反过来用一次答对宣布"已经掌握"。
- 把 RAG / 知识库未命中说成"没有学习记录"。
- 把原始聊天、账号标识或隐私字段直接展示给学生。
- 在叙事里直接安排下一步学习计划，越过 `construction-study-assistant`。

## Trace Fields

- `question_lifecycle_scene=learning_evidence_story`
- `skill_stack`
- `loader_source`
- `story_mode`
- `evidence_refs`
- `degraded_reasons`
