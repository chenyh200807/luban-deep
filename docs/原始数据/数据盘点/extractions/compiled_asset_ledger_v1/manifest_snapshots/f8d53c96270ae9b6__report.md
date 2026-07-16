# DeepTutor Daily Health Check - 2026-07-05

## Verdict

Health verdict: **RED**

`failure_signature`: `tier1_deep_question_regression_plus_artifacts_cwd_test_isolation_and_release_hold_dirty`

今天不能安全视为核心回归全绿。Observability、release-gate runner、wechat harness shadow、fresh `pr_gate_core` benchmark 都通过；红灯集中在 Tier 1 的 `deep_question` 行为回归，以及若干测试对旧 repo-root cwd 的硬编码假设。

## Authority / Baseline

- `pwd -L`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `pwd -P`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- git toplevel: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- branch: `feat/leak-authority-and-quality-gate-hardening`
- HEAD: `fb615c3b4e6d470e270981e53c2f77a45d86c999`
- `origin/main`: `3f8259a2540f44a009f1bb8559a1d62f4a1ec1ec`
- `core.worktree`: empty
- automation baseline from memory: `767132e7cec24f7036d2c8627e9ae6a3012310ca`
- `.env`: present, readable, non-symlink, `python-dotenv` parsed 207 keys

Required docs were read/recorded with hashes:

- `AGENTS.md`: `9d9fa828a6b240bbed0c55adbb6928bbb086ae328c68c8713119788df103a02b`
- `CONTRACT.md`: `421205a1c601bf07b22593bd2a6c4877784359a822a94c7ddb5f8691e1d7592a`
- `contracts/index.yaml`: `a5457f3c212b81c0d215e1167f26cd445f08f143663a3a21b0e969b8089b29b5`
- `docs/plan/INDEX.md`: `f31442c18f1686e7f508e989c2e0a311a9ef43a24b9b1778a88c0d93f5c94f18`

## Dirty Worktree Signal

Final dirty state remained user/parallel WIP. No reset, stash, checkout, cleanup, commit, or push was performed.

- `M`: 1 file, `../.codegraph/.gitignore`
- `R`: 131 artifact renames under `artifacts/luban_case_family_assets/diagram_microlesson/finished/... -> finished/_archive_v1/2026-07-05_v1/...`
- `??`: 4 untracked files:
  - `../docs/plan/鲁班移动端提分闭环/implementation-notes.md`
  - `../docs/原始数据/考点原料/log_A.txt`
  - `../docs/原始数据/考点原料/log_C.txt`
  - `../docs/原始数据/考点原料/log_D.txt`

Release-style gates are expected to hold while this dirty state exists.

## Results

| Layer | Command | Result | Evidence |
| --- | --- | --- | --- |
| Tier 0 | authority/env/doc read | PASS | cwd/toplevel/core.worktree correct; `.env` parsed |
| Tier 1 | `python ../scripts/check_contract_guard.py` | PASS | contract guard, WS allowlist, route model, evidence/mistake guards passed |
| Tier 1 | `pytest ../tests/api/test_unified_ws_turn_runtime.py ../tests/api/test_mobile_router.py ../tests/services/session ../tests/services/learner_state -q` | FAIL | `903 passed, 1 failed` |
| Tier 1 | `pytest ../tests/core/test_deep_question_submission_grading.py ../tests/services/construction_grading ../tests/services/rag/test_learning_fact_retrieval_pipeline.py ../tests/services/rag/test_retrieval_plan.py -q` | FAIL | `863 passed, 10 failed` |
| Tier 1 Web | `npm --prefix ../web run test:wechat-harness:data` | PASS | 5 node tests passed; `wechat_harness_shadow` only |
| Web safety | memory + Next guard pre/post | PASS/WARN | no AI-owned Next tree; no non-self `next-server`, postcss worker, or SkyComputerUse |
| Tier 2 | `pytest ../tests/services/observability ../tests/scripts/test_observability_cli_inputs.py -q` | PASS | `315 passed` |
| Tier 2 | workflow/release-gate pytest subset | PASS | `46 passed` |
| Tier 2 | `python ../scripts/run_observability_daily.py --report-date 2026-07-04 --timezone Asia/Shanghai` | PASS command / HOLD readiness | generated `observability-daily-1783211889`; local default auth secret warning |
| Tier 2 | `python ../scripts/run_release_gate.py --report-only` | PASS command / FAIL gate | `release-gate-1783211914`, `TRUSTED`, `FAIL`, `hold`, blocker `runtime_release_dirty`, `stale_inputs=[]` |
| Tier 2 | `python ../scripts/run_benchmark.py --suite pr_gate_core` | PASS | `PASS=19 FAIL=0 SKIP=0 RATE=1.0` |
| True entry | DevTools `real_wechat_package` | DEFERRED | not needed to diagnose today's RED; required before release closure |
| Surface | Playwright/self-hosted smoke | DEFERRED | not run because Tier 1 is already RED and long-lived Next hosting is forbidden |

## Failures

### P0 - `deep_question` answer leak / canonical decision regression

Failing tests:

- `test_deep_question_blocks_unanswered_direct_answer_reveal`
- `test_deep_question_blocks_action_only_generation_without_anchor_before_coordinator`
- `test_deep_question_blocks_non_construction_generation_before_coordinator`
- `test_deep_question_allows_explicit_construction_generation_topic`
- `test_deep_question_different_topic_request_does_not_inherit_question_anchor`

Observed signatures:

- Unanswered follow-up returned `## ✅ 答案与解析` and exposed `正确答案：A（观察法）`, violating the test expectation that unanswered direct-answer reveal must not leak the answer.
- Practice-generation paths now raise `RuntimeError: missing canonical turn_semantic_decision` at `DeepQuestionCapability._require_canonical_turn_semantic_decision`.

Root-cause frame:

- One business fact: `DeepQuestion` must never reveal answer authority before the learner has answered, and practice-generation decisions must come from canonical turn semantic authority.
- One authority: orchestrator / turn runtime writes `turn_semantic_decision`; `DeepQuestion` consumes it. Question-review / follow-up reveal authority decides whether answer fields may be exposed.
- Breakpoint: current HEAD includes a large `deep_question.py` / `turn_runtime.py` change. The new fail-fast guard correctly rejects fabricated `turn_semantic_decision`, but some unit/entry paths still reach generation without canonical injection. Separately, unanswered follow-up still allows `correct_answer` / `explanation` content to reach the response path.
- Minimal repair scope: fix `deep_question` unanswered redaction and canonical injection/test contract. Do not restore the retired fabricated fallback as a second authority.

### P1 - Artifacts-cwd test isolation failures

Failing tests:

- `tests/services/learner_state/test_evidence_story_read_model.py::test_no_public_endpoint_added_for_evidence_story`
- `tests/services/construction_grading/test_m35_eval_fixture_contract.py::*` five fixture tests

Observed signatures:

- `FileNotFoundError: deeptutor/api/routers/mobile.py`
- `FileNotFoundError: tests/fixtures/luban_m35_case_scoring/manifest.json`
- `FileNotFoundError: tests/fixtures/luban_m35_case_scoring/student_answers.jsonl`

Root cause:

- These tests hard-code repo-root-relative paths while this automation is required to run with process cwd at `artifacts`.
- This is a test isolation bug against the 2026-07-04 automation cwd contract, not direct product behavior evidence.

## Today’s Best Codex Tasks

1. Fix `deep_question` unanswered answer leak and canonical `turn_semantic_decision` handling. Keep orchestrator/turn runtime as the single authority; do not re-add fabricated fallback logic.
2. Make cwd-sensitive tests repo-root-aware using `Path(__file__)` or a helper based on `git rev-parse --show-toplevel`: `test_evidence_story_read_model.py` and `test_m35_eval_fixture_contract.py`.
3. Classify the dirty asset archive renames and untracked raw logs before any release gate. Report-only release gate will continue to hold on `runtime_release_dirty`.

## Next Minimal Fix Prompt

```
在 /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts 启动，不要派生 worktree。先读 AGENTS.md、CONTRACT.md、contracts/index.yaml。修 daily health 的 P0：`tests/core/test_deep_question_submission_grading.py` 当前 5 个 deep_question 失败。要求：未作答 follow-up 绝不泄露 correct_answer/explanation；practice_generation 继续由 orchestrator/turn_runtime 提供 canonical `turn_semantic_decision`，不得恢复 fabricated fallback。同步修 P1 cwd-sensitive 测试，让它们在 artifacts cwd 下也能定位 repo-root 文件。验证：contract guard；两个 Tier 1 pytest 组；wechat harness data；必要时补 observability subset。
```

