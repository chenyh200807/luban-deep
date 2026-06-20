# WeChat TutorBot Real Package Batch R2 - 2026-06-06

## Scope

- Evidence surface: `real_wechat_package`
- Mechanism: WeChat DevTools CLI `auto` + `miniprogram-automator`
- Project root: `yousenwebview`
- Exercised page: `packageDeeptutor/pages/chat/chat`
- Auth state: `qa_token`
- Auth mode: `local_dev_wechat`
- Backend: `http://127.0.0.1:8001`
- Langfuse: local API verified every recorded trace id.
- Boundary: all seven rows are one continuous real-package conversation, not seven independent fresh conversations.
- Safety: no remote deploy, no production DB write, no canonical learner truth write, no new chat WebSocket.

## Results

| round | scenario | conversation_id | turn_id | resolved_authority | question_id | result |
| --- | --- | --- | --- | --- | --- | --- |
| `REAL-WX-R2-001` | exact MCQ wrong answer | `unified_1780760885257_fa054593` | `turn_1780760885260_af96368ed9` | `tutorbot_exact_fast_path` | `historical:cf366dd4c395fffa` | pass |
| `REAL-WX-R2-002` | active option challenge | same | `turn_1780760892040_19e55259ba` | `deep_question_grading` | `historical:cf366dd4c395fffa` | pass with P2 watch |
| `REAL-WX-R2-003` | answer revision | same | `turn_1780760908441_96c4241cc3` | `deep_question_grading` | `historical:cf366dd4c395fffa` | pass |
| `REAL-WX-R2-004` | switch to new full MCQ | same | `turn_1780760910562_70667c9922` | `tutorbot_exact_fast_path` | `historical:53cbdad71ba26c1c` | pass |
| `REAL-WX-R2-005` | low-info exam index | same | `turn_1780760925020_8db6b16118` | `tutorbot_lifecycle_clarification` | none | pass with P2 watch |
| `REAL-WX-R2-006` | open-world teaching after clarification | same | `turn_1780760929517_bc6d37ac16` | `tutorbot_kb_first_full_agent_policy` | none | pass |
| `REAL-WX-R2-007` | out-of-bank case grading request | same | `turn_1780760945897_3322ccd72d` | `tutorbot_lifecycle_clarification` | none | pass |

## Authority Findings

- Objective-question authority held for wrong answer, answer revision, and question switch.
- RAG/textbook evidence did not override exact-question official answers.
- Low-information exam index request failed closed into lifecycle clarification; no official answer was fabricated.
- Open-world teaching after a low-information clarification did not inherit stale official-answer authority.
- Case-like request without enough official case/rubric authority did not emit an official score.

## Issue Register

- `WX-REAL-R2-001` P2 / P1-watch: `REAL-WX-R2-002` asked `那C为什么不对？一句话`, but semantic decision classified it as `answer_active_object` / `route_to_grading`, updating the answer slot to `第1题：C`. The visible answer remained correct and same-question authority did not drift, so this is not a P1 fix now. Watch for variants where an option challenge overwrites a different learner answer or causes future route drift.
- `WX-REAL-R2-002` P2 trace hygiene: `REAL-WX-R2-005` lifecycle clarification active object used a long `exam-query:` object id containing injected reference context from the previous active question. It did not hijack `REAL-WX-R2-006`, but it is a mirror-state readability risk. Do not fix with another wrapper; if promoted, normalize clarification object identity in the lifecycle authority.
- `WX-REAL-R2-003` test harness limitation: relaunching the package page did not create a fresh conversation; the batch is valid as continuous-conversation evidence only.

## Evidence Files

- `summary.json`: machine summary and per-round trace ids.
- `authority-ledger.jsonl`: aggregate ledger rows.
- `transcript.jsonl`: full per-round transcript and authority trace snapshots.
- `REAL-WX-R2-*.json`: one detailed artifact per round.
- `run-real-package-batch.js`: artifact-local rerun script; it is not product runtime code.
