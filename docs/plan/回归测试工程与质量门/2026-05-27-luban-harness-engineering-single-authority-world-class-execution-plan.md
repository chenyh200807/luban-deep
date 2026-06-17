# 鲁班 Harness Engineering 单一权威收敛与世界级化执行计划

> **For agentic workers:** 本计划经 codex 对抗审查后**收缩重写**（2026-05-27）。当前只允许执行 **窄 P0（审计+强制+护栏）**；统一执行壳、chat 迭代化、KV-cache 深改等全部 **deferred**，等 launch-readiness / assessment 主线稳定后再排。任何"新增 router/classifier/interpreter/fallback/state"或"把某个 legacy shim 升级成 authority"的冲动，先过 `AGENTS §5.7` 五问 + 查 `contracts/capability.md`。

**Status:** Proposed（codex-revised：窄 P0 active，其余 deferred）
**Date:** 2026-05-27（v2，对抗审查后重写）
**Owner:** TBD
**主线归属:** 横切「TutorBot 与统一聊天入口」+「上下文与语义连续性」+「Observability 与 release gate」+「Benchmark 主脊梁」+「题目生命周期 skill authority」，不另起平行业务主线。

---

## 0. 北极星与一等业务事实（v2 修正）

**一等业务事实：每个 turn 的"如何执行"——要不要召回、要不要 exact 权威、属于哪个题目生命周期 scene、是否 follow-up——每一项只能有一个 canonical authority；两套执行壳（chat / tutorbot）只能 *读取* 这些 authority，不得各自重判。**

> v1 把收敛目标错放在"统一成一个 `TurnExecutionKernel`"。codex 对抗审查（见文末 REVIEW REPORT）指出：chat 是延迟敏感的同步问答壳，tutorbot 是带 bus / channel / cron / team / heartbeat 的持久自主壳，**SLA 与执行模型本就不同**，硬合并会造出比"重复"更糟的抽象。**修正后的收敛目标是共享 fat skill / authority，而不是共享 kernel**——这才真正符合 `AGENTS §0 thin wrappers, fat skills`：fat skill 是共享的 policy/authority，两个 thin 执行壳可以合法地保留不同执行模型。

### 这套计划如何让"未来模型变强能直接受益"（仍然成立，但靠 deferred roadmap 实现）
模型变强的红利（更长上下文、更强多步规划/工具编排、更少 hand-holding）需要薄壳 + 单一权威 + 干净上下文才能透传。本计划先用 **窄 P0** 把"单一权威"这块地基夯实（删重判、补 trace golden、加 guard），再在地基稳固后按 **Deferred Roadmap** 逐步兑现迭代化 / 可恢复压缩 / KV-cache / model-swap 抽象。**先地基后红利**，不在地基未稳时开大重构。

---

## 1. 目标 / 非目标

### 目标（v2 收缩）
1. **修正并强制 scene 单一权威**：`question_lifecycle_skills` 是唯一 scene→skill authority（`contracts/capability.md` 第 27 条已确立）；删除/降级两套 harness 里对 `teaching_modes.detect_construction_exam_scene` 等 legacy scene 的独立重判，改读 `context.metadata["question_lifecycle_scene"]` / `["question_lifecycle_skill_names"]`。
2. **把 grounding / exact-authority 的真实分叉写成按题型/按表面的行为差异矩阵**，区分"有意分叉（不同 SLA/surface，保留）"与"无意重复（收敛 + 重验）"。**不做"只搬不改语义 / 字节级一致"的承诺。**
3. **补 trace 级 golden eval**（tool 序列 / metadata / sources / authority_applied / visible output），让现有过粗的 benchmark 网能抓住语义回归。
4. **加 authority guard**（`check_harness_authority.py`）防止重判复发。
5. **把统一执行的目标从 kernel 降级为共享 fat skill**，并把迭代化 / 压缩 / KV-cache / model-swap 写成 **Deferred Roadmap**，明确 gating 条件。

### 非目标（本计划明确不做 / 暂不做）
- 不统一成单一 `TurnExecutionKernel`（v1 错误目标，撤销）。
- 不新增聊天 WebSocket 路由（`/api/v1/ws` 唯一入口，硬约束）。
- 不改 turn/session/replay/resume 对外 contract 语义。
- **不在本轮做 chat 迭代化、可恢复压缩、KV-cache 稳定前缀**——全部 deferred（见 §4 Deferred Roadmap）。
- 不把 `capabilities/tutorbot.py` 当"行数下降"目标收薄（它扛 delta gating / authority summary / redaction / active_object 写出等 contract 敏感职责）。
- 不与 learner-state / assessment / launch-readiness 主线争抢同一风险预算。

---

## 2. 单一 Authority 自检（AGENTS §5.7 五问，v2）

| 问题 | 回答 |
|---|---|
| **one business fact** | 每个 turn 的 scene 判定 / grounding 决策 / exact 适用，各是一个独立的一等事实。 |
| **one authority** | scene = `question_lifecycle_skills`（已确立）；grounding = `query_intent.build_grounding_decision`（通用层）；exact = `services/rag/exact_authority`（按题型层）。 |
| **competing authorities（现状）** | 两套 harness 各自重判：`agentic_pipeline.py` 与 `tutorbot/agent/loop.py` 仍调 `teaching_modes.detect_construction_exam_scene`；tutorbot 在 grounding 上叠 bot_id/practice/learner-state scene/web_search prefetch；exact 在两端按不同题型分叉。 |
| **canonical path** | orchestrator 调 authority → 写 turn/trace metadata → 两个执行壳 **只读 metadata** → tools → stream → turn_runtime 持久化。 |
| **delete or demote** | 删两壳里独立的 scene 重判，降级 `detect_construction_exam_scene` legacy shim 调用点；把 grounding/exact 的无意重复收敛到各自 authority。 |

---

## 3. Phase P0 — 审计 + 强制 + 护栏（**当前唯一 active 阶段**）

> 原则：这是审计与收权，不是大重构。每个 Task 独立 commit + 独立验证。

**Task P0.1 — trace 级 golden 基线（先做，防回归网）**
- 背景：codex 指出现网网太粗——`pr_gate_core` 不含 grounding，grounding 只有 4 个静态 case（`deeptutor/services/benchmark/fixtures/rag_grounding_eval_cases.json`），long-dialog gate 只跑 `--max-cases 1`（`eval/gates.yaml:107`）。这张网抓不住 scene/grounding/exact 的语义回归。
- 做什么：为 chat 与 tutorbot 两壳，各采一组覆盖 {grounding 命中、MCQ exact、case_study exact、free_text、construction scene、follow-up、低信息考试查询} 的代表性 case，**冻结 trace 级 golden**：`tool 调用序列 + 关键 metadata（question_lifecycle_decision / scene / selected_skill_names / authority_applied）+ sources + 最终可见输出`。
- 代码入口：`eval/gates.yaml`、`deeptutor/services/benchmark/`、`scripts/run_benchmark.py`、`scripts/run_long_dialog_v1_retest.py`。
- 验收：golden 落 **tracked fixture** `deeptutor/services/benchmark/fixtures/harness_authority_decision_golden.json`（**注意**：`artifacts/` 被 `.gitignore` 排除——"review artifacts must never enter git"，golden 必须进 tracked 路径，gate 才能在全新 checkout/CI 工作）；新增一个能 diff 决策级字段的 harness eval gate；故意改一处 scene 重判 → gate 红（证明网有效）。已落地（2026-05-27）。

**Task P0.2 — scene 权威强制（v1 错误已修正）**
- 一等事实：题目生命周期 scene → skill stack。**唯一 authority = `deeptutor/services/question_lifecycle_skills.py`**（`SCENE_COMPOSITION` + `resolve_question_lifecycle_scene_decision`），由 orchestrator 写入 turn metadata；`contracts/capability.md` 第 27 条。
- 做什么：审计 `agentic_pipeline.py` 与 `tutorbot/agent/loop.py` 中所有对 `teaching_modes.detect_construction_exam_scene` / `get_construction_exam_skill_instruction`（已是 legacy shim，`teaching_modes.py:554`）的独立调用；改为只读 `context.metadata["question_lifecycle_scene"]` / `["question_lifecycle_skill_names"]`；删除/降级 legacy 重判。
- **不要**把 `teaching_modes` 升级成 authority（v1 的硬错）。
- 验收：grep 确认两壳不再独立调 `detect_construction_exam_scene`；scene golden = 基线；`scripts/check_contract_guard.py`（capability domain）绿。

**Task P0.3 — grounding 分叉行为矩阵 + 有意识收敛**
- 现状（codex 实证）：`query_intent.build_grounding_decision` 给通用 decision；chat 只读 `should_force_retrieval_first`（`agentic_pipeline.py`）；tutorbot 额外叠 bot_id / practice_generation / learner-state scene / scene_requires_rag / web_search prefetch（`tutorbot/agent/loop.py:1062` 附近）。
- 做什么：写一张 **按 surface/题型的 grounding 行为矩阵**，逐条标注"有意分叉（保留，注明 SLA/surface 理由）"或"无意重复（收敛到 `query_intent` authority + 重验）"。只收敛无意重复项。
- 验收：矩阵进 `docs/plan/`；收敛项 grounding golden = 基线（语义等价，**不要求字节级一致**）；`tests/services/rag/*` 绿。

**Task P0.4 — exact-authority 分叉行为矩阵（按题型定契约）**
- 现状（codex 实证）：chat 对任何 exact 都 buffer，case_study 走 LLM rewrite，MCQ 失败后正则替换最终答案（`agentic_pipeline.py:2072/2226`）；tutorbot 只对 MCQ/free_text 强制 exact，case_study 仅在完整覆盖且数值缺失时 fallback（`services/rag/exact_authority.py:142`、`tutorbot/agent/loop.py:991`）。
- 做什么：定义 **exact behavior contract by kind**（MCQ / free_text / case_study 各自的适用与组装规则）；`exact_authority.py` 保持"按题型"authority；两壳的消费差异文档化，无意重复项收敛。
- 验收：exact golden = 基线（按题型语义等价）；**删除"两壳字节级一致"这条验收**。

**Task P0.5 — authority guard（防复发）**
- 做什么：`scripts/check_harness_authority.py` 静态断言——(a) `question_lifecycle_skills` 之外无第二套 scene→skill 映射、两壳无独立 scene 重判；(b) grounding/exact 的判定关键字只出现在各自 authority + 委托调用处。
- 验收：构造"在 wrapper 里加 scene 重判 / grounding regex"的改动 → guard 红；接入 `eval/gates.yaml` quick gate。

**P0 出口 gate（硬）：** 三类 authority 各只剩一个判定点（guard 可证）；trace golden 全绿；contract guard 绿；grounding/exact 分叉矩阵入册。

---

## 4. Deferred Roadmap（**现在不做**，gating：P0 完成 + launch-readiness/assessment 主线稳定）

> 这些就是"未来模型红利"的兑现项。先冻结为有序 roadmap，避免在地基未稳时开工。

- **D1 共享 fat-skill 抽取（替代 v1 的"统一 kernel"）**：保留 chat 同步壳 / tutorbot 自主壳两个执行模型；把 P0 矩阵里确认的共享 policy 抽成两壳都调用的 fat skill。**不做单一 kernel。**
- **D2 chat 有界迭代**：仅对 **显式 deep mode** 引入多跳；smart/fast 默认不变。前置条件：先写 **stream trace 兼容规范 + replay 断言**（codex 指出迭代化会改 WS 事件序与 turn_runtime 的 terminal/active_object 抽取，`turn_runtime.py:4354`，不是"只换内核"）。
- **D3 可恢复压缩 + 工具产物外置**：大产物落盘留指针 + `read_artifact` 按需回取，替代不可恢复截断。
- **D4 KV-cache 稳定前缀**：前置 **prompt partition 设计**（稳定前缀 vs 动态尾部）——codex 指出两壳每轮动态拼 memory/scene/tool表/workspace/skills（`agentic_pipeline.py:1358/1792`、`tutorbot/agent/context.py:36`、`loop.py:2431`），不是局部拆字符串；+ 命中率进 Langfuse。
- **D5 轨迹级 eval 扩容 + model-swap 单点抽象 + 防复发 guard 升级**：换模型只改 catalog/config 一处。

---

## 5. Required Outputs（eng-review 规约）

### NOT in scope（本轮明确不做，附理由）
- 统一 `TurnExecutionKernel`——SLA 不同，收益不及风险（codex P0 #1）。
- chat 迭代化 / KV-cache / 可恢复压缩——前置设计未完成 + 抢风险预算（D2/D3/D4）。
- `capabilities/tutorbot.py` 收薄——contract 敏感职责，不以 LOC 为目标（codex P1 #9）。

### What already exists（复用而非重建）
- **scene authority 已存在**：`question_lifecycle_skills`（`SCENE_COMPOSITION` + `resolve_question_lifecycle_scene_decision`）+ orchestrator 写 metadata；本计划是 **强制两壳读它**，不是新建。
- **grounding authority 已存在**：`query_intent.build_grounding_decision`。
- **exact authority 已存在**：`services/rag/exact_authority`。
- **上下文工程层已成熟**：`services/session/context_{budget,pack,builder,router,trace,sources}.py`，P0 不动它。
- **eval 骨架已存在**：`eval/gates.yaml` + benchmark；P0.1 是补 trace 级粒度，不是另起一套。

### 关键风险与失败模式
| 风险 | 缓解 |
|---|---|
| 收敛 grounding/exact 时偷偷改了行为 | P0.1 trace golden 先行；矩阵区分有意/无意分叉；只收敛无意项 + 重验 |
| 把 legacy shim 误升为 authority（v1 已犯） | guard 静态断言 + contract guard capability domain |
| trace golden 仍漏语义回归 | golden 锚到 metadata 字段（scene/skill/authority_applied）而非只看可见文本 |
| 与他人 WIP 混提 | 仅新增/改本计划 + INDEX 行；不自动 commit；不碰 learner-workspace WIP |

---

## 6. 相关代码入口汇总
- scene authority：`deeptutor/services/question_lifecycle_skills.py`（`SCENE_COMPOSITION` / `resolve_question_lifecycle_scene_decision`）；legacy 待降级 `deeptutor/tutorbot/teaching_modes.py:554`
- grounding：`deeptutor/services/query_intent.py:build_grounding_decision`；消费点 `agentic_pipeline.py`、`tutorbot/agent/loop.py:1062`
- exact：`deeptutor/services/rag/exact_authority.py:142`；消费点 `agentic_pipeline.py:2072/2226`、`tutorbot/agent/loop.py:991`
- 两个执行壳：`agents/chat/agentic_pipeline.py`、`tutorbot/agent/loop.py`；薄壳 `capabilities/chat.py`、`capabilities/tutorbot.py`
- turn/stream：`services/session/turn_runtime.py:4354`、`core/stream.py`、`core/trace.py`
- eval/guard：`eval/gates.yaml`、`scripts/check_contract_guard.py`、`scripts/check_harness_authority.py`(新)、`scripts/run_benchmark.py`、`deeptutor/services/benchmark/fixtures/`
- contract：`contracts/capability.md`（第 22/26/27 条）、`contracts/turn.md`、`contracts/rag.md`、`CONTRACT.md`、`contracts/index.yaml`

## 7. 与现有计划主线的关系
- 直接对齐：`2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md`（scene authority 主线，本计划强制两壳遵守它）。
- 复用：`2026-04-16-tutorbot-context-orchestration-prd.md`（上下文层不动）。
- 护栏依赖：`2026-04-23-deeptutor-benchmark-single-spine-prd.md`。
- gating 依赖：`2026-05-25-prelaunch-readiness-checklist.md` + assessment 主线稳定后才解锁 Deferred Roadmap。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review (outside voice) | codex exec read-only | 架构/可行性对抗 | 1 | issues_open→revised | 9 findings (6×P0, 3×P1) |

**CODEX 对抗审查（2026-05-27，high reasoning，read-only，live repo）核心发现：**
1. (P0/9) 单一 `TurnExecutionKernel` 把不同 SLA 硬合并，抽象更差 → 改为共享 fat skill + 两执行壳。**已采纳。**
2. (P0/8) chat 迭代化改 WS 事件语义 / turn_runtime terminal 抽取，非"只换内核" → D2 前置 stream trace 兼容规范。**已采纳（defer）。**
3. (P0/9) grounding 已分叉（tutorbot 叠 bot_id/practice/learner-state/web_search prefetch）→ 行为矩阵，不"只搬不改"。**已采纳（P0.3）。**
4. (P0/9) exact 已分叉（按题型不同）→ 按题型契约，删"字节级一致"。**已采纳（P0.4）。**
5. (P0/10) **v1 scene authority 指错文件**：authority 是 `question_lifecycle_skills`，`teaching_modes` 是 legacy shim 应降级。**已修正（P0.2）。**
6. (P0/9) golden 网太粗（grounding 4 case / max-cases 1）→ trace 级 golden。**已采纳（P0.1）。**
7. (P1/8) chat 迭代破 latency/cost，flag 回滚不了新 trace surface → 仅显式 deep mode 多跳。**已采纳（D2）。**
8. (P1/8) KV-cache 稳定前缀需 prompt partition 设计，非局部拆字符串。**已采纳（D4 前置）。**
9. (P1/9) `capabilities/tutorbot.py` 非可随意收薄的薄壳，LOC 是坏指标 → 按 contract 职责拆。**已采纳（非目标）。**

**CROSS-MODEL:** 本机 Claude 评审与 codex 在"两套 harness + 重复语义"诊断上一致；在处方上 codex 更收缩（不统一 kernel、降优先级），Claude 评审采纳 codex。无悬而未决的对立。

**UNRESOLVED:** 0（用户已拍板"按 codex 收缩重写"）。

**VERDICT:** ENG REVIEW 已吸收，计划从"5 阶段统一 kernel"收缩为"窄 P0 + Deferred Roadmap"。当前**只允许执行 P0**；Deferred Roadmap 待 P0 完成 + launch-readiness/assessment 主线稳定后再排。
