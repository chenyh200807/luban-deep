# DeepTutor Launch Readiness Dashboard Implementation Plan

- Date: 2026-05-18
- Status: Implemented locally for P0-P2
- Parent lines:
  - [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md)
  - [2026-04-23-deeptutor-benchmark-single-spine-prd.md](2026-04-23-deeptutor-benchmark-single-spine-prd.md)
- Code entry:
  - `deeptutor/services/observability/launch_readiness.py`
  - `deeptutor/api/routers/observability.py`
  - `deeptutor/services/observability/control_plane_store.py`

## Goal

Build one DeepTutor launch panel that answers:

> Can this release ship now?

The panel must summarize contract guard, benchmark, OA / ARR / AAE, Playwright, WeChat DevTools, and Langfuse into one go / no-go read model instead of leaving the decision scattered across reports.

## Non-Goals

1. Do not add a second release authority beside `release_gate_runs`.
2. Do not run tests from the dashboard request path.
3. Do not make BI frontend code reconstruct gate logic.
4. Do not introduce another chat, turn, or trace contract.
5. Do not hide missing evidence as green.

## Mandatory Design Gate

### Thin Wrapper / Fat Skill Split

- Thin wrapper: `GET /api/v1/observability/launch-readiness`.
- Fat authority: `deeptutor.services.observability.launch_readiness`.
- Persistent evidence source: `ObservabilityControlPlaneStore`.
- Existing release authority: `release_gate_runs`.

### One Business Fact

There is one business fact:

> A release is shippable only if all required launch evidence is present and not failing.

### One Authority

- Release-level recommendation remains owned by `release_gate_runs`.
- Launch panel owns only the read model that merges release gate, manual readiness checks, and observer evidence.
- BI may display the payload but must not recalculate go / no-go.

### Competing Authorities To Demote

1. Markdown QA reports.
2. Playwright HTML report folders.
3. WeChat DevTools CLI console output.
4. Manual Langfuse screenshots or ad hoc trace links.
5. Per-script stdout.

They can remain evidence, but they must be recorded into control-plane rows before they influence the panel.

### Additive Justification

The only new control-plane kind is `readiness_checks`.

It is justified because contract guard, Playwright, and WeChat DevTools are executable evidence that do not naturally belong to OM, ARR, AAE, OA, or release gate. The row is intentionally generic and evidence-only:

- `check_id`
- `status`
- `summary`
- `evidence`
- optional `blockers`

It does not define a second release recommendation.

### LLM vs Deterministic

The launch panel is deterministic. LLM/OA can generate root-cause hypotheses, but whether a row is `PASS / WARN / FAIL / NOT_RUN` must come from structured evidence.

## P0 Shape

The first deliverable is a backend read model:

1. `release_gate` from latest `release_gate_runs`.
2. `contract_guard` from latest `readiness_checks[check_id=contract_guard]`.
3. `benchmark` from release gate P2 or latest ARR / benchmark run.
4. `oa_arr_aae` from release gate P2 / P3 / P4 or latest ARR / AAE / OA presence.
5. `playwright` from latest `readiness_checks[check_id=playwright]`.
6. `wechat_devtools` from latest `readiness_checks[check_id=wechat_devtools]`.
7. `langfuse` from latest `observer_snapshots.langfuse_trace_linkage`.

Required rows missing evidence are `NOT_RUN`, not `PASS`.

## P1 Writer Adapters

Status: Implemented locally.

Next, add thin writer adapters that record existing commands into `readiness_checks`:

1. `scripts/run_readiness_check.py --check-id contract_guard` -> `contract_guard`.
2. `scripts/run_readiness_check.py --check-id playwright --command ...` -> `playwright`.
3. `scripts/run_readiness_check.py --check-id wechat_devtools` -> `wechat_devtools`，默认执行 `scripts/run_wechat_devtools_daily_smoke.py`，目标是 `yousenwebview/packageDeeptutor`。
4. Langfuse / ClickHouse trace verification may remain in `observer_snapshots` unless a dedicated manual trace audit is needed.

## P2 BI Surface

Status: Implemented locally.

BI consumes only:

`GET /api/v1/observability/launch-readiness`

Suggested UI rows:

| Row | Required | Source |
| --- | --- | --- |
| Release Gate | yes | `release_gate_runs` |
| Contract Guard | yes | `readiness_checks` |
| Benchmark / ARR | yes | `release_gate_runs` or `arr_runs` |
| OA / ARR / AAE | yes | `release_gate_runs` |
| Playwright | yes | `readiness_checks` |
| WeChat DevTools | yes | `readiness_checks` |
| Langfuse Trace Linkage | yes | `observer_snapshots` |

## Acceptance

1. Missing required evidence yields `final_status=FAIL` and `recommendation=hold`.
2. All required rows passing yields `final_status=PASS` and `recommendation=canary`.
3. The router returns the same rows without reconstructing gate logic.
4. Tests cover missing evidence, all-pass evidence, and the API route.

## Current Risks

1. Writer adapters are available, but CI/deploy jobs still need to call them around the real Playwright and WeChat DevTools commands.
2. Current BI files already contain parallel BI / invite-test changes in the working tree; the launch-readiness surface was integrated by minimal additive edits.
3. Langfuse row currently proves trace linkage existence, not semantic correctness of every trace. Deeper trace audit remains an observer / OA responsibility.
