# 鲁班智考阅卷链路回归矩阵

**Status:** Active regression checklist  
**Owner surface:** `deep_question` / `question_followup` / `construction_grading` / 微信小程序题卡  
**Goal:** 防止“出题、答题、批改、再出题”链路重新出现答案泄露、题卡不可交互、前端空答案覆盖服务端 authority、正确答案判 0 分、再出题误判为重批改等回归。

## 1. 单一业务事实

阅卷链路只维护一个一等事实：

> 用户看到的是不含标准答案的题卡；服务端保存的是带标准答案、解析、评分依据和题目身份的 authoritative question object；用户作答后，服务端先恢复 authoritative object 并生成结构化 `construction_grading_result`，再交给 Skill/表达层解释错因、改写和下一题建议。

禁止把以下对象变成新的评分 authority：

- 微信小程序回传的 redacted `followup_context`
- LLM 最终 Markdown
- `construction-exam-tutor` 普通讲解 Skill
- 前端题卡选项状态
- 临时 prompt 里的“参考答案”文字

## 2. 回归矩阵

| ID | 场景 | 必须成立的业务事实 | Canonical authority | 自动化守门 | 线上/手工验收 |
| --- | --- | --- | --- | --- | --- |
| G1 | 生成 5 道选择题 | 用户只看到题目和选项，不看到答案/解析 | `deep_question` result metadata + server active object | `tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_preselected_deep_question_overrides_schema_defaults_from_user_message`; `wx_miniprogram/tests/test_ai_message_state.js` | 小程序生成 5 张题卡，卡片可点选，内容无“答案/正确选项/解析”泄露 |
| G2 | 题型 alias 渲染 | `single_choice / multi_choice` 都必须成为交互题卡 | `render_presentation` canonical presentation | `tests/services/test_question_followup.py::test_canonical_presentation_keeps_choice_aliases_as_interactive_cards`; `wx_miniprogram/tests/test_ai_message_state.js` | 5 道题不只第一题可交互；单选/多选样式均可提交 |
| G3 | 前端 redacted 单题提交 | 前端空 `correct_answer` 不能覆盖服务端标准答案 | stored active question / `question_followup_context` | `tests/api/test_unified_ws_turn_runtime.py::test_redacted_public_followup_context_does_not_override_grading_authority`; `tests/services/test_question_followup.py::test_merge_redacted_single_submission_with_authoritative_question_set` | 回答第 2 题正确时，线上判满分，不出现“系统异常，实际本题 1 分” |
| G4 | 前端 redacted 批量提交 | q1/q2/q5 等任意题号都按 `question_id` 恢复标准答案，不按前端顺序误配 | stored question_set items | `tests/services/test_question_followup.py::test_merge_redacted_batch_submission_restores_all_authoritative_items_by_id` | 用户跳答第 5 题或批量提交时，每题对应自己的标准答案和解析 |
| G5 | 结构化评分先于 Skill 表达 | 最终分数来自 `construction_grading_result`，不是 Markdown 二次猜分 | `construction_grading` service | `tests/core/test_deep_question_submission_grading.py` | Langfuse trace 里能看到 `construction_grading_result.authority=construction_grading`；回答正确不被解释层改成 0 分 |
| G6 | 答完后继续要相关题 | “再给我相关五道题”进入 generation，重置上一题 submission，不再重批上一题 | `turn_runtime` followup action resolution | `tests/api/test_unified_ws_turn_runtime.py::test_answered_active_question_can_generate_related_questions_without_regrading` | 答完一题后要求继续出题，应生成新题组，不能再次输出上一题评分 |
| G7 | 问解析/为什么错 | “下一题为什么错”是 followup，不是 generation | active question + followup action | `tests/api/test_unified_ws_turn_runtime.py::test_resolve_question_followup_does_not_treat_next_question_explainer_as_generation` | 用户追问解析时不重新出题 |
| G8 | 多选题判分 | 标准答案确定性判定；若部分得分 policy 未明确，不编造精确部分分 | `construction-mcq-grading` / `grade_mcq_submission` | `tests/core/test_deep_question_submission_grading.py::test_build_submission_context_attaches_authoritative_mcq_grading_result` | 多选漏选/错选报告必须列 `missed_options / extra_options` |
| G9 | 案例题批改 | 案例题先生成结构化 case grading result，再由 Skill 表达 | `CaseGradingSkillKernel` | `tests/core/test_deep_question_submission_grading.py::test_build_submission_context_attaches_authoritative_case_grading_result` | 输出采分点命中、漏点、错因和得分表达，不直接让普通讲解 prompt 自由打分 |
| G10 | 线上重启/中断 | 服务重启不能被误判成业务评分逻辑错误 | Docker health + WS close code + Langfuse trace | 暂无单测；归入运维 smoke | 若遇到 WS `1012`，先查容器 events / deploy window，再判断业务回归 |

## 3. Skill 使用边界

现有 Skill 要派上用场，但不能制造第二套评分链路：

| Skill | 正确用途 | 禁止用途 |
| --- | --- | --- |
| `construction-mcq-grading` | 选择题阅卷协议、错因分类、下一题信号、用户可见表达顺序 | 让 LLM 自由覆盖 `correct_answer` 判分 |
| `construction-case-grading` | 案例题三档阅卷协议、采分点证据句、错因、得分表达改写 | 在没有结构化 result 的情况下直接输出最终分 |
| `construction-exam-tutor` | 普通讲解、复盘、知识点解释 | 承担结构化评分 authority |

运行时顺序固定为：

```text
active question authority
  -> construction_grading_result
  -> Skill-style explanation / error diagnosis / next task suggestion
  -> learner state writeback
```

## 4. PR / 发布前最小命令

```bash
pytest \
  tests/api/test_unified_ws_turn_runtime.py::test_redacted_public_followup_context_does_not_override_grading_authority \
  tests/api/test_unified_ws_turn_runtime.py::test_answered_active_question_can_generate_related_questions_without_regrading \
  tests/services/test_question_followup.py::test_canonical_presentation_keeps_choice_aliases_as_interactive_cards \
  tests/services/test_question_followup.py::test_merge_redacted_single_submission_with_authoritative_question_set \
  tests/services/test_question_followup.py::test_merge_redacted_batch_submission_restores_all_authoritative_items_by_id \
  tests/core/test_deep_question_submission_grading.py \
  -q
node wx_miniprogram/tests/test_ai_message_state.js
```

涉及微信小程序题卡、`deep_question`、`turn_runtime`、`question_followup_context`、`construction_grading` 的改动，至少跑上面这组。上线到阿里云后，再用真实 `/api/v1/chat/start-turn` + `/api/v1/ws` 验证 G1/G3/G6，并在 Langfuse 里确认 grading trace。

