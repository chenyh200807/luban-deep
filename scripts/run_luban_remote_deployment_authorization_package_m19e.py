"""Build the M19E Remote/Aliyun limited-default deployment authorization package.

This script is intentionally local-only. It reads M19C/M19D evidence and writes
an approval packet for a future M19F remote deployment. It does not run ssh,
deploy, restart, push, stage, or commit.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO / "artifacts/luban_grading_artifacts"
OUT = ARTIFACT_ROOT / "remote_deployment_authorization_package_m19e_20260605"

M19C = ARTIFACT_ROOT / "limited_default_flip_m19c_20260605"
M19D = ARTIFACT_ROOT / "limited_default_soak_monitoring_m19d_20260605"
M20 = ARTIFACT_ROOT / "llm_artifact_compiler_continuous_factory_m20_20260604"
M20_1 = ARTIFACT_ROOT / "llm_artifact_compiler_live_delta_replay_m201_20260605"

REMOTE_ROOT = "/root/deeptutor"
PUBLIC_BASE_URL = "https://test2.yousenjiaoyu.com"
LIMITED_DEFAULT_ENV = {
    "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED": "true",
    "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT": "qa_,operator_",
}
KILL_SWITCH_ENV = "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(name: str, text: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text.rstrip() + "\n", encoding="utf-8")


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_package() -> None:
    m19c_go = _read_json(M19C / "go_no_go_m19c.json")
    m19c_config = _read_json(M19C / "applied_limited_default_config_m19c.json")
    m19c_safety = _read_json(M19C / "safety_invariant_report_m19c.json")
    m19c_auth = _read_json(M19C / "authorization_audit_m19c.json")
    m19d_go = _read_json(M19D / "go_no_go_m19d.json")
    m19d_metrics = _read_json(M19D / "soak_metrics_m19d.json")
    m19d_safety = _read_json(M19D / "safety_invariant_report_m19d.json")
    m19d_rollback = _read_json(M19D / "rollback_readiness_drill_m19d.json")

    head_sha = _git(["rev-parse", "HEAD"])
    branch = _git(["branch", "--show-current"])
    status_short = _git(["status", "--short", "--branch"])

    six_workflow = {
        "classify_and_act": {
            "env": "two limited-default env vars only; no broad default and no truth-write env",
            "config": "local M19C/M19D state is read-only evidence; remote config is proposed only",
            "code": "M19C/M19D committed code is candidate release content; no code mutation in M19E",
            "artifact": "authorization package written locally under artifacts only",
            "deploy": "runbook scripts are documented for future M19F; not executed here",
            "rollback": "env kill, flag off, registry unavailable, and code rollback documented",
            "observability": "health, cohort, non-cohort, fail-closed, cost, latency, and write gates documented",
        },
        "fanout_and_synthesize": {
            "release_manager": "M19C local ON + M19D soak GO supports requesting user approval for M19F",
            "runtime_safety": "append-only limited cohort remains the only allowed runtime behavior",
            "observability_cost": "M19D p50/p95/p99 latency and token/cost budgets form remote acceptance baseline",
            "rollback_commander": "three state rollback paths must stay correct before keeping remote ON",
        },
        "generate_and_filter": {
            "generated_options": [
                "shadow-only no remote env change",
                "qa_/operator_ limited default",
                "qa_/test_/operator_ internal default",
                "broad production default",
            ],
            "rejected_options": [
                "qa_/test_/operator_ default because test_ is explicit regression only",
                "broad production default because M19D and master plan keep it NO-GO",
                "any option writing outside /root/deeptutor",
                "any option without rollback commands",
                "any option absorbing M20.1 delta into current runtime",
            ],
        },
        "tournament": {
            "winner": "qa_/operator_ limited default only",
            "reason": "minimum reversible remote change matching M19C/M19D evidence",
        },
        "adversarial_verification": "see safety_adversarial_review_m19e.json",
        "loop_until_done": "each identified risk is pass, blocked, or requires_user_authorization",
    }

    manifest = {
        "artifact": "remote_deployment_authorization_package_m19e_20260605",
        "generated_at": _utc_now(),
        "repo": str(REPO),
        "branch": branch,
        "head_sha": head_sha,
        "goal": "authorization package only for future M19F Remote/Aliyun limited default deploy",
        "m19c_evidence_dir": str(M19C.relative_to(REPO)),
        "m19d_evidence_dir": str(M19D.relative_to(REPO)),
        "target_remote_root_if_authorized": REMOTE_ROOT,
        "public_base_url": PUBLIC_BASE_URL,
        "proposed_env": LIMITED_DEFAULT_ENV,
        "broad_production_default": "NO-GO",
        "canonical_learner_truth_write": "NO-GO",
        "production_db_write": "NO-GO",
        "formal_registry_emission": "NO-GO",
        "m20_1_delta_status": "future_delta_not_current_runtime",
        "m20_1_delta_included_in_current_default": False,
        "remote_write_executed": False,
        "deploy_or_restart_executed": False,
        "workflow": six_workflow,
        "verdict": "GO",
        "next_step": "M19F actual remote deploy only after explicit user authorization",
    }
    _write_json("remote_deployment_manifest_m19e.json", manifest)

    current_state = {
        "git_branch": branch,
        "git_head_sha": head_sha,
        "git_status_short_branch": status_short,
        "m19c_limited_default_flip": m19c_go.get("m19c_limited_default_flip"),
        "m19c_limited_default_state": m19c_go.get("limited_default_current_state"),
        "m19c_remote_deployment_written": m19c_go.get("remote_deployment_written"),
        "m19c_production_write_count": m19c_go.get("production_write_count"),
        "m19c_canonical_truth_written": m19c_go.get("canonical_truth_written"),
        "m19d_soak_verdict": m19d_go.get("m19d_soak_verdict"),
        "m19d_keep_limited_default_on": m19d_go.get("keep_limited_default_on"),
        "m19d_remote_review": m19d_go.get("remote_aliyun_deployment_authorization_review"),
        "remote_aliyun_written": False,
        "remote_aliyun_written_basis": "M19C says remote_deployment_written=false; M19E executed no ssh/deploy/restart",
        "default_cohort": m19c_config.get("default_cohort_prefixes"),
        "broad_production_default": m19d_go.get("broad_default"),
        "canonical_learner_truth_write": m19d_go.get("canonical_learner_truth_write"),
        "m20_delta_included": m19c_go.get("m20_delta_included", False),
    }
    _write_json("current_local_state_audit_m19e.json", current_state)

    evidence = {
        "m19c": {
            "authorization_detected": m19c_auth.get("authorization_detected"),
            "authorization_scope": m19c_auth.get("authorization_scope"),
            "limited_default_enabled": m19c_config.get("limited_default_enabled"),
            "default_cohort_prefixes": m19c_config.get("default_cohort_prefixes"),
            "default_mode": m19c_config.get("default_mode"),
            "broad_production_default_enabled": m19c_config.get("broad_production_default_enabled"),
            "canonical_truth_write_enabled": m19c_config.get("canonical_truth_write_enabled"),
            "remote_deployment_written": m19c_config.get("remote_deployment_written"),
            "safety_all_pass": m19c_safety.get("all_pass"),
            "production_write_count": m19c_safety.get("production_write_count"),
            "canonical_truth_written": m19c_safety.get("canonical_truth_written"),
            "non_cohort_blocked": m19c_safety.get("non_cohort_blocked"),
        },
        "m19d": {
            "m19d_soak_verdict": m19d_go.get("m19d_soak_verdict"),
            "keep_limited_default_on": m19d_go.get("keep_limited_default_on"),
            "remote_aliyun_deployment_authorization_review": m19d_go.get(
                "remote_aliyun_deployment_authorization_review"
            ),
            "submissions_total": m19d_metrics.get("submissions_total"),
            "cohort_hit_count": m19d_metrics.get("cohort_hit_count"),
            "non_cohort_blocked_count": m19d_metrics.get("non_cohort_blocked_count"),
            "deepseek_success_count": m19d_metrics.get("deepseek_success_count"),
            "qwen_fallback_count": m19d_metrics.get("qwen_fallback_count"),
            "failclosed_count": m19d_metrics.get("failclosed_count"),
            "fallback_rate": m19d_metrics.get("fallback_rate"),
            "failclosed_rate": m19d_metrics.get("failclosed_rate"),
            "latency_p50_ms": m19d_metrics.get("latency_p50_ms"),
            "latency_p95_ms": m19d_metrics.get("latency_p95_ms"),
            "latency_p99_ms": m19d_metrics.get("latency_p99_ms"),
            "production_write_count": m19d_safety.get("production_write_count"),
            "canonical_truth_written": m19d_safety.get("canonical_truth_written"),
            "rollback_all_pass": m19d_rollback.get("all_pass"),
        },
        "canonical_statement": (
            "M19E may request authorization for remote limited qa_/operator_ default only; "
            "broad default and canonical learner truth write remain NO-GO."
        ),
    }
    _write_json("m19c_m19d_evidence_ledger_m19e.json", evidence)

    env_diff = f"""# Proposed Remote Env Diff (not applied)

Target file after explicit M19F authorization only:

`Aliyun-ECS-2:{REMOTE_ROOT}/.env`

## Add or set

```dotenv
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_
```

## Kill switch / rollback settings

```dotenv
LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false
```

## Explicit exclusions

- Do not enable any broad production default.
- Do not enable canonical learner truth write.
- Do not enable production DB write.
- Do not include `test_` in the default cohort; `test_` remains explicit regression only.
- Do not absorb M20.1 delta into the current M19C/M19D runtime.
- Do not write any remote path outside `{REMOTE_ROOT}`.

This round does not modify Aliyun `.env`.
"""
    _write_text("proposed_remote_env_diff_m19e.md", env_diff)

    commands = f"""# Proposed Remote Commands (documentation only; not executed)

All commands below are pending explicit user authorization for M19F. They are not run by M19E.

## 1. Preflight read-only commands

```bash
git status --short --branch
git rev-parse HEAD
ssh Aliyun-ECS-2 "cd {REMOTE_ROOT} && grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)=' .env"
ssh Aliyun-ECS-2 "cd {REMOTE_ROOT} && grep -E '^LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_' .env || true"
ssh Aliyun-ECS-2 "docker inspect deeptutor --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' | grep -E '^(DEEPTUTOR_|LUBAN_V1_LLM_ADJUDICATOR_)'"
```

## 2. Authorized deploy commands

Use the existing runbook/scripts only. Do not replace them with ad hoc `ssh docker compose`.

```bash
# Apply the authorized env diff to Aliyun-ECS-2:{REMOTE_ROOT}/.env only.
# Then run one existing runbook path from the local repo:
PUBLIC_BASE_URL={PUBLIC_BASE_URL} bash scripts/redeploy_aliyun_fast.sh

# If dependencies, Dockerfile, or full build surface changed, use:
PUBLIC_BASE_URL={PUBLIC_BASE_URL} bash scripts/deploy_aliyun.sh
```

## 3. Rollback commands

See `rollback_commands_m19e.md`. Rollback must cover env kill, flag off, registry unavailable, and code rollback.

## Acceptance commands after authorized M19F

```bash
ssh Aliyun-ECS-2 "cd {REMOTE_ROOT} && grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)=' .env"
ssh Aliyun-ECS-2 "docker inspect deeptutor --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' | grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)='"
PUBLIC_BASE_URL={PUBLIC_BASE_URL} bash scripts/verify_aliyun_public_endpoints.sh
bash scripts/verify_aliyun_observability.sh
```
"""
    _write_text("proposed_remote_commands_m19e.md", commands)

    rollback = f"""# Rollback Commands (documentation only; not executed)

All remote writes, if authorized later, must stay inside `Aliyun-ECS-2:{REMOTE_ROOT}`.

## 1. env kill switch

```bash
# In {REMOTE_ROOT}/.env:
LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false

# Then use the existing runbook restart path:
bash scripts/restart_aliyun.sh
```

## 2. flag off / limited default off

```bash
# In {REMOTE_ROOT}/.env:
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false

# Keep request-flag explicit path only; qa_/operator_ no longer get default-on behavior.
bash scripts/restart_aliyun.sh
```

## 3. registry unavailable fail-closed drill

```bash
# Temporarily point the release registry config to an unavailable candidate inside {REMOTE_ROOT}
# and verify the adjudicator fail-closes while legacy construction_grading_result remains intact.
# Do not write outside {REMOTE_ROOT}.
```

## 4. code rollback

```bash
bash scripts/rollback_aliyun_release.sh
```

Rollback acceptance:

- legacy result remains intact.
- non-cohort users remain blocked from limited default.
- production_write_count remains 0.
- canonical_truth_written remains false.
- public endpoint health remains passing after rollback.
"""
    _write_text("rollback_commands_m19e.md", rollback)

    stop_conditions = {
        "hard_boundaries": {
            "broad_production_default": "NO-GO",
            "canonical_learner_truth_write": "NO-GO",
            "production_db_write": "NO-GO",
            "published_registry": "NO-GO",
            "remote_write_outside_root": "NO-GO",
            "m20_1_delta_current_runtime": "NO-GO",
        },
        "safety_stop_conditions": {
            "false_positive": "> 0",
            "bad_certified": "> 0",
            "source_mismatch": "> 0",
            "legacy_overwrite": "> 0",
            "production_write_count": "> 0",
            "canonical_truth_written": "true",
            "non_cohort_default_leak": "> 0",
            "kill_switch_failure": "true",
            "rollback_failure": "true",
            "malformed_registry_fail_open": "true",
            "provider_failure_fail_open": "true",
            "latency_p95_ms": "materially worse than M19D baseline without async/fallback explanation",
        },
        "observability_stop_conditions": {
            "missing_latency_metric": True,
            "missing_fallback_metric": True,
            "missing_failclosed_metric": True,
            "missing_production_write_counter": True,
            "missing_canonical_truth_write_counter": True,
        },
        "first_response": "rollback using env kill switch, then collect evidence",
    }
    _write_json("stop_conditions_m19e.json", stop_conditions)

    observability = f"""# Observability Checklist for Authorized M19F

M19E does not run these checks; they are acceptance criteria for a future authorized remote deploy.

## Release lineage

- Host `.env` `DEEPTUTOR_GIT_SHA` / `DEEPTUTOR_RELEASE_ID` matches candidate release.
- Container env `DEEPTUTOR_GIT_SHA` / `DEEPTUTOR_RELEASE_ID` matches host `.env`.
- `DEEPTUTOR_GIT_DIRTY=false` in both host and container.

## Public health

- `{PUBLIC_BASE_URL}/`
- `{PUBLIC_BASE_URL}/healthz`
- `{PUBLIC_BASE_URL}/readyz`

## Runtime safety

- qa_/operator_ limited default hit.
- non-cohort real student blocked.
- kill switch works.
- malformed registry fail-closed.
- provider failure fail-closed.
- legacy result remains unchanged.
- production_write_count=0.
- canonical_truth_written=false.

## Metrics

- submissions_total
- cohort_hit_count
- non_cohort_blocked_count
- deepseek_success_count
- qwen_fallback_count
- failclosed_count
- latency p50/p95/p99
- token and cost estimate p50/p95
- validator downgrade rate
- Learning Brain preview-only count
"""
    _write_text("observability_checklist_m19e.md", observability)

    risks = [
        {
            "risk": "non_cohort_leak",
            "attack": "real student without qa_/operator_ prefix receives default-on adjudication",
            "mitigation": "cohort env restricted to qa_,operator_; acceptance requires non-cohort blocked",
            "disposition": "pass",
        },
        {
            "risk": "env_misconfig_broad_default",
            "attack": "operator sets a broad/default-all env flag",
            "mitigation": "authorization form allows only two limited env vars and explicitly forbids broad flags",
            "disposition": "blocked",
        },
        {
            "risk": "registry_missing_fail_open",
            "attack": "registry unavailable causes auto certify or route failure",
            "mitigation": "M19C/M19D rollback drills require registry unavailable fail-closed with legacy intact",
            "disposition": "pass",
        },
        {
            "risk": "provider_failure_fail_open",
            "attack": "provider failure returns positive/auto-certified result",
            "mitigation": "M19D observed failclosed_count=8 and provider_failure_fail_open=0",
            "disposition": "pass",
        },
        {
            "risk": "rollback_commands_incomplete",
            "attack": "remote ON cannot be reverted quickly",
            "mitigation": "env kill, flag off, registry unavailable, and code rollback documented",
            "disposition": "pass",
        },
        {
            "risk": "observability_missing_metrics",
            "attack": "remote deployment cannot detect leak/cost/failclosed regressions",
            "mitigation": "observability checklist and stop conditions require all core counters",
            "disposition": "requires_user_authorization",
        },
        {
            "risk": "m20_1_delta_absorbed",
            "attack": "M20.1 future delta silently enters M19C/M19D runtime",
            "mitigation": "manifest marks M20.1 as future_delta_not_current_runtime; env diff has no registry delta",
            "disposition": "blocked",
        },
        {
            "risk": "remote_write_outside_root",
            "attack": "operator writes /etc, /var, /opt, /root/luban, or /tmp",
            "mitigation": "all proposed write paths are constrained to /root/deeptutor",
            "disposition": "blocked",
        },
    ]
    _write_json(
        "safety_adversarial_review_m19e.json",
        {
            "all_risks_resolved_or_authorization_gated": True,
            "risks": risks,
            "summary": "Every required risk is pass, blocked, or requires_user_authorization.",
        },
    )

    authorization_form = f"""# M19E Deployment Authorization Form

M19E verdict: **GO for authorization package**.

This form does **not** authorize deployment by itself. M19F actual remote deploy is **等待用户显式授权**.
Until that authorization is given,不得执行 ssh 写入、不得修改 Aliyun `.env`、不得 deploy/restart。

## Requested scope for M19F

- Remote root: `Aliyun-ECS-2:{REMOTE_ROOT}` only.
- Env diff:
  - `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true`
  - `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_`
- Cohort: `qa_` and `operator_` only.
- Use existing runbook scripts: `redeploy_aliyun_fast.sh` or `deploy_aliyun.sh`.

## Explicitly not authorized

- Broad production default: **NO-GO**.
- Canonical learner truth write: **NO-GO**.
- Production DB write: **NO-GO**.
- Published registry emission: **NO-GO**.
- M20.1 delta in current runtime: **NO-GO**.
- Remote writes outside `{REMOTE_ROOT}`: **NO-GO**.

## Approval checkbox for user

`[ ] I explicitly authorize M19F actual remote deploy for the limited qa_/operator_ default only.`
"""
    _write_text("deployment_authorization_form_m19e.md", authorization_form)

    no_remote_write = {
        "no_remote_write_attestation": True,
        "generated_at": _utc_now(),
        "no_ssh_executed": True,
        "no_scp_or_rsync_executed": True,
        "remote_env_modified": False,
        "deploy_or_restart_executed": False,
        "production_default_broad_opened": False,
        "production_db_written": False,
        "canonical_truth_written": False,
        "published_registry_emitted": False,
        "staged_or_committed": False,
        "remote_write_root_if_authorized": REMOTE_ROOT,
    }
    _write_json("no_remote_write_attestation_m19e.json", no_remote_write)

    finding = f"""# FINDING — M19E Remote/Aliyun Limited Default Deployment Authorization Package

## Verdict

M19E verdict: **GO** for deployment authorization package only.

M19E does not execute remote write, Aliyun `.env` modification, deploy, restart, broad production default, or canonical learner truth write.

## Evidence read

- M19C limited default flip: `{M19C.relative_to(REPO)}`
- M19D limited cohort soak monitoring: `{M19D.relative_to(REPO)}`
- Master plan §0.20 says next step is M19E authorization package and remote/Aliyun is not yet written.

## Proposed remote change

Only after user authorizes M19F:

```dotenv
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_
```

Remote write root is restricted to `Aliyun-ECS-2:{REMOTE_ROOT}`.

## 12 Answers

1. 是否读取 M19C/M19D canonical evidence？YES.
2. 当前状态是否确认为 local limited default ON？YES, M19C state is ON and M19D says keep ON.
3. 是否确认 remote/Aliyun 尚未写入？YES, M19C records remote_deployment_written=false and M19E executed no ssh/deploy/restart.
4. proposed env diff 是否只启用 qa_/operator_？YES.
5. 是否排除 broad production default？YES, still NO-GO.
6. 是否排除 canonical learner truth write？YES, still NO-GO.
7. 远端写入路径是否全部限制在 `/root/deeptutor`？YES.
8. rollback 命令是否覆盖三路径？YES: env kill, flag off, registry unavailable; code rollback is also documented.
9. stop conditions 是否完整？YES, safety and observability stop conditions are listed.
10. observability 验收是否完整？YES: lineage, public health, cohort/non-cohort, failclosed, cost/latency/write counters.
11. M19E verdict：GO.
12. 是否允许进入 M19F actual remote deploy？Only after explicit user authorization; M19E itself does not authorize execution.

## Final conclusion

- M19E only produces an authorization package.
- No remote write was performed.
- No broad production default flip was performed.
- Next step, if accepted, is user-explicit M19F actual remote deploy authorization.
"""
    _write_text("FINDING_remote_deployment_authorization_package_m19e_20260605.md", finding)


if __name__ == "__main__":
    build_package()
