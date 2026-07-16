# DeepTutor Daily Health Check - 2026-07-08

## Health verdict

**RED**

`failure_signature`: `contract_guard_failed_mobile_turn_capability_surface_missing_contract_update`

今天不是核心行为回归坏了，而是 dirty `deeptutor/api/routers/mobile.py` 触碰了 `turn` / `capability` contract-sensitive surface，但没有同步更新对应 contract surface。按 DeepTutor contract discipline，这足以阻断 GREEN。

## Repo authority

- `pwd -L`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `pwd -P`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- git toplevel: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- `core.worktree`: empty
- branch: `release/old-blue-frontend`
- HEAD: `5373b518a7944a9efdbb6f834ce45e44d8145e07`
- `origin/main`: `c7f57b74bbd4afdae413809e773551db2933e34f`
- branch relation: `release/old-blue-frontend...origin/release/old-blue-frontend [behind 3]`

## Baseline

- automation memory available: yes
- memory baseline used: `c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753`
- committed scan window: `c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753..5373b518a7944a9efdbb6f834ce45e44d8145e07`
- baseline ancestry: `c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753` is an ancestor of HEAD
- `.env`: present, readable, non-symlink, parsed by python-dotenv with 216 keys

## Dirty state

Dirty tracked work remains first-class health signal and was not reset/stashed/cleaned.

Main buckets:

- contract/governance docs: `.env.example`, `AGENTS.md`, `CLAUDE.md`, `contracts/env_registry.yaml`, `contracts/learner-state.md`
- mobile / billing / member / wallet: `deeptutor/api/routers/mobile.py`, `deeptutor/services/member_console/*`, `deeptutor/services/wallet/service.py`, related tests
- Luban lesson: `deeptutor/api/routers/luban_lesson.py`, `deeptutor/services/luban_lesson/*`, related tests
- WeChat/yousen shadow: `wx_miniprogram/pages/*`, `yousenwebview/packageDeeptutor/pages/*`, `yousenwebview/tests/*`
- ops/docs/assets: `docker-compose.yml`, `scripts/sync_to_aliyun.sh`, deleted `docs/plan/鲁班移动端提分闭环/implementation-notes.md`, new marketing/plan/raw-data artifacts

## Checks

| Status | Check | Evidence |
| --- | --- | --- |
| FAIL | `python ../scripts/check_contract_guard.py` | `contract-guard: failed`; `mobile.py` changed in `turn` and `capability` sensitive domains without contract surface update |
| PASS | Tier 1 WS/mobile/session/learner_state | `960 passed, 5 warnings in 162.91s` |
| PASS | Tier 1 DeepQuestion/construction/RAG | `873 passed in 28.99s` |
| PASS | Web preflight | memory snapshot below stop thresholds; no AI-agent-owned Next tree; `pgrep` PID was transient and gone by `ps` |
| PASS | `npm run test:wechat-harness:data` | 5/5 passed; only `MODULE_TYPELESS_PACKAGE_JSON` warning |
| PASS | dirty backend narrow tests | `238 passed in 346.13s` for Luban lesson, member_console, wallet |
| PASS | `tests/services/test_wechat_pay.py` | `2 passed in 0.34s` |
| PASS | yosen/wx shadow node tests | profile badges, capability status, points sync, billing packages, billing payment/visual/login contracts all passed |
| DEFERRED | Tier 2 observability/release gate | not run because Tier 1 contract guard already RED; this is not a release closure |
| DEFERRED | real WeChat DevTools true-entry | not run; shadow harness is not `real_wechat_package` evidence |
| DEFERRED | Playwright/self-hosted smoke | not run; no release-style closure attempted |

## Failure root cause

- One business fact: contract-sensitive mobile turn/capability surface changes must be accompanied by the registered contract surface update.
- One authority: `CONTRACT.md` + `contracts/index.yaml` + `scripts/check_contract_guard.py`.
- Breakpoint: dirty `deeptutor/api/routers/mobile.py` is detected as sensitive for both `turn` and `capability`, but the dirty set does not include a required contract surface file for either domain.
- Minimal repair scope: either update the appropriate contract surface (`contracts/turn.md`, `contracts/capability.md`, or another required listed surface) to reflect the intentional API/control-plane semantics, or revert/narrow the `mobile.py` semantic surface change if it was accidental. Existing tests already pass, so do not add fallback/regex; fix the authority paperwork or shrink the change.

## Severity

- P0: contract guard failure on `mobile.py` for `turn` and `capability`.
- P1: dirty worktree remains broad and branch is behind remote; not release-ready.
- P2: true WeChat and Playwright evidence remain pending; acceptable for daily integration, not acceptable for release.

## Next Codex tasks

1. Fix the `mobile.py` contract-guard failure by updating the correct registered contract surface or narrowing the mobile change.
2. Classify the broad dirty WIP into commit-ready vs discard/move-out groups before any release gate.
3. If a release candidate is intended, run real `yousenwebview` project-root / `packageDeeptutor` DevTools evidence after the same Web/Next guard.

## Minimal repair prompt

From `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`, inspect the dirty diff for `../deeptutor/api/routers/mobile.py` against `HEAD`, decide whether the change alters `turn` or `capability` contract semantics, then either update the appropriate contract surface listed by `scripts/check_contract_guard.py` or shrink the `mobile.py` change. Do not reset/stash unrelated WIP. Verify with `PYTHONPATH=.. python ../scripts/check_contract_guard.py` and rerun `../tests/api/test_mobile_router.py`.

## Artifact logs

Run directory: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/automation-runs/daily-bug-scan/20260708T092437+0800`

