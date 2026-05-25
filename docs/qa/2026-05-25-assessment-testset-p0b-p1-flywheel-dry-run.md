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

The "练 3 道同类题" buttons were verified as visible CTAs on wrong-item cards.
They were not clicked through by coordinate automation because the DevTools
accessibility bridge exposed no safe button click primitive in this run. Backend
service smoke above already verified the corresponding writeback and report
projection path.

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

## Release Readiness Verdict

Current verdict: `AUTOMATED_READY_WITH_PROD_SMOKE_TOKEN_PENDING`.

Automated backend, local service gates, RLS safety, and the WeChat DevTools
visible loop are ready for pilot evidence. Remaining external gate: production
HTTP smoke needs a real learner bearer token.
