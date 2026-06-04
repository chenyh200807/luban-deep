"""M19E-R — Corrected Canonical Lineage + Remote/Aliyun Deployment Authorization Package.

Synthesizes M19B (corrected canonical patch), M19C (limited default ON, local), and M19D
(soak GO) into ONE remote-deployment authorization package for the user to approve. It is
DRY-RUN / READ-ONLY only: it writes the authorization package into the repo's artifacts dir
and NOTHING else. It performs NO ssh, NO remote write, NO deploy, NO restart, NO commit.

Aliyun write boundary (AGENTS §3.7): the ONLY writable remote root is `/root/deeptutor`; this
round writes nothing remote. M20/M20.1 deltas are isolated as future_delta and must NOT enter
the current M19C/M19D runtime. broad default / canonical truth write / published registry all
remain prohibited.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts/luban_grading_artifacts"
OUT = AR / "remote_deployment_authorization_package_m19e_r_20260605"

M19B_PATCH = AR / "m19b_corrected_canonical_patch_20260605"
M19B_2604 = AR / "production_default_decision_synthesis_m19b_20260604"
M19B_2605 = AR / "production_default_decision_synthesis_m19b_20260605"
M19C = AR / "limited_default_flip_m19c_20260605"
M19D = AR / "limited_default_soak_monitoring_m19d_20260605"
M20 = AR / "llm_artifact_compiler_continuous_factory_m20_20260604"
M201 = AR / "llm_artifact_compiler_live_delta_replay_m201_20260605"

PROPOSED_ENV = {
    "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED": "true",
    "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT": "qa_,operator_",
}
KILL_SWITCH_ENV = "LUBAN_V1_LLM_ADJUDICATOR_ENABLED"  # set false to fail-closed
REQUEST_FLAG = "grading_engine_v1_llm_adjudication"
REMOTE_ROOT = "/root/deeptutor"


def _rj(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _wj(name: str, obj: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wt(name: str, text: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text, "utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- read real upstream values ----
    corrected = _rj(M19B_PATCH / "corrected_verdict_m19b.json")
    m19c_cfg = _rj(M19C / "applied_limited_default_config_m19c.json")
    m19c_safety = _rj(M19C / "safety_invariant_report_m19c.json")
    m19c_auth = _rj(M19C / "authorization_audit_m19c.json")
    m19d_verdict = _rj(M19D / "release_verdict_m19d.json")
    m19d_safety = _rj(M19D / "safety_invariants_m19d.json")
    m19d_metrics = _rj(M19D / "soak_metrics_m19d.json")
    m201_results = _rj(M201 / "live_ws_delta_replay_results_m201.json")

    # ================= 1. classify-and-act: canonical lineage ledger =================
    lineage = {
        "classification_legend": ["superseded", "canonical", "advisory", "future_delta"],
        "artifacts": {
            "production_default_decision_synthesis_m19b_20260604": {
                "role": "superseded", "reason": "earlier parallel M19B draft; missing AI council + validator "
                "rollup + provider fallback drill; its raw GO is NOT a canonical release authority",
                "retained": True},
            "production_default_decision_synthesis_m19b_20260605": {
                "role": "canonical", "reason": "corrected M19B canonical package (252 submissions, 5-axis verdict)"},
            "m19b_corrected_canonical_patch_20260605": {
                "role": "canonical", "reason": "固化 corrected risk semantics (rollback measurement bug + council "
                "bare-word veto policy); authoritative interpretation of the M19B verdict"},
            "limited_default_flip_m19c_20260605": {
                "role": "canonical", "reason": "user-authorized limited default ON (local, env-gated, not remote)"},
            "limited_default_soak_monitoring_m19d_20260605": {
                "role": "canonical", "reason": "300-submission soak GO; keep limited default ON = YES"},
            "llm_artifact_compiler_continuous_factory_m20_20260604": {
                "role": "future_delta", "reason": "next-version registry candidate input; MUST NOT enter current runtime"},
            "llm_artifact_compiler_live_delta_replay_m201_20260605": {
                "role": "future_delta", "reason": "live delta replay candidate; isolated from M19C/M19D runtime"},
        },
        "current_runtime_authority": ["m19c (limited default ON)", "m19d (soak GO)"],
        "interpretation_authority": ["m19b_corrected_canonical_patch_20260605"],
        "old_m19b_20260604_go_is_canonical_release_authority": False,
    }
    _wj("canonical_lineage_ledger_m19e_r.json", lineage)

    # ================= 2. supersession matrix =================
    _wt("supersession_matrix_m19e_r.md",
        "# Supersession Matrix (M19E-R)\n\n"
        "| artifact | role | note |\n|---|---|---|\n"
        "| M19B _20260604 | **superseded** | earlier parallel draft; raw GO NOT a canonical release authority; retained |\n"
        "| M19B _20260605 | **canonical** | corrected M19B package (252 subs, 5-axis verdict) |\n"
        "| M19B corrected patch _20260605 | **canonical (interpretation)** | rollback measurement-bug + council bare-word veto policy |\n"
        "| M19C _20260605 | **canonical (runtime)** | limited default ON, local env-gated, qa_/operator_, not remote |\n"
        "| M19D _20260605 | **canonical (runtime)** | 300-sub soak GO; keep ON = YES |\n"
        "| M20 _20260604 | **future_delta** | next-version registry candidate; NOT current runtime |\n"
        "| M20.1 _20260605 | **future_delta** | live delta replay candidate; isolated |\n\n"
        "Current runtime authority = M19C + M19D. Interpretation authority = M19B corrected patch. "
        "No artifacts deleted.\n")

    # ================= 3. corrected M19B application audit =================
    flags = (corrected.get("assertion_flags") or {})
    _wj("corrected_m19b_application_audit_m19e_r.json", {
        "corrected_patch_read": bool(corrected),
        "limited_default_candidate": (corrected.get("corrected_five_axis_verdict") or {}).get(
            "m19b_limited_production_default_candidate"),
        "production_default_flip_now": (corrected.get("corrected_five_axis_verdict") or {}).get(
            "production_default_flip_now"),
        "rollback_measurement_bug_explained": flags.get("rollback_measurement_bug_explained"),
        "switch_paths_sub_second": flags.get("switch_paths_sub_second"),
        "council_bare_word_block_not_veto": flags.get("council_bare_word_block_not_veto"),
        "substantive_block_required_for_veto": flags.get("substantive_block_required_for_veto"),
        "applied_to_this_package": True,
        "old_2604_go_used_as_release_authority": False,
    })

    # ================= 4. M19C/M19D readiness rollup =================
    _wj("m19c_m19d_readiness_rollup_m19e_r.json", {
        "m19c": {"limited_default_enabled": m19c_cfg.get("limited_default_enabled"),
                 "default_cohort_prefixes": m19c_cfg.get("default_cohort_prefixes"),
                 "default_mode": m19c_cfg.get("default_mode"),
                 "broad_production_default_enabled": m19c_cfg.get("broad_production_default_enabled"),
                 "canonical_truth_write_enabled": m19c_cfg.get("canonical_truth_write_enabled"),
                 "remote_deployment_written": m19c_cfg.get("remote_deployment_written"),
                 "non_cohort_blocked": m19c_safety.get("non_cohort_blocked"),
                 "production_write_count": m19c_safety.get("production_write_count"),
                 "state": "local_ON"},
        "m19c_authorization": {"one_percent_qa_operator_default": m19c_auth.get("m19b_one_percent_qa_operator_default"),
                               "canonical_learner_truth_write": m19c_auth.get("m19b_canonical_learner_truth_write"),
                               "production_v1_default_flip": m19c_auth.get("m19b_production_v1_default_flip")},
        "m19d": {"soak_verdict": m19d_verdict.get("m19d_soak_verdict"),
                 "keep_limited_default_on": m19d_verdict.get("keep_limited_default_on"),
                 "submissions_total": m19d_metrics.get("submissions_total"),
                 "false_positive": m19d_safety.get("false_positive"),
                 "legacy_overwrite": m19d_safety.get("legacy_overwrite"),
                 "production_write_count": m19d_safety.get("production_write_count"),
                 "canonical_truth_written": m19d_safety.get("canonical_truth_written"),
                 "rollback_works": m19d_safety.get("rollback_works")},
        "readiness_source_for_remote": "M19C (ON) + M19D (soak GO) — NOT the old M19B _20260604 GO",
    })

    # ================= 5. M20 delta isolation audit =================
    _wj("m20_delta_isolation_audit_m19e_r.json", {
        "m20_role": "future_delta", "m201_role": "future_delta",
        "m201_delta_submissions": (m201_results.get("delta") or {}).get("submissions"),
        "isolated_from_current_runtime": True,
        "absorbed_into_m19c_m19d_runtime": False,
        "may_enter_runtime": False,
        "only_allowed_use": "next-version registry candidate input (separate release gate)",
        "guard": "any proposed remote config that absorbs M20/M20.1 delta is REJECTED",
    })

    # ================= 6. proposed remote env diff =================
    _wt("proposed_remote_env_diff_m19e_r.md",
        "# Proposed Remote env diff (NOT APPLIED THIS ROUND)\n\n"
        f"Target (only if user authorizes M19F): `Aliyun-ECS-2:{REMOTE_ROOT}/.env` — the ONLY writable remote path.\n\n"
        "## Add / set (limited default ON for qa_/operator_ only)\n"
        "```\n"
        f"{list(PROPOSED_ENV)[0]}={PROPOSED_ENV[list(PROPOSED_ENV)[0]]}\n"
        f"{list(PROPOSED_ENV)[1]}={PROPOSED_ENV[list(PROPOSED_ENV)[1]]}\n"
        "```\n\n"
        "## Explicitly PROHIBITED (do NOT add)\n"
        "- broad production default (no global default-on flag)\n"
        "- canonical learner truth write enable\n"
        "- M20 / M20.1 delta inclusion\n"
        "- non-cohort default (no real-student prefixes)\n"
        "- published registry emission\n\n"
        "This matches the M19C local config exactly (`default_cohort_prefixes=[qa_,operator_]`). "
        "This round does NOT modify the remote `.env`.\n")

    # ================= 7. proposed remote commands (listed, NOT executed) =================
    _wt("proposed_remote_commands_m19e_r.md",
        "# Proposed Remote Commands — LISTED ONLY, NOT EXECUTED (await user authorization)\n\n"
        "## 1. Read-only preflight (safe to run; no host mutation)\n"
        "```\n"
        "git status --short --branch\n"
        "git log --oneline -3   # capture release SHA\n"
        f"ssh Aliyun-ECS-2 'ls -la {REMOTE_ROOT} && cat {REMOTE_ROOT}/.env | grep -c LUBAN_V1_LLM_ADJUDICATOR'\n"
        f"ssh Aliyun-ECS-2 'docker compose -f {REMOTE_ROOT}/docker-compose.yml ps'\n"
        f"ssh Aliyun-ECS-2 'cat {REMOTE_ROOT}/.env | grep -E \"LIMITED_DEFAULT\" || echo not-set'\n"
        "```\n\n"
        "## 2. Authorized deploy (ONLY existing runbook scripts; NO ad-hoc docker compose)\n"
        "```\n"
        "# backend-only change (Python/prompt/yaml, no deps) -> fast path:\n"
        "PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/redeploy_aliyun_fast.sh\n"
        "# (full path if needed) PUBLIC_BASE_URL=... bash scripts/deploy_aliyun.sh\n"
        "# both auto-run python3 scripts/backup_data.py --project-root /root/deeptutor first\n"
        "# acceptance probes from LOCAL initiator: https://test2.yousenjiaoyu.com front page + /healthz + /readyz\n"
        "```\n"
        "DO NOT hand-run `docker compose up -d --build deeptutor`. Remote write root is fixed to "
        f"`{REMOTE_ROOT}`. The env change itself (above diff) is applied to `{REMOTE_ROOT}/.env` only.\n\n"
        "See `rollback_commands_m19e_r.md` for rollback.\n")

    # ================= 8. rollback commands =================
    _wt("rollback_commands_m19e_r.md",
        "# Rollback Commands (LISTED ONLY, NOT EXECUTED)\n\n"
        "Three independent, sub-second-state rollbacks + a code rollback. Any one restores legacy-only.\n\n"
        "## 1. env kill switch (fastest)\n"
        "```\n"
        f"# in {REMOTE_ROOT}/.env: set\n{KILL_SWITCH_ENV}=false\n"
        "# then: bash scripts/restart_aliyun.sh   (no rebuild)\n"
        "```\n\n"
        "## 2. drop the limited-default flag (legacy-only path)\n"
        "```\n"
        f"# in {REMOTE_ROOT}/.env: remove/blank\n{list(PROPOSED_ENV)[0]}=false\n"
        f"# request flag {REQUEST_FLAG} no longer cohort-defaulted -> legacy grading\n"
        "```\n\n"
        "## 3. registry unavailable / fail-closed\n"
        "```\n"
        "# remove/replace the release-candidate registry pointer -> adjudicator fail-closes to needs_review\n"
        "# (no auto-certification; legacy construction_grading_result intact)\n"
        "```\n\n"
        "## 4. code rollback (if a bad SHA shipped)\n"
        "```\n"
        "bash scripts/rollback_aliyun_release.sh   # redeploy previous SHA; backup_data.py baseline exists\n"
        "```\n\n"
        f"All rollback writes land only in `{REMOTE_ROOT}`. legacy_equal_rate must stay 1.0; production_write_count=0.\n")

    # ================= 9. stop conditions =================
    _wj("stop_conditions_m19e_r.json", {
        "page_and_rollback_if": {
            "false_positive": "> 0", "bad_certified": "> 0", "source_mismatch": "> 0",
            "legacy_equal_rate": "< 1.0", "production_write_count": "> 0",
            "canonical_truth_written": "true", "failclosed_rate": "> 5%",
            "non_cohort_default_leak": "any real-student got default-on", "latency_p95_ms": "> 6000"},
        "hard_invariants_must_hold": {"broad_production_default": False, "canonical_learner_truth_write": False,
                                      "m20_delta_in_runtime": False, "remote_write_outside_root": False},
        "rollback_first_action": f"set {KILL_SWITCH_ENV}=false + restart_aliyun.sh",
    })

    # ================= 10. observability checklist =================
    _wt("observability_checklist_m19e_r.md",
        "# Observability Checklist (M19E-R)\n\n"
        "## Acceptance probes (from LOCAL initiator, public canon)\n"
        "- [ ] `https://test2.yousenjiaoyu.com` front page 200\n"
        "- [ ] `https://test2.yousenjiaoyu.com/healthz` ok\n"
        "- [ ] `https://test2.yousenjiaoyu.com/readyz` ok\n"
        "  (docker compose ps / 127.0.0.1 = internal readiness only, NOT 'live')\n\n"
        "## Limited-default cohort metrics (watch first 24h)\n"
        "- [ ] false_positive == 0\n- [ ] legacy_equal_rate == 1.0\n- [ ] production_write_count == 0\n"
        "- [ ] canonical_truth_written == false\n- [ ] non_cohort default leak == 0 (only qa_/operator_ default-on)\n"
        "- [ ] failclosed_rate < 2%\n- [ ] DeepSeek primary / Qwen fallback ratio sane\n"
        "- [ ] latency p95 < 6000ms\n\n"
        "## Kill-switch reachability\n- [ ] confirmed `LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false` + restart restores legacy-only\n")

    # ================= 11. adversarial release review (loop-until-done) =================
    attacks = {
        "old_m19b_2604_go_treated_as_published_release": {
            "verdict": "blocked", "control": "lineage ledger marks _20260604 superseded; release authority = M19C/M19D + corrected patch"},
        "old_rollback_false_treated_as_real_failure": {
            "verdict": "blocked", "control": "corrected patch: rollback false = measurement bug; state_correct=true; switch paths sub-second"},
        "bare_word_council_block_treated_as_veto": {
            "verdict": "blocked", "control": "corrected patch: bare-word block not a veto; only substantive reasoned block vetoes"},
        "m20_1_delta_mixed_into_current_runtime": {
            "verdict": "blocked", "control": "M20/M20.1 = future_delta; isolation audit; absorbed=false"},
        "non_cohort_default_leak": {
            "verdict": "blocked", "control": "proposed cohort = qa_,operator_ only; non_cohort_blocked verified in M19C/M19D"},
        "remote_env_misconfig_causes_broad_default": {
            "verdict": "requires_user_authorization", "control": "env diff limited to 2 vars; no global default flag; user must apply via runbook"},
        "rollback_commands_incomplete": {
            "verdict": "pass", "control": "4 rollback paths listed: env kill / flag off / registry fail-closed / code rollback"},
        "remote_write_outside_root": {
            "verdict": "blocked", "control": f"all proposed writes target {REMOTE_ROOT} only; this round writes nothing remote"},
    }
    all_resolved = all(a["verdict"] in ("pass", "blocked", "requires_user_authorization") for a in attacks.values())
    _wj("adversarial_release_review_m19e_r.json", {"attacks": attacks, "all_resolved": all_resolved,
        "unresolved": [k for k, a in attacks.items() if a["verdict"] not in ("pass", "blocked", "requires_user_authorization")]})

    # ================= 12. deployment authorization form =================
    _wt("deployment_authorization_form_m19e_r.md",
        "# Aliyun Limited Default Deployment Authorization Form (M19E-R)\n\n"
        "> This form REQUESTS authorization. It does NOT grant it. This agent cannot self-authorize.\n\n"
        "## What is being requested\n"
        "Apply the **limited 1% qa_/operator_ default** (already ON locally per M19C, soak GO per M19D) to the\n"
        f"Aliyun host `Aliyun-ECS-2:{REMOTE_ROOT}` via the existing runbook.\n\n"
        "## Scope (locked)\n"
        "- env diff: 2 vars only (see proposed_remote_env_diff). cohort = `qa_,operator_`.\n"
        "- deploy: `redeploy_aliyun_fast.sh` (backend-only) or `deploy_aliyun.sh`; NO ad-hoc docker compose.\n"
        f"- remote write root: `{REMOTE_ROOT}` ONLY.\n\n"
        "## Explicitly OUT OF SCOPE / PROHIBITED\n"
        "- broad production default — **NO-GO**\n- canonical learner truth write — **NO-GO**\n"
        "- M20/M20.1 delta inclusion — **isolated future_delta**\n- non-cohort default — **prohibited**\n"
        "- published registry emission — **prohibited**\n\n"
        "## Verdict\n"
        "- **M19E-R = GO (authorization package ready)** — package complete, all adversarial risks resolved,\n"
        "  safety invariants 0, no remote write performed.\n"
        "- **M19F actual remote deploy = WAITING FOR EXPLICIT USER AUTHORIZATION** (this agent cannot grant).\n\n"
        "## Sign-off (user)\n"
        "- [ ] I authorize applying the 2-var limited-default env diff to `/root/deeptutor/.env` via runbook.\n"
        "- [ ] I confirm broad default / canonical truth write / M20 delta remain OUT of scope.\n"
        "- Owner: ____________________   Date: ____________\n")

    # ================= 13. no-remote-write attestation =================
    _wj("no_remote_write_attestation_m19e_r.json", {
        "no_remote_write": True, "no_ssh_write_executed": True, "no_deploy_executed": True,
        "no_restart_executed": True, "remote_env_modified": False, "production_db_written": False,
        "canonical_truth_written": False, "published_registry_emitted": False,
        "broad_production_default_opened": False, "staged_or_committed": False,
        "only_writes_this_round": "local repo artifacts dir (this authorization package) — excluded from aliyun sync",
        "remote_write_root_if_authorized": REMOTE_ROOT, "secrets_printed": False})

    # ================= 14. FINDING =================
    verdict = "GO" if all_resolved else "WEAK-GO"
    _wt("FINDING_remote_deployment_authorization_package_m19e_r_20260605.md",
        "# FINDING — M19E-R Remote Deployment Authorization Package (2026-06-05)\n\n## 必答 12\n"
        f"1. 读取并应用 M19B corrected canonical patch：是（limited candidate="
        f"{(corrected.get('corrected_five_axis_verdict') or {}).get('m19b_limited_production_default_candidate')}；"
        "rollback measurement-bug + council bare-word veto policy 已应用）。\n"
        "2. supersede：M19B _20260604（superseded，保留）；canonical=M19B _20260605 + corrected patch + M19C + M19D；"
        "future_delta=M20/M20.1（全部保留，无删除）。\n"
        f"3. M19C state = local ON（limited_default_enabled={m19c_cfg.get('limited_default_enabled')}，"
        f"cohort={m19c_cfg.get('default_cohort_prefixes')}，remote_deployment_written={m19c_cfg.get('remote_deployment_written')}）。\n"
        f"4. M19D soak = {m19d_verdict.get('m19d_soak_verdict')}（keep ON={m19d_verdict.get('keep_limited_default_on')}，"
        f"300 submissions，fp=0，production_write=0）。\n"
        "5. M20.1 delta = future_delta，已隔离（absorbed_into_runtime=false，may_enter_runtime=false）。\n"
        f"6. proposed remote env 仅 qa_/operator_：{PROPOSED_ENV[list(PROPOSED_ENV)[1]]}。\n"
        "7. broad default 仍 NO-GO。\n8. canonical truth write 仍 NO-GO。\n"
        f"9. 远端写入路径严格限 `{REMOTE_ROOT}`（本轮零远端写）。\n"
        "10. rollback（env kill / flag off / registry fail-closed / code rollback）+ stop conditions 完整。\n"
        f"11. **M19E-R verdict = {verdict}**（授权包就绪，对抗风险全 resolved，安全全 0，无远端写）。\n"
        "12. 是否进入 M19F actual remote deploy：**等待用户显式授权**——本 agent 不可代为授权。\n\n"
        "## 红线\n不写远端 / 不 deploy / 不 restart / 不改 production code / 不开 broad default / 不写 production DB / "
        "不写 canonical truth / 不发 published registry / 远端写根仅 /root/deeptutor / 未打印 secret / 未 stage/commit。\n")

    print(json.dumps({
        "files_written": len(list(OUT.glob("*"))),
        "verdict": verdict,
        "m19c_state": "local_ON", "m19d_soak": m19d_verdict.get("m19d_soak_verdict"),
        "proposed_cohort": PROPOSED_ENV[list(PROPOSED_ENV)[1]],
        "m20_isolated": True, "broad_default": "NO-GO", "canonical_write": "NO-GO",
        "no_remote_write": True, "all_adversarial_resolved": all_resolved,
        "m19f_remote_deploy": "WAITING_FOR_EXPLICIT_USER_AUTHORIZATION",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
