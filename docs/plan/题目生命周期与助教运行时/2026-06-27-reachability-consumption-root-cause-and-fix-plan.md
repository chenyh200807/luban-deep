# 控制面三家族 SEV-1 真根因 + 治本计划（reachability/consumption 病）

> **状态**: 专家团队（3 家族根因专家 + 1 宏观指挥官）root-cause-debugging 方法论裁决产物，基线 13683a29c。这是 owner 拍板用的强化修复计划。
> **触发**: 回指错绑 / 判分错 / 答案泄露三类反复复发 SEV-1，"为什么这么难修"的系统性反思。
> **三大原则**: thin wrappers fat skills / first principles / less is more。绝不治标。

## 病因一句话（first principles，不含模块名）

> **系统已把"该信什么"判定为单一权威，但没有保证"每个出口都被那份权威喂到 / 读到"——canonical 真值算对了，却在传播链的某些分叉上要么没注入（下游现编第二份），要么没被消费（下游空转无视它）。病不在"算不出真值"，而在"真值的到达性(reachability) 与被消费性(consumption) 没有结构性保证"。**

这是 root-cause skill 里 `dormant authority`（空转门）+ `unconsumed island`（孤岛）+ `multi-writer across lifecycle`（第二 writer 覆盖）三个 shared failure shape 的合体。

## 为什么这么难修（反思结论）

**我们（和历次计划）一直在找"缺的组件"或"要合并的重复"——但权威大多已建好且正确。真正难的是收权的后半程：保证每个出口被 canonical 真值到达 / 消费。这种病没有显眼的缺失物，只在具体分叉上以 bug 形式冒头，所以反复打地鼠。** 这也解释了为什么 S3/S4/S5 每次 investigation 都推翻"简单收敛"的 premise——premise 在找错的东西。

**"缺显式题目生命周期状态机"假设被三家族 + 指挥官独立证伪**：状态机（active_object/version/state_snapshot/apply_active_object_transition、RevealDecision、graded surface 锚定）都已存在且健全。加状态机 = 新增 authority，违 less is more。

## 架构裁决：1 主病 + 1 内容真相病

**主病 = authority 碎片化的特定亚型「canonical 已建，旧第二权威未退役 / dormant 权威未接线」**：

| 家族 | canonical 权威（已建健全）| 病灶（未退役/未接线）| shape |
|---|---|---|---|
| 回指 | orchestrator canonical decision（主链路已走 _route_via_canonical_decision 单点）| preselect 路径(orchestrator.py:425-433)不注入 canonical → deep_question 现编 _default_turn_semantic_decision(:3792) + S5/S6 无条件 build(:4538/4621) | multi-writer + dormant |
| 判分 | graded surface（question_id 粒度锚定）| **option 面字母序未独立锚定**（同 question_id 重排被整份覆盖 active_object_builder.py:208）+ 两套 value-projection 补丁(deep_question.py:821/historical_questions.py:262) | producer/consumer 粒度 |
| 泄露 | RevealDecision（per-item 正确，结构层已消费）| **自由文本层全空转**: coerce_user_visible_answer(user_visible_output.py:156)不读 reveal + prompt 闸(teaching_modes.py:667)gate 错信号 + continuity 注入(:226)无条件灌未答题干 + TerminalResultAssembler 自承不消费(:24) | dormant + island |

**内容真相病（指挥官修正了家族报告）= 「没有真值源的考点」覆盖率问题，非编造失控**：运行时 fail-closed 硬闸**已存在**（runtime_llm_adjudicator.py:346/392 未知点 fail-closed needs_review；open_world_diagnostic.py:198 有官方分 pack 跑 open-world 直接 raise）。所以现编采分点冒充官方分**已被兜住**；残留风险是没真值源的考点学生拿到 unverified 体验。优先级低于报告暗示。

## 共同收口：无一招通吃，但共享同一治法模板可并行

三家族共享抽象动作「把 canonical 权威的『保证存在/被消费』从分散补丁收成结构性保证」，但落两个链路位置：
- **入口侧（保证存在）**: 回指——canonical 必须在所有到达 deep_question 入口注入。
- **出口侧（保证被消费）**: 泄露——RevealDecision 必须在所有可见出口被读。
- **粒度侧**: 判分——锚定粒度从 question_id 降到 option-surface。

三个独立收口，互不耦合 → **可并行**。都是"连接已有件 / 退役第二 writer"，无一新建治理。

## 实施序（从病因排，低→高风险）

### 动作 1 — 泄露出口侧接线（低风险，纯接线，SEV 安全/反作弊优先）
- **one fact**: 任何学生可见文本（结构化+LLM 自由文本）不含未作答题答案。
- **one authority**: RevealDecision(question_followup.py:689)，已是单一裁决，**不新建**。
- **delete/demote**: get_practice_generation_instruction(teaching_modes.py:667) 错信号 gate（"本轮出题"→"context 有未答题"）；TerminalResultAssembler slice-4 占位改真消费。
- **why not old**: split-brain，再加文本扫描正则 = 把语义降级成模式匹配（skill 明禁），永远漏新形态。
- **why this layer**: RevealDecision 是已算好的语义真值，在单一可见 sink coerce_user_visible_answer(user_visible_output.py:156)消费 = 结构性保证。
- **file:line**: user_visible_output.py:156（sink 加 reveal_decision 参数据此遮蔽）/ teaching_modes.py:667（gate 信号改）/ teaching_modes.py:226（continuity 注入加 per-item reveal guard）/ terminal_result_assembler.py:54（真 interpret）。
- **验证**: unit + live≥3 轮终态（拉 /api/v1/conversations/{cid}/messages 核终态不信流式）+ 学生军团。
- **风险**: sink 高频汇点改签名扫全 call site；遮蔽过度伤已答题（用 per-item）。
- **替代（不确定性）**: continuity 注入直接过滤伤连续性不变量。**替代=不删注入，给未答题答案位打 reveal-masked 标记**（主 LLM 看题干不看答案），需 Langfuse dump 注入文本实际形态后定。

### 动作 2 — 回指入口侧：canonical 必达 + deep_question fail-fast（中风险，先 7 天 shadow 观测）
- **one fact**: 每个到达 deep_question 的 turn 带 orchestrator 签发的 canonical turn_semantic_decision。
- **one authority**: build_turn_semantic_decision / orchestrator（turn.md 硬约束 24）。
- **delete**: deep_question _default_turn_semantic_decision(:3792) + 9 处 `or build_turn_semantic_decision` + S5/S6 无条件 build(:4538/4621)，改 fail-fast 只读。
- **why not old**: 现编=第二 writer（canonical 在场 S5/S6 仍现编）；加"检查 canonical 在不在"的门=第 N+1 decider。
- **file:line**: orchestrator.py:425-433（preselect 补注入镜像 :270-289）/ deep_question.py:3792/4538/4621（删现编 fail-fast）。
- **验证**: **先保留 task#12 step2 shadow 观测 7 天**（Langfuse control_plane_shadow_hits 确认 preselect 是唯一 canonical_present:False 来源再删，原作者注释就是这意图）+ live≥3 轮回指。
- **风险**: 盲删兜底若有未观测入口漏注入→fail-fast 伤可用性。必先 shadow 证明 preselect 唯一漏点。
- **替代**: 弱区 #9 省略指代/#11 否定回指——**不扩 regex marker**，确认 is_unresolved_switch_followup 把低置信 fall-through 主 LLM（§6 安全带）用共享历史消歧。

### 动作 3 — 判分 option 面锚定（高风险，异源核）
- **one fact**: 判分比对的 option-letter↔value 面=学生当前题面真实经历那份，首次生成后只读。
- **one authority**: turn-START 锚定的 graded surface（现锚 question_id，扩到 option-surface）。
- **delete**: 最终删两套 value-projection 补丁(deep_question.py:821/historical_questions.py:262)。
- **file:line**: active_object_builder.py:208（same_identity 真时不覆盖 option 序）/ deep_question.py:5587 / mcq.py:100 / question_followup.py:1245（三 decider 统一读锚定面）。
- **验证**: unit（"bot 出题→对话内重排→再判"比对首锚序）+ live≥3 + **异源核**（DeepSeek/Codex，判分改动同源判官有盲点）。
- **风险**: 最高。改 judging 锚定语义回归面覆盖所有判分路径，锚错误判学生（task#20 簇 A 姊妹路径仍破）。
- **替代**: 三 decider 语义不同（mcq 集合/case 关键词/followup 字母值）**不强行合**，只统一它们读的『锚定面』来源（收锚定权不收比对逻辑权）。

## 红线 / 伪进展清单

1. 🚫 自由文本加答案扫描正则堵泄露（挡 literal 漏语义打地鼠）→ 接 RevealDecision。
2. 🚫 deep_question 加"canonical 在不在"检查门（第 N+1 decider）→ orchestrator 保证注入 + fail-fast。
3. 🚫 回指弱区再补 marker regex（语义降级模式匹配）→ 低置信 fall-through 主 LLM。
4. 🚫 判分只加 projection 补丁不改锚定（加深 patch）→ 改锚定粒度。
5. 🚫 跳过 task#12 step2 的 7 天 shadow 观测盲删兜底→ 先 OBSERVE 哪些 live 路径漏 canonical。
6. 🚫 内容真相病用收权/正则治（黑名单冒充）→ 补内容源。
7. 🚫 harness 流式判"修好了"（流式取剥前预览）→ 拉持久化 assistant content 核终态。

## 不确定性 + 取证方案

| 不确定项 | 取证 |
|---|---|
| preselect 是否回指唯一漏 canonical 入口 | Langfuse 挖 control_plane_shadow_hits 的 canonical_present:False site/scene 分布（已埋点采集中）|
| continuity reveal guard 是否伤连续性 | dump 实际注入文本，验 reveal-masked 标记 vs 直接过滤 |
| 判分三 decider 能否共一锚定面 | 独立核三者读的 surface 来源可否统一单一锚 |
| 三家族 live 真生效 | 学生军团 + 异源判官（同源有盲点）每族≥3 轮核终态 |

## 一句话

三家族是**同一主病**（收权只做了一半——canonical 已建，第二权威没退役/dormant 门没接线）的三个症状 + 一个**已被 fail-closed 兜住**的内容真相病（覆盖率问题非编造失控）。无一招通吃，但三收口共享"接通已有件、退役第二 writer、绝不新建第三门"纪律可并行。序：泄露（低，纯接线）→回指（中，先 7 天 shadow）→判分（高，改锚定+异源核）。**每步减 decider，不加门。**
