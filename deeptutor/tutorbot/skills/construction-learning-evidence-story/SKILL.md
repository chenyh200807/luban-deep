---
name: construction-learning-evidence-story
description: "建筑实务学情故事 Skill。把后端 read model 给的 evidence_refs 投影成学员可读的'观察-训练-验证'故事；不读字段、不算阈值，仅做表达层。"
metadata: {"nanobot":{"emoji":"📖"}}
always: false
---

# Construction Learning Evidence Story

这是建筑实务**学情故事叙述** Skill。它只负责"如何讲"，不负责"读什么数据 / 按什么口径 / 算哪个阈值"——那些事实在 `LearnerStateService` read model 契约里。

## 何时使用

学员触发学习状态 / 错因回顾意图时使用：

- "我最近哪里错"
- "为什么我总错这类题"
- "我最近练得怎么样"
- "我的弱点在哪"
- 学情页打开 / "查看学习证据"按钮

仅在 ChatOrchestrator 将本轮 scene 判定为 `learning_evidence_story` 时加载本 Skill。

## 单一 Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 学习证据 (evidence_refs / attempts / errors) | `LearnerStateService` read model 提供的结构化 payload | **只读 payload**，不读 DB 字段 |
| 错因分类 / 采分点漏分 | read model 内 error_tags / scoring_point_misses 字段 | 引用而非重新计算 |
| 弱点 / 掌握度阈值 | learner_state.knowledge_state projection (read model 内) | 引用 read model 输出，不自定阈值 |
| 时间窗口 / 聚合口径 | read model 内 window_truncated / aggregation 字段 | 透传，不自行决定窗口 |

## 表达层规则（presentation-only）

1. **每个 claim 必须 cite `evidence_refs`**：
   - "你在 2026-05 案例题专项施工方案漏分 3 次"，必须有 `evidence_refs` 中至少一条对应
   - 没有 evidence_refs 的 claim → **drop** 或 degrade 成 "暂无足够数据"
2. **禁 PII**：任何形式的 user_id、openid、phone、real_name、wx_user_id、原始历史对话文本，都**禁止**出现在输出中
3. **故事结构**："观察的模式 → 训练动作 → 验证结果"，三段都齐备时输出完整故事；缺一段时降级表达，不补
4. **不发明数字**：禁止说 "你的掌握度是 65%" / "你比 80% 同学强"，除非 payload 字段里有
5. **不诊断 / 不推荐**：本 Skill 不输出"你应该练 X"——那是 `study_assistant` scene 的事

## 禁止条款（v2.1 R6 / R18）

下列内容**不得**出现在本 Skill 文本或输出中：

- DB 字段名 (例 learner_memory_events、evidence_source)
- 数值阈值 (例 掌握度大于等于八成算掌握)
- SQL 关键词 (大写 select / join / where)
- 聚合口径定义 (例 近十四天 attempt 数)

CI guard：plan §11 v2-C3 计划的 `scripts/check_skill_pii.py` 上线后自动检测；命中则 fail。**当前 (Task 8 pending) 由 `tests/services/test_tutorbot_teaching_modes.py::test_learner_state_narration_skills_have_scope_guard_keywords` 在 pytest 中强制执行同等约束。**

## 用户可见输出

按这个结构（精简）：

1. **观察的模式**：1-2 句，引用具体题目 / 错因 (来自 evidence_refs)
2. **训练动作**：1 句，引用已发生的训练 (来自 evidence_refs)
3. **验证结果**：1 句，引用复测 outcome (来自 evidence_refs)
4. **下一步入口**（可选）：仅展示按钮 / 链接，不重复 study_assistant 内容

若 payload 缺失：

- "暂无足够学习证据，先做几道题再回来看"
- "本周训练记录不足以下结论"
- 不要为了"看起来有内容"硬凑

## Anti-Patterns

### ❌ "你总是错专项施工方案" — 没有 evidence_refs 支持的全称 claim
Ground: plan §6.5 (v1 失败模式) + Round 2 verification gate
Why wrong: 学员会看到与自己作答不符的"系统编造"判断，信任崩塌；这是 read-model 与 narration 边界破裂的典型症状。
Correct shape: 每个 claim 之前先检查 `evidence_refs`，无则 drop 或 degrade。

### ❌ 输出 "你的掌握度是 72%" 但 read model payload 里没有该字段
Ground: plan §6.5 + AGENTS §5.7 single authority
Why wrong: skill markdown 不能发明数字 / 阈值；那是 read model 的责任。
Correct shape: 只展示 read model 已经计算并暴露的数值字段；缺失则不展示。

### ❌ Skill markdown 写 近十四天 attempt 数大于等于三才算稳定
Ground: plan §6.1 v2.1 R6 + 历史教训
Why wrong: 把"业务事实"写进 markdown，等于建第二套学情口径，违反 single authority。
Correct shape: 阈值 / 窗口口径放在 read model contract；markdown 只描述展示形态。

### ❌ 故事文本中泄露 openid / phone / 历史原文对话
Ground: plan §6.6 PII 释义；§4 历史证据闭环 PII redaction
Why wrong: 隐私违规；teacher / sales projection 也共用本 Skill，扩散风险高。
Correct shape: 任何引用学员个体信息都通过 read model 已脱敏的 redacted 字段；本 Skill 不再二次组合 PII。
