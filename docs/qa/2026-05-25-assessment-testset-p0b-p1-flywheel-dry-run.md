# Assessment TestSet P0B/P1 Production Flywheel Dry Run

Date: 2026-05-25

Scope: execute the P0B/P1 production flywheel plan through automated gates and
safe live probes. Secrets are not recorded.

## Reality Lock

Git authority must use explicit environment variables in this workspace:

```text
GIT_DIR=/Users/yehongchen/.gitdirs/deeptutor-documents.git
GIT_WORK_TREE=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
branch=codex/assessment-flywheel-hardening-20260525
```

The worktree contains many unrelated dirty files from other trains. Assessment
flywheel changes are kept to assessment services, assessment scripts, Supabase
assessment migrations, Yousen assessment surface, tests, and QA docs.

## Gate 0 Storage Security

Post-remediation probe:

```text
assessment_sessions=assessment_sessions
assessment_forms=assessment_forms
assessment_forms.rls_enabled=true
assessment_forms.client_select_grants=0
assessment_forms_rows=55
assessment_forms_answer_rows=55
set role anon; select count(*) from public.assessment_forms;
ERROR: permission denied for table assessment_forms
```

Applied hotfix:

```text
supabase/migrations/20260525130000_assessment_forms_service_role_only.sql
```

Verdict: `assessment_forms` still stores answer-bearing `items_json`, but it is
service-role only after RLS/revoke. Client-facing assessment traffic must use the
redacted API.

## Topic Catalog Audit

Dry-run command wrote:

```text
artifacts/assessment_flywheel/p0b-p1-flywheel-verify/topic_catalog_dry_run.json
docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md
```

Result:

```text
topic_count=10
question_bank_size=4638
stable_topics=10
pilot_topics=0
authoring_needed_topics=0
forms_per_topic=5
form_source=supabase_persisted
persisted=false (dry-run only)
```

## Persisted Form Bank

The live database already contains persisted form rows:

```text
assessment_forms_rows=55
answer_rows=55
```

No new `--persist` run was executed in this dry run. The plan's `--persist`
gate remains an operator action with reviewed JSON, target-main guard, and an
idempotency key.

## Service-Level Flywheel Smoke

Environment flags used for this local service smoke:

```text
ASSESSMENT_USE_SUPABASE=true
DEEPTUTOR_MISTAKE_BOOK_ENABLED=true
DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED=true
```

Observed:

```text
catalog_topics=10
all_catalog_topics=stable/enabled
created_question_count=12
created_form_source=supabase_persisted
pre_submit_leaked_keys=[]
submitted_score_pct=17
retry_report_writeback_status={"learning_event_count": 12, "mistake_book_count": 10}
report_schema=p0a-v1
report_writeback_status={"learning_event_count": 12, "mistake_book_count": 10}
explain_cache_status=static_projection
explain_score_mutation_allowed=False
```

This proves the backend chain:

```text
catalog -> create -> submit -> learning_evidence -> mistake_book -> report -> deep explanation projection
```

It does not replace production HTTP smoke or WeChat DevTools manual evidence.

## Production API Smoke

Script added:

```text
scripts/smoke_assessment_flywheel.py
```

Script contract:

```text
GET  /api/v1/assessment/topics
POST /api/v1/assessment/create
POST /api/v1/assessment/{quiz_id}/submit
GET  /api/v1/assessment/{quiz_id}/report
POST /api/v1/assessment/{quiz_id}/items/{question_id}/explain
```

The script fail-closes when no learner token is provided:

```text
assessment_flywheel_smoke_requires_token
no_token_rc=2
```

Invalid-token probe:

```text
http_401: {"detail":"Authentication required", "...": "...", "error_code":"http_401"}
invalid_token_rc=1
```

Current status: blocked on a real learner bearer token. A server `API_AUTH_TOKEN`
is not accepted by the learner-authenticated mobile route and returns
`Authentication required`.

## Flywheel Manual Gate

Status: passed for the visible WeChat DevTools loop; production HTTP smoke is
still blocked on a real learner bearer token.

Observed tool state:

```text
WeChat DevTools Stable v2.01.2510290
project=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview
assessment_page=packageDeeptutor/pages/assessment/assessment
report_page=packageDeeptutor/pages/report/report
```

Observed visible loop:

```text
report -> 摸底测试 -> assessment catalog -> 防水工程专题测评 -> 12-question run
-> submit -> 诊断报告 -> 本次错题 -> 练 3 道同类题 CTA -> report prescription update
```

Specific UI evidence:

```text
Topic catalog: 综合摸底 20 题, 专题测评 12 题, 10 topics visible.
Stable topic labels: 防水工程, 装饰装修, 建筑机电, 地基基础, 主体结构, 模板脚手架, 安全管理, 进度计划, 合同索赔, 质量验收.
Quiz run: 防水工程专题测评, 12 questions, progress and answered count advanced to 12/12.
Pre-submit redaction: no correct answer or answer key visible during the 12-question run.
Result page: 17 本次专题测评得分, 答对 2 / 12 题, 空白 0 题.
Wrong-item cards: show user's answer, correct answer, simple rationale, and "练 3 道同类题".
Report update: 今日处方 changed to 防水材料与构造, 约 8 分钟, 12 次证据, 先做 3 道“防水材料与构造”专项题.
```

The "练 3 道同类题" buttons were verified as visible CTAs on wrong-item cards,
then clicked through with WeChat DevTools automation after the route fix.

```text
DevTools automation ws=127.0.0.1:9421
before_path=packageDeeptutor/pages/assessment/assessment
after_path=packageDeeptutor/pages/report/report
after_query.detail=training
after_query.source=assessment_wrong_item
after_query.attempt_ref=attempt_smoke_devtools_001
storage.deeptutor.report.pendingTrainingAction.question_count=3
storage.deeptutor.report.pendingTrainingAction.training_mode=same_type_repair
assertion: not_chat=true
```

## Automated Gates

Fresh automated gate output:

```text
PYTHONPATH=. pytest tests/services/assessment tests/scripts/test_assessment_topic_catalog_scripts.py tests/api/test_mobile_assessment_payload_redaction.py tests/api/test_mobile_router.py tests/services/member_console/test_service.py tests/services/learner_state/test_learning_report_read_model.py tests/services/learner_state/test_conversation_learning_evidence_event.py tests/supabase/test_learner_state_rls_migration.py -q
321 passed in 10.65s
```

```text
node yousenwebview/tests/test_package_assessment_contract.js
PASS test_package_assessment_contract.js (17 assertions)

node yousenwebview/tests/test_assessment_testset_view_model.js
PASS test_assessment_testset_view_model.js (60 assertions)
```

```text
python scripts/check_contract_guard.py
contract-guard: passed
[capability] passed
[rag] passed
error-code-guard: passed | codes=E02, E04, M02, M06, M07, unknown_error
node-id-guard: no hard-coded knowledge_node_id literals found
```

## Metrics Coverage

| Metric | Source | P0B/P1 use | Status |
| --- | --- | --- | --- |
| submit_rate | started/submitted | form difficulty and UX | automated surface present |
| abandon_rate | started without submit | length/time friction | automated surface present |
| wrong_item_practice_ctr | practice clicked/result viewed | flywheel pull | frontend/event contract present |
| training_completion_rate | completed/clicked | training quality | writeback contract present |
| retest_rate | retest started/recommended | loop strength | read-model projection present |
| topic_authoring_needed_count | catalog validator | content backlog | dry-run reports 0 |

## Deviations And Decisions

- The broad untracked migration `20260525120000_close_rls_off_business_tables.sql`
  was not used for this plan because it touches many unrelated business tables.
  The applied migration is assessment-only.
- `assessment_forms_public` is created as a redacted metadata view, but no client
  grants are opened in this release.
- Deep explanation is a static projection/cache-key bounded P1 path in this
  implementation; it does not mutate score or mastery.
- The result report remains `schema_version=p0a-v1` because the implemented P1
  explanation is returned out-of-band and does not alter stored report shape.

## 2026-05-25 Final Production Smoke Addendum

Production endpoint: `https://test2.yousenjiaoyu.com/api/v1`

```text
release_id=1.0.0+a7d2ee7aa12aca0946516e3e7218f5bf29554c27+production
auth.register=true
token_sha256_12=1fd8c3de3e9d
profile_user_id=e75f5b70-145f-4176-91d9-997a89434602
topics.topic_count=10
```

Topic diagnostic smoke:

```text
assessment_type=topic_diagnostic
blueprint_version=topic_waterproof_v1
form_source=supabase_persisted
question_count=12
submit_has_score=true
score_pct=17
report_quiz_match=true
wrong_count=10
deep_explanation_ready=true
score_mutation_allowed=false
pre_submit_redaction=passed
```

20-question mini simulation smoke:

```text
assessment_type=real_exam_simulation
blueprint_version=real_exam_simulation_mini_v1
form_source=supabase_questions_bank
question_count=20
submit_has_score=true
score_pct=15
report_quiz_match=true
wrong_count=17
deep_explanation_ready=true
score_mutation_allowed=false
pre_submit_redaction=passed
```

## Release Readiness Verdict

Current verdict: `PILOT_READY_WITH_MANUAL_SIGNOFF_ITEMS`.

Automated backend, production learner-token smoke, RLS safety, 20-question mini
simulation, and WeChat DevTools wrong-item training click-through are now
verified. Remaining non-automated items are product/ops signoffs: production
migration governance for future schema changes, ongoing content authoring
backlog review, and human spot-checks before broad rollout.

## 2026-05-25 P0B Flywheel Closure Addendum

This addendum closes the remaining Gate D gap between wrong-item CTA and
structured training completion.

```text
DevTools automation ws=127.0.0.1:9421
project=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview
report_path=packageDeeptutor/pages/report/report
report_query_detail=training
training_label=练 3 道同类题
training_query=请围绕我刚才错的“地下防水卷材搭接”，出 3 道同类选择题训练我。先只出题，不要提前给答案和解析。
intent_attempt_ref=attempt_devtools_full_001
intent_signal=assessment_wrong_item_practice
intent_question_count=3
after_path=packageDeeptutor/pages/chat/chat
chat_message_count=2
chat_contains_training_prompt=true
```

The first DevTools run exposed a Gate D.5 failure: report correctly routed to
chat with the assessment intent, but the default chat route produced free-form
text instead of submit-able training cards. The fix is to keep report/chat as
thin surfaces and route only `assessment_wrong_item_practice` first-generation
turns through the existing `deep_question` authority.

```text
DevTools automation ws=127.0.0.1:9421
report_path=packageDeeptutor/pages/report/report
training_label=练 3 道同类题
after_path=packageDeeptutor/pages/chat/chat
mcq_found={"cards":[{"count":3,"interactive":true,"stems":["地下防水卷材施工时，卷材搭接长度的最小值是多少？","地下防水卷材相邻搭接缝的错开宽度应符合什么要求？","地下防水卷材铺贴时，最多允许的叠层（层数）是？"]}]}
submit_called=true
submit_done=true
message_count_after_submit=4
last_role=ai
last_content=### 阅卷结论 你答了第1题C、第2题C、第3题C；正确答案分别是第1题C、第2题B、第3题B；得分1/3分。
```

The same run showed a read-model gap after submit: the learner report still
preferred a generic training prescription instead of a retest CTA. A regression
test now locks the intended authority: `training_completed` conversation
evidence remains non-mastery / non-attempt-countable, but it can drive
`learner_facing.next_action = 再测一次<专题>`.

```text
PYTHONPATH=. pytest tests/services/learner_state/test_learning_report_read_model.py::test_training_completed_conversation_recommends_topic_retest_without_mastery_claim -q
.                                                                        [100%]
1 passed in 0.93s
```

Gate D status after this addendum:

| Step | Evidence | Status |
| --- | --- | --- |
| Result CTA returns to report training area | Existing DevTools route evidence | Passed |
| Report training action preserves attempt_ref / wrong-item intent | `test_report_snapshot_dedupe.js` + DevTools output | Passed |
| Wrong-item training generates 3 submit-able MCQs | DevTools `mcq_found.count=3 interactive=true` | Passed |
| Training submit writes through structured MCQ path | DevTools submit terminal assistant feedback | Passed |
| Retest recommendation after `training_completed` | read-model regression test | Passed locally; requires deploy/prod re-smoke |

## 2026-05-25 Contract Guard Closure Addendum

This addendum closes two production-readiness regressions found while re-running
the P0B/P1 automated gates after the flywheel closure:

- `assessment` evidence refs emitted by Assessment TestSet writeback must
  survive canonical learning-evidence normalization as `source_type=assessment`,
  not fall back to `active_question`.
- Production member-console initialization must not fail every auth/admin path
  just because Supabase `assessment_sessions` is not configured; instead,
  assessment create/resume/report/explanation/writeback-retry paths fail closed
  with `assessment_sessions_supabase_not_configured`.
- `assessment_sessions.user_id` must not require a mirror row in `public.users`;
  the durable assessment authority identifies the learner by text `user_id` and
  is protected by its own RLS / owner checks.

Verification:

```text
PYTHONPATH=. pytest tests/services/assessment/test_learning_evidence.py::test_assessment_ref_survives_canonical_learning_evidence_normalization tests/services/member_console/test_service.py::test_login_with_password_does_not_fail_when_wallet_bootstrap_is_unavailable tests/services/member_console/test_service.py::test_production_without_supabase_sessions_only_blocks_assessment_paths tests/supabase/test_learner_state_rls_migration.py::test_assessment_sessions_do_not_require_public_users_mirror_row -q
....                                                                     [100%]
4 passed in 1.39s
```

Full automated gate:

```text
PYTHONPATH=. pytest tests/services/assessment tests/scripts/test_assessment_topic_catalog_scripts.py tests/api/test_mobile_assessment_payload_redaction.py tests/api/test_mobile_router.py tests/services/member_console/test_service.py tests/services/learner_state/test_learning_report_read_model.py tests/services/learner_state/test_conversation_learning_evidence_event.py tests/supabase/test_learner_state_rls_migration.py -q
322 passed in 9.28s
```

Frontend and contract gates:

```text
PASS test_report_snapshot_dedupe.js (67 assertions)
PASS test_ws_stream_auth_refresh.js (21 assertions)
PASS test_package_chat_surface_layout_contract.js (17 assertions)
PASS test_report_layout.js (90 assertions)
PASS test_assessment_testset_view_model.js (61 assertions)

contract-guard: passed
[learner_state] passed | protected=deeptutor/services/member_console/service.py | tests=tests/services/member_console/test_service.py | contract=contracts/learner-state.md
error-code-guard: passed | codes=E02, E04, M02, M06, M07, unknown_error
node-id-guard: no hard-coded knowledge_node_id literals found
```

## 2026-05-25 Production Deploy Addendum

Deployment target: `Aliyun-ECS-2:/root/deeptutor`

```text
git_push=passed
branch=codex/assessment-flywheel-hardening-20260525
remote_head=1135aaece98deb68832599289e64d3c67926ae12
```

Supabase migration:

```text
env_source=heuristic_jackson_env
target_guard=passed
questions_bank_count=4638
assessment_sessions_regclass=assessment_sessions
fk_before=0
migration=applied
fk_after=0
```

The migration was idempotent in the probed target database: the
`assessment_sessions_user_id_fkey` constraint was already absent before apply
and remained absent after apply.

Aliyun fast redeploy:

```text
DEEPTUTOR_RELEASE_ID=1.0.0+1135aaece98deb68832599289e64d3c67926ae12+production
DEEPTUTOR_GIT_SHA=1135aaece98deb68832599289e64d3c67926ae12
DEEPTUTOR_GIT_DIRTY=false
DEEPTUTOR_DEPLOY_MANIFEST_HASH=8ea978607e60f8b6
public_frontend=https://test2.yousenjiaoyu.com/
public_healthz=https://test2.yousenjiaoyu.com/healthz passed
public_readyz=https://test2.yousenjiaoyu.com/readyz passed
observability=passed
langfuse_connectivity=jgzk-langfuse:3000 reachable
```

Production assessment smoke:

```text
auth_register=passed
auth_user_id=auth_1e16f2000f274146a22ebb0d

assessment_type=topic_diagnostic
quiz_id=quiz_4fc72a8293ac
question_count=12
blueprint_version=topic_waterproof_v1
report_ready=true
deep_explanation_ready=true
pre_submit_redaction=passed

assessment_type=real_exam_simulation
quiz_id=quiz_0482172fafd6
question_count=20
blueprint_version=real_exam_simulation_mini_v1
report_ready=true
deep_explanation_ready=true
pre_submit_redaction=passed
```

Deployment hygiene note:

```text
tracked_git_disabled=found_before_cleanup
```

`.git.disabled` was discovered as a tracked repo file and had been synced to the
allowed remote deploy root. It is not runtime-sensitive, but it is deploy-surface
noise. The branch now removes it from Git and adds `.git.disabled*` to both
`.gitignore` and `scripts/sync_to_aliyun.sh` excludes so future deploys do not
ship local worktree pointer artifacts.

## 2026-05-26 PRD Completion Sweep Addendum

Execution surface:

```text
worktree=/private/tmp/deeptutor-main-release-20260526-000555
branch=codex/assessment-prd-completion-20260526
base=origin/main@56f7f674cc4401e4855930db929f41fa2cca2087
```

Three read-only subagents audited docs/gates, backend/API/DB, and Yousen
frontend/flywheel. The shared conclusion is that P0B/P1 is pilot-ready after
automated gates, while broad rollout still requires manual/production signoffs.

New automated closures:

```text
assessment_forms_provider_guard=supabase_service_role_key_required_for_assessment_forms
real_exam_source_policy_payload=present_on_real_exam_simulation_mini
real_exam_smoke_overclaim_guard=assessment_real_exam_copy_overclaims_official
deep_explanation_daily_budget=20_misses_per_user_per_day_default
deep_explanation_global_circuit_breaker=assessment_deep_explanation_circuit_open:<reason>
yousen_topic_catalog_copy=3 套试运行 / 5 套稳定
yousen_wrong_item_review_copy=本题讲评
```

Verification:

```text
PYTHONPATH=. pytest tests/services/assessment/test_blueprint_coverage.py::test_supabase_assessment_provider_requires_service_role_key_for_form_bank tests/services/assessment/test_testset_assembly.py::test_real_exam_simulation_mini_assembles_20_items_without_official_claim tests/services/assessment/test_deep_explanation.py::test_global_explanation_circuit_breaker_blocks_generation_when_open tests/scripts/test_assessment_topic_catalog_scripts.py::test_assessment_flywheel_smoke_rejects_overclaimed_official_real_exam_copy tests/scripts/test_assessment_topic_catalog_scripts.py::test_assessment_flywheel_smoke_accepts_safe_real_exam_style_copy -q
.....                                                                    [100%]
5 passed in 0.21s

PYTHONPATH=. pytest tests/services/assessment/test_blueprint_coverage.py tests/services/assessment/test_testset_assembly.py tests/services/assessment/test_deep_explanation.py tests/scripts/test_assessment_topic_catalog_scripts.py -q
42 passed in 0.95s

node yousenwebview/tests/test_assessment_testset_view_model.js
PASS test_assessment_testset_view_model.js (72 assertions)

PYTHONPATH=. pytest tests/services/assessment tests/scripts/test_assessment_topic_catalog_scripts.py tests/api/test_mobile_assessment_payload_redaction.py tests/api/test_mobile_router.py tests/services/member_console/test_service.py tests/services/learner_state/test_learning_report_read_model.py tests/services/learner_state/test_conversation_learning_evidence_event.py tests/supabase/test_learner_state_rls_migration.py -q
329 passed in 11.18s

node yousenwebview/tests/test_package_assessment_contract.js
PASS test_package_assessment_contract.js (17 assertions)

python scripts/check_contract_guard.py
contract-guard: no protected contract domains changed
error-code-guard: passed | codes=E02, E04, M02, M06, M07, unknown_error
node-id-guard: no hard-coded knowledge_node_id literals found
```

Completion matrix:

| Train | Automated status | Remaining hard gate |
| --- | --- | --- |
| Train 0 | Passed: storage RLS evidence, service-role provider guard, payload redaction | Re-probe every target DB before broad release |
| Train 1 | Passed: 10-topic catalog, 5 forms/topic, authoring backlog empty, UI status copy | Keep authoring backlog owner review for content drift |
| Train 2 | Passed locally: CTA/report training, wrong-item context, structured training evidence, retest read-model projection | Real learner-token production smoke for `training_completed -> report retest` |
| Train 3 | Passed: 20-question mini, safe source policy metadata, smoke overclaim guard | Source/copyright/teaching signoff before any `官方真题` wording |
| Train 4 | Pilot-safe: static projection, cache key, score invariance, daily budget, global breaker | Persistent cache + LLM lifecycle + cost dry-run before broad P1 |

Verdict remains:

```text
PILOT_READY_WITH_MANUAL_SIGNOFF_ITEMS
```
