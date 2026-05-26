# Question Lifecycle Production Canary

**Date:** 2026-05-26
**Surface:** `yousenwebview/packageDeeptutor` in WeChat DevTools plus production
metrics and Langfuse.
**Production URL:** `https://test2.yousenjiaoyu.com`
**Production release observed:** `1.0.0+89df1da7728a3a92e9df71be68c212533072cbc1+production`

## Summary

The current production behavior is healthy for the core question lifecycle
authority path:

- `2025真题` was manually observed in WeChat DevTools and correctly returned a
  clarification/catalog/practice/paste-question choice. It did not emit
  `标准答案`, `阅卷结论`, or `命中题库原题`.
- Production metrics show 11 started turns, 11 completed turns, 0 failed turns,
  and 0 recent HTTP errors during this canary window.
- Langfuse is receiving current `tutorbot.construction-exam-coach` and
  `turn.runtime` traces for the tested WeChat user.
- The latest inspected production trace includes the expected construction exam
  skill stack, including `construction-question-review`,
  `construction-question-supply`, `construction-mcq-grading`,
  `construction-learning-evidence-story`, `construction-study-assistant`, and
  `construction-learning-support`.

## Manual / Live Evidence

| Case | Result | Evidence |
| --- | --- | --- |
| `2025真题` | Pass | WeChat DevTools rendered: `你提到的是“2025真题”，但还没有指定要做哪件事。` and offered catalog / practice / paste concrete question for review |
| WeChat input automation | Tool limitation | Computer Use could read the DevTools tree and verify the visible response, but could not reliably write into the miniprogram WebView input. Further cases were therefore validated through orchestrator tests and production telemetry snapshots |
| Production health | Pass | `/healthz` returned `status=ok`; `/readyz` returned `ready=true` |
| Production metrics | Pass | `turns_started_total=11`, `turns_completed_total=11`, `turns_failed_total=0`; `POST /api/v1/chat/start-turn` had 11 requests and 0 errors |
| Langfuse | Pass | Recent traces include `tutorbot.construction-exam-coach` and `turn.runtime` for the WeChat user |

## Automated Matrix Added

The following user-facing boundary cases are now pinned in
`tests/runtime/test_orchestrator_autoroute.py`:

- `防水真题` stays topic-only and blocks exact-question authority.
- `再出3题练地下防水` routes to practice generation, with answers and
  explanations hidden.
- Bare `我选B` without an active question returns a clarification decision, not
  fabricated grading.
- `我答B，再出3题` grades first and does not skip directly to generation.
- `q1 A, q3 C, q5 B` stays in batch grading when a batch question context is
  present.
- `横道图和网络图有什么区别` stays ordinary TutorBot/general chat, not question
  generation, grading, or real-question review.

## Validation

```text
python -m pytest tests/runtime/test_orchestrator_autoroute.py -q
56 passed in 163.01s

python -m pytest tests/services/test_question_lifecycle_scene_derivation.py \
  tests/services/test_question_lifecycle_acceptance.py \
  tests/runtime/test_orchestrator_autoroute.py -q
110 passed in 162.56s

git diff --check
clean
```

Earlier scoped lifecycle suite:

```text
python -m pytest tests/services/test_question_lifecycle_scene_derivation.py \
  tests/services/test_question_lifecycle_acceptance.py \
  tests/runtime/test_orchestrator_autoroute.py \
  tests/capabilities/test_deep_question_question_review.py \
  tests/capabilities/test_deep_question_lightweight_generation.py \
  tests/core/test_deep_question_submission_grading.py \
  tests/core/test_deep_question_active_object.py \
  tests/services/test_tutorbot_response_mode.py -q
167 passed in 127.43s
```

## Current Assessment

No product-code blocker was found in this canary. The observed issue was a
testing-tool limitation in Computer Use WebView text entry, not the runtime route
authority.

The strongest remaining follow-up is a manual WeChat DevTools pass for the full
16-case list using human input, because automated accessibility text entry did
not reliably operate the miniprogram WebView input in this environment.

Non-blocking operations note: production startup logs still contain a
`startup.assessment_form_prewarm` logger-call TypeError. The container remains
healthy and the question lifecycle path is unaffected, but this should be fixed
in a separate startup-log cleanup task.
