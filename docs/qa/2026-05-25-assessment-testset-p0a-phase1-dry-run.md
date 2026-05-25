# Assessment TestSet P0A Phase 1 Dry Run

**Date:** 2026-05-25
**Mode:** commit-ready evidence only; no staging, no commit, no push, no
migration apply.
**PRD:** `docs/plan/2026-05-24-luban-assessment-testset-module-prd.md`
**Execution plan:** `docs/plan/2026-05-24-luban-assessment-testset-p0a-execution-plan.md`

## Summary

P0A Phase 1 is implemented in code and automated gates are green for the scoped
P0A surface:

- durable session repository contract with lease, TTL, owner checks, idempotent
  submit, and degraded recovery;
- deterministic scoring with registered MCQ error codes;
- per-item `learning_evidence` and mistake-book writeback;
- result report read model with `schema_version: "p0a-v1"`;
- mobile API create/submit/report paths kept as thin wrappers;
- yusen run/result view-model and copy invariants;
- pre-submit payload redaction gate.

Production database apply and WeChat DevTools manual gate remain pending.

## File Manifest

```text
97f87468bb1643a649506ee801ca951aa89b5028cbb1522cd446bde1bdd53d81     178  CONTRACT.md
29d924edd5e79525f0e036a811833dc11d1b4e1eeb7521771a5dd288fbb3a6e7     256  contracts/index.yaml
0ca266b4bb039cc5ed105421d9e7bde8cf52586d53bca971fdfe526dcc0af152     509  contracts/learner-state.md
c1692633cb6511bbdeef7a2afaff27c18088de93d5a58b242abe79e36f48b915     101  contracts/turn.md
4318bf184259abb246e3c2b4c509fa42aa8f9688124ab005768555a166182e30     180  deeptutor/services/assessment/blueprint.py
b5d6cad94d7f303fae0b64cf0c23d4da66c42560bc19b797bb62ef78081a47bf    1203  deeptutor/services/assessment/blueprint_service.py
3e00ab05bdfabda6b340f1d0e1eceabb0d2a342c466a37e480f95ddbcbd6a0be     133  deeptutor/services/assessment/report_read_model.py
12dfc83dd1678780ca8a9ff36b66003cb6fb9479c04adb45065cca049eb4e7d7     139  deeptutor/services/assessment/scoring.py
b568c5b4fbaeebd26a8794117fa3577c40e97265d6ae845063f64ca032b73919     758  deeptutor/services/assessment/session_repository.py
473321bed1fc057d0659389b2e556d4c521ee824a40197c75fd1bd92a6f0d3d8     102  deeptutor/services/assessment/writeback.py
d47f0adc6fb482804386af4ad6075c9e224895a5bbd64bd68cb635b4f169d0a2    2540  deeptutor/api/routers/mobile.py
126f8e56b9c4f93619c2929bd3c94344ad42189404258df8b5cdf4cb168aba0b    5452  deeptutor/services/member_console/service.py
74d75c58f0b2baeeba5d379b27140028d9cc076fb3f8fad80609678353a43c49     926  deeptutor/services/learner_state/learning_synthesis.py
53e42b9e16a20fcdd3cbe11404852f6243eafb042ba6641e3379a09464872b10     119  scripts/audit_2026_compiler_supabase_coverage.py
745342473efcc24f7438185d50ca4c51bfd82cefaf1c2a94e950d8d69c6a11d0     141  tests/scripts/test_2026_source_compiler_scripts.py
11e190331ad2573071adde7d8b1711175177dd19893f3cf8a3409e8ccba67cac     554  scripts/audit_assessment_testset_p0a.py
72790cb48d038d023f4f3146b35895004cc39235e2f049b391aef4ac6501c6a1     104  supabase/migrations/20260524000100_assessment_sessions.sql
9cd09ecbb88ed1b9d355393094cb785d5b0ffc922bc20084b8ec48e6bbe1b13b     218  tests/api/test_mobile_assessment_payload_redaction.py
0fcc0e57f435a7b0384a661a701c2515ba2b843fea3687349059158ea5889630    4388  tests/api/test_mobile_router.py
fee6033d032df0f9e503c665ebe35f86370fa8a30e1783a54c4d06ce2c21334d     493  tests/services/assessment/test_blueprint_coverage.py
fd3d853d157881d4c63740593b497bf2c8a3961e79b1f1148964ec4e731bb04b      69  tests/services/assessment/test_scoring.py
8dc55526f76d06377d485f940305952379f31820caee203103cd96fa8310c4d9     228  tests/services/assessment/test_session_repository.py
82b33b23c07400bf0908a9d628cc4bec601f97a5a9833f34a25ccd46abbf8f5c     124  tests/services/assessment/test_testset_assembly.py
983b03fec42e5241ddd271f40d9ff788dc122ac9de952d25057ae3459b0ae67f     181  tests/services/assessment/test_writeback.py
0a87957e616fd2e746367e464bbe37cd4630b3c901b22f6d6bda3dc9c98352be    1639  tests/services/learner_state/test_learning_report_read_model.py
531cc874faf7368f87cbd1d5c4ab23cefc19003ce6ef8219c5875498690bd063     475  tests/services/learner_state/test_learning_synthesis.py
b18b54c38c6cc46a3f0223472aff35e1ca9a6ad9e7427eebaeadf04f964268bb     791  yousenwebview/packageDeeptutor/pages/assessment/assessment.js
1f5ea9e9e161d3f1b8b6ff7de3a9e54d3d8a2ec97b63b28c7756653eedc38d2b     306  yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml
5835e4ce5fed0c9012464ac7576598b7ddc12db20a59a2c8da2dde0e4efc5c12     583  yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss
3300f276f41480d31bbba1fdae5b0d0c4c137168f9b6a8190a942a43cbd2af2e     813  yousenwebview/packageDeeptutor/utils/api.js
66dfdbda86aa2bc39258ab3424131cc8c3fa940eb192488b1de6323096fdee7f     306  yousenwebview/tests/test_package_assessment_contract.js
ec663a3952858954aaf92043b1b00137d07fb585a2c46058d630a182eb37cfc5     275  yousenwebview/tests/test_assessment_testset_view_model.js
afcd31624e93b96f4fa4240e9344c36d0d5a3f65a540f89f657f42f9920de1f6    1216  docs/plan/2026-05-24-luban-assessment-testset-p0a-execution-plan.md
```

## Verification Stdout

Python gate:

```text
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
.                                                                        [100%]
217 passed in 14.70s
```

Node gate:

```text
PASS test_package_assessment_contract.js (17 assertions)
PASS test_assessment_testset_view_model.js (24 assertions)
```

Default contract guard in the dirty worktree:

```text
contract-guard: failed
[capability] protected files changed but no domain tests were updated.
[learner_state] protected files changed but no domain tests were updated.
error-code-guard: passed | codes=E02, E04, M02, M06, M07, unknown_error
node-id-guard: no hard-coded knowledge_node_id literals found
```

Scoped contract guard over this P0A/source-compiler change set:

```text
contract-guard: passed
[turn] passed | protected=deeptutor/api/routers/mobile.py | tests=tests/api/test_mobile_router.py | contract=CONTRACT.md, contracts/index.yaml, contracts/turn.md
[capability] passed | protected=deeptutor/api/routers/mobile.py | tests=tests/api/test_mobile_router.py | contract=CONTRACT.md, contracts/index.yaml
[learner_state] passed | protected=deeptutor/services/learner_state/learning_synthesis.py, deeptutor/services/member_console/service.py | tests=tests/services/learner_state/test_learning_report_read_model.py | contract=CONTRACT.md, contracts/index.yaml, contracts/learner-state.md
error-code-guard: passed | codes=E02, E04, M02, M06, M07, unknown_error
node-id-guard: no hard-coded knowledge_node_id literals found
```

Source compiler fail-fast regression:

```text
...                                                                      [100%]
3 passed in 0.26s
```

## PRD §13 Gate Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Deferred feedback | Automated pass | Pre-submit create/resume payload is redacted; answers appear only in post-submit report fixtures/tests |
| Payload redaction | Automated pass | `tests/api/test_mobile_assessment_payload_redaction.py` recursively blocks answer/grading/rubric/scoring/correct keys before submit |
| P0A scope | Automated plus copy review | P0A topic diagnostic only; no P0B, CAT, official-exam claim, or deep explanation implementation |
| Durable session | Code/migration ready, apply pending | repository contract tests plus migration SQL; production apply requires explicit approval |
| Owner/RLS | Code review plus contract tests | repository owner checks pass; SQL RLS policies created but not applied |
| Submit idempotency | Automated pass | same submit body returns original report; different body raises conflict |
| Device lease | Automated pass | heartbeat, idle expiry, take-over, and conflict tests |
| Server-wins draft | Automated pass | draft patch keeps earlier server value |
| Result report versioning | Automated pass | report uses `schema_version: "p0a-v1"` and read model dispatches on version |
| Learning evidence writeback | Automated pass | per-item `assessment_testset` evidence and mistake-book writeback tests |
| Training intent authority | Automated pass | assessment submit writeback does not emit `training_intent` |
| Degraded recovery | Automated pass | degraded reason recorded and recoverable through writeback refs |
| Error code registry | Scoped guard pass | P0A scoring emits registered `M0X` codes; unregistered code test raises before writeback |
| Yousen result surface | Node pass | view-model and package contract tests cover run/result states and copy invariants |
| WeChat DevTools manual | Pending | requires user-run simulator or real-device evidence |

## v1.1 §6.1 Matrix

| Requirement | Status | Note |
| --- | --- | --- |
| Topic decision | Ready | `waterproof` coverage has enough candidates; teaching signoff still needed for final source mix/copy |
| Authoring backlog | Not needed for current pool | Reactivates only if teaching rejects enough candidates below threshold |
| Durable `assessment_sessions` | Code/migration ready | migration not applied |
| Device lease | Implemented in repository contract | explicit `/take-over` endpoint can still be deferred if UI chooses expiry reclaim |
| Dedupe/rate limit | Implemented for P0A create path | existing in-progress session returned |
| Deterministic scoring | Implemented | no LLM in score path |
| Result report | Implemented | `p0a-v1` report shape |
| Session-local next action | Implemented | derived from wrong-item knowledge nodes/sections, no LLM |
| Per-item learning evidence | Implemented | source feature `assessment_testset` consumed by synthesis |
| Mistake-book writeback | Implemented | wrong-item refs recorded |
| Metrics | Partial | service logs/fields cover started/submitted/scored/degraded paths; dashboard baseline deferred |
| Deep explanation | Deferred | not implemented in P0A |

## Error Code Notes

`unknown_error` appears in the scoped guard output because it is present in the
existing error-code registry and legacy synthesis fallback scan. P0A writeback
does not introduce a new permanent product taxonomy:

- scoring emits `M05`, `M06`, `M07`, or `M01`;
- writeback calls `check_emitted_error_codes` before persistence;
- `tests/services/assessment/test_writeback.py::test_error_codes_must_exist_in_error_code_registry`
  blocks unregistered codes before learning evidence is written.

Hard Gate #12 is therefore not triggered by this run.

## Deviations And Pending Manual Work

| Item | Status | Reason |
| --- | --- | --- |
| Supabase migration apply | Applied on 2026-05-25 after explicit user approval | target guard passed, SQL applied with `psql`, table/RLS/policy/index counts verified |
| Supabase CLI/shadow apply | Not run | direct `psql` apply was used against the guarded DeepTutor main DB |
| WeChat DevTools | Attempted, blocked | CLI reports `wait IDE port timeout`; app is running but automation port is unavailable |
| `docs/plan/INDEX.md` link | Updated | P0A row now points to this QA evidence |
| Default `check_contract_guard.py` | Fails in dirty worktree | unrelated dirty protected files pollute default scan; scoped guard passes |
| Source compiler PR-2/3 | Pending precheck | taxonomy readability determines whether the compiler track can proceed |

## Supabase Migration Apply Evidence

Preflight:

```text
target_guard=passed
questions_bank_count=4638
users_id_type=text
assessment_sessions_regclass=(missing)
```

Apply stdout:

```text
migration_returncode=0
BEGIN
CREATE EXTENSION
CREATE TABLE
COMMENT
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
ALTER TABLE
DROP POLICY
CREATE POLICY
DROP POLICY
CREATE POLICY
DROP POLICY
CREATE POLICY
GRANT
COMMIT
```

Post-apply verification:

```text
assessment_sessions_regclass=assessment_sessions
rls_enabled=true
policy_count=3
index_count=7
column_count=29
```

Notes:

- `pgcrypto` already existed.
- Policy drops printed "does not exist, skipping" notices on first apply, as
  expected.
- No real learner/session rows were inserted during this verification.

## WeChat DevTools Attempt

Commands attempted:

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli open \
  --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview \
  --port 9420 --lang zh --disable-gpu
```

```text
IDE may already started at port 30238, trying to connect
#initialize-error: wait IDE port timeout
```

Retrying with port `30238` and `cli islogin --port 30238` produced the same
timeout. `ps` confirms WeChat DevTools is running, but `lsof` shows no listener
on the expected automation ports. Computer Use also timed out reading the app
window. Manual simulator evidence therefore remains pending; avoid force-quitting
the user's existing DevTools session without a separate confirmation.

## Source Compiler PR-2/3 Precheck

Command:

```bash
LUBAN_2026_SOURCE_ROOT=/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026 \
PYTHONPATH=. python scripts/run_2026_source_inventory.py --run-id pr2-precheck --force
```

Stdout:

```text
blocked_dataless=106 class_book=18 class_lecture_bundle=8 class_lecture_page=327 class_question=13 class_standard=8 class_taxonomy=1 dataless=106 json_files=375 readable=269 redundant_skipped=234
```

Taxonomy row:

```text
source_class=taxonomy
source_path=taxonomy/FINAL_CLEANED_TAXONOMY2026.json
compile_eligibility=blocked_dataless
readable=false
record_count=null
sha256=null
```

Post-approval download attempt:

```text
brctl download ".../taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
du -h ".../taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
0B
```

`ls -lO@` still reports `compressed,dataless`, and a bounded read probe did not
materialize local bytes. This remains a physical/iCloud sync blocker.

Post-download inventory rerun:

```text
blocked_dataless=106 class_book=18 class_lecture_bundle=8 class_lecture_page=327 class_question=13 class_standard=8 class_taxonomy=1 dataless=106 json_files=375 readable=269 redundant_skipped=234
```

Decision:

- PR-2/3 remain pending.
- Do not use `--allow-dataless-scan-disabled`.
- User must physically download `taxonomy/FINAL_CLEANED_TAXONOMY2026.json`
  before Task 3.0 and downstream compiler tasks can proceed.

## Migration Apply Draft

Do not run this without explicit approval:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
psql "$DB_URL" -X -v ON_ERROR_STOP=1 -P pager=off \
  -f supabase/migrations/20260524000100_assessment_sessions.sql
```

Required before apply:

1. user reviews the migration SQL;
2. target-database guard confirms DeepTutor main or approved shadow;
3. RLS owner smoke is ready;
4. rollback/degraded plan is accepted.
