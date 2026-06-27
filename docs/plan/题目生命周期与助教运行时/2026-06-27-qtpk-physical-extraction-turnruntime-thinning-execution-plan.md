# QTPK 物理抽出 + TurnRuntime 瘦身 — 执行计划（Task 2/4 物理落地）

> **状态**: Child execution plan of [2026-06-26 控制面收权 umbrella](2026-06-26-fast-mode-orchestrator-simplification-architecture-plan.md) **§Task 2（QTPK 收权）+ §Task 4（TurnRuntime 收回 transport）的物理执行**。不另立第二份计划；所有 slice 复用父计划 gate（writer allowlist + authority baseline + hard corpus）。
> **为什么**: 单一权威不变量（one fact one authority）已达成上线，但 question-turn policy 物理上仍被解析三次、active_object/scene/submission 业务推断仍住在 turn_runtime。本计划把它们物理收成 QTPK 层，TurnRuntime 瘦成 transport-only。
> **基线**: 8cad311fd（含已完成的逻辑收权）。

## 目标架构（用户定）
```
entry adapters → TurnRuntime(auth+persist+stream+replay ONLY) → QuestionTurnPolicyKernel(current object+submission+scene) → CapabilityAdapter(thin dispatch) → Fat kernels(CaseGrading/MCQ/RAG/LearnerEvidence/Security) → TerminalResultAssembler(唯一 visible-output, 已达成) → stores
```

## 核心发现
question-turn policy 物理被解析**三次**：`start_turn:4127-4223`（mode-selection）→ `_run_turn:4953-5108`（权威 restore）→ orchestrator `_resolve_semantic_routing:767-797`（canonical）。`apply_active_object_transition`(semantic_router.py:259) 已是 suspend/resume/demote canonical，但 turn_runtime restore/demote 块是其**平行手写副本**。QTPK = 收成一次解析，物理住进只读转发现有 canonical 的模块。

## QTPK 设计（非 god object）
- 新模块 `deeptutor/services/question_turn_policy.py`。形态 A（先）：`resolve_turn_policy()` 入口 + 把 `_resolve_question_followup_context_and_action`、active_object helper(1031-1133)、E8 merge 从 turn_runtime **物理搬进**；内部**只调** `resolve_question_semantic_routing` / `resolve_question_lifecycle_scene_decision` / `apply_active_object_transition` / `active_object_builder`，**不重实现**。形态 B（终）：`QuestionTurnPolicyKernel` dataclass envelope。
- owns 5 fact：scene / relation+next_action / submission intent+evidence / current object identity / active-object patch。**禁止第六类**（reveal/response_mode/practice strategy/terminal/score）。
- **import-allowlist CI guard**：QTPK 只许 import semantic_router / question_lifecycle_skills / active_object_builder / question_followup；禁 LLM/grading/RAG/learner-state/reveal/terminal。god object 防线。

## TurnRuntime 瘦身（留 transport：auth/persist/stream/replay/deadline + 安全带）
搬出业务推断（restore/demote/回指/seed/E8 merge/result normalize/active_object helper），写动作（set_active_object/set_suspended_stack）保留但写 QTPK 输出值。**E8 套题防塌 + task#14 回指防 demote 是 §6 SEV-1 安全带，搬迁先建 differential parity 网。**

## CapabilityAdapter 瘦身
orchestrator 删第三次解析（`_resolve_semantic_routing` 改读已签发 decision）+ 删与 canonical 重复的 `_select_capability_after_lifecycle` branch + 删本地 submission 重判；保 unresolved-switch context-continuity 安全带 + MCQ preselect bypass。最终 = 读 decision→map capability→dispatch。

## 分片（有序，每片 authority count 真降 + live gate）
| Slice | 内容 | 行为 | live gate |
|---|---|---|---|
| **S0** | 建 question_turn_policy.py 空模块 + import-allowlist CI guard + differential test 脚手架（旧路径 vs QTPK 同输入断言相同），不改调用方 | 零行为 | 无需 live（先做，最安全）|
| **S1** | 物理搬 `_resolve_question_followup_context_and_action` + active_object helper + `_message_references_stored_question_set_item` 进 QTPK，callsite import 回去 | 零行为（纯 move parity）| unit parity + harness baseline 不变 |
| **S2** | E8 `_merge_grading_result_into_active_set` 提纯函数进 QTPK，turn_runtime 只留 get/set，逐字保分支 | 零行为 | **判分 live≥3**（套题判一题不塌/单题/真切换）|
| **S3** | 删 start_turn 预解析。**investigation 修正(2026-06-27): 非单片, 拆 4 子步**——start_turn 有①followup 重复解析(可删, 与 _run_turn 真重复)②mode-selection(fast/deep)=唯一权威 _run_turn 只消费。**新发现双权威**: 两个 _active_object_requires_deep(start_turn 粗版 turn_runtime:1039 vs tutorbot 细版 tutorbot:782 答题/出题 followup→fast)。删任一块改 fast/deep 学生面+chat_mode persist 退化(mobile 回显)+mirror 丢失。**S3a 收敛两个 _active_object_requires_deep 单一权威→S3b 建 mode 差分网→S3c 修 mobile persist→S3d 删 start_turn 块** | 改行为(学生面 fast/deep) | **每子步 fast/deep live≥3**(活跃题+讲解=deep/活跃题+答题=fast/活跃题+出题=fast/mirror followup/mobile 回显) |
| **S4** | restore/demote/回指 收敛到 apply_active_object_transition（differential 暴露手写 vs canonical 差异，以 canonical 为准补 hard corpus）| 改行为（双权威收敛）| **回指+判分+scene live≥3**（最危险，拆 2 会话）|
| **S5** | orchestrator 删第3次解析（读已签发 decision）+ 削重复 branch（Task 4）| 改行为 | autoroute+WS 全绿 + 回指/判分/scene live≥3 |

先 S0→S1→S2（零行为 parity 网 + SEV-1 E8 安全搬）。S3-S5 真收敛逐片 live≥3。

## 不变量 + 风险
- QTPK 只读转发 canonical 不造第六类 fact（god object 自检 + import guard）。
- `apply_active_object_transition` 是 demote canonical，S4 是收敛手写副本到它（非反向）。
- E8/回指 §6 安全带搬迁先建 differential parity（S0）。
- 每片 before_after_counts 真降（counter 产出非 PR 描述）。
- 学生面判 fixed 拉持久化终态非流式。
- 异源红队 GLM-5.2（非 Claude）+ ground truth 跑真代码裁决。

## owner 决策点
exam_track（session preference 非 question-turn fact，不进 QTPK）/ 形态 A→B 时机 / S4 手写 vs canonical 差异逐条裁 / mode-selection active_object 预判归宿。

## 预估
6 slice（S0-S5），~6-9 会话；S2/S3/S4/S5 需 live≥3；末尾 live closure（全 hard corpus + 微信 true-entry）。挂父计划 §14.A Task 2(S1-S4)+Task 4(S5)。
