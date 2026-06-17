# 降级叙述与证据引用细则（construction-learning-evidence-story）

本文件是 SKILL.md 的深度参考：降级各级输出模板、证据引用格式对照、时间窗口与冲突叙述的完整示例。
所有示例字段名与 `deeptutor/services/construction_grading/schema.py`、
`deeptutor/services/learner_state/personalization_context.py` 的真实形状一致。

## 1. 证据引用格式对照

### 1.1 learner-state 侧（event_id 字符串）

claim / improvement signal / ContextPack 的 `evidence_refs`、`recent_evidence_refs` 都是 event_id 字符串列表：

```json
{
  "claim_id": "concept_wei_da:missing_expert_review",
  "claim_status": "repeated",
  "trend_state": "repeated_active",
  "occurrence_count": 2,
  "evidence_refs": ["evt_20260524_q1_grading", "evt_20260530_q4_grading"],
  "occurrence_timeline": [
    {"event_id": "evt_20260524_q1_grading", "observed_at": "2026-05-24T10:02:00Z"},
    {"event_id": "evt_20260530_q4_grading", "observed_at": "2026-05-30T20:11:00Z"}
  ]
}
```

规则：id 原样转抄；不能出现输入里没有的 id；不能把两个 id 合并成一个"代表性"引用。

### 1.2 批改侧 error_events（GradingErrorEvent）

```json
{
  "error_code": "missing_required_term",
  "severity": 0.8,
  "concept_tag": "危大工程专项施工方案",
  "evidence": "方案编完直接报项目经理签字后实施",
  "diagnosis": "漏掉了超过一定规模的危大工程需组织专家论证这一步"
}
```

- 学生作答原文片段在 `evidence` 字段。**没有 `mistake_type`，没有 `evidence_span`**。
- 叙事引用方式："你当时写的是『方案编完直接报项目经理签字后实施』（来自批改记录），漏掉了专家论证环节。"

### 1.3 批改侧 evidence_refs（EvidenceRef 三元组）

```json
{"source": "rubric_item", "field": "criterion", "value": "专家论证触发条件"}
```

叙事转述："这个判断来自批改时的采分点『专家论证触发条件』。"不展示内部 value 的原始 JSON。

### 1.4 attempt ref（签名 token）

形如一段 base64 字符串。只整体携带/引用，绝不解码、拼接或猜测其内部内容。

## 2. 降级各级输出模板

多个 degraded_reasons 并存时：`degraded_reasons` 全部列出，叙述按其中**最严格**的表达上限收口。

### D0 `no_evidence`（完全无证据）

固定空叙述，不允许变体加结论：

> 目前还没有可以引用的学习记录，无法负责任地总结你的情况。先完成一次作答或测评，记录就会从那里开始。

`story_mode="empty"`，`evidence_refs=[]`，不输出 observed_pattern。

### D1 `single_observation`（单次观察）

> 5 月 24 日那道危大工程题里，你漏写了专家论证（证据：当次批改记录）。**这只是一次观察**，还不能说明这是长期薄弱点——再遇到同类题对比一下，才知道是偶然疏漏还是规律。

禁用词："总是"、"一直"、"长期"、"你的弱项是"。

### D2 `no_training_loop`（有错误证据，无训练证据）

> 这个考点你累计错过 2 次（5/24、5/30 两次批改记录），但目前只看到问题证据，**还没有看到针对它的训练闭环**——也就是说系统还没观察到你专门练过这一块。

可自然衔接交棒："想安排针对性练习的话可以让学习助手接手。"——但不自己开方。

### D3 `no_retest`（有训练，无复测）

> 你在 5 月 31 日做过同考点变式训练（证据：训练记录），但**还没有同类题复测来确认是否真的改善**。下次再遇到危大工程题，就是检验的机会。

禁止写"训练后已经掌握/已经改善"。

### D4 `no_rag_support`（learner 证据在，外部知识检索无命中）

照常基于 learner-state 证据叙述，仅追加一句：

> （本次没有从教材知识库找到额外佐证，以上结论全部来自你自己的作答与批改记录。）

**绝不能**因为检索未命中而说"没有找到学习记录"。

## 3. 时间窗口表达示例

| 证据分布 | 正确表达 | 错误表达 |
| --- | --- | --- |
| 2 次都在近 7 天 | "最近一周这个点错了 2 次" | — |
| 2 次都在 3 周前 | "此前累计错过 2 次，最近一周没有新记录" | "你最近总错这个点" |
| 1 次近 7 天 + 1 次更早 | "累计 2 次，其中最近一周 1 次" | "最近错了 2 次" |
| 无时间戳 | "记录里出现过 2 次"（不加时间副词） | "前几天错了 2 次" |

## 4. 冲突叙述（新对旧错）完整示例

输入同时有：旧 claim（repeated）+ `recent_improvement_signals` 命中同一 concept/error_code。

正确叙述（先旧后新，最新为现状）：

> 危大工程的专家论证这个点，你此前错过 2 次（5/24、5/30）。6 月 1 日的复测题里你已经完整写出了论证触发条件（证据：复测批改记录）——**按最新一次表现，这个点正在好转**，再稳定答对一次就更有把握了。

错误叙述：
- 只讲旧错，无视改善信号（让学生白练）；
- "这个点你已经掌握了"（一次答对不等于掌握，且掌握度不是本 Skill 的 authority）；
- 删掉历史："你在这个点上没有问题"。

`gaps` 中 `claim_contradicted` / `claim_superseded` / `claim_stale` / `claim_rejected` 的 claim：默认直接省略；若用户明确问起，用"系统曾经有过这个判断，但后来的记录推翻/更新了它"的句式，不再作为现状断言。

## 5. story_mode 判定

| story_mode | 条件 |
| --- | --- |
| `complete_loop` | 错误证据 + 训练证据 + 复测/改善信号齐全 |
| `evidence_only` | 只有作答/批改证据 |
| `degraded` | 任一 D1-D4 成立 |
| `empty` | D0：无任何 evidence_refs |
