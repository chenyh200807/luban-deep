# Task 5 执行计划 — TerminalResultAssembler 单一可见输出权威迁移

> **状态**: Child execution plan of [2026-06-26 控制面收权 umbrella](2026-06-26-fast-mode-orchestrator-simplification-architecture-plan.md) §Task 5。
> **为什么单列**: Task 5 是新组件 + 跨 6 capability 文件的 RESULT 构造迁移 + reveal 3→1 收敛,plan 明文需 live≥3 验证。**不能单会话完成**;本文件把它拆成有序、每片带 live gate 的分片,使多会话工作 ready-to-run。
> **基线**: code-grounded on 0d7412b4b(= main + Task0-2-4 + live-shadow,Task 4 已删 scene pre-stamp)。

## 0. 现状(investigator 2026-06-26 实证)

**RESULT writer ~12 处**(stream_bus.py:241 `stream.result()` 是唯一原语;每个 contentful writer 直接调它):
- tutorbot.py:280, :656
- deep_question.py:4677(`_emit_result_with_citations`,已收 9 内部 caller:4267/4321/4457/4540/4644/5272/5332/5380)+ deep_question.py:5176(第二直接)
- deep_solve.py:261 / math_animator.py:181 / deep_research.py:303,:345 / visualize.py:123
- agents/chat/agentic_pipeline.py:2525 / api/routers/co_writer.py:352
- agents/notebook/analysis_agent.py:62(**手搓 StreamEvent(RESULT) 经 EventSink 回调,非 StreamBus**——特殊,见 §3 slice 注意)

**reveal 3 evaluator 语义不同**(收敛=行为改动需 live,反例已证):
- A tutorbot._reveal_reference_flags(:860):preference 短路 + overrides,**无 unanswered-block**
- B deep_question overrides(:4147):question_review_mode → 无条件 reveal=True,**无 preference**
- C should_reveal_reference_material(question_followup.py:1208):preference + explicit marker + **unanswered-block**
- 共享底层 marker predicate `detect_answer_reveal_preference`(:666)已收敛;上层组合语义不同。
- 三者处数据流串行不同阶段(generation-write B → persist → followup-read C;A 另一 generation-visible 路径)。

**§6 安全带(保留)**: unified_ws._redact_*(unified_ws.py:351-454)last-mile redaction,与 evaluator 解耦,任何迁移都不碰。

## 1. §3 creation gate 约束

引入 TerminalResultAssembler(新 carrier)必须伴随 production writer 删除/降级,净 authority 下降。**单 capability 迁移不满足**(assembler +1,只迁一个 RESULT writer -1 = 净 0)。所以授权下降只在**全部 12 site 迁完 + 直接 stream.result 调用清零**时成立。本计划末片才宣称 Task 5 authority 收口。

## 2. 分片(有序,每片独立可 commit + 各自 gate)

### Slice 5.1 — 引入 assembler 骨架 + 迁移无 reveal/grading 的 leaf capability(确定性 behavior-preserving)
- 建 `deeptutor/core/terminal_result_assembler.py`:`TerminalResultAssembler.emit(stream, payload, *, capability_name, reveal_decision=None)` —— 唯一 `stream.result()` 调用点;byte-identical 包装(同 type/source/`merge_trace_metadata(data,metadata)`)。
- 迁移 **deep_solve.py:261 / visualize.py:123 / math_animator.py:181 / deep_research.py:303,345**(非 grading 非 reveal,result_payload 简单)。
- **gate**: 每个迁移 capability 的现有测试 byte-identical 通过 + same-SHA WS;异源(DeepSeek+GLM)验 byte-identical。**不减 authority(assembler 未收口),是 foundation**。
- **注意 analysis_agent.py:62**: 它走 EventSink 回调非 StreamBus,需先给 NotebookAnalysisAgent 注入 StreamBus 或 assembler 适配 EventSink —— 单独评估,可能延后。

### Slice 5.2 — chat / co_writer 迁移
- agentic_pipeline.py:2525 / co_writer.py:352 经 assembler。
- gate 同 5.1。

### Slice 5.3 — deep_question RESULT 迁移(grading 路径,**需 live≥3**)
- deep_question.py:4677(`_emit_result_with_citations`)+ 5176 经 assembler。`_emit_result_with_citations` 已是 in-capability assembler(收 9 caller),迁移=把它的 citation+content 组装搬进 TerminalResultAssembler 或让它委托。
- **gate**: hard corpus + **live≥3 行为回归**(grading verdict/citation byte-identical;E8 题组塌缩 SEV-1 不回归)+ 异源验 + 持久化终态核对(memory:判分类改终态非流式)。

### Slice 5.4 — tutorbot RESULT 迁移(reveal 路径,**需 live≥3**)
- tutorbot.py:280, :656 经 assembler。
- **gate**: reveal flags byte-identical + hidden-answer 泄露=0(payload/citation/wechat card/body)+ live≥3 + 异源验。

### Slice 5.5 — reveal 3→1 收敛(**最高风险,需 live≥3 + 异源 + 反例语料**)
- 把 A/B/C 三 evaluator 的上层组合统一进单一 canonical reveal writer(其他只读)。**必须先决定统一规则**(question_review 强制 vs preference 短路 vs unanswered-block 谁优先)——这是行为决策,需 owner + eval。
- **gate**: 对 investigator 的 2 反例语料(question_review+"先别给答案" / preference=True+未作答)+ 全 reveal 语料,证收敛后行为=有意设计的统一规则(非意外回归);hidden-answer 泄露=0;live≥3;DeepSeek+GLM 异源 + 反例驱动。**reveal 错=答案泄露 recurrence-prone,门槛最高**。

### Slice 5.6 — 收口 + authority 宣称
- 全部 12 site 迁完 → 直接 `stream.result()` 调用清零(除 assembler) → RESULT writer N→1 + reveal 3→1。
- 更新 control_plane_writers allowlist:visible_result/reveal 条目收敛;`authority_count_after < before` 实测。
- ACK/PROGRESS 零领域 payload 静态门(已有 live-shadow guard dormant arm)接通。
- same-SHA replay + hard corpus + 微信 true-entry + 异源最终验。

## 3. 不变量(贯穿所有片)
- observe-only/byte-identical 优先;任何行为改动(reveal 统一规则)需 live≥3 + 异源 + 反例语料。
- §6 redaction(unified_ws._redact_*)保留不变。
- 每片独立 commit;5.3/5.4/5.5 不得在无 live 验证下宣称完成(memory:harness 流式≠终态,判分/泄露类核持久化终态)。
- 异源红队用 DeepSeek V4 Pro + GLM-5.2(非 Claude,同源盲点)。

## 4. 完成判据(umbrella §6.5)
末片 5.6:RESULT writer 1 + reveal writer 1 + authority_count_after<before + hidden-answer 泄露=0 + same-SHA replay + 微信 true-entry + 异源 GO。telemetry/progress/ack 不冒充 closure。
