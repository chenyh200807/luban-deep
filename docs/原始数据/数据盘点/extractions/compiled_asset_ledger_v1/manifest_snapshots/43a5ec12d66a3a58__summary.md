# WeChat TutorBot Real Package Probe - 2026-06-06

## Scope

- Entry: `real_wechat_package`
- Project root opened by DevTools: `yousenwebview`
- Page exercised: `packageDeeptutor/pages/chat/chat`
- Auth state: `qa_token`
- Auth mode: `local_dev_wechat`
- Backend: `http://127.0.0.1:8001`
- No remote deploy, no production DB write, no canonical learner truth write, no new chat WebSocket.

## Round REAL-WX-TERM-001

- Scenario: full historical single-choice exam question; learner picked wrong option `C`.
- Conversation: `unified_1780760296561_0f2aa0c4`
- Turn: `turn_1780760296564_c4ea46ced5`
- Trace id: `f90f50195a9ef627c1e8b6124034849b`
- Langfuse: verified via local API, trace HTTP 200, name `tutorbot.construction-exam-coach`, observations `5`
- Resolved authority: `exact_question`
- Question id: `historical:cf366dd4c395fffa`
- Answer authority source: `historical_question_bank`
- Current option surface official answer: `A` / `5%`
- Learner answer: `C`
- Result: pass. Visible terminal answer kept official `A (5%)` and did not let the learner answer override the answer key.

## Authority Trace

The persisted turn result has `authority_applied=true`, `execution_engine=tutorbot_runtime`, and `exact_question.correct_answer=A`.

Evidence sources attached to the same turn include:

- Historical question bank source ref: `FINAL_CLEANED_QIANTIZAN.json`, node `1A411010`, `建筑设计`
- RAG textbook corroboration: `CET_1A411011_P0020_001`, `p.20 屋面基本构造要求`, showing `压型金属板、金属夹芯板 | 5`

## Issue Register

- `WX-REAL-OBS-001` P2 observation: `exact_question.metadata.canonical_correct_answer=D` coexists with `exact_question.correct_answer=A` because the resolver projected the bank answer to the user's current option surface (`option_surface=query`). Runtime readers inspected in this check consume `exact_question.correct_answer`, so this did not affect the answer. Keep it registered as trace hygiene / reader-confusion risk; escalate if any downstream reader uses metadata `canonical_correct_answer` as grading authority.

## Evidence Files

- `real-package-terminal-1780760289173.json`: DevTools automator terminal probe output.
- `authority-trace-real-package-terminal-1780760289173.json`: compact transcript, DB session/turn, authority trace, quality rating.
- `authority-ledger.jsonl`: ledger row for aggregate reporting.
