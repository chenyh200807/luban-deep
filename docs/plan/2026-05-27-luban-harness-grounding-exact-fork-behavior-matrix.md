# 鲁班 Harness — grounding / exact 分叉行为矩阵（P0.3 + P0.4）

> **归属**：[`2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md`](./2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md) 的 P0.3 / P0.4 交付物。
>
> **结论先行**：grounding 的*决策* authority（`query_intent`）与 exact 的*内容* authority（`services/rag/exact_authority`）**各自单一且被两壳共享**；两壳之间的差异是**有意的 surface / 执行模型分叉**（chat = 延迟敏感同步对话壳，tutorbot = 自主预取 / 确定渲染壳），符合 `AGENTS §0 thin wrappers, fat skills`。**本轮核对未发现可离线安全收敛的"无意重复"**，因此不做收敛性代码改动；同时**删除 v1 "两壳字节级一致" 的伪验收**。

**Status:** Accepted（code-verified against main @ 2026-05-27）
**Date:** 2026-05-27
**核对基线:** commit `470d80de`（含 question-lifecycle authority 迁移后的现网）

---

## 0. 方法

逐条核对两壳对 grounding / exact authority 的**真实调用点**（行号经 grep 核实，非沿用 v1 计划的旧行号——v1 的 scene 诊断已被证明过时，故此处全部重核）。每条标注：

- **有意分叉（keep）**：差异来自不同 SLA / surface / 执行模型，保留，并注明理由。
- **无意重复（converge）**：两壳各自重新实现了同一个一等事实的判定，应收敛到 authority。

收敛动作只允许在**能离线验证语义等价**时进行（本计划用户决定：决策层离线 golden，无 live LLM）。无法离线验证的收敛一律标 deferred，不在本轮强行改。

---

## 1. grounding 行为矩阵

**单一 authority（决策层）**：`deeptutor/services/query_intent.py`
- `build_grounding_decision(...)`（`query_intent.py:249`）
- `build_grounding_decision_from_metadata(...)`（`query_intent.py:341`）
- 返回 `GroundingDecision`（`query_intent.py:171`），字段：`grounded_construction_exam_runtime / should_force_retrieval_first / should_prefetch_grounded_rag / current_info_required / textbook_delta_query / should_try_exact_fast_path / reasons ...`

| # | surface / 维度 | chat 壳（`agentic_pipeline.py`） | tutorbot 壳（`tutorbot/agent/loop.py`） | 分类 | 理由 |
|---|---|---|---|---|---|
| G1 | 调用入口 | `build_grounding_decision(...)`（`:2791`） | `build_grounding_decision_from_metadata(...)`（`:1101`） | 有意 | 同一 authority 的两个签名：chat 走逐参数同步调用；tutorbot 走 runtime_metadata 变体。决策核仍是 `query_intent`。 |
| G2 | 消费字段 | 仅 `decision.should_force_retrieval_first`（`:2801`） | `should_prefetch_grounded_rag` + `should_force_retrieval_first`（`:1113-1140`） | 有意 | chat 同步问答只需"答前是否先检索"；tutorbot 是自主壳，需要"是否**预取**（proactive prefetch）"。prefetch 概念对同步壳无意义。 |
| G3 | bot_id 绑定 | 无 | `bot_id != "construction-exam-coach"` 分支（`:1111-1122`） | 有意 | tutorbot 多实例、按 `bot_id` 绑定不同默认工具/知识库（`bot_runtime_defaults` 契约）；chat 无 bot 身份。 |
| G4 | practice-generation 感知 | 无 | `looks_like_practice_generation_request` → prefetch 抑制（`:1098/1125`） | 有意 | 出题预取属 tutorbot 题目生命周期编排；chat 不承载出题自主流程。 |
| G5 | learner-state scene 路由 | 无 | `_construction_scene_uses_learner_state_authority(scene)` + `query_uses_learner_state_authority`（`:1132-1133`） | 有意 | learner-state 召回是 tutorbot 自主壳的上下文工程；scene 来自单一 lifecycle authority 的 metadata，tutorbot 只是**读 scene 做预取编排**，未重判 scene。 |
| G6 | scene→prefetch 策略 | 无 | `_construction_scene_requires_rag_prefetch(scene)`（`:1142`） | 有意 | 同 G5：读 metadata scene 决定是否预取，属执行模型编排，非第二套 grounding 决策。 |
| G7 | exact 后置 web_search | 无 | `_should_force_web_search_after_exact_prefetch`（`:1162`） | 有意 | tutorbot 自主壳在 exact 预取后补联网；chat 同步壳由用户显式触发 web_search。 |

**grounding 结论**：决策核（"要不要召回 / 是否当前信息 / 是否 exact 候选"）单一且共享。tutorbot 在其上叠的是 **prefetch 编排层**（G2-G7），由其"自主 + 多实例 + 预取"执行模型驱动，对延迟敏感的同步 chat 壳不适用。**无 G* 项构成对 grounding 决策的重新判定 → 无无意重复 → 不收敛。**

---

## 2. exact 行为矩阵（按题型定契约）

**单一 authority（内容层）**：`deeptutor/services/rag/exact_authority.py`
- 抽取：`extract_exact_question_authority_from_metadata(...)`（`:86`）→ 归一 `authority_kind ∈ {mcq, free_text, case_study}`
- 强制判定：`should_force_exact_authority(...)`（`:142`）
- 渲染：`build_exact_authority_response(...)`（`:420`，三题型分支）

### 2.1 exact behavior contract by kind（authority 层，两壳共享的内容真相）

| answer_kind | `should_force_exact_authority` | 内容契约（authority 渲染语义） |
|---|---|---|
| `mcq` | **True**（`:144`） | 命中题库原题 → 以题库标准选项为最终结论；渲染含阅卷结论 / 解析 / 易错点 / 核心要点 / 收尾提醒（`:422-473`）。 |
| `free_text` | **True**（`:144`） | 以题库标准答案 + 解析为准，原文呈现（`:474-477`）。 |
| `case_study` | **False**（`:146-149`） | case-study exact 是**内容 authority 而非呈现 authority**——必须由最终作答层综合成用户可见答案，不强制原样输出（注释 `:147-148`）。 |

> 这张表就是 P0.4 要求的"按题型契约"：`should_force` 与渲染规则**只在 `exact_authority.py` 定义一次**（guard `check_harness_authority.py` 静态保证），两壳消费它。

### 2.2 两壳消费差异

| # | 维度 | chat 壳（`agentic_pipeline.py`） | tutorbot 壳（`tutorbot/agent/loop.py`） | 分类 | 理由 |
|---|---|---|---|---|---|
| E1 | 抽取 | `extract_exact_question_authority_from_metadata`（`:2065`） | 同一函数（经 `_prefetched_exact_question` 通道，`:678`） | 共享 | 内容 authority 抽取单一。 |
| E2 | 呈现策略 | prompt contract（`_exact_question_response_contract` `:2078`）+ **LLM rewrite**（`_rewrite_exact_question_response` `:2339`） | **确定性渲染** `build_exact_authority_response`（`_build_exact_authority_response_sync` `:717-718`） | 有意 | chat 是对话壳，需把 authority 综合进自然语言回答（LLM 在 authority 契约约束下改写）；tutorbot 是确定壳，直接输出 authority 渲染，杜绝 LLM 漂移。两者都以同一 `exact_authority` 内容为准，差的是**呈现**，不是**内容真相**。 |
| E3 | case_study 处理 | 经 E2 的 contract+rewrite 综合 | 覆盖率 gating：`_case_exact_required_numbers` / `_prefetched_case_exact_question_can_answer`（`:651-717`） | 有意 | 对应 2.1 中 case_study `should_force=False`：两壳都"不原样输出 case_study"，但 chat 用 LLM 综合、tutorbot 用覆盖率判定能否作答。均未重定义 case_study 的内容契约。 |

**exact 结论**：内容 authority（抽取 / should_force / 渲染语义）单一且共享，按题型契约见 2.1。两壳差异是**呈现策略**的有意分叉（LLM 综合 vs 确定渲染），由 surface 决定。**未发现对 `should_force` / 内容契约的重新定义 → 无无意重复 → 不收敛**。**删除 v1 "两壳字节级一致" 验收**：字节级一致与"对话壳要 LLM 综合"直接矛盾，是错误目标。

---

## 3. 验收

- grounding / exact **authority 定义唯一性**：由 `scripts/check_harness_authority.py` 静态保证（`build_grounding_decision` 唯一在 `query_intent.py`、`should_force_exact_authority` 唯一在 `exact_authority.py`）。gate `harness_authority_guard` 绿。
- **按题型 exact 语义**：`scripts/run_harness_authority_baseline.py` golden 冻结了 mcq/free_text/case_study 的 `should_force` 与渲染输出（tracked fixture `deeptutor/services/benchmark/fixtures/harness_authority_decision_golden.json`；`artifacts/` 被 git-ignore 故不落那里）；gate `harness_authority_baseline` 绿。
- grounding 决策回归：`tests/services/test_query_intent.py` + `tests/services/rag/*` 绿（见执行计划 P0 验收汇总）。

## 4. 未收敛项与 deferred

本轮**无**强行收敛（所有核对到的分叉均为有意）。若未来要把"prefetch 编排"或"exact 呈现策略"进一步抽成两壳共享 fat skill，归入执行计划 **Deferred Roadmap D1（共享 fat-skill 抽取）**，前置条件不变：P0 完成 + launch-readiness / assessment 主线稳定，且需在有 LLM key 的环境补 live trace 验证后再动 chat 的 LLM rewrite 路径。
