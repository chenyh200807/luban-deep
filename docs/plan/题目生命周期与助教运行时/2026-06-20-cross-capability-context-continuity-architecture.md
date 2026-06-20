# 跨能力上下文连续性 — 架构级根治（"切链路丢上下文/失忆/鸡同鸭讲"反复复发类）

- 日期：2026-06-20
- 状态：核心结构修复 + 契约不变量 + 防复发回归闸已落地（test2 live eval 待补，见 §验证）
- 契约：[contracts/turn.md](../../../contracts/turn.md) §硬约束 24（Context-Continuity 不变量）
- 触发：学员"出新题→回指刚才那道屋面坡度题讲考点"被 fail-closed 成"没定位到那道题，请重发题干"（task#11）。同一类（能力切换后失忆 / 鸡同鸭讲）此前已多次出现、多次单点补丁（2026-06-11 open-world-grading-and-cross-capability-context-continuity Fix 2 等），仍复发——说明缺的是**架构不变量 + 强制**，不是又一个补丁。

## 为什么反复复发（root-cause skill：原则停在口号层、没变成设计门槛）

上下文连续性此前只加在**执行层**：2026-06-11 让 TutorBot 主 LLM 无条件注入 `conversation_context_text`（`build_cross_capability_context_instruction`），主 LLM 因此"记得"前文。

但**路由/决策层**没有同等保证。系统里有 15+ 个**各自独立**判断"这轮是不是作答 / 指哪道题"的确定性闸（`resolve_submission_attempt` 被 18 处调用；`_looks_like_*` 系列遍布 question_lifecycle_skills / question_followup / deep_question / semantic_router）。任何一个闸只要按表层 token（如句中相对从句"我选A"）误判，就会把一个**依赖上下文的 turn 路由到一条永远到不了那个连续主 LLM 的死路**——典型是 `deep_question` 的结构化切题解析器，它只读 `suspended_object_stack`、读不到共享历史，解析不到结构化对象就 fail-closed 成"没定位到/请重发"。结果：主 LLM 明明记得前文，用户却收到失忆式拒答。

实测铁证（task#11，test2）：粘贴题判分后再出新题，原题**根本不在 `suspended_object_stack`**（栈里只有 `open_chat_topic`），它只存在于 `conversation_context_text`。结构化解析路径天然救不了它；只有主 LLM + 共享历史能。

shared failure shape：`unconsumed island`（共享历史 authority 已注入、但切题决策不消费它）+ `duplicate decision`（多闸各自重判 relation/submission）。

## 架构不变量（Context-Continuity，三条结构性规则）

落到 [contracts/turn.md §硬约束 24](../../../contracts/turn.md)，三条一起才是闭环：

1. **单一共享历史 authority**：`conversation_context_text` 是"本会话讨论过什么"的唯一共享历史，由 `turn_runtime` 构建、**无条件注入每个能力执行器**（主 LLM 侧已由 2026-06-11 Fix 2 保证）。任何能力不得声称不知道前文。
2. **单一 relation authority**：一个 turn"与既有上下文的关系"只由 canonical `turn_semantic_decision`（`semantic_router.build_turn_semantic_decision`）判定一次；路由/能力/闸只读不重判。新增独立 submission/relation 判定 = 违约。
3. **依赖上下文的 turn 必落到上下文连续执行器，禁止 fail-closed 失忆**：当 relation 是"回指一个解析不到结构化对象的过去对象"（canonical 签名 `semantic_router.is_unresolved_switch_followup`），orchestrator 必须路由到持有 `conversation_context_text` 的主 LLM（TutorBot），由它从历史承接；不得送进需要结构化 `active_object` 的解析器后 fail-closed。

## 本轮已落地（结构修复 + 强制）

- `semantic_router.is_unresolved_switch_followup(decision)`：把"未解析切题"签名收敛成**单一 canonical predicate**；`deep_question._is_unresolved_switch_followup` 降为 thin wrapper 委托它（消除重复定义，防漂移）。
- `runtime/orchestrator.py`：在 `question_review` / `practice_generation` / `_select_capability_after_lifecycle` 三个 deep_question 分支，命中 unresolved-switch 时改路由到 `_default_chat_capability`（TutorBot，上下文连续），不再进 deep_question 死路。
- 已修的三道误判闸（task#11 前序，`question_followup._looks_like_past_question_explanation_request` + lifecycle resolver 压闸）保留，作为规则 2 的"不把回指误当作答"的对称 guard（单一来源在 question_followup）。
- 契约：turn.md §硬约束 24 固化三条规则。
- 防复发回归闸：`tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_routes_unresolved_switch_to_context_continuous_main_llm` —— 断言 unresolved-switch 路由到 TutorBot 而非 deep_question。

## 剩余迁移（roadmap，增量进行，勿一次性 big-bang）

规则 2 的彻底落地是把 Agent 排查出的 15+ 个独立 submission/relation 闸**逐步收敛**到"读 canonical decision / 并入 question_followup 单一对称 guard"。本轮先治住"fail-closed 失忆"这条最痛的路径（规则 3）+ 立起不变量与回归闸；其余闸按以下顺序增量迁移，每步独立 PR + 定向 eval：

1. `question_lifecycle_skills` 的 `_looks_like_*`（unanchored / ambiguous / free_text / free_text_grading / full_case）——已部分接入回指 guard，待统一为"读 canonical relation"。
2. `deep_question` 的 `_looks_like_wrong_cause_request` / `_looks_like_missing_selection_check` / `_looks_like_option_*`——补回指/讲解 intent guard 或改读 decision。
3. `semantic_router._decision_from_fallback` / `_decision_from_ambiguity_gate`——确保 relation 收口。

**防复发 CI 闸（建议下一步）**：加 contract-guard 规则，检测在 question_followup 单一来源之外**新增**独立 submission/option 抽取或 relation 判定的形态，CI 报警（静态闸是止血，真闭环是规则 2/3 的 runtime 单一汇点）。

## 验证

- 离线确定性：canonical predicate 三态 + deep_question 委托一致；orchestrator 路由回归测试（unresolved-switch → tutorbot）；88 项 orchestrator autoroute/semantic_router 测试全绿无回归。
- live eval（test2）：switch_practice 三轮 ×N，确认 T3"刚才那道屋面坡度题讲考点"由 TutorBot 从历史讲原题（不 fail-closed、不串到新题集、不幻觉）。**不确定性**：主 LLM 语义承接可靠性只能 live N 次跑验证；若不稳，回退路由保留已部署的安全兜底（"没定位到，请重发"，安全诚实不致命）。

## 回滚

单 commit 粒度；无 schema/DB 变更，无 env flag。回退 orchestrator 路由即恢复旧的结构化解析 + 安全兜底。

---

## 真闭包迁移设计(task #12,2026-06-21 双专家定稿)

### 诊断:单一权威已存在、被三个 producer 旁路
`semantic_router.resolve_question_semantic_routing`(semantic_router.py:594,产 `turn_semantic_decision`)**已经**消费完整输入(message + active_object + suspended_object_stack + question_followup_context + history),已owns submission/followup/practice/ambiguity/stack-resume 全部逻辑——**无需新建任何权威**。债在于它被旁路:
- **Producer 1 = turn_runtime**(最先,turn 入口):`_build_turn_semantic_decision`(turn_runtime.py:1020,调用:4836)自建第二套 decision;R1 `_resolve_question_followup_context_and_action`(:1417)+ R3-R6 各自 `resolve_submission_attempt`。
- **Producer 2 = question_lifecycle_skills**(第二,orchestrator 内):`derive_question_lifecycle_scene`(:934,调 resolve_submission_attempt:1004 + looks_like_question_followup:1024)再判一遍 relation 决定 scene 路由叉。
- **Producer 3 = semantic_router**(第三):本该唯一的 C0。

### 保留 vs 收口(关键区分)
- **保留独立(genuine message-shape recognizers,只吃 message)**:`looks_like_free_text_mcq_question_surface`/`_mcq_grading`/`full_case_answer_submission`/`free_text_case_grading`/`value_only_mcq_option_surface`/`free_text_mcq_answer_request` + deep_question 自带题面解析。它们是 C0 **消费**的输入,不是重复决策。task#12 step1(PR #156)已把其中的 MCQ 正则原语收口到 `mcq_surface_patterns.py`。
- **收口(relation/submission 判定)**:turn_runtime R1-R7、lifecycle R8-R11、orchestrator R12-R17、deep_question R18-R19 → 全部降为"喂证据 + 读 C0 结果"。
- **误标不可迁(baseline 里但无路由作用的内容/风格分类器)**:`_looks_like_empty_retrieval_answer`/`_looks_like_diagram_answer`/`_looks_like_question_stem_label`/`_looks_like_process_only_answer`/`_looks_like_session_followup`/`_looks_like_structured_submission_followup` + deep_question 判分后选项措辞闸(option_mapping/scoring/wrong_cause/missing_selection)。**永久 allowlist,不迁。**

### ordering 难题的解(推荐方案 B)
不让 lifecycle 读 metadata(可被忽略),也不留两个 decider。**把 `turn_semantic_decision` 在 `_select_capability` 入口算一次,作为参数传入 `resolve_question_lifecycle_scene_decision`**;lifecycle 用纯表 `(next_action,relation,target_object_type)→scene` 映射,保留它的 business gating(scene→skill stack、clarification 政策),但**停止再判 relation**(删 R8 的 resolve_submission_attempt/looks_like_question_followup;R9/R10 由 C0 的 ambiguity gate 投影,直接删)。decision 作参数 → 结构上无法旁路。

### 安全增量顺序(每步独立 PR + harness golden 逐项 diff + live eval + 退 baseline 行)
0. **characterization harness**(本 PR):golden 基线,每步必须保持逐项不变。
1. ✅ 表面识别原语单一源(PR #156)。
2. deep_question 删 `_default_turn_semantic_decision`(:5002)伪造回退 → 只读、缺则 fail loud。
3. orchestrator scope/legacy 闸(R12-R16)改读 decision;用既有 shadow 基建做 A/B parity。
4. **lifecycle 变 decision 的纯投影**(R8-R11)——解开 ordering;高危,scene 分布 diff 验证。
5. turn_runtime 停产第二套 decision(R1-R7)——最高危,最后做,全 WS readback gate + 生产 shadow。
6. CI 闸 fail-on-new → fail-on-any(baseline 清空到只剩 genuine recognizers + 内容分类器 allowlist)。

### 假收口陷阱(专家明列,务必避免)
新建 `TurnRelationResolver` 类(=第四套)/ lifecycle 经 metadata 读(可忽略,应传参)/ 留 `_default_turn_semantic_decision` 当 fallback(=第二权威,应 fail loud)/ 把 C0 的 LLM interpreter 降级成正则让 lifecycle 先跑(=语义降级,契约禁)/ 迁移内容分类器(=制造耦合)/ 把 CI 静态闸当闭包(真闭包是 runtime fail-closed:每个 consumer 缺 `turn_semantic_decision` 即抛错)。

### harness 落点
`tests/runtime/characterization/`(snapshot.py 直接调 `_select_capability` 快照决策键;conftest.py 双 LLM mock 靶点 + 调用计数;routing_matrix.py 起步 10 行 tier A/C;golden/routing_decisions.json)。Tier-A 行额外断言**不触 LLM**(守 §67/§72 确定性不变量)。局限:只保真矩阵内行;Tier C 只证"给定该 mock 输出路由不变",LLM 实际输出仍需 N 次 live eval。
