# DeepTutor Daily Health Check — 2026-07-09T08:42:22+0800

## Verdict

**RED** — `contract_guard_failed_mobile_turn_capability_dirty_surface`.

今天的核心行为回归是绿的，但仓库治理闸红：dirty `deeptutor/api/routers/mobile.py` 触碰了 `turn` 与 `capability` contract-sensitive surface，而本次工作区未同步满足对应 contract surface 要求。这个状态下不应继续合并/发布；可以继续开发，但必须先把 `mobile.py` 这条 dirty change 做 contract-compliant 或缩小/拆出。

## Tier 0 / Repo Authority

| Item | Result |
| --- | --- |
| `pwd -L` | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` |
| `pwd -P` | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` |
| git toplevel | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor` |
| `core.worktree` | empty |
| branch | `release/old-blue-frontend` |
| HEAD | `571a793a0f7855bd4b4341d354bc1a8b879ab65c` |
| origin/main | `06aedc6466d1b32b1f4e975ab79327a05ea3e5f7` |
| branch relation | ahead 3, behind 3 vs `origin/release/old-blue-frontend` |
| `.env` | present, readable, non-symlink; `python-dotenv` parsed 216 keys |

Baseline from automation memory: previous useful SHA is `c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753`; committed diff window `c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753..571a793a0f7855bd4b4341d354bc1a8b879ab65c`.

## Dirty Worktree Signal

Dirty files remain user/parallel WIP; no reset, stash, checkout, cleanup, commit, push, SSH, rsync, or production write was performed.

Main groups:

- Contract/governance/docs: `.env.example`, `AGENTS.md`, `CLAUDE.md`, `contracts/env_registry.yaml`, `contracts/learner-state.md`, `docs/plan/INDEX.md`, deleted Luban implementation note, new plan/raw-data docs.
- Protected/backend surfaces: `deeptutor/api/routers/mobile.py`, Luban lesson router/service/read model, member console external auth/service, wallet service, `docker-compose.yml`.
- Tests: mobile router, Luban lesson, member console, wallet, BI member admin, wx/yousen billing/profile tests.
- Frontend/WeChat: BI conversation drawer, wx billing/profile, yosen billing/profile pages.
- Untracked artifacts/scripts: F16 HTML assets, Luban light practice service/test, `wechat_pay.py`/test, J01 governed-gold scripts, concept card JSON files.

## Results

| Surface | Status | Evidence |
| --- | --- | --- |
| Contract guard | FAIL | `python ../scripts/check_contract_guard.py` failed for `turn` and `capability`; sensitive file `deeptutor/api/routers/mobile.py`; required contract files not satisfied for dirty change. |
| Tier 1 WS/mobile/session/learner_state | PASS | `960 passed, 5 warnings` in 147.39s. |
| Tier 1 DeepQuestion/construction/RAG | PASS | `873 passed` in 24.04s. |
| Web memory preflight | PASS | Codex-owned RSS about 3.74GB; no AI-agent-owned Next tree; pgrep found no SkyComputerUse/next-server/postcss. |
| WeChat harness data | PASS | `npm --prefix ../web run test:wechat-harness:data`: 5 passed; Node `MODULE_TYPELESS_PACKAGE_JSON` warning only. |
| Diff-aware backend narrow tests | PASS | TutorBot unanswered reference, question_followup, turn_start demotion pipeline, member_console: `356 passed` in 352.67s. |
| Login visual contract | PASS | `node ../wx_miniprogram/tests/test_login_button_visual_contract.js`: 26 assertions. |
| Yosen billing packages | PASS | `node ../yousenwebview/tests/test_billing_packages.js`: 42 assertions. |
| Yosen learn/review view-model commands | WARN | `test_learn_view_model.js` and `test_review_view_model.js` are absent in current tree; commands fail with `MODULE_NOT_FOUND`. Treat as deleted/renamed test entry signal, not product behavior evidence. |
| Post Web/Next guard | PASS | Codex-owned RSS about 3.75GB; no AI-agent-owned Next tree; pgrep found no SkyComputerUse/next-server/postcss. |
| Tier 2 observability/release gate | DEFERRED | Daily integration health already RED on contract guard; no release closure attempted. |
| Real WeChat true-entry / Playwright | DEFERRED | Not required for today’s daily integration answer; no DevTools scenario was executed, so no `real_wechat_package` PASS claimed. |

## Failure Root Cause

One business fact: contract-sensitive mobile HTTP bridge changes must keep the public turn/capability control-plane authority coherent.

One authority: `CONTRACT.md` + `contracts/index.yaml` + registered domain contract/test lists, enforced by `scripts/check_contract_guard.py`.

Breakpoint: working tree has dirty `deeptutor/api/routers/mobile.py` changes. The guard classifies that file under both `turn` and `capability`; the current dirty set does not include the required contract surface update for those domains. Behavior tests pass, but governance authority is broken.

Minimal fix boundary:

1. Inspect the dirty `mobile.py` diff and decide whether it truly changes turn/capability semantics.
2. If yes, update the appropriate registered contract surface(s) and existing registered tests, then rerun contract guard.
3. If no, shrink/move the dirty change so it no longer touches the protected surface.

Do not paper over this with a wrapper/fallback or by weakening contract guard.

## P0 / P1 / P2

- **P0**: Fix `contract_guard_failed_mobile_turn_capability_dirty_surface`.
- **P1**: Reconcile the deleted `yousenwebview/tests/test_learn_view_model.js` and `test_review_view_model.js` entries with replacement tests or remove stale automation references; current commands prove test-entry drift, not UI safety.
- **P1**: Classify and land/split the large dirty worktree before any release-style gate; release readiness remains impossible while `runtime_release_dirty` would be true.
- **P2**: Later, when targeting release, run real `yousenwebview` DevTools true-entry and Playwright/self-hosted evidence in a safe short-lived flow.

## Best Next Codex Tasks

1. **Make mobile contract guard green**: inspect `deeptutor/api/routers/mobile.py`, update the proper `turn`/`capability` contract surfaces or shrink the change, then run `python ../scripts/check_contract_guard.py` and `pytest ../tests/api/test_mobile_router.py -q`.
2. **Restore yosen view-model test authority**: either identify the replacement for deleted learn/review view-model tests or add a narrow new contract test that matches the current page architecture.
3. **Dirty WIP triage**: split backend protected changes, wx/yosen surface changes, docs/plan changes, and generated artifacts into separate landing decisions.

## Commands Run

```bash
pwd -L
pwd -P
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git config --get core.worktree
python -c "from dotenv import dotenv_values; v=dotenv_values('../.env'); print('dotenv_keys', len(v))"
sed -n '1,240p' ../AGENTS.md
sed -n '241,520p' ../AGENTS.md
sed -n '521,700p' ../AGENTS.md
sed -n '1,220p' ../CONTRACT.md
sed -n '1,260p' ../contracts/index.yaml
sed -n '1,260p' ../docs/plan/INDEX.md
sed -n '1,240p' ../agent-skills/deeptutor-engineering-lifecycle-gate/SKILL.md
sed -n '1,260p' ../agent-skills/deeptutor-test-verification-gate/SKILL.md
sed -n '1,260p' ../agent-skills/deeptutor-web-bi-frontend-gate/SKILL.md
git diff --name-only c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753..HEAD
git diff --stat c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753..HEAD
/usr/bin/env SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_KEY=test SUPABASE_SERVICE_ROLE_KEY=test LANGFUSE_ENABLED=false PYTHONPATH=.. python ../scripts/check_contract_guard.py
/usr/bin/env SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_KEY=test SUPABASE_SERVICE_ROLE_KEY=test LANGFUSE_ENABLED=false PYTHONPATH=.. python -m pytest ../tests/api/test_unified_ws_turn_runtime.py ../tests/api/test_mobile_router.py ../tests/services/session ../tests/services/learner_state -q
/usr/bin/env SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_KEY=test SUPABASE_SERVICE_ROLE_KEY=test LANGFUSE_ENABLED=false PYTHONPATH=.. python -m pytest ../tests/core/test_deep_question_submission_grading.py ../tests/services/construction_grading ../tests/services/rag/test_learning_fact_retrieval_pipeline.py ../tests/services/rag/test_retrieval_plan.py -q
/Users/yehongchen/.codex/bin/codex-memory-snapshot.sh
/Users/yehongchen/.codex/bin/agent-owned-next-guard.sh --check
pgrep -af 'SkyComputerUse|SkyComputerUseClient|SkyComputerUseService|next-server|/web/\.next/dev/build/postcss\.js|next/dist/bin/next dev'
npm --prefix ../web run test:wechat-harness:data
/usr/bin/env SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_KEY=test SUPABASE_SERVICE_ROLE_KEY=test LANGFUSE_ENABLED=false PYTHONPATH=.. python -m pytest ../tests/capabilities/test_tutorbot_unanswered_reference_short_circuit.py ../tests/services/test_question_followup.py ../tests/services/test_turn_start_demote_canonical_pipeline.py ../tests/services/member_console/test_service.py -q
node ../wx_miniprogram/tests/test_login_button_visual_contract.js
node ../yousenwebview/tests/test_billing_packages.js
node ../yousenwebview/tests/test_learn_view_model.js
node ../yousenwebview/tests/test_review_view_model.js
/Users/yehongchen/.codex/bin/codex-memory-snapshot.sh
/Users/yehongchen/.codex/bin/agent-owned-next-guard.sh --check
pgrep -af 'SkyComputerUse|SkyComputerUseClient|SkyComputerUseService|next-server|/web/\.next/dev/build/postcss\.js|next/dist/bin/next dev'
git status --short --branch
git diff --name-only
```
