# 2026-06-06 WeChat TutorBot Question Authority QA Matrix

## Status

This is the working matrix for the next 30-round real or near-real WeChat TutorBot QA loop.

Current evidence status:

- `real_wechat_package`: partially covered. QA30-017/018 have WeChat DevTools automation evidence for `yousenwebview/packageDeeptutor` visible-card submit/retry payload authority. Full terminal answer quality over `/api/v1/ws` is still pending.
- `standalone_shadow`: partially covered. `wx_miniprogram/pages/chat/chat.js` context continuity was fixed only as shadow parity.
- `node_contract`: covered for the current P1 shadow parity fix.
- `backend_harness`: not expanded in this artifact.
- `runtime_base_authority`: fixed for DevTools QA. `yousenwebview` develop+DevTools now has a tested local-first contract (`127.0.0.1:8001`, then `8012`, then `test2` fallback); explicit `__USE_LOCAL_DEVTOOLS__=false` is the tested remote mode.

Question source manifest:

- `docs/qa/2026-06-06-wechat-tutorbot-question-source-manifest.md`
- The active repo does not contain `docs/2026/题库`; the current QA source bank is the external FastAPI20251222 path recorded in that manifest.

Do not use `standalone_shadow`, `node_contract`, or `backend_harness` rows as proof that the real `yousenwebview/packageDeeptutor` WeChat path passed.

## Single Authority Contract

One business fact:

> A learner's current exam question, official answer, learner answer, grading result, and follow-up explanation must be decided from one canonical question authority for the current turn.

One authority:

- Real WeChat frontend: `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- Transport: `/api/v1/chat/start-turn` plus the existing `/api/v1/ws`
- Payload authority: `followup_question_context` for current question object
- Answer authority: exact question / official question context in the TutorBot question lifecycle skill/service
- Expression authority: terminal writer can shorten or explain, but cannot change official answer

Competing authorities to watch:

- RAG answer text changing official answers
- LLM/council answer override
- frontend prompt text becoming the only question evidence
- stale active object from previous turn
- `promptIntent` carrying question data
- `structuredSubmitContext` being mistaken for backend truth
- standalone `wx_miniprogram` evidence being mistaken for real `packageDeeptutor` evidence

## Per-Round Ledger Fields

Each probe row must record:

| Field | Required value |
| --- | --- |
| `round_id` | Stable id, e.g. `QA30-001` |
| `entry_surface` | `real_wechat_package` / `standalone_shadow` / `node_contract` / `backend_harness` |
| `transcript` | Learner turns and TutorBot visible replies |
| `conversation_id` | WeChat/backend conversation id, or `N/A` for static contract tests |
| `turn_id` | Backend turn id, or `N/A` |
| `question_source` | Exact file, question id, topic, or `missing_question_anchor` |
| `source_hash` | SHA256 from `2026-06-06-wechat-tutorbot-question-source-manifest.md` when official-answer authority is claimed |
| `question_id` | Canonical question id if resolved |
| `resolved_authority` | `exact_question`, `followup_question_context`, `lifecycle_clarification`, `rag_degraded_guard`, etc. |
| `learner_answer` | Parsed learner answer, or `none` |
| `official_answer` | Official answer if available |
| `authority_trace` | How the system got from input to answer authority |
| `expected` | What a satisfied learner should receive |
| `actual` | Visible TutorBot response |
| `correctness` | pass / fail / partial |
| `language_understanding` | 1-5 |
| `explanation_quality` | 1-5 |
| `expression_quality` | 1-5 |
| `customer_satisfaction` | 1-5 |
| `refusal_class` | `not_refusal` / `reasonable_clarification` / `wrong_refusal` / `unsafe_refusal` |
| `severity` | P0 / P1 / P2 / pass |
| `issue_id` | Link to issue register row if failed |
| `fix_status` | open / fixed / deferred / blocked |
| `evidence_commands` | Commands, screenshots, trace ids, or Langfuse links |

## Severity Rules

P0:

- Official answer is changed by RAG, LLM, council, or frontend text.
- TutorBot refuses a question while canonical question context is present.
- Cross-turn state mixes two different questions and grades against the wrong one.
- New chat WebSocket route, production DB write, or canonical learner truth write is introduced.

P1:

- `followup_question_context` is dropped across page jump, submit, retry, reconnect, or history restore.
- Visible answer is correct but authority trace is wrong or missing.
- T题库外 / low-information request fabricates an official answer.
- Real WeChat evidence is mislabeled as harness/shadow or the reverse.
- Learner answer extraction changes what the learner selected.

P2:

- Answer is correct but too long, too cold, or less useful than expected.
- RAG unavailable wording is shaky but does not change official answer.
- Standalone/shadow parity drift that does not affect current real `packageDeeptutor` path.
- Optional observability field is missing but the turn can still be traced by other evidence.

## 30-Round Scenario Matrix

| ID | Entry | Scenario | Source | Expected authority | Pass condition |
| --- | --- | --- | --- | --- | --- |
| QA30-001 | real_wechat_package | Full single-choice true exam, learner picks correct answer | 2025/2024 JSON bank | exact_question | Correct official answer, no answer_key override |
| QA30-002 | real_wechat_package | Full single-choice true exam, learner picks wrong answer | 2025/2024 JSON bank | exact_question | Marks wrong and explains exact official answer |
| QA30-003 | real_wechat_package | Shuffled options where correct value changes letter | historical bank | exact_question with query option surface | Grades by current option surface, not old letter |
| QA30-004 | real_wechat_package | Multi-choice with compact `A施工方案 B支架构造` text | historical bank | exact_question | Extracts actual learner answer only |
| QA30-005 | real_wechat_package | Multi-choice natural answer, no letters | historical bank | exact_question or clarification | Does not count unselected candidates as learner answer |
| QA30-006 | real_wechat_package | Value-only option anchor such as underground diaphragm wall values | historical bank | exact_question | Resolves only if high confidence; otherwise clarifies |
| QA30-007 | real_wechat_package | Follow-up: `为什么不是B？一句话` | prior exact question | active question context | Uses same question and brevity constraint |
| QA30-008 | real_wechat_package | Follow-up: `错因是什么？10个字以内` | prior wrong answer | active question context | Returns short wrong-cause from same question |
| QA30-009 | real_wechat_package | Follow-up: numerical boundary `1.0m行不行` | prior exact question | active question context | Gives yes/no from official explanation |
| QA30-010 | real_wechat_package | Switch to a new full question after old active object | new full question | new exact_question | New question overrides stale active object |
| QA30-011 | real_wechat_package | Low-info request `2021案例二第3问答案发我` | missing anchor | lifecycle_clarification | Clarifies missing题干/题卡, no fabricated answer |
| QA30-012 | real_wechat_package | Repeat low-info `我说了在题卡里` | missing anchor | lifecycle_clarification | Still clarifies unless card object exists |
| QA30-013 | real_wechat_package | Case grading with full student answer | case JSON | case grading authority | Gives score points, missed points, next action |
| QA30-014 | real_wechat_package | Case explanation follow-up after grading | prior case | active case context | Explains same case, no new question generation |
| QA30-015 | real_wechat_package | Question-bank-outside knowledge question | no official question | teaching diagnosis | Helpful teaching answer, no official score |
| QA30-016 | real_wechat_package | Ambiguous topic request, no question | no anchor | clarification or diagnostic | Asks for题干/题卡 without wrong refusal |
| QA30-017 | real_wechat_package | Submit visible AI card lacking `followupContext` | frontend card | followup_question_context from visible card | start-turn carries question/options/user_answer |
| QA30-018 | real_wechat_package | Retry after visible card grading | prior user message | same followup_question_context | Retry sends same context and `persist_user_message=false` |
| QA30-019 | real_wechat_package | Multi-card submit with mixed context/no-context cards | frontend cards | `followup_question_context.items` | Preserves each selected question item |
| QA30-020 | real_wechat_package | Cold history restore then retry | history restore | restored context or fail-closed | Does not pretend context exists if not restorable |
| QA30-021 | real_wechat_package | Assessment wrong-item -> report -> TutorBot | assessment object | followup_question_context | TutorBot knows stem/options/learner answer |
| QA30-022 | real_wechat_package | Wrong-item same-type training follow-up | prior wrong item | active question context | Diagnoses错因 and gives similar practice without losing item |
| QA30-023 | real_wechat_package | WebSocket reconnect during answer | same turn | same turn authority | No duplicate answer or context loss |
| QA30-024 | backend_harness | RAG degraded with exact question resolved | historical exact | exact_question + degraded metadata | Answer still official, trace marks degraded |
| QA30-025 | backend_harness | RAG degraded without exact evidence | no exact | degraded guard | Does not fabricate official answer |
| QA30-026 | backend_harness | RAG returns conflicting answer text | exact question present | exact_question | LLM/RAG cannot override official answer |
| QA30-027 | backend_harness | Deep_question preselected but user asks existing题 answer | existing context | TutorBot lifecycle | Does not route to question generation |
| QA30-028 | node_contract | Package start-turn payload schema | package ws-stream | canonical protocol | Sends `followup_question_context`, not new chat WS or duplicate truth |
| QA30-029 | standalone_shadow | Standalone wx visible-card submit/retry parity | wx_miniprogram | shadow parity only | Mirrors context continuity but is not production evidence |
| QA30-030 | real_wechat_package | Customer-satisfaction regression: concise, warm, actionable explanation | mixed | correct authority + expression | Score >= 4/5 without answer drift |

## Current Issue Register Addendum

| Issue | Severity | Status | Root cause | Evidence | Fix |
| --- | --- | --- | --- | --- | --- |
| `WX-SHADOW-001` | P1 shadow / P2 production | fixed | standalone `wx_miniprogram` kept old retry/context transfer and could turn question-object retry into text replay | `node wx_miniprogram/tests/test_chat_retry_billing_contract.js` failed before fix | Preserve `followupQuestionContext/structuredSubmitContext/promptIntent` on user message and retry options; add visible-card context builder |
| `EVIDENCE-001` | P1 | open | QA evidence can confuse real `packageDeeptutor` path with standalone/shadow `wx_miniprogram` path | subagent reachability audit | Every future ledger row must set `entry_surface` and report evidence boundary |
| `EVIDENCE-002` | P1 | fixed | `yousenwebview` DevTools runtime base URL contract drifted: implementation defaulted local for QA, but the contract test still expected remote and a temporary comment said to revert | `node yousenwebview/tests/test_app_runtime_base_selection.js` failed before this fix; DevTools runtime evaluate returned local-first base candidates | Keep develop+DevTools local-first as the canonical internal QA mode, remove temporary revert comment, and add explicit remote-mode assertions |

## This-Round Verification

Commands run:

```bash
node wx_miniprogram/tests/test_chat_retry_billing_contract.js
node wx_miniprogram/tests/test_chat_mcq_submit_prompt.js
node wx_miniprogram/tests/test_chat_question_context_continuity.js
node wx_miniprogram/tests/test_chat_pending_turn_continuity_contract.js
node wx_miniprogram/tests/test_app_runtime_base_selection.js
node yousenwebview/tests/test_app_runtime_base_selection.js
node yousenwebview/tests/test_api_base_failover.js
node yousenwebview/tests/test_chat_send_surface_telemetry.js
node yousenwebview/tests/test_ws_stream_auth_refresh.js
node yousenwebview/tests/test_package_chat_retry_billing_contract.js
```

All listed checks passed in the current run where applicable. The runtime base URL fix specifically passed:

- `node yousenwebview/tests/test_app_runtime_base_selection.js` -> `PASS test_app_runtime_base_selection.js (11 assertions)`
- `node wx_miniprogram/tests/test_app_runtime_base_selection.js` -> `PASS test_app_runtime_base_selection.js (6 assertions)`
- WeChat DevTools automation read `getApp().globalData` from `yousenwebview`: `apiUrl=http://127.0.0.1:8001`, `gatewayUrl=http://127.0.0.1:8001`, candidates `[8001, 8012, https://test2.yousenjiaoyu.com]`.

Not run yet:

- Full WebSocket terminal answer QA on `yousenwebview`
- real device smoke
- full 30-round conversation loop
- Langfuse trace review for this exact shadow fix

## Next Single Mainline

Run a full `/api/v1/chat/start-turn` + `/api/v1/ws` terminal-answer loop on the real `yousenwebview/packageDeeptutor` DevTools path for QA30-001/002/007. QA30-017/018 have payload-continuity evidence, but answer correctness, refusal class, and expression quality still need live WS evidence.
