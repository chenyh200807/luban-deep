# 主动作决策细则（construction-study-assistant）

SKILL.md 的深度参考：决策树各分支的输入信号、边界案例、粒度示例、退让对话示例。
字段名与 `deeptutor/services/learner_state/training_intent.py`、
`personalization_context.py`、`next_best_action.py` 的真实形状一致。

## 1. 决策树输入信号对照

| 优先级 | 规则 | 命中信号（真实字段） |
| --- | --- | --- |
| 1 纠错复测 | retest_first | `active_training_intent.success_criteria.requires_revalidation == true`；或 `recent_improvement_signals` 非空（改善待巩固）；或 next_best_action_candidates 里 `action_type == "retest_or_targeted_practice"` |
| 2 弱项补练 | weak_point_repair | `top_claims` 中 `trend_state == "repeated_active"` 或 `claim_status in {repeated, confirmed}` 且 `evidence_refs` 非空 |
| 3 计划推进 | plan_progress | study plan 投影存在未完成的当前步骤 |
| 4 新内容/摸底 | new_content_probe | 以上皆空；或 intent `status == "degraded"`（无 evidence_refs，处方退化为 1 题 discovery_probe）|

注意：

- training intent 是处方唯一权威。ContextPack 的 `next_best_action_candidates` 只是它的产品化视图，
  两者冲突时以 intent 本体为准。
- intent `status == "degraded"` 意味着学情记录不足——此时**唯一诚实的动作是摸底**（assessment 或 1 道探测题），
  禁止包装成"针对你的弱项"。

## 2. 同级并列时的次序

1. 证据更新（`occurrence_timeline` 最新 `observed_at` 更近）优先。
2. 仍并列：`occurrence_count` 更大的优先。
3. 仍并列：直接问用户一选一（"危大工程和防水你想先碰哪个？"），不要两个都给。

## 3. 动作粒度示例

| 不合格（太大） | 合格（10 分钟内可启动） |
| --- | --- |
| 复习危大工程整章 | 重做 5/30 错的那道专项方案题 + 看它的解析 |
| 刷 30 道选择题 | 做 2 道专家论证触发条件的同考点选择题 |
| 制定考前一个月计划 | 完成今天 study plan 里的第一小节讲义 |
| 把错题本全部过一遍 | 只复盘最近一道错题的一个漏分点 |

大目标的处理：拆出第一步交给学生，并说明"先做这一步，后面的交给学习计划"。

## 4. basis_refs 追溯规则

- 合法来源：`training_intent_id`（如 `ti_...`）、`claim_id`（如 `concept_x:error_y`）、
  event_id（如 `evt_...`）、study plan 步骤标识。
- 每条 basis_ref 在用户可见输出的"为什么是它"里都要有一句对应人话。
- 自检：把 basis_refs 逐个删掉后，"为什么是它"这句话是否失去依据？是 → 合格；否 → 说明有依据是编的。

## 5. 退让路径对话示例

学生："2 道题也不想做。"

- 第一退（降粒度）："那只做 1 道，做完就停。"
- 第二退（换类型）："题也不想碰的话，花 5 分钟看一遍上次那题漏的采分点就行。"
- 收尾（尊重停止）："好，今天先到这。这个建议放在这里，想做的时候随时回来。"

硬性规则：

- 最多退两次，第三次直接收尾；不重复推销同一动作。
- 退让不写任何状态：不记"用户拒绝"、不下调任何学情判断、不改 study plan。
- 拒绝伴随情绪信号（"烦死了""没希望了"）→ 立即停止给动作，转 `construction-learning-support`。

## 6. 与 evidence story 的边界案例

| 用户话语 | 归属 | 理由 |
| --- | --- | --- |
| "我下一步练什么？" | 本 Skill | 将来动作 |
| "我为什么总错这个点？" | evidence story | 解释已发生事实 |
| "为什么让我练这个？" | 本 Skill 一句话 + 需要展开时交棒 | 依据引用 ≤1 句话 |
| "我这周练得怎么样，接下来呢？" | 先 evidence story 后本 Skill | 双 scene，各自 authority |
| "给我安排，并解释清楚每个证据" | 本 Skill 给动作，证据链交棒 | 不在本 Skill 内写证据故事 |

## 7. action_mode 与入口映射

| action_mode | 入口 surface | 典型场景 |
| --- | --- | --- |
| practice | practice / deep_question | 复测、补练、新考点练习 |
| review | question review / mistake detail | 错因复盘 |
| assessment | assessment | 摸底、degraded intent |
| lecture | 讲义专题 | 概念尚未建立时先输入再练 |
| rest | 无入口 | 退让收尾、深夜/过载场景 |
