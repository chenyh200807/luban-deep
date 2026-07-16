# DeepTutor Daily Health Check - 2026-07-06

## Verdict

Health verdict: **RED**

failure_signature: `tier1_deep_question_canonical_decision_regression_plus_artifacts_cwd_test_isolation_and_yousen_parity_drift`

结论分层：

- 核心开发健康：RED。Tier 1 出现 5 个 `deep_question` canonical `turn_semantic_decision` 失败，这是业务 authority 红灯，不是单纯环境问题。
- 测试隔离健康：RED/P1。`artifacts` cwd 下仍有 7 个 hard-coded repo-root relative path 失败。
- Web/微信 shadow：YELLOW。`web` wechat harness data 通过，但 dirty `yousenwebview` Node shadow tests 有 1 个 wx/yousen report view model byte parity 失败。
- 发布 readiness：HOLD。release gate report-only 是 `FAIL/hold`，blockers 为 `runtime_release_dirty`, `playwright_evidence_missing`, `wechat_devtools_true_entry_pending`；这不是部署许可。

## Tier 0 Authority

- `pwd -L`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `pwd -P`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- git toplevel: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- branch: `release/card-fit`
- HEAD: `99a1d4111218b5b36f2b340d333014018d6803ad`
- `origin/main`: `0d91e8a4c38407ee515ee81b7d09410346c3ab1c`
- branch relation: `release/card-fit...origin/main [ahead 1, behind 119]`
- `core.worktree`: empty
- `.env`: exists, readable, not symlink, parsed by `python-dotenv` with 207 keys.
- Required docs read fully with line count and sha256 proof: `AGENTS.md`, `CONTRACT.md`, `contracts/index.yaml`, `docs/plan/INDEX.md`.

## Automation Baseline

- memory `last_scanned_sha`: `bd0714a9ba1c14eb14f4e9f5aa52159e60ff681e`
- current HEAD: `99a1d4111218b5b36f2b340d333014018d6803ad`
- baseline exists: yes
- lineage: `bd0714a9...` is not an ancestor of HEAD, and HEAD is not an ancestor of `bd0714a9...`
- merge-base: `30077fdd4ae3d549f120404128a53d9b6b4372c2`
- key implication: the previous daily follow-up fix commit `bd0714a9b fix(deep-question): harden followup authority` lives on `feat/leak-authority-and-quality-gate-hardening`, not on current `release/card-fit`. Today's RED is partly a branch-lineage regression: an already-fixed failure family is absent from this branch line.

## Dirty State

Dirty state was present before and after the run. No reset, stash, checkout, cleanup, commit, push, SSH, rsync, or production Supabase write was performed.

Grouped signal:

- `.codegraph/.gitignore`: 1 modified local metadata file.
- docs/plan: 1 deleted `鲁班移动端提分闭环/implementation-notes.md`, 2 untracked plan docs.
- `yousenwebview`: 53 dirty paths, concentrated in `packageDeeptutor` pages, utils, tab bar, and tests.
- untracked new frontend surfaces: `concept-cards`, `errorbank`, `gauntlet` pages and view models, plus matching tests.
- observability/benchmark scripts wrote ignored local runtime artifacts under `data/runtime/observability/...` and `tmp/benchmark/...`; these did not appear as tracked dirty files in final `git status`.

## PASS / FAIL / WARN / DEFERRED

| Layer | Command | Result | Evidence |
| --- | --- | --- | --- |
| Tier 1 | `python scripts/check_contract_guard.py` with test env overrides | PASS, exit 0, 3s | `logs/tier1_contract_guard.log` |
| Tier 1 | `pytest tests/api/test_unified_ws_turn_runtime.py tests/api/test_mobile_router.py tests/services/session tests/services/learner_state -q` | FAIL, exit 1, 154s, `955 passed, 2 failed` | `logs/tier1_ws_mobile_session_learner_state.log` |
| Tier 1 | `pytest tests/core/test_deep_question_submission_grading.py tests/services/construction_grading tests/services/rag/test_learning_fact_retrieval_pipeline.py tests/services/rag/test_retrieval_plan.py -q` | FAIL, exit 1, 27s, `863 passed, 10 failed` | `logs/tier1_deep_question_grading_rag.log` |
| Tier 1 | `npm --prefix web run test:wechat-harness:data` | PASS, exit 0, 5/5 | `logs/tier1_wechat_harness_data.log` |
| Tier 2 | `pytest tests/services/observability tests/scripts/test_observability_cli_inputs.py -q` | PASS, exit 0, `315 passed` | `logs/tier2_observability_pytest.log` |
| Tier 2 | `scripts/run_observability_daily.py --report-date 2026-07-05 --timezone Asia/Shanghai` | PASS command, run `observability-daily-1783298289`, payload `TRUSTED`; release status still FAIL | `logs/tier2_observability_daily.log` |
| Tier 2 | `scripts/run_release_gate.py --report-only` | PASS command, run `release-gate-1783298299`, payload `TRUSTED`, final `FAIL/hold` | `logs/tier2_release_gate_report_only.log` |
| Tier 2 | `scripts/run_benchmark.py --suite pr_gate_core` | PASS, `19/19`, pass_rate `1.0` | `logs/tier2_benchmark_pr_gate_core.log` |
| Extra shadow | dirty `yousenwebview/tests/*.js` Node tests | FAIL, 20 files run, 1 failed | `logs/tier2_yousen_dirty_shadow_tests_rerun.log` |
| Web safety | memory snapshot + Next guard + pgrep before/after/final | PASS guard, no AI-agent-owned Next tree, no persistent pgrep target | `logs/web_*`, `logs/final_*` |
| True entry | real WeChat DevTools `yousenwebview` project root + `packageDeeptutor` target page | DEFERRED | Tier 1 RED plus release readiness already hold; harness shadow is not true-entry proof. |
| Playwright/self-hosted | short-lived self-hosted smoke | DEFERRED | Not required for daily development verdict after Tier 1 RED; long-lived Next remains forbidden. |

## Failure Details

### P0 - DeepQuestion canonical decision authority

Failed tests:

- `test_deep_question_blocks_unanswered_direct_answer_reveal`
- `test_deep_question_blocks_action_only_generation_without_anchor_before_coordinator`
- `test_deep_question_blocks_non_construction_generation_before_coordinator`
- `test_deep_question_allows_explicit_construction_generation_topic`
- `test_deep_question_different_topic_request_does_not_inherit_question_anchor`

Signature:

```text
RuntimeError: deep_question ... missing canonical turn_semantic_decision
(orchestrator is the single authority - turn.md §硬约束 24)
```

Root-cause frame:

- one business fact: `deep_question` must consume the canonical turn semantic decision from orchestrator/turn runtime; it must not fabricate a second authority.
- one authority: orchestrator/turn runtime writes/injects `turn_semantic_decision`; `deep_question` only reads and fails fast when it is missing.
- breakpoint: current `release/card-fit` hits `deep_question` practice-generation paths without canonical injection. This is the same failure family that was fixed in `bd0714a9...`, but that commit is not in this branch line.
- minimal fix boundary: bring the canonical injection/redaction fix from `bd0714a9...` into `release/card-fit` or reapply the same narrow changes; do not restore fabricated fallback.

### P1 - `artifacts` cwd test isolation failures

Failed tests:

- `tests/services/learner_state/test_evidence_story_read_model.py::test_no_public_endpoint_added_for_evidence_story`
- `tests/services/learner_state/test_home_next_step_projection.py::test_module_is_pure_no_ledger_write_no_intent_generation`
- 5 tests in `tests/services/construction_grading/test_m35_eval_fixture_contract.py`

Signature:

```text
FileNotFoundError: deeptutor/api/routers/mobile.py
FileNotFoundError: deeptutor/services/learner_state/home_next_step_projection.py
FileNotFoundError: tests/fixtures/luban_m35_case_scoring/manifest.json
```

Root-cause frame:

- one business fact: daily health now executes from `artifacts`; tests must resolve repo-root fixtures from file location or git toplevel, not process cwd.
- one authority: git toplevel / file-relative path resolution.
- breakpoint: tests still use repo-root relative `Path("...")` under an `artifacts` cwd process.
- minimal fix boundary: patch only these tests to use `Path(__file__).resolve()` derived roots or a shared repo-root helper.

### P1 - Yousen wx/yousen report view model parity drift

Failed shadow test:

- `yousenwebview/tests/test_report_view_model.js`

Signature:

```text
AssertionError [ERR_ASSERTION]: wx and yousen report view models must stay byte-identical
operator: strictEqual
```

Root-cause frame:

- one business fact: wx and yousen report view model copies must remain byte-identical when this contract test is the parity authority.
- one authority: the parity test treats byte identity as the synchronization gate.
- breakpoint: dirty `yousenwebview/packageDeeptutor/utils/learning-report-view-model.js` / related frontend WIP has drifted from the paired wx copy.
- minimal fix boundary: synchronize the intended report view model source of truth across wx/yousen, then rerun the dirty yosen Node shadow set.

## Observability / Release Evidence

Observability daily payload:

- run: `observability-daily-1783298289`
- verdict: `TRUSTED`
- metrics: `change_impact_risk_level=medium`, `om_ready=True`, `benchmark_pass_rate=1.0`, `release_gate_status=FAIL`
- local warning: default `DEEPTUTOR_AUTH_SECRET`

Release gate report-only payload:

- run: `release-gate-1783298299`
- verdict: `TRUSTED`
- final_status: `FAIL`
- recommendation: `hold`
- blockers: `runtime_release_dirty`, `playwright_evidence_missing`, `wechat_devtools_true_entry_pending`
- stale_inputs: `[]`
- release spine: `git_sha=99a1d4111218`, `git_dirty=true`, `deployment_environment=local`

Benchmark:

- run: `benchmark-1783298307`
- suite: `pr_gate_core`
- result: `PASS=19 FAIL=0 SKIP=0 RATE=1.0`

## Web / Next Safety

- pre memory snapshot: Codex-owned RSS about 3.3GB; no stop condition.
- post/final memory snapshot: Codex-owned RSS about 3.35GB; no stop condition.
- `agent-owned-next-guard.sh --check`: no AI-agent-owned Next dev process tree before, after, or at final.
- independent `pgrep` returned transient PIDs that were gone by `ps`; no persistent `next-server`, postcss worker burst, or SkyComputerUse process remained.
- No Computer Use was used.
- No long-lived `next dev` or browser process was started by this automation.

## Today's Best Codex Repair Tasks

1. **Bring the `bd0714a9...` DeepQuestion authority fix onto `release/card-fit`.**
   - Minimal prompt: "在 `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` 作为 cwd，比较 `bd0714a9ba1c14eb14f4e9f5aa52159e60ff681e` 与当前 `release/card-fit`，只移植 canonical `turn_semantic_decision` 注入和 hidden answer redaction 相关修复；不要恢复 fallback，不清理无关 dirty WIP。验证两组 Tier 1 pytest。"
2. **Fix `artifacts` cwd-sensitive tests.**
   - Minimal prompt: "只修 `test_evidence_story_read_model.py`, `test_home_next_step_projection.py`, `test_m35_eval_fixture_contract.py` 的 repo-root relative path，改成 file-relative 或 git toplevel helper；从 `artifacts` cwd 复跑对应 7 个失败测试。"
3. **Synchronize wx/yousen report view model parity.**
   - Minimal prompt: "只处理 `test_report_view_model.js` 报告的 wx/yousen report view model byte drift，明确哪个文件是 authority，做最小同步后 rerun dirty `yousenwebview/tests/*.js` Node shadow set；不要启动 Next 或 DevTools。"

## Final Notes

This run answered daily development health, not full release readiness. Core gates are not green because `deep_question` is red on the current branch. Even after fixing that, release readiness remains hold until dirty state is intentionally resolved and real Playwright / real WeChat true-entry evidence is collected.
