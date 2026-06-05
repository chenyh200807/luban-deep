# 2026-06-06 WeChat TutorBot Question Authority QA Matrix

## Status

This is the working matrix for the next 30-round real or near-real WeChat TutorBot QA loop.

Current evidence status:

- `real_wechat_package`: partially covered. QA30-017/018 have WeChat DevTools automation evidence for `yousenwebview/packageDeeptutor` visible-card submit/retry payload authority. QA30-002 now has one real DevTools terminal-answer smoke for `/api/v1/chat/start-turn` + `/api/v1/ws` after `WX-REAL-004`. QA30-REAL-FINAL7 added 3 real terminal turns for active-question follow-up/regrade; QA30-REAL-011/015 added low-info/open-world terminal turns. Full 30-round terminal answer quality loop is still pending.
- `standalone_shadow`: partially covered. `wx_miniprogram/pages/chat/chat.js` context continuity was fixed only as shadow parity.
- `node_contract`: covered for the current P1 shadow parity fix.
- `backend_harness`: expanded for the active-question option challenge regression. `minimal_final7` passed 3/3 on local `/api/v1/chat/start-turn` + `/api/v1/ws`; earlier `minimal_final4/5/6` all failed 1/3 and are retained as before/after evidence under the ignored artifact directory.
- `runtime_base_authority`: fixed for DevTools QA. `yousenwebview` develop+DevTools now has a tested local-first contract (`127.0.0.1:8001`, then `8012`, then `test2` fallback); explicit `__USE_LOCAL_DEVTOOLS__=false` is the tested remote mode.
- `internal_authority_trace`: covered for the 5 current real `yousenwebview/packageDeeptutor` DevTools terminal rows. `scripts/extract_wechat_tutorbot_authority_ledger.py` now reads the existing local SQLite session store (`turn_events + sessions.runtime_state`) and emits compact authority rows without adding a production endpoint, new runtime state, production DB write, or second answer truth.
- `near_real_http_ws`: expanded by `QA30-STATE-001..003` and `QA30-NR-004..016`. These probes use WeChat-shaped `/api/v1/chat/start-turn` + `/api/v1/ws` with internal QA billing bypass, but not the DevTools container. `QA30-NR-004..016` now has a final after-fix authority ledger with 12/12 trace-complete rows under `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix/`; it specifically caught and then verified fixes for stale active/explicit/suspended question authority and option/value follow-up misrouting.

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
| `WX-AUTH-003` | P1 | fixed in backend harness | Active question option challenge such as `那C呢？一句话` could be interpreted by different modules as option submission, practice generation, or new question review. The shared failure shape was duplicate decision authority: option parsing, semantic router, lifecycle `question_review`, and mobile session alias all had partial authority over the same current-question fact. | Before: `minimal_final4/5/6` each passed 1/3. `minimal_final6` showed old historical question moved to `suspended_object_stack` while `question_review`/`deep_question_generation` created a C-language question. After: `minimal_final7` passed 3/3 and kept `historical:cf366dd4c395fffa` across follow-up and regrade. | Keep option-challenge wording as follow-up, clear misleading generation hints without explicit practice intent, preserve stored active question before suspend, resolve mobile public/mirror session ids without mirror-of-mirror, and make lifecycle `question_review` defer to active-question semantic routing before free-text review. |
| `WX-REAL-004` | P1 | fixed in real `packageDeeptutor` | Backend and `ws-stream` delivered the correct public TutorBot final answer, but the package renderer treated public phrases like `标准答案是 D` as hidden answer authority and sanitized the visible message to empty. | Before: real DevTools probe for `unified_1780691416028_69b788c2` / `turn_1780691416030_a1570ba196` saw `_onToken len=42` and `_onFinal responseLen=42`, but final AI `content/renderableContent` length was `0`. After: real DevTools probe for `unified_1780692282387_81bf021b` / `turn_1780692282389_f4cdd6118a` had `content/renderableContent` length `42` with `不对，标准答案是 D（D. 5%）...`. | Move phrase-based hidden-answer redaction out of public AI content projection: `ai-message-state.coerceUserVisibleContent()` now keeps public final prose while still blocking deterministic internal DSML/toolcall leakage. Keep `render-schema` authority scrubbing for structured MCQ/followup/presentation boundaries. |
| `WX-EXP-005` | P2 | deferred | Real package active-question option follow-up stayed on the same official answer, but did not directly answer `那C呢？` as `C=3%，不对`; it only restated D/5%. | `artifacts/qa/wechat-tutorbot-real-final7-20260606/summary.json`, `QA30-REAL-FINAL7-002`, `conversation_id=unified_1780692619402_d7820eca`, `turn_id=turn_1780692636572_eaf7c2a65d`. | Record as expression/follow-up usefulness issue. Do not add regex/router patch until repeated across more rounds or promoted to P1. |
| `WX-EXP-006` | P2 | deferred | Real package regrade after `那我改选D，对吗？一句话` preserved authority and graded correctly, but ignored the brevity constraint and emitted a long grader template. | `artifacts/qa/wechat-tutorbot-real-final7-20260606/summary.json`, `QA30-REAL-FINAL7-003`, `conversation_id=unified_1780692619402_d7820eca`, `turn_id=turn_1780692651216_75ccc15068`. | Record as TutorBot expression policy / mode adherence issue. Avoid treating this as answer-authority failure; no P0/P1 code change this round. |
| `EVIDENCE-003` | P1 evidence gap | fixed | The first real DevTools rows recorded visible terminal answers but not enough internal authority trace to prove object/route/answer source continuity. | `artifacts/qa/wechat-tutorbot-real-authority-trace-20260606/authority-ledger.jsonl`; `pytest -q tests/scripts/test_extract_wechat_tutorbot_authority_ledger.py`. | Add a thin internal QA extractor that reads persisted `turn_events.metadata_json` and `sessions.preferences_json.runtime_state` only. It reports scenario-aware trace completeness and does not mutate runtime, DB, or frontend state. |
| `WX-STATE-007` | P2 state hygiene probe | near-real not reproduced / DevTools pending | After a low-information clarification, later open-world teaching turns had no active question in their own result events, but the durable session active object still pointed to the earlier `question_lifecycle_clarification`. The near-real probe shows this stale durable object did not hijack open-world follow-up routing. | Initial signal: `artifacts/qa/wechat-tutorbot-real-authority-trace-20260606/authority-ledger.jsonl`, `QA30-REAL-015`. Follow-up probe: `artifacts/qa/wechat-tutorbot-state-after-clarification-probe-20260606/authority-ledger.jsonl`, `QA30-STATE-001..003`, all `trace_complete=true`; `QA30-STATE-003` answered漏保参数 via `tutorbot_kb_first_fast_policy`, not the old 2021 case. | Keep as state hygiene risk until a real DevTools repeat verifies the same behavior. Do not patch now: no user-visible failure, no answer-authority drift, and a patch would likely add state-clearing complexity before reproducing a defect. |
| `WX-AUTH-008` | P1 | fixed in near-real HTTP+WS | Full new MCQ turns after an old active question were still graded against the stale question. The shared failure shape was object-continuity authority drift: candidate context, explicit context, and suspended stack could all read the old question before lifecycle/exact authority got the current full question surface. | Before: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-fix/authority-ledger.jsonl`, `QA30-NR-006` graded `historical:cf366dd4c395fffa` (roof slope), official `A`, learner `C`, `answer_authority_source=active_object`. After explicit-context-only fix it still failed via suspended stack. Final after: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix/authority-ledger.jsonl`, `QA30-NR-006` resolved `historical:53cbdad71ba26c1c`, official `D`, learner `C`, `answer_authority_source=exact_question`, `trace_complete=true`. | Turn runtime now demotes stale explicit question context when the current message is a full free-text MCQ whose题干/选项 surface does not match that context; candidate contexts are skipped for full new MCQ requests; semantic routing also refuses to resume suspended old questions for full new MCQ surfaces. Same-question full MCQ still preserves explicit context. |
| `WX-AUTH-009` | P1 | fixed in near-real HTTP+WS | Option/value challenges such as `那1.0m行不行？一句话` or `A错在哪里？` could be treated as answer revision/submission. The shared failure shape was duplicate decision authority: deterministic option parser saw a follow-up, but LLM follow-up interpreter could still return `revise_answers` and deep_question would regrade. | Before: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-fix/authority-ledger.jsonl`, `QA30-NR-011` was `deep_question_grading`, learner `第1题：ACDE`, `next_action=route_to_grading`. Final after: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix/authority-ledger.jsonl`, `QA30-NR-011` is `deep_question_followup`, same `historical:9474436148e22029`, visible answer `不行，应≥1.2m。`; `QA30-NR-013` also remains follow-up. | `question_followup` now recognizes option-letter challenge variants and option-value numeric challenges before option submission extraction. Turn runtime emits deterministic `ask_followup` for stable follow-up formats before calling the LLM interpreter, so LLM cannot promote a stable follow-up into revise-answer authority. |
| `WX-EXP-010` | P2 | deferred | Several correct near-real answers remain too long for `一句话` / low-friction WeChat usage, especially exact multi-choice templates and open-world teaching. This is expression authority, not answer authority. | Final after-fix transcript: `QA30-NR-008`, `QA30-NR-010`, and `QA30-NR-016` are correct/traceable but verbose. | Record for expression policy / response mode work. Do not mix into current P1 authority fix; next pass should tune terminal writer brevity without changing official-answer authority. |
| `OBS-004` | P2 evidence gap | open | Local Langfuse SDK initializes but auth check to `http://localhost:3030` fails, so Langfuse cannot be treated as this run's authority evidence. | Backend logs in all three core12 reruns show `Langfuse initialization skipped: Langfuse auth check failed: [Errno 61] Connection refused`; authority evidence instead comes from `turn_events` and `sessions.runtime_state` via `scripts/extract_wechat_tutorbot_authority_ledger.py`. | Keep SQLite turn-event authority ledger as primary evidence until Langfuse local service is reachable and trace ids can be linked to turns. Do not fake trace ids or report Langfuse closure. |

## Real WeChat Finding: `WX-REAL-004`

One business fact:

> A backend-public TutorBot final answer must remain visible as the terminal AI message in the real WeChat package.

One authority:

- Writer: backend TutorBot `/api/v1/ws` public `content` / `result.metadata.response`.
- Transfer: `yousenwebview/packageDeeptutor/utils/ws-stream.js` forwards public `content` and `final` events.
- Reader/projection: `packageDeeptutor/pages/chat/chat.js` and `utils/ai-message-state.js` project the already-public answer into page state.
- Boundary: frontend rendering may block deterministic internal tool leakage, but it must not reclassify public final answer text as hidden answer authority.

Competing authorities found:

- `render-schema.sanitizeAuthorityMarkdownText()` was written for structured hidden fields (`correct_answer`, `grading_key`, MCQ followup context, presentation fallback), but `ai-message-state.coerceUserVisibleContent()` reused it for public final prose.
- The subsequent `done` event made the empty projection look like a transport or TutorBot refusal, but the first wrong reader was the public-content sanitizer.

Break point:

- Last correct point: real DevTools probe saw `_onToken` with length `42` and `_onFinal.responseLen=42`.
- First wrong point: `coerceUserVisibleContent()` called `sanitizeAuthorityMarkdownText()` and turned `不对，标准答案是 D...` into an empty visible message.

Fix type:

- 收权 and demotion. Public final content stays under backend stream authority; structured hidden-field redaction remains in `render-schema` where it belongs. No new chat WebSocket, no new answer authority, no production DB write.

After evidence:

```json
{
  "entry_surface": "real_wechat_package",
  "round_id": "QA30-002",
  "conversation_id": "unified_1780692282387_81bf021b",
  "turn_id": "turn_1780692282389_f4cdd6118a",
  "resolved_authority": "tutorbot_exact_fast_path",
  "learner_answer": "C",
  "official_answer": "D",
  "actual": "不对，标准答案是 D（D. 5%），题库解析依据是：屋面最小坡度：压型金属板：5%。",
  "correctness": "pass",
  "refusal_class": "not_refusal",
  "customer_satisfaction": 5
}
```

## Backend Harness Finding: `WX-AUTH-003`

One business fact:

> If a learner is inside a current historical MCQ, a terse option challenge like `那C呢？一句话` must stay attached to that same `question_id`, official answer, learner answer, and grading state.

One authority:

- Writer: exact-question fast path / question-followup context emitted by TutorBot runtime.
- Persistence: session `runtime_state.active_object` plus `suspended_object_stack` only when a real new object replaces the current one.
- Reader: TurnRuntimeManager restores active question context, then ChatOrchestrator asks semantic routing before lifecycle free-text review/generation can mutate the context.
- Terminal answer: `deep_question_followup` / `deep_question_grading` can explain or regrade, but cannot swap the official question.

Competing authorities found:

- Option parser treated `C`-style wording too close to a submission.
- LLM follow-up interpreter could return `generate_more_questions`.
- Mobile start-turn access check found mirror variants but did not canonicalize the runtime session id; the first fix then over-selected mirror when direct and mirror both existed, causing mirror-of-mirror behavior.
- Lifecycle `question_review` ran before active-object semantic routing and converted `那C呢？一句话` into `mode=custom/topic=那C呢？一句话`, causing a new C-language question.

Fix type:

- 收权, not fallback sprawl. The wrapper now only canonicalizes session id. Active-question semantics are decided once through the existing question context path before lifecycle review/generation can replace the object.

Evidence:

- Ignored artifact path: `artifacts/qa/wechat-tutorbot-authority-option-challenge-fix-20260606/`
- Before: `minimal_final4_summary.json`, `minimal_final5_summary.json`, `minimal_final6_summary.json` -> each `passed=1`, `failed=2`.
- After: `minimal_final7_summary.json` -> `passed=3`, `failed=0`.
- Final ledger:

```jsonl
{"round_id":"QA30-FINAL7-001","resolved_authority":"tutorbot_exact_fast_path","question_id":"historical:cf366dd4c395fffa","learner_answer":"B","is_correct":false,"passed":true}
{"round_id":"QA30-FINAL7-002","resolved_authority":"deep_question_followup","next_action":"route_to_followup_explainer","question_id":"historical:cf366dd4c395fffa","learner_answer":"B","is_correct":false,"passed":true}
{"round_id":"QA30-FINAL7-003","resolved_authority":"deep_question_grading","next_action":"route_to_grading","question_id":"historical:cf366dd4c395fffa","learner_answer":"第1题：D","is_correct":true,"passed":true}
```

## Real WeChat QA Extension: `QA30-REAL-FINAL7` and Open-World

Artifacts:

- `artifacts/qa/wechat-tutorbot-real-final7-20260606/summary.json`
- `artifacts/qa/wechat-tutorbot-real-final7-20260606/ledger.jsonl`
- `artifacts/qa/wechat-tutorbot-real-openworld-20260606/summary.json`
- `artifacts/qa/wechat-tutorbot-real-openworld-20260606/ledger.jsonl`

Real package terminal results:

| Round | Conversation | Turn | Scenario | Result | Satisfaction | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `QA30-REAL-FINAL7-001` | `unified_1780692619402_d7820eca` | `turn_1780692619406_68b9905083` | full historical MCQ, learner chose C | pass | 5 | Correctly answered `不对，标准答案是 D（D. 5%）...`; no refusal, no answer drift. |
| `QA30-REAL-FINAL7-002` | `unified_1780692619402_d7820eca` | `turn_1780692636572_eaf7c2a65d` | follow-up `那C呢？一句话` | partial / P2 | 3 | Preserved D/5% authority but did not explicitly say C=3% is wrong. |
| `QA30-REAL-FINAL7-003` | `unified_1780692619402_d7820eca` | `turn_1780692651216_75ccc15068` | revise answer to D | pass / P2 expression | 2 | Correctly graded D as right but ignored `一句话` and emitted full grader template. |
| `QA30-REAL-011` | `unified_1780692809261_3829d868` | `turn_1780692809264_bd924a68cd` | low-info request `2021案例二第3问答案发我` | pass | 4 | Did not fabricate official answer; asked for题卡/题干 and explained why direct answer would be invented. |
| `QA30-REAL-015` | `unified_1780692809261_3829d868` | `turn_1780692826595_36edaeb7b5` | open-world knowledge question | pass | 5 | Fail-opened to teaching explanation; no official score or fake standard answer. |

Authority interpretation:

- These 5 rows are real `yousenwebview/packageDeeptutor` DevTools terminal evidence, not backend harness or standalone shadow.
- Public stream evidence proves terminal answer visibility, conversation/turn continuity, and no official-answer drift.
- Internal active-object evidence is still incomplete in the artifact: it records public WS status/final events and `/conversations/{id}/messages` readback, but does not yet snapshot internal `runtime_state.active_object`, `question_lifecycle_decision`, and `turn_semantic_decision`. Add this to the next runner before claiming full authority trace coverage for all 30 rounds.

Internal authority trace was added after the initial visible-answer artifact.

Artifact:

- `artifacts/qa/wechat-tutorbot-real-authority-trace-20260606/authority-ledger.jsonl`

Command:

```bash
python scripts/extract_wechat_tutorbot_authority_ledger.py \
  --turn QA30-REAL-FINAL7-001=turn_1780692619406_68b9905083 \
  --turn QA30-REAL-FINAL7-002=turn_1780692636572_eaf7c2a65d \
  --turn QA30-REAL-FINAL7-003=turn_1780692651216_75ccc15068 \
  --turn QA30-REAL-011=turn_1780692809264_bd924a68cd \
  --turn QA30-REAL-015=turn_1780692826595_36edaeb7b5 \
  --output artifacts/qa/wechat-tutorbot-real-authority-trace-20260606/authority-ledger.jsonl
```

Summary from the internal ledger:

| Round | Trace expectation | Trace complete | Answer authority | Internal authority result |
| --- | --- | --- | --- | --- |
| `QA30-REAL-FINAL7-001` | `exact_question_tutorbot` | yes | `exact_question` | `question_lifecycle_decision.scene=mcq_grading`; active object `historical:cf366dd4c395fffa`; learner `C`, official `D`. |
| `QA30-REAL-FINAL7-002` | `active_question_followup_or_grading` | yes | `deep_question_followup` | `turn_semantic_decision.next_action=route_to_followup_explainer`; same active object `historical:cf366dd4c395fffa`; no state change. |
| `QA30-REAL-FINAL7-003` | `active_question_followup_or_grading` | yes | `active_object` | `turn_semantic_decision.next_action=route_to_grading`; `allowed_patch=update_answer_slot`; same active object version advanced to `3`. |
| `QA30-REAL-011` | `lifecycle_clarification` | yes | `lifecycle_clarification` | Low-information exam query was blocked as `missing_question_anchor`; no official answer fabricated. |
| `QA30-REAL-015` | `open_world_teaching` | yes | `tutorbot_kb_first_fast_policy` | Open-world construction knowledge answer used teaching path, no `question_id`, no official score, no fake standard answer. |

## Near-Real State Hygiene Probe: `QA30-STATE-001..003`

Artifact:

- `artifacts/qa/wechat-tutorbot-state-after-clarification-probe-20260606/summary.json`
- `artifacts/qa/wechat-tutorbot-state-after-clarification-probe-20260606/transcript.jsonl`
- `artifacts/qa/wechat-tutorbot-state-after-clarification-probe-20260606/authority-ledger.jsonl`

Evidence boundary:

- Entry: `near_real_http_ws_wechat_payload`
- Path: `/api/v1/chat/start-turn` + `/api/v1/ws`
- Not real DevTools container evidence; use it as a fast state-continuity probe before real package repeat.
- Billing: local internal QA bypass only; no production DB write, no learner truth write, no remote deploy.

Result:

| Round | Learner turn | Conversation | Turn | Trace expectation | Authority result | Visible behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `QA30-STATE-001` | `2021案例二第3问答案发我，别废话` | `unified_1780693823345_77c68200` | `turn_1780693823347_55c52cf5f0` | `lifecycle_clarification` | `business_gate_result=blocked_low_information_exam_query`; active object is `question_lifecycle_clarification`. | Reasonable clarification; no fabricated official answer. |
| `QA30-STATE-002` | `施工现场临时用电“三级配电、两级保护”是什么意思？一句话` | same | `turn_1780693844162_365a9a505e` | `open_world_teaching` | `execution_path=tutorbot_kb_first_fast_policy`; no active question in result event; durable session still has previous clarification object. | Helpful open-world teaching answer, no official score. |
| `QA30-STATE-003` | `那漏保参数呢？一句话` | same | `turn_1780693869252_f9dd44b38d` | `open_world_teaching` | Still `tutorbot_kb_first_fast_policy`; stale clarification did not hijack routing. | Correctly answered漏保参数: 总配延时型、开关箱 30mA/0.1s、潮湿环境 15mA. |

Conclusion:

- Current near-real evidence does not promote `WX-STATE-007` to P1. The stale durable clarification object is observable, but the turn-level result authority stayed open-world teaching.
- Next real DevTools batch should include this same three-turn pattern before marking the risk closed for the primary front end.

## Near-Real Core12 Finding: `QA30-NR-004..016`

Artifacts:

- Before current P1 fixes: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12/`
- After first local fix, still failing stale suspended object: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-fix/`
- After explicit-context fix, still failing stale suspended object: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-explicit-fix/`
- Final after suspended-stack fix: `artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix/`

Evidence boundary:

- Entry: `near_real_http_ws_wechat_payload`
- Path: `/api/v1/chat/start-turn` + existing `/api/v1/ws`
- Account: fixed internal QA account `qa_tutorbot_mcq`
- Billing: local internal QA bypass only
- Not real DevTools container evidence, not production DB write, not canonical learner truth write, not remote deploy.

One business fact:

> Each turn must decide whether the learner is answering the current active question, asking about it, or supplying a new complete question. That relation must be authoritative before grading.

One authority:

- Writer: exact-question / question lifecycle result for complete current-question surfaces; question-followup context for true active-question follow-up.
- Persistence/transfer: existing `active_object`, `question_followup_context`, and `suspended_object_stack`.
- Reader: `TurnRuntimeManager._resolve_question_followup_context_and_action` and semantic routing.
- Terminal writers: TutorBot exact fast path, `deep_question_followup`, or lifecycle clarification. They may explain, but cannot choose a different official question.

Competing authorities found:

- Candidate active question context read the old question before lifecycle/exact saw the new complete MCQ.
- Explicit `question_followup_context` could be stale and still parse `我选C` from a new complete question as an old-question answer.
- `suspended_object_stack` could resume an older question because its options contained the same answer letter.
- Deterministic option/value follow-up detection could be overruled by LLM `revise_answers`.

Break points:

- Last correct point for `QA30-NR-006`: user supplied a full new MCQ surface with options `A.檐口顶点 B.屋脊 C.墙顶点 D.最高点` and answer `C`.
- First wrong point before fix: semantic/active-object path bound that `C` to old roof-slope question `historical:cf366dd4c395fffa` and graded against official `A=5%`.
- Last correct point for `QA30-NR-011`: `question_followup` could identify `那1.0m行不行？一句话` as a current-question numeric follow-up.
- First wrong point before fix: LLM follow-up interpreter promoted it to `revise_answers`, causing `deep_question_grading` to regrade old `ACDE`.

Fix type:

- 收权 and demotion, not another router. Full new MCQ surfaces now demote stale explicit/candidate/suspended question readers unless the message surface matches the explicit question. Stable option/value challenges now produce deterministic `ask_followup` before LLM interpretation.
- No new chat WebSocket, no new answer truth, no production DB write, no learner truth write.

Before/after metrics:

| Round | Before path | Before authority | Final path | Final authority | Outcome |
| --- | --- | --- | --- | --- | --- |
| `QA30-NR-006` | `deep_question_grading` | old active roof question `historical:cf366dd4c395fffa`, official `A`, learner `C` | `tutorbot_exact_fast_path` | new historical-building question `historical:53cbdad71ba26c1c`, official `D`, learner `C` | fixed P1 |
| `QA30-NR-011` | `deep_question_grading` | active underground wall question, learner rewritten as `第1题：ACDE` | `deep_question_followup` | same underground wall question, no regrade | fixed P1 |
| `QA30-NR-013` | `deep_question_followup` | same underground wall question | `deep_question_followup` | same underground wall question | regression guard pass |

Final ledger summary:

| Round | Scenario | Authority result | Customer result |
| --- | --- | --- | --- |
| `QA30-NR-004` | shuffled roof options, learner A | exact question on query option surface, official `A` | pass |
| `QA30-NR-005` | follow-up asks if old letters were used | same roof active question follow-up | pass |
| `QA30-NR-006` | switch to full historical-building MCQ | exact question `historical:53cbdad71ba26c1c`, official `D`, learner `C` | pass |
| `QA30-NR-008` | natural-language multi-select template support | exact question, learner `ABE`, official `ABE` | pass, verbose |
| `QA30-NR-009` | why C not count | active question follow-up | pass, not concise enough |
| `QA30-NR-010` | underground wall learner `ACDE` | exact question, official `CDE` | pass, verbose |
| `QA30-NR-011` | `那1.0m行不行？一句话` | active question follow-up | pass |
| `QA30-NR-012` | value-only underground wall, learner `CDE` | exact question, official `CDE` | pass |
| `QA30-NR-013` | `A错在哪里？一句话` | active question follow-up | pass |
| `QA30-NR-014` | low-info case request | lifecycle clarification | pass |
| `QA30-NR-015` | repeated `题卡里` demand | lifecycle clarification | pass |
| `QA30-NR-016` | open-world temporary electricity question | open-world teaching, no official score | pass, verbose |

Verification commands:

```bash
pytest -q \
  tests/services/test_question_followup.py \
  tests/services/test_semantic_router.py \
  tests/api/test_unified_ws_turn_runtime.py::test_full_new_mcq_does_not_regrade_stale_active_question \
  tests/api/test_unified_ws_turn_runtime.py::test_full_new_mcq_does_not_regrade_stale_explicit_question \
  tests/api/test_unified_ws_turn_runtime.py::test_full_same_mcq_keeps_explicit_question_context \
  tests/api/test_unified_ws_turn_runtime.py::test_explicit_question_value_challenge_routes_to_followup \
  tests/api/test_unified_ws_turn_runtime.py::test_resolve_question_followup_explicit_context_keeps_option_challenge_from_llm_generation \
  tests/api/test_unified_ws_turn_runtime.py::test_resolve_question_followup_explicit_context_ignores_generation_hint_for_option_challenge \
  tests/scripts/test_run_wechat_tutorbot_qa_batch.py \
  tests/scripts/test_extract_wechat_tutorbot_authority_ledger.py

python scripts/run_wechat_tutorbot_qa_batch.py \
  --api-base-url http://127.0.0.1:8001 \
  --username qa_tutorbot_mcq \
  --password QaTutorbot2026 \
  --output-dir artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix \
  --timeout-seconds 120

python scripts/extract_wechat_tutorbot_authority_ledger.py \
  $(awk '{print "--turn", $0}' artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix/turn_ids.txt) \
  --entry-surface near_real_http_ws_wechat_payload \
  --output artifacts/qa/wechat-tutorbot-near-real-batch-20260606-core12-after-suspended-fix/authority-ledger.jsonl
```

Subagent trace-review checklist for the next runner:

- Record `capability`, `execution_engine`, `question_lifecycle_decision`, `turn_semantic_decision`, `active_object.object_id/version/source_turn_id`, question/options hash, `user_answer`, `is_correct`, `question_authority_source`, `correct_answer_present`, result `mode`, `grading_blocked`, assistant content source, and terminal status.
- For follow-up rounds, `active_object.object_id` must remain the same as the first round unless the user supplies a new full question.
- For revise-answer rounds, `allowed_patch` should be answer-slot update, not new active object.
- Frontend visible answer is necessary but not sufficient evidence; it must be paired with internal session authority snapshots.

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
node yousenwebview/tests/test_question_review_readonly_mcq.js
node yousenwebview/tests/test_package_chat_retry_billing_contract.js
pytest -q tests/api/test_mobile_router.py::test_mobile_chat_start_turn_uses_canonical_runtime_session_for_mirror_conversation tests/api/test_mobile_router.py::test_mobile_chat_start_turn_keeps_direct_runtime_session_when_direct_and_mirror_exist tests/api/test_mobile_router.py::test_mobile_chat_start_turn_passes_chat_mode_and_followup_context tests/api/test_mobile_router.py::test_mobile_chat_start_turn_requires_authentication tests/api/test_mobile_router.py::test_mobile_chat_start_turn_rejects_other_users_conversation tests/api/test_mobile_router.py::test_list_conversations_uses_owner_source_and_archived_filters tests/api/test_mobile_router.py::test_list_conversations_can_request_archived_items tests/api/test_mobile_router.py::test_get_conversation_messages_merges_internal_tutorbot_variants tests/api/test_mobile_router.py::test_get_conversation_messages_rejects_existing_non_mobile_session tests/api/test_mobile_router.py::test_delete_conversation_deletes_direct_and_mirror_variants
pytest -q tests/services/test_question_followup.py tests/services/test_semantic_router.py tests/services/test_semantic_router_eval_cases.py tests/services/test_semantic_router_stack.py
pytest -q tests/api/test_unified_ws_turn_runtime.py::test_resolve_question_followup_explicit_context_keeps_option_challenge_from_llm_generation tests/api/test_unified_ws_turn_runtime.py::test_resolve_question_followup_explicit_context_ignores_generation_hint_for_option_challenge tests/api/test_unified_ws_turn_runtime.py::test_answered_active_question_can_generate_related_questions_without_regrading tests/api/test_unified_ws_turn_runtime.py::test_submission_with_next_training_request_routes_to_grading tests/api/test_unified_ws_turn_runtime.py::test_start_turn_recovers_stored_active_question_for_plain_text_option_followup tests/api/test_unified_ws_turn_runtime.py::test_start_turn_merges_redacted_public_submission_with_stored_active_question
pytest -q tests/runtime/test_orchestrator_autoroute.py::test_preselected_deep_question_grades_submission_before_practice_generation tests/runtime/test_orchestrator_autoroute.py::test_lifecycle_practice_generation_respects_active_question_followup tests/runtime/test_orchestrator_autoroute.py::test_lifecycle_question_review_respects_active_question_followup tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_grades_before_generation_in_mixed_answer_then_more_practice tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_autoroutes_question_followup_without_revealing_answer tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_prefers_llm_followup_action_before_regex_fallback tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_treats_explicit_choice_type_as_generation_with_active_question tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_clears_previous_answer_when_explicit_generation_reuses_active_question
```

All listed checks passed in the current run where applicable. The runtime base URL fix specifically passed:

- `node yousenwebview/tests/test_app_runtime_base_selection.js` -> `PASS test_app_runtime_base_selection.js (11 assertions)`
- `node wx_miniprogram/tests/test_app_runtime_base_selection.js` -> `PASS test_app_runtime_base_selection.js (6 assertions)`
- WeChat DevTools automation read `getApp().globalData` from `yousenwebview`: `apiUrl=http://127.0.0.1:8001`, `gatewayUrl=http://127.0.0.1:8001`, candidates `[8001, 8012, https://test2.yousenjiaoyu.com]`.
- WeChat DevTools terminal-answer smoke after `WX-REAL-004`: real `packageDeeptutor/pages/chat/chat`, `conversation_id=unified_1780692282387_81bf021b`, `turn_id=turn_1780692282389_f4cdd6118a`, `_onToken len=42`, `_onFinal responseLen=42`, final `content/renderableContent len=42`.
- Real package `QA30-REAL-FINAL7` three-turn run: `pass=2`, `partial=1`, `fail=0` after human QA correction; P2 issues only.
- Real package open-world run: `pass=2`, `partial=0`, `fail=0`.

Not run yet:

- Full 30-round WebSocket terminal answer QA on `yousenwebview`
- real device smoke
- internal `active_object` / lifecycle decision snapshot capture for every real package round
- Langfuse UI review for this exact fix. Local SDK initialized, but `localhost:3030` auth check failed during backend harness runs; use event metadata and SQLite session rows as current evidence.

## Next Single Mainline

Upgrade the real `yousenwebview/packageDeeptutor` DevTools runner to capture internal session authority snapshots (`active_object`, lifecycle decision, semantic decision, result mode), then continue the remaining 30-round matrix. Current real package terminal evidence is useful, but full authority closure still requires pairing frontend-visible transcript with backend internal state.
