# Semantic Router 误切率基线——首版结果（Path A 执行）

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-30 |
| 类型 | Baseline Results（只读核验产物） |
| 状态 | v1 |
| 方法 | runbook Path A：只读生产 SQLite `data/user/chat_history.db`（`mode=ro`），导出 313 条 `turn_semantic_decision` + join 用户消息/活跃对象/`turns.capability`，本地标注。**未写库、未翻 flag、未部署。** |
| PII | 生产用户消息全程留本地，本报告**仅含聚合统计 + 脱敏/泛化样例**，无原始消息、无任何标识符。 |
| 上游 | [2026-05-30-semantic-router-baseline-runbook.md](2026-05-30-semantic-router-baseline-runbook.md)（Path A/B + 门槛） |

---

## 0. 执行摘要（裁决先行）

**裁决：当前遥测无法产出可信的"绝对误切率"数字——所以不能机械套 runbook 的 ≤2%/>5% 门槛。这本身是首版基线最重要的发现（instrumentation gap）。临时风险读数：判别性主动对象路由（答题/下一题/追问）在 reason 可信子集里未见系统性误切；唯一可量化前未决的风险是"开放对话默认出题"兜底 + "切新题/取新卷被当成对当前题追问/批改"两类。建议：不回退（无系统性伤害证据）、也不宣称"已验证安全"；先补一条 instrumentation（记录 (raw_input, final_capability) 稳定对）或走 Path B shadow，再出真数字。**

---

## 1. 为什么不能直接给"绝对误切率"——三个数据断点（§5 诚实暴露）

只读导出 313 条决策后，发现现有遥测有三处让"决策→对错"无法干净判定：

1. **用户消息时间 join 不可靠**：`messages` 无 `turn_id`，只能按 `session_id`+时间回找最近用户消息。实测 **111/313 (35%) join 不到消息**（多为按钮动作"出题/提交"无文本行）；且大量 grading 行的 `reason` 逐字引用真实输入（如答案提交），而 join 到的消息是**过期的、不相关的**。→ joined 消息不能直接判对错（会把 join artifact 误报成误切）；`reason` 才反映 router 真实所见。
2. **40% 决策是非判别性兜底/不确定**：`route_to_generation` 138 条中 **110 条是逐字相同的 conf=0.70 模板**（"无活跃对象→默认出题"），`hold_and_wait` 14 条**全 conf=0.00**（router 无法决定）。这 ~124 条不是逐条语义判断，不能当判别性路由统计对错。
3. **18% 决策没驱动最终路由**：`turn_semantic_decision` 与 `turns.capability` 交叉——**55/313 (18%)** 决策说 grading/generation，但 turn 实际跑成 `chat`（lifecycle 在 semantic router 之前裁决，或决策仅做活跃对象记账）。即"记录了决策"≠"该决策驱动了用户体验"。

> 结论：**Path A 在当前 instrumentation 下只能给"判别性可信子集"的近似，给不了全量绝对误切率。** 要全量真数字，必须先补 instrumentation 或走 Path B。

---

## 2. 聚合统计（只读实测，2026-05-30）

```
N decisions (turn_semantic_decision in turn_events.result) = 313
next_action      : route_to_generation 138 / route_to_grading 112 / route_to_followup_explainer 49 / hold_and_wait 14
turns.capability : deep_question 258 / chat 55
置信度 p50       : generation 0.70 / grading 0.92 / followup 0.95 / hold_and_wait 0.00
非判别性占比      : conf=0.70 模板兜底 110 + deterministic_fallback 6 + hold_and_wait(conf0) 14 ≈ 124/313 (40%)
决策≠路由         : 决策为 grading/generation/followup 但 turn 跑成 chat = 55/313 (18%)
join 不到用户消息  : 111/313 (35%)
```

**next_action × 实际 capability**（决策是否驱动路由）：
| next_action | →deep_question | →chat（决策未驱动） |
| --- | --- | --- |
| route_to_generation | 107 | 31 |
| route_to_grading | 96 | 16 |
| route_to_followup_explainer | 41 | 8 |
| hold_and_wait | 14 | 0 |

---

## 3. 尽力标注：判别性可信子集（reason 逐字引用输入、非模板、有明确文本）

对 **90 条（≈29% 抽样，含全部已读 grading/followup/高置信 generation）** 用 `reason` 为主信号（router 实际所见）+ `turns.capability` 校验，逐条判路由对错：

| 子集 | 读样本结论 |
| --- | --- |
| 答题提交（"我选X"/"第N题:X" → 批改） | **可靠**：reason 一致识别为答案提交→批改；看似错的全是 join artifact（joined 消息过期）。**未见高危误判分**（把非作答当作答批改）。 |
| 继续/下一题（"下一题"/"再来一道"/"继续" → 出题） | **可靠**：高置信(0.9+)，正确路由到出题。 |
| 追问解析（"对不对"/"为什么"/"真题解析" → 追问解释） | **基本可靠**：正确识别为对当前题追问。 |
| **候选误切类 A（切新题/取新卷被当成对当前题 followup/批改）** | 发现少量：用户引入**新题目/新真题卷**请求（脱敏例："分析一道某知识点真题"/"给我某年真题解析"），active 对象却是**另一道不相关题**，router 选了 followup/批改当前题而非切新对象。router 自己 reason 里都标注了"内容不匹配"。≈ 90 条里 3-4 例（均在"切主题"场景）。 |
| **候选误切类 B（开放对话概念解释被默认出题）** | conf=0.70 模板对概念解释类提问（脱敏例："某概念是什么？"）也输出 route_to_generation。但这些 turn 多数实际仍产出了解释（prev_assistant 为讲解），疑似该决策未驱动路由或 deep_question 内部仍解释——**未确证为可见误切**，需 per-turn capability+输出核验。 |

**判别性子集的近似误切**：在可信判别样本里，高危批改误判 **未见**；候选误切集中在"切新题/新卷"被当 followup（类 A，少量、router 自知不匹配）。粗略量级：判别性子集误切 **个位数%**，且**无高危（误判分）系统性误切**。⚠️ 这是 29% 抽样 + reason 自证（部分循环）下的近似，不是全量绝对率。

---

## 4. 套 runbook 门槛 → 裁决

| runbook 门槛 | 能否套用 |
| --- | --- |
| ≤2% 且 grading≤1% → 维持 | **不能机械判定**：无全量绝对率；但判别子集**未见高危批改误判**，无"系统性误判分"证据。 |
| 2–5% → 缩 scope | 候选误切（类 A 切新题）量级落在个位数%，但样本/方法限制不足以触发缩 scope。 |
| >5% 或 grading>2% → 回退 | **无证据触发**：未见系统性或高危误切。 |

**裁决：维持 primary（不回退、不缩 scope），但不宣称"已验证安全"。** 理由：未见系统性/高危误切证据，回退无依据；但当前 instrumentation 给不了可信全量数字，"安全"是未证实而非已证实。

**两个并行动作（择一或都做，仍属后续"调 flag/补码"步骤，本只读报告不执行）**：
- **(优先) 补 instrumentation**：把 `(raw_user_input, final_capability, semantic_router_mode, drove_route:bool)` 作为稳定对落进可查存储（现在 router 遥测仅 Langfuse、消息 join 不可靠、决策≠路由不可分）。补完即可对真实流量出可信全量误切率，无需开 shadow。
- **(可选) Path B shadow**：开 `SHADOW_MODE`（legacy 主用+新路由影子）跑一段→rollout report 出"新 vs 老分歧率"。代价见 runbook §3（行为退回 legacy、给分歧非对错）。

**两类候选误切交产品复核**（不依赖基线数字即可推进）：
- 类 A：用户在已有活跃题时引入**新题/新卷主题**，应优先切新对象（出题/检索）而非对旧题 followup/批改。
- 类 B：开放对话里的**概念解释类提问**默认 route_to_generation 是否合理（确认是否真产生"答非所问"的出题，而非解释）。

---

## 5. 置信度局限（必读）
- **抽样**：判别性标注基于 90/313（29%），非全量；候选误切类的频率是粗略量级，非精确率。
- **方法循环性**：用 router 自己的 `reason` 当输入信号判 router 对错，无法捕捉"router 误读了输入"的错（它若把 A 听成 B，reason 也写 B）。真·绝对率需独立的 (raw_input, capability) 对。
- **join/记账噪声**：35% 无消息、40% 非判别兜底、18% 决策未驱动路由——这些已从判别子集中剔除，但说明全量"误切率"在当前数据上不可信。
- **数据时段**：单库快照（messages=6985 / turn_events=299376），未做时间分段；内测早期样本，分布会随用量变。

---

## 6. 关联文件 / 取数面
- runbook：[2026-05-30-semantic-router-baseline-runbook.md](2026-05-30-semantic-router-baseline-runbook.md)
- 决策单：[2026-05-30-prod-state-and-flag-flip-decision.md](2026-05-30-prod-state-and-flag-flip-decision.md)（#8）
- 代码：`deeptutor/services/semantic_router.py`（决策构建）、`deeptutor/runtime/orchestrator.py:248-320`（lifecycle 先于 semantic router）、`deeptutor/services/session/turn_runtime.py:4461-4482`（router 遥测仅发 Langfuse）、`scripts/report_semantic_router_rollout.py`（shadow-only）
- 取数面：阿里云 `/root/deeptutor/data/user/chat_history.db`（只读 `mode=ro`；`turn_events.turn_semantic_decision` 313 条 / `turns.capability` join）

---

*本报告为 2026-05-30 只读核验快照，仅含聚合统计与脱敏样例。所有后续动作待人工在独立步骤执行；本报告未改任何 flag/库/部署，未将任何原始用户消息写入仓库。*
