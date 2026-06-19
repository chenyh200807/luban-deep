# WeChat TutorBot Real Package UI Semantic Batch R4 - 2026-06-06

## Scope

- Evidence surface: `real_wechat_package`
- Interaction mode: `ui_textarea_input_and_send_button_tap`
- Project root: `yousenwebview`
- Page: `packageDeeptutor/pages/chat/chat`
- Auth state: `qa_token`
- Auth mode: `local_dev_wechat`
- Backend: `http://127.0.0.1:8001`
- Boundary: DevTools real package with local backend and dev WeChat token. This is UI-level semantic QA, not true-device/prod-login closure.

## Metrics

- Rows: 10
- Authority pass: 9
- Semantic pass: 5
- Semantic fail: 5
- Rows with LLM observations: 10
- Langfuse ERROR observations in these rows: 0

## Findings

- All 10 rows have Langfuse LLM observations after delayed trace requery.
- Official answer authority held in 9/10 rows; one row failed previous-question resume and used the wrong active question authority.
- Semantic understanding passed only 5/10 rows. Main weak spots: option challenge treated as resubmission, shallow follow-up answers that ignore the challenged option/premise, and previous-object resume after a switch.
- Evidence is UI-level DevTools automation through textarea input and send-button tap, not page method calls.

## Files

- `summary.json`
- `authority-ledger.jsonl`
- `transcript.jsonl`
- `REAL-WX-UI-R4-*.json`
- `run-ui-semantic-batch.js`
