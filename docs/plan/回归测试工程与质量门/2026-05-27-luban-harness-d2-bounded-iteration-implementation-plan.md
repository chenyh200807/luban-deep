# 鲁班 Harness — D2 chat 有界多跳 实施计划（PR-ready）

> **归属**：[`2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md`](2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md) §4 Deferred D2 的**可执行实施计划**。前置设计见 [`2026-05-27-luban-harness-deferred-roadmap-design-prerequisites.md`](2026-05-27-luban-harness-deferred-roadmap-design-prerequisites.md) §D2。
>
> **为什么单独成 PR**：D2 改的是 `/api/v1/ws` 生产 turn flow（`AgenticChatPipeline.run`），触 CONTRACT.md / turn 契约，爆炸半径大、验收需大量真实 deep-mode 运行。本文把它拆成**小步、可回滚、每步真实验收**的 PR，安全网（D5 deep-mode 轨迹断言）已先行落地（commit `f822ebb6`）。

**Status:** Plan（实现待专门 PR）
**Date:** 2026-05-27
**前置已就位**：stream-trace 兼容规范（前置设计 §D2）+ D5 deep-mode replay 断言（`harness_trajectory_eval` 的 `deep_mode_single_terminal_result` case）。

---

## 1. 目标 / 非目标

**目标**：仅对**显式 deep mode**（`context.config_overrides["chat_mode"] == "deep"`）引入**有界多跳**——允许 `acting → observing` 在 deep 模式下迭代最多 `N` 轮（默认 N=2），让模型在看到工具结果后可再规划一轮工具，再进入单次 responding。

**非目标**：
- smart / fast / answer_now / greeting / retrieval_first 路径**一律不变**（单轮）。
- 不改 WS 事件类型集合（13 种，`core/stream.py:StreamEventType`），不新增用户可见事件。
- 不改 `_emit_sources_and_result` 的"单次终态发射"语义——多跳后仍**只发一个 RESULT**。
- 不改 turn/replay/resume 对外 contract。

## 2. 现状（code-verified @ `f822ebb6`）

`AgenticChatPipeline.run`（`agentic_pipeline.py:210`）主路径是**固定多阶段、单轮**：

```
thinking(:302) → acting(:303, _run_native_tool_loop 单轮一次 create) → observing(:310) → responding(:319) → _emit_sources_and_result(:328)  ← 唯一 RESULT
```

- `_run_native_tool_loop`（:906）：一次 `client.chat.completions.create(tools=...)`，执行该轮 tool calls，返回 `tool_traces`。**无 round 循环**。
- `_emit_sources_and_result` 聚合 sources + 发射单个 RESULT 事件。
- terminal / active_object 抽取在 `turn_runtime.py`（`_build_terminal_turn_observation_event` / `_sanitize_public_terminal_event` / `_active_object_ref`）：认**最终一段 assistant content + 最终 active_object**。

## 3. 改动设计

在 `run()` 的 `acting → observing` 段（:302-318）包一层**有界循环**，仅 deep mode 生效：

```python
rounds = self._deep_iteration_rounds(context)   # deep→FF_CHAT_DEEP_MAX_ROUNDS(默认2);其余→1
accumulated_traces: list[ToolTrace] = []
thinking_text = await self._stage_thinking(...)
for round_idx in range(rounds):
    round_traces = await self._stage_acting(context, enabled_tools, thinking_text, stream)
    accumulated_traces.extend(round_traces)
    observation = "" if skip else await self._stage_observing(..., tool_traces=accumulated_traces, ...)
    if not self._deep_wants_another_round(round_traces, round_idx, rounds):
        break
    thinking_text = observation  # 下一轮 acting 以上一轮观察为输入
final_response, responding_trace = await self._stage_responding(..., tool_traces=accumulated_traces, observation=observation, ...)
await self._emit_sources_and_result(..., tool_traces=accumulated_traces, ...)   # 仍单 RESULT
```

新增**单一职责**的两个 helper（薄、可测）：
- `_deep_iteration_rounds(context) -> int`：deep 且 FF 开 → `FF_CHAT_DEEP_MAX_ROUNDS`（clamp [1,3]，默认 2）；否则 1。**FF 关或非 deep → 恒返回 1 = 当前行为**（这就是回滚开关）。
- `_deep_wants_another_round(round_traces, idx, rounds) -> bool`：仅当本轮真的产生了工具调用且未达上限时才继续；否则停。**deterministic，不靠 LLM 再判**。

> 单一 authority 守则：多跳是**执行壳的编排**，不引入第二套 scene/grounding/exact 判定（仍只读既有 authority）。`accumulated_traces` 是跨轮聚合的唯一来源，sources 去重在 `_emit_sources_and_result` 既有逻辑内完成。

## 4. WS 事件契约不变量（D2 必须保持，D5 deep-mode case 已守）

1. 一个 turn **恰一个 RESULT** 事件（多轮 acting/observing 后只 responding 一次）。
2. 事件序 well-formed：`stage_start` 开头，最后一个有意义事件是 `result`；**不出现第二个 result**。
3. 多轮的 `tool_call/tool_result/observation` 允许重复出现，但 `sources` 在终态聚合去重。
4. turn_runtime terminal 抽取仍只认**最终 responding 段**的 content / active_object（多轮中间 content 不得被误当 terminal）。
5. smart/fast/其余路径事件序**逐字节不变**（回归保护）。

## 5. 分步 PR（每步独立、可验、可回滚）

| 步 | 改动 | 验收 |
|---|---|---|
| **S1** | 加 FF `FF_CHAT_DEEP_MAX_ROUNDS`（默认未设=1）+ `_deep_iteration_rounds` / `_deep_wants_another_round` 两 helper（纯函数）| 单测:deep+FF→2、非 deep→1、FF 关→1、达上限/无工具→停 |
| **S2** | run() 主路径把 acting→observing 包进有界循环,`accumulated_traces` 跨轮聚合;**FF 默认关时逐字节等价当前单轮** | 单测:FF 关时 messages/stage 调用序与改前一致;`tests/agents/chat/` 全绿 |
| **S3** | 开 FF,真实 deep-mode 多跳跑 | `harness_trajectory_eval` deep-mode case 仍 PASS(单 result/well-formed);新增"强制触发 2 轮工具"case 断言 tool_call 出现 ≥2 次但仍单 result |
| **S4** | turn_runtime terminal/active_object 在多段 content 下的回放断言 | `tests/api/test_unified_ws_turn_runtime.py` + 多跳 replay:terminal 取最终段 |
| **S5** | smart/fast 回归 + Langfuse trace 检查多跳不污染 RAG 使用计数 | smart/fast 轨迹 golden 不变;Langfuse 观察单 turn 单 result |

## 6. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 多跳破坏单 RESULT 契约 | S3 用 D5 deep-mode 断言守;违反即红 |
| 中间轮 content 被误当 terminal | S4 专测 turn_runtime 抽取最终段 |
| 改动泄漏到 smart/fast | `_deep_iteration_rounds` 非 deep 恒 1;S2/S5 逐字节回归 |
| 与后台 main 活动撞车 | 在独立分支/PR 做;合入前 rebase + 重跑全 gate |
| 成本/延迟上升 | 上界 clamp [1,3];FF 灰度;命中率/延迟进 Langfuse 观察 |

**回滚**：`FF_CHAT_DEEP_MAX_ROUNDS` 未设或=1 → 行为完全回到当前单轮 golden,无需 revert 代码。

## 7. 出口 gate

- FF 关:`tests/agents/chat/` + smart/fast 轨迹**逐字节不变**。
- FF 开:`harness_trajectory_eval` deep-mode + 多轮 case 全 PASS(单 result、well-formed、sources 聚合)。
- `tests/api/test_unified_ws_turn_runtime.py` 绿(terminal 抽取正确)。
- `contract_guard` turn+rag 双域绿(改 `agentic_pipeline.py` 需同步 domain 测试 + contract surface,参 P0.2/D4 先例)。
- CONTRACT.md / `contracts/turn.md` 增一条:deep-mode 多跳的合法事件序规范。
