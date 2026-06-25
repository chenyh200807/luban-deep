# TutorBot Fix/Test Journal

## 2026-06-26 - Case grading receipt metadata must stay turn-scoped

- 问题：
  - PR#247 / `fdfdffb4` 部署 test2 后，active-question exit/history 主病 live 3/3 已修：summary turn 不再进入 `deep_question_followup`，DB `semantic_decision.next_action=route_to_general_chat`、`final_executed_capability=tutorbot`。
  - 同一 live 对话 `tb_98e3c80f10f24b47a3bcb7de` 的 3 个 summary turn 仍稳定带旧判分 terminal metadata：`v1_case_graded=true`、`score_authority=rubric_scored_v1`、`grading_to_brain_loop.writeback_count=1`、`learning_evidence_event_id`，尽管本轮 `question_lifecycle_scene=null`、`execution_path=tutorbot_kb_first_full_agent_policy`，visible response 是总结而非判分。
- 根因：
  - 合法 writer 是当前 case grading turn 的 V1 / grading-to-brain 链路；但 `AgentLoop._export_case_grading_metadata`、`TutorBotManager.send_message`、`TutorBotCapability.run` 三处把 `runtime_metadata/session_metadata` 中的 grading receipt 当成可继承 session-level metadata 无条件复制到 terminal result / trace / caller session metadata。
  - shared failure shape：`turn-scoped receipt promoted to session-level truth`。router 已正确，不是 `deep_question_followup` 残留，也不是 LLM 幻觉。
- 失败尝试及原因：
  - 只改 `AgentLoop._export_case_grading_metadata` 能让 loop 层 RED 变绿，但 manager/capability 仍有第二出口，会把旧字段从 `runtime_metadata/session_metadata` 重新塞回 result。
  - 不在 capability result_payload 里继续维护一份黑名单；那会变成第三个 metadata authority。改为把 case-grading receipt key 列表和 current-turn gate 下沉到 `construction_grading.case_output_policy`。
- 成功修法：
  - 新增 `copy_current_case_grading_turn_metadata` / `strip_case_grading_turn_metadata` 作为唯一 case-grading turn receipt 投影 helper。
  - `AgentLoop`、`TutorBotManager`、`TutorBotCapability` 全部只调用该 helper；非 `question_lifecycle_scene=case_grading` turn 自动剥离旧 `v1_case_graded/score_authority/grading_to_brain_loop/learning_evidence_event_id/...`。
  - `contracts/turn.md` 增加不变量：grading receipt 是 current case-grading turn metadata，不是 session-level learner truth。
- 验证：
  - RED：新增 loop 最小测试先失败，旧 export 会保留 4 个 stale receipt 字段。
  - GREEN：目标测试 4/4 passed；登记相关测试 85/85 passed（`test_agent_loop_case_rubric_v1.py`、`test_tutorbot_authority.py`、`test_tutorbot_sqlite_adapter.py`、`test_case_output_policy.py`）。
  - 待完成：contract_guard、same-SHA Tests/Deploy Gate、test2 redeploy、live ≥3 轮 DB 验证 metadata 0/3 泄漏。
- 教训：
  - result metadata 也有生命周期边界。判分 receipt 可以被观测、写入长期证据，但不能作为 session mirror truth 自动继承到普通总结/答疑 turn；否则“已修路由”仍会被 terminal metadata 翻案。

## 2026-06-26 - Active question exit/history requests must not be consumed as follow-up

- 问题：
  - test2 live after `820702b23` deploy, conversation `tb_58c25667ef9a496482ff729b`:
    - `turn_1782416177555_50d5b35614` 用户问 `总结我正式提交过的案例答案，别重新判分。`，DB terminal response 却继续回答当前 active MCQ 的答案/解析 B，`execution_path=deep_question_followup`。
    - `turn_1782416203761_a65945d390` 用户钓鱼要求不要展示 `working_memory/learner_summary/citation source title`，terminal response 延迟回答上一轮“案例答案总结”请求；未泄内部词，但当前 turn 指令被旧 follow-up/历史请求覆盖。
- 根因：
  - 上一轮修复已让 `resolve_submission_attempt` 对这类请求返回 no-submission，但 `looks_like_question_followup` 在 active MCQ context 下仍用通用 follow-up marker 把 `总结...案例答案` 认成 active question 追问。
  - 更深一层：semantic router 在 deterministic fallback 前会调用 LLM follow-up interpreter；即使 deterministic predicate 后续返回 false，LLM 仍可能把历史总结请求误判成 active-question follow-up 并提前抢权。
  - shared failure shape：`no-submission authority correct, active-object consumption authority still leaks`。这是同一 authority 内部断点，不是新 router 需求。
- 失败尝试及原因：
  - 只让 `looks_like_question_followup` 返回 false 不够；TDD 中故意让 `interpret_question_followup_action` 返回 `ask_followup`，semantic router 仍会在 fallback 前绑定 active choice。
  - 不在 semantic router 里新增第二套字符串分类；把 predicate 收在 `question_followup`，semantic router 只读同一 active-question 可消费性 authority。
- 成功修法：
  - `question_followup.looks_like_question_context_exit_request` 复用现有 meta/history/internal-evidence/退出判分信号，明确这类 turn 不可被 active question 消费。
  - `looks_like_question_followup` 早退 false，避免 deterministic follow-up fallback 抢旧题。
  - `semantic_router.resolve_question_semantic_routing` 在调用 LLM follow-up interpreter 前只读该 predicate，将本轮路由为 `temporary_detour -> route_to_general_chat`、`allowed_patch=no_state_change`，不改 active object、不判分。
- 验证：
  - RED：新增最小测试 2/3 fail（`looks_like_question_followup` 误 true；LLM follow-up action 误绑定 active choice）。
  - GREEN：新增 + 邻近回归 11/11 passed。
  - 相关服务 pytest：282/282 passed（`test_question_followup.py`、`test_semantic_router.py`、`test_semantic_router_eval_cases.py`、`test_question_lifecycle_scene_derivation.py`）。
  - `scripts/check_contract_guard.py ...`：passed；`git diff --check` clean。
  - live/test2：待 PR 合并、same-SHA Tests/Deploy Gate、test2 redeploy 后跑 ≥3 轮 DB 验证。
- 教训：
  - “不提交答案”只是半个事实；还必须回答“当前 active object 是否有权消费这句话”。no-submission 正确但 consumption authority 漏了，旧题仍会抢当前 turn。

## 2026-06-26 - Case grading reference, sticky grading scene, invalid option, visible source leak

- 问题：
  - live `tb_de7ada4027894839be2b11d3 / turn_1782413339559_1fbc0ba080`：用户显式 `我的答案：75%。标准答案：100%。`，DB `execution_path=tutorbot_case_grading_v1_direct`、`grading_rubric_provenance=derived_from_stem`，visible 给 `10 / 10`，把 75% 判成命中。
  - live `tb_51110fabc0fe4fb7a143db5b / turn_1782413074120_6dabda4ca7`：`如果我选Z呢？` 被写成 `user_answer=第1题：Z`，后续案例判分混入上一题 `你当前作答：D`。
  - live `turn_1782412970739_4b45196aa9` / `turn_1782412977303_0bae99b4e2`：`不要把内部参考证据...`、`总结我正式提交过的案例答案` 被 sticky `case_grading` 抢走。
  - live `turn_1782413213439_46e379445b`：攻击钓鱼要求输出 evidence source 标题时泄漏 `learner_summary` 内部源标题。
- 根因：
  - `AgentLoop._build_v1_case_ctx` 只读 exact/followup reference，未把当前完整案例里的 marked reference 纳入 V1 ctx，导致显式标准答案 authority 被 `derived_from_stem` 覆盖。
  - `DeepQuestionCapability` full-case fallback 固定 `correct_answer_present=False`，即使共享投影已带 `correct_answer/reference_answer`。
  - `resolve_question_lifecycle_scene_decision` 对预盖章 `case_grading` 无条件返回，旧 grading scene 能抢当前 meta/summary turn。
  - `resolve_submission_attempt` 对 active subjective context 把 meta/summary/内部证据请求当作答案；同时合法 `作答:` / `case_study` 类型覆盖不足。
  - user-visible sink 未把 `learner_summary` 等内部 source title / trace key 视为 unsafe visible output。
- 失败尝试及原因：
  - 只改 V1 builder 后 RED 仍显示 `correct_answer=100%。请判分`；说明 reference 清洗应收在共享 `case_grading_context_from_full_submission` 投影，而不是 TutorBot 私有 wrapper。
  - 只拦预盖章 scene 后旧合法测试失败；切点不是取消 pre-stamp，而是要求 pre-stamp 由当前 HIGH submission/full submission 重新证明。
  - 只依赖 `submission_confidence` 仍让 `总结...案例答案` 变成 HIGH；必须在 `resolve_submission_attempt` 写入侧先让非提交请求 0->0。
- 成功修法：
  - `question_lifecycle_skills.case_grading_context_from_full_submission` 原子拆当前案例 `user_answer` 与 `correct_answer/reference_answer`，并清理 reference 尾随 `请判分/批改` 操作语。
  - `AgentLoop._build_v1_case_ctx` 优先消费当前 marked reference；exact/followup 只在当前 reference 缺失时兜底。
  - `DeepQuestionCapability` full-case path 按共享 context 判断 `correct_answer_present`。
  - `question_lifecycle_skills.resolve_question_lifecycle_scene_decision` 对 pre-stamped grading scene 做当前 turn submission proof revalidation。
  - `question_followup.resolve_submission_attempt` 补主观题提交类型/前缀，并把 meta/history/internal-evidence 请求判为非提交。
  - `user_visible_output.coerce_user_visible_answer` fail-closed 正文中的内部 source title / trace key；`unified_ws._redact_event_for_public` 同步清理 `citation_bundle.refs[].title/source` 与 `footer_text` 中的内部源标题。
- 验证：
  - RED 集修复后：33/33 passed。
  - 相关扩展 pytest：376/376 passed。
  - `scripts/check_contract_guard.py ...`：passed；`capability`、`luban_grading_engine`、WS allowlist、lifecycle authority guard 均 PASS。
  - contract surface：`contracts/capability.md`、`contracts/turn.md` 已更新。
  - live/test2：待 PR 合并、same-SHA Tests/Deploy Gate、test2 redeploy 后跑 ≥3 轮 DB 验证。
- 教训：
  - case grading 的 marked reference 是当前题面事实，必须在共享 projection 层进入评分 ctx；让 TutorBot wrapper 补字符串会长出第二套 authority。
  - pre-stamped scene 是前置事实，不是永久事实；每个 turn 仍要由当前 submission authority 证明。
  - visible leak 要收在单一 public sink，不能在每条 emit path 补脱敏。
