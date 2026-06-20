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
