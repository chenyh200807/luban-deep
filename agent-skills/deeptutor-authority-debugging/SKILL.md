---
name: deeptutor-authority-debugging
description: Use this for DeepTutor bugs involving TutorBot, WeChat, question authority, active object, state continuity, follow-up routing, refusal, RAG/LLM answer drift, terminal truth, trace mismatch, or fallback behavior. Use it before changing code whenever the symptom might be context loss, route confusion, wrong answer authority, or a patch spiral.
---

# DeepTutor Authority Debugging

Use this skill to debug authority failures without turning them into more
fallbacks or regex patches.

## Start Gate

Before reading implementation details too deeply, write a short root-cause
frame:

```text
one business fact:
one authority:
competing authorities:
canonical path:
last correct point:
first wrong point:
delete or demote:
deterministic vs LLM boundary:
verification target:
```

If any field is unclear, keep investigating. Do not patch yet.

## Failure Shapes

Classify the bug by shared shape rather than by surface phrasing:

- `state continuity`: an active object or session fact exists but is not restored.
- `object continuity`: the current question/case/topic is replaced by another object.
- `authority drift`: RAG, LLM, frontend text, or fallback changes canonical truth.
- `duplicate decision`: two modules independently decide route/action/answer.
- `mirror state`: a copied context competes with canonical runtime state.
- `terminal truth`: canonical result is correct, but final stream/UI/history changes it.
- `reasonable clarification vs wrong refusal`: no anchor should clarify; existing anchor must answer or fail closed according to policy.

## Investigation Order

1. Confirm repo and surface authority:
   - `pwd -P`
   - `git rev-parse --show-toplevel`
   - `git status --short --branch`
   - Identify whether evidence is real package, near-real HTTP+WS, harness, shadow, or backend.

2. Trace the canonical path:
   - writer: exact question / lifecycle / grading service / active object writer
   - persistence: session runtime state, active object, turn metadata
   - transfer: `/api/v1/chat/start-turn` plus `/api/v1/ws`
   - routing: lifecycle decision, semantic router, follow-up resolver
   - terminal: TutorBot / deep_question / frontend projection / message history

3. Find the first wrong reader or decision point.
   Do not start from the final text unless the failure is terminal truth.

4. Prefer subtraction:
   - remove or demote duplicate readers
   - stop stale mirror state from participating
   - make wrappers delegate to the fat service
   - keep aliases at the edge only

## Fix Rules

- Put business policy in the existing fat authority service or skill.
- Keep wrappers thin: normalize input, call the authority, preserve trace, return.
- Use deterministic rules only for stable, low-ambiguity formats such as:
  - numbered item identity (`第 N 题`)
  - explicit option letters
  - negated answer-reveal markers
  - complete MCQ option surface detection
- Do not let regex decide broad semantic intent when active authoritative context exists.
- If a commit is mostly good but contains a local overfix, record the problem and repair that slice. Do not revert the whole commit unless the whole direction is wrong.

## Verification Matrix

Every fix needs at least:

- one positive regression for the reported failure
- one counterexample with similar wording but opposite intent
- one state/authority assertion, not only visible text
- one terminal check when UI or message history is involved

For question authority, verify visible answer, hidden authority, learner answer,
official answer, active object, and route metadata agree.

After the fix, also re-check the evidence labels: harness, near-real HTTP+WS,
DevTools `islogin`/`open --project`, and real WeChat package are different
surfaces (see `wechat-tutorbot-real-entry-qa`); do not let a fix report
upgrade a lower surface into real-package closure.

## Final Report

Use this structure:

```text
Root cause:
What was competing for authority:
What changed:
Why this is less complex:
Why the system is now closer to single authority, not one more patch layer:
Regex/fallback boundary:
Verification:
Why the problem was initially framed too narrowly:
Transferable lesson:
Remaining risk:
```

Case note: this skill's frame comes from the 2026-06-06 WeChat TutorBot
authority loop retro, where a question-authority bug was repeatedly patched
narrow (per-scenario fixes, harness evidence mistaken for real WeChat closure)
instead of collapsing the competing authorities once. If a fix plan starts to
look like that shape, stop and redo the Start Gate.
