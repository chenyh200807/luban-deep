# TutorBot Fix/Test Journal

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
