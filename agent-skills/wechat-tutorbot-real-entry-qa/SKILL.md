---
name: wechat-tutorbot-real-entry-qa
description: Use this for DeepTutor WeChat mini-program TutorBot QA, especially when testing real learner conversations, true exam questions, refusal behavior, active-question follow-up, DevTools, /wechat-harness, wx_miniprogram, the yousenwebview project root with packageDeeptutor subpackage pages, Langfuse, or authority ledgers. Use it whenever a result could be mistaken for real WeChat closure.
---

# WeChat TutorBot Real-Entry QA

Use this skill to test TutorBot as a learner would experience it in the main
WeChat front end, while keeping evidence boundaries explicit.

## Evidence Surfaces

Always label each row with exactly one surface:

- `real_wechat_package`: `yousenwebview` opened as the WeChat DevTools
  project root, exercising the `packageDeeptutor` subpackage pages, or a real
  device.
- `near_real_http_ws`: WeChat-shaped `/api/v1/chat/start-turn` plus `/api/v1/ws`, not DevTools.
- `wechat_harness_shadow`: web `/wechat-harness` visible-behavior QA.
- `standalone_shadow`: `wx_miniprogram` shadow package or render-contract auxiliary surface.
- `backend_harness`: direct backend tests/scripts.
- `node_contract`: static frontend contract tests.

Only `real_wechat_package` can close the primary WeChat front-end risk. The
others are useful probes, not production closure.

## Project Root Hard Gate

The WeChat mini-program project is `yousenwebview`.

`packageDeeptutor` is only a subpackage/page target inside that project. Do not
say "run/open `packageDeeptutor`" or "`yousenwebview/packageDeeptutor` passed"
as shorthand for real WeChat closure, because that hides the project-root
authority boundary.

Every `real_wechat_package` row must record:

- `devtools_project_root=yousenwebview`
- `target_subpackage=packageDeeptutor`
- `target_page=/packageDeeptutor/pages/chat/chat` or the concrete page exercised
- `entry_flow=deeptutorEntry_bridge|direct_subpackage_page|real_user_navigation|manual`

## DevTools CLI

Prefer the WeChat DevTools CLI for real package smoke before falling back to
manual GUI control:

```bash
WX_DEVTOOLS_CLI=/Applications/wechatwebdevtools.app/Contents/MacOS/cli
REPO_ROOT=$(git rev-parse --show-toplevel)
$WX_DEVTOOLS_CLI islogin
$WX_DEVTOOLS_CLI open --project "$REPO_ROOT/yousenwebview" --lang zh
$WX_DEVTOOLS_CLI auto --project "$REPO_ROOT/yousenwebview" --auto-port 9420
```

Keep `entry_surface` as `real_wechat_package` for the primary package, and put
the mechanism in `trace source` such as `devtools_cli_open`,
`devtools_cli_auto`, `miniprogram_automator`, or `manual_devtools`.

Cost-ordered execution gradient: run cheap deterministic checks first
(`/wechat-harness`, node contract, backend harness) for visible behavior and
contract coverage; then DevTools CLI for real-package evidence; only add real
device / production miniprogram checks for device-specific risk, pre-release
verification, auth/network differences, or explicit user request.

CLI evidence rules:

- `islogin` is only an environment preflight.
- `--project` must point to the `yousenwebview` project root. Do not open
  `yousenwebview/packageDeeptutor` as a DevTools project; it is the target
  subpackage surface inside the project.
- If a plan, transcript, or final report uses `yousenwebview/packageDeeptutor`
  without separately naming project root and target subpackage/page, mark the
  evidence wording invalid and correct it before drawing a real-package
  conclusion.
- `open --project` is only a project-open preflight until a page/scenario is
  actually exercised.
- `auto --project` only counts as automation evidence when an automator/Minium
  script drives the page and records scenario output.
- Record auth separately for every real-package row: `auth_state` should be
  one of `logged_in`, `qa_token`, `auth_blocked`, or `unknown`; `auth_mode`
  should be one of `real_wechat`, `local_dev_wechat`, `manual_token`, or
  `none`.
- Local/devtools test login may use the existing backend dev/mock WeChat login
  path (backend `DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN`, or `dev-` / `mock-` login
  codes) only in non-production. It must still obtain a normal auth token from
  the auth authority, exercise the same `/api/v1/chat/start-turn` and
  `/api/v1/ws` path, and must not write production DB, fabricate canonical
  learner truth, or create a second chat entry.
- If DevTools project-open or auto is skipped, report true-entry status as
  `partial` or `pending`, even if Web harness and contract tests pass.
- Do not run `upload` by default; use upload/preview commands only when the user
  explicitly asks for publishing or package preview, and prefer
  `miniprogram-ci` over DevTools CLI publish commands for upload/preview
  pipelines.

## Scenario Design

Build scenarios from the learner's point of view:

- exact MCQ, learner chooses correct answer
- exact MCQ, learner chooses wrong answer
- active-question follow-up (`为什么不是B`, `那C呢`, numeric option challenge)
- answer revision after follow-up
- multi-item question set with indexed submissions
- missing-anchor true exam request
- existing active question plus answer request
- case grading with and without scoring authority
- open-world construction knowledge question
- reconnect / retry / history restore where relevant

For each scenario record:

```text
round_id:
entry_surface:
auth_state:
auth_mode:
conversation_id:
turn_id:
learner_transcript:
visible_answer:
question_id:
learner_answer:
official_answer:
resolved_authority:
route / lifecycle decision:
runtime active object:
trace source:
refusal_class:
language_understanding 1-5:
explanation_quality 1-5:
expression_quality 1-5:
customer_satisfaction 1-5:
pass / partial / fail:
```

## Background Monitoring

Run at least one backend/observability monitor while testing:

- backend logs for route, errors, and Langfuse initialization
- SQLite `turn_events` / `sessions.runtime_state` authority ledger when available
- Langfuse traces only if auth and local/remote service are actually reachable
- DevTools page state and request base for real package runs

Never fake Langfuse closure. If Langfuse is unavailable, say so and use the
SQLite authority ledger as the primary trace evidence.

## Pass Criteria

A satisfactory TutorBot answer must meet all of these:

- no fabricated official answer for missing-anchor true exam requests
- no wrong refusal when canonical question context exists
- visible answer matches official authority
- learner answer extraction matches what the learner selected
- route/action matches the learner intent
- hidden answer authority is not leaked before allowed reveal
- expression is useful enough for a WeChat learner, not only technically correct

## Anti-Confusion Rules

- Do not treat `/wechat-harness` or `wx_miniprogram` PASS as real package closure.
- Do not treat DevTools CLI `islogin` or `open --project` as a real package
  scenario PASS without page-level or script-level evidence.
- Do not let a backend harness hide a frontend projection bug.
- Do not let a visible answer pass hide runtime state drift.
- Do not let a trace-complete row imply customer satisfaction; score expression separately.
- Do not add regex/router patches for expression-only P2 issues unless repeated evidence promotes them.

## Report

Lead with:

```text
real package status:
devtools_project_root:
target_subpackage:
target_page:
near-real status:
shadow/harness status:
P0/P1/P2 findings:
wrong refusals:
reasonable clarifications:
authority drift:
expression/customer-satisfaction issues:
evidence gaps:
next verification:
```
