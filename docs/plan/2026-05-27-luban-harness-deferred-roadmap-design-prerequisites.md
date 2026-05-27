# 鲁班 Harness — Deferred Roadmap (D1–D5) 前置设计规范

> **归属**：[`2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md`](./2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md) §4 Deferred Roadmap 的**前置设计交付物**。
>
> **本文档不是实现，也不解冻 §4**。它把执行计划点名的"前置条件"（D2 stream-trace 兼容规范、D4 prompt-partition 设计等）落成可审查的设计，使 D1–D5 在 gate 打开（**P0 完成 + launch-readiness/assessment 主线稳定 + keyed 环境可验收**）后能直接进入实现，而不必临场再补设计。
>
> **硬边界**：每个 D 项的**实现**仍受执行计划 §4 gate 约束；本文只交付离线可验收的设计，不动 risky harness/contract 代码。

**Status:** Design-only（前置规范，实现仍 deferred）
**Date:** 2026-05-27
**核对基线:** main @ `9ba55cc1`（行号均经现网核实；计划原引用行号已多处漂移，本文用核实后的锚点）

---

## 0. 共同实现 gate（所有 D 项适用）

任一 D 项进入**实现**前必须同时成立：

1. **P0 完成** ✅（已达成：golden + 两 gate + scene 收权 + 矩阵 + guard）。
2. **launch-readiness / assessment 主线稳定**（外部条件，见 `2026-05-25-prelaunch-readiness-checklist.md`）。
3. **keyed 运行环境可用**：D2/D4/D5 的验收（replay 断言、KV 命中率、轨迹 eval）必须跑真实两壳管线，本地无 LLM key 时**不得声称完成**（与执行计划 §0 用户决策一致：离线只能做决策层 golden）。
4. 该 D 项的本文档设计章节已 review 通过。

---

## D1 — 共享 fat-skill 抽取（替代 v1 "统一 kernel"）

### 目标
把 P0 矩阵确认的**真正共享**的 policy 抽成两壳都调用的 fat skill；**保留** chat 同步壳 / tutorbot 自主壳两个执行模型，**不做单一 kernel**。

### 现网锚定（已部分实现，避免重复造）
- **scene→skill 指令构建：已经是共享 fat skill**。P0.2 之后两壳都走 `deeptutor/services/question_lifecycle_skills.py::build_question_lifecycle_skill_context`（chat `agentic_pipeline.py::_question_lifecycle_skill_instruction`；tutorbot `loop.py:1834`）。**D1 这部分已落地，不需重做。**
- **grounding 决策 / exact 内容**：P0 矩阵结论是**单一 authority 已共享**（`query_intent` / `exact_authority`），两壳差异是**有意 surface 分叉**（chat 同步只读 `should_force_retrieval_first`+LLM rewrite；tutorbot 预取编排+确定渲染）。

### 前置交付物（设计）
- D1 的剩余候选**很小**：只有"是否把 prefetch 编排骨架 / exact 呈现选择"抽成共享 policy 接口。矩阵已判定它们是有意分叉 → **默认不抽**；只有当未来出现第三个执行壳、或两壳 prefetch 逻辑开始字面重复时才抽。
- 若要抽：fat skill 接口形如 `resolve_turn_execution_policy(ctx) -> {grounding_decision, exact_decision, scene_skill_context}`（**只读 authority 的聚合 reader**，不新增判定），两壳各自决定**如何消费**（同步 vs 预取）。

### 实现 gate
§0 全部 + 出现"两壳 prefetch/exact 消费逻辑字面重复"的实证触发条件（否则按矩阵保持有意分叉，不抽）。

---

## D2 — chat 有界迭代（仅显式 deep mode 多跳）

### 目标
仅对**显式 deep mode** 引入有界多跳；smart/fast 默认单轮不变。

### 现网锚定（核实）
- **WS 事件词汇**（`deeptutor/core/stream.py:17 StreamEventType`）：`stage_start / stage_end / thinking / observation / content / tool_call / tool_result / progress / sources / result / error / session / done`。迭代化**不得新增**用户可见事件类型，也不得改变同一 turn 内的事件**相对顺序契约**。
- **terminal / active_object 抽取**（`deeptutor/services/session/turn_runtime.py`）：`_build_terminal_turn_observation_event`（:379）、`_sanitize_public_terminal_event`（:339）、`_safe_terminal_assistant_content`（:290）、active_object 引用 `_active_object_ref`（:533）。多跳会产生多段 content / 多轮 tool —— **terminal 抽取必须仍只认最终一段 assistant content + 最终 active_object**，不能因为多跳出现多个 terminal 候选。

### 前置交付物（设计：stream trace 兼容规范 + replay 断言）
1. **兼容规范**：定义"deep-mode 多跳 turn"的合法事件序——多组 `(thinking* tool_call tool_result)` 后收敛到**单个** `result` + `done`；`sources` 聚合所有跳的来源；不得出现第二个 `result`。
2. **replay 断言**（待 keyed env 落测）：对一组 deep-mode case 断言 (a) 事件序符合上述规范；(b) `turn_runtime` terminal 抽取的最终 content / active_object 与单轮语义一致；(c) smart/fast case 事件序**逐字节不变**（回归保护）。
3. **回滚**：deep 多跳由显式 flag 控；flag 关闭后事件序必须退回当前单轮 golden。

### 实现 gate
§0 全部 + 本节兼容规范 review 通过 + replay 断言在 keyed env 跑绿（含 smart/fast 无回归）。

---

## D3 — 可恢复压缩 + 工具产物外置

### 目标
用"大产物落盘留指针 + 按需回取"替代不可恢复截断，让长对话/大工具输出不丢上下文。

### 现网锚定（核实）
- chat 已有 task workspace：`agentic_pipeline.py:1727 get_path_service().get_task_workspace("chat", turn_id)`、`code_runs` 目录（:1777）。
- 截断点：上下文层 `deeptutor/services/session/context_{budget,pack}.py`（P0 不动）。

### 前置交付物（设计）
- `read_artifact(pointer)` 工具契约：大工具产物（>N tokens）写入 turn workspace，上下文里只留 `{artifact_id, summary, size, pointer}`；LLM 需要全文时调 `read_artifact` 回取。
- 压缩**可恢复**：被压缩段必须留 pointer，不得物理丢弃；恢复路径 = pointer → workspace 文件。
- 与 contract 关系：pointer/artifact 只是 evidence_bundle / metadata 内的 compact 字段，**不新增流式入口**，不改 turn/replay 对外语义。

### 实现 gate
§0 全部 + artifact 存储与 `context_budget` 的交互设计 review + 离线可对"压缩→回取语义等价"做单测（这部分**可离线验**，不强依赖 keyed env）。

---

## D4 — KV-cache 稳定前缀（prompt partition 设计）

### 目标
把每轮 prompt 切成**稳定前缀 + 动态尾部**，让稳定前缀命中 KV-cache，降首 token 延迟/成本。

### 现网锚定（核实——计划原引用行号已漂，以下为现网实际）
两壳都**每轮动态拼整段 prompt**：
- chat `agentic_pipeline.py`：`tool_table = registry.build_prompt_text(...)`（:1156）、`context.memory_context`（:1363）、各 stage system prompt（`_acting_system_prompt` :1790 / `_responding_system_prompt` :1919）、scene skill（:2883）。
- tutorbot `context.py:build_system_prompt`（:36）：identity + bootstrap files + memory（:49）+ always-skills（:53）+ skills_summary（:59）。
  （计划原写的 `loop.py:2431` 已漂，那里现为 guardrail/refusal；真正的 skill 拼装在 `context.py:36`。）

### 前置交付物（设计：prompt partition）
- **稳定前缀候选**（turn 间不变 → 可缓存）：身份/角色、markdown/style 规则、（工具集稳定时的）tool_table、always-skills。
- **动态尾部**（每轮变）：memory context、lifecycle scene skill、当前 user turn、active_object。
- 设计产物：为两壳各定义 `partition_prompt(ctx) -> (stable_prefix, dynamic_tail)` 的边界规则 + 不变量（稳定前缀不得含 user/turn/memory 派生内容，否则破坏缓存且可能泄漏跨 turn 状态）。
- 命中率必须可观测：进 Langfuse（与既有 `rag.supabase.search` observation 同源，不新增 sidecar）。

### 实现 gate
§0 全部 + partition 不变量 review + KV 命中率指标在 keyed env 跑出基线（本地无 key 验不了，**不得提前声称完成**）。

---

## D5 — 轨迹级 eval 扩容 + model-swap 单点抽象

### 目标
把 P0.1 决策层 golden 扩到**轨迹级**（tool 序列 / 多跳 / 最终输出），并把换模型收敛到**单点**改 catalog/config。

### 现网锚定（核实）
- 决策层 golden 已有：`scripts/run_harness_authority_baseline.py` + `deeptutor/services/benchmark/fixtures/harness_authority_decision_golden.json`（P0.1）。
- benchmark 轨迹层入口：`scripts/run_benchmark.py`（`--api-base-url` → live_ws，否则 in_process_runtime，均需 LLM）。
- guard 已有：`scripts/check_harness_authority.py`（P0.5）。

### 前置交付物（设计）
- 轨迹 golden 扩容方案：在 keyed env 下，为 deep-mode（D2）/ prefetch（grounding）/ exact 按题型采 tool 序列 + 最终可见输出 golden，接 `eval/gates.yaml` deep gate（区别于 P0.1 的 quick 决策层 gate）。
- model-swap 单点：模型选择只允许改 `catalog/config` 一处；guard 升级断言"无散落的硬编码 model id"（可复用 `check_harness_authority.py` 的静态扫描骨架，**这部分可离线实现+验**）。

### 实现 gate
§0 全部；其中 model-swap 单点 guard **可离线先做**，轨迹 golden 扩容需 keyed env。

---

## 汇总：哪些"前置"其实可离线先落地（不破 gate）

| 项 | 可离线先做的部分 | 状态 / 仍需 keyed env / gate 的部分 |
|---|---|---|
| D1 | （scene-skill 共享已由 P0.2 落地） | 其余按矩阵保持有意分叉，触发条件未到不抽 |
| D2 | 兼容规范文档（本文） | replay 断言落测（需 keyed env） |
| D3 | `read_artifact` 契约 | **决定保持设计态（2026-05-27）**：现在建原语=未接线投机抽象 + 概念重复，违反 §2/§Concept Discipline，故不建；实现等接进 context_budget（gated）再做 |
| D4 | partition 边界规则 + 不变量文档（本文） | KV 命中率基线（需 keyed env） |
| D5 | **model-swap 单点 guard + inventory** | **已落地（2026-05-27，commit `c45713a6`）**：`scripts/check_model_authority.py` + `model_authority_guard` quick gate（守默认单点 + 债务 inventory）；轨迹 golden 扩容仍需 keyed env |

> plan-owner 决策（2026-05-27）：D5 的离线 guard **已落地**；D3 离线原语**决定不建**（投机抽象，保持设计态）。其余 D1–D5 实现仍受 §0 gate + keyed 环境约束。本文档仅交付设计，不自动启动剩余实现。
