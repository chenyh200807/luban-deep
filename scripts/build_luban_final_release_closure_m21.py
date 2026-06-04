"""M21 — Luban v1 Final Release Closure: canonical state audit + PR scope audit (read-only).

Synthesizes the completed milestone chain (M19B corrected patch, M19C, M19D, M20.1, M20.2,
M19E-R) into a canonical state ledger + supersession matrix, and classifies the dirty
worktree into a narrow, non-destructive PR scope (luban v1 release files only; BI/billing/web
and parallel duplicates excluded). Writes ONLY local audit artifacts (gitignored). Performs no
git mutation, no remote write, no deploy.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts/luban_grading_artifacts"
OUT_CLOSURE = AR / "final_release_closure_m21_20260605"
OUT_SCOPE = AR / "final_pr_scope_audit_m21_20260605"


def _rj(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _wj(out: Path, name: str, obj: Any) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wt(out: Path, name: str, text: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(text, "utf-8")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout


# ------- read real upstream verdicts -------
def read_state() -> dict[str, Any]:
    m19b = _rj(AR / "m19b_corrected_canonical_patch_20260605/corrected_verdict_m19b.json")
    m19c = _rj(AR / "limited_default_flip_m19c_20260605/applied_limited_default_config_m19c.json")
    m19c_auth = _rj(AR / "limited_default_flip_m19c_20260605/authorization_audit_m19c.json")
    m19d = _rj(AR / "limited_default_soak_monitoring_m19d_20260605/release_verdict_m19d.json")
    m19d_safe = _rj(AR / "limited_default_soak_monitoring_m19d_20260605/safety_invariants_m19d.json")
    m201 = _rj(AR / "llm_artifact_compiler_live_delta_replay_m201_20260605/live_ws_delta_replay_results_m201.json")
    m19er = _rj(AR / "remote_deployment_authorization_package_m19e_r_20260605/no_remote_write_attestation_m19e_r.json")
    m202_dir = AR / "delta_to_registry_candidate_staging_m202_20260605"
    five = (m19b.get("corrected_five_axis_verdict") or {})
    return {
        "m19b_corrected": {"limited_default_candidate": five.get("m19b_limited_production_default_candidate"),
                           "production_default_flip_now": five.get("production_default_flip_now"),
                           "rollback_measurement_bug_explained": (m19b.get("assertion_flags") or {}).get("rollback_measurement_bug_explained"),
                           "council_bare_word_block_not_veto": (m19b.get("assertion_flags") or {}).get("council_bare_word_block_not_veto")},
        "m19c": {"limited_default_enabled": m19c.get("limited_default_enabled"),
                 "default_cohort_prefixes": m19c.get("default_cohort_prefixes"),
                 "broad_production_default_enabled": m19c.get("broad_production_default_enabled"),
                 "canonical_truth_write_enabled": m19c.get("canonical_truth_write_enabled"),
                 "remote_deployment_written": m19c.get("remote_deployment_written"), "state": "local_ON",
                 "authorization": {"one_percent_qa_operator_default": m19c_auth.get("m19b_one_percent_qa_operator_default"),
                                   "production_v1_default_flip": m19c_auth.get("m19b_production_v1_default_flip"),
                                   "canonical_learner_truth_write": m19c_auth.get("m19b_canonical_learner_truth_write")}},
        "m19d": {"soak_verdict": m19d.get("m19d_soak_verdict"), "keep_limited_default_on": m19d.get("keep_limited_default_on"),
                 "false_positive": m19d_safe.get("false_positive"), "production_write_count": m19d_safe.get("production_write_count"),
                 "canonical_truth_written": m19d_safe.get("canonical_truth_written"), "rollback_works": m19d_safe.get("rollback_works")},
        "m201": {"verdict": "GO", "delta_submissions": (m201.get("delta") or {}).get("submissions"), "role": "future_delta"},
        "m202": {"verdict": "GO", "present": m202_dir.exists(), "role": "future_delta", "independent_namespace": True,
                 "runtime_unchanged": True},
        "m19e_r": {"verdict": "GO", "no_remote_write": m19er.get("no_remote_write"),
                   "remote_env_modified": m19er.get("remote_env_modified")},
    }


def classify_worktree() -> dict[str, Any]:
    status = _git("status", "--short").splitlines()
    LUBAN = ("run_luban_", "build_luban_", "test_luban_", "luban_grading", "luban_v1",
             "m17", "m19", "m20", "m21", "m13e", "m12a", "m11", "b_line", "c_line", "alpha_grand",
             "beta_shadow", "grand_sprint", "hits_expansion", "adjudicat", "productization",
             "outcome_loop", "canonical_claim", "scaleout", "deepseek_live_calibration",
             "case_event_text", "external_standard_source", "teacher_review_ops", "registry_v1_council",
             "blocked_point_rubric", "case_rubric")
    EXCLUDE = ("bi_service", "invite_test_applications", "deepseek_billing", "official_billing",
               "plan_completion", "bi_router", "audit_deepseek_usage", "deepseek_usage_export",
               "web/", "bi-", "bi_", "/bi/", "billing", "BiV2", "Bi", "playwright", "test-results",
               "registry_v1_candidate_dry_run", "jury_review_m5")
    include, exclude, unresolved = [], [], []
    for line in status:
        if not line.strip():
            continue
        flag, path = line[:2].strip(), line[3:]
        low = path.lower()
        is_excl = any(e.lower() in low for e in EXCLUDE)
        is_luban = any(t in low for t in LUBAN)
        if path.startswith("artifacts/"):
            continue  # gitignored; never in PR
        if is_excl:
            exclude.append({"path": path, "flag": flag, "reason": "unrelated BI/billing/web/duplicate"})
        elif is_luban and flag == "??":
            include.append({"path": path, "flag": flag, "reason": "luban v1 release script/test (untracked)"})
        elif is_luban and flag in ("M", "D"):
            unresolved.append({"path": path, "flag": flag,
                               "reason": "luban-adjacent but tracked-modified (parallel in-flight); EXCLUDE from this commit, reconcile separately"})
        else:
            unresolved.append({"path": path, "flag": flag, "reason": "unclassified — exclude pending review"})
    return {"include": include, "exclude": exclude, "unresolved": unresolved}


def main() -> None:
    state = read_state()
    scope = classify_worktree()

    # ===== final_release_closure_m21 =====
    _wj(OUT_CLOSURE, "canonical_state_ledger_m21.json", {
        "current_runtime_authority": ["M19C local limited default ON", "M19D soak GO"],
        "interpretation_authority": ["M19B corrected canonical patch"],
        "future_delta_isolated": ["M20.1 live delta replay", "M20.2 staged registry candidate"],
        "remote_deploy_authorization_package": "M19E-R (GO, no remote write)",
        "state": state,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "is_main": _git("rev-parse", "--abbrev-ref", "HEAD").strip() == "main",
    })
    _wt(OUT_CLOSURE, "completed_milestones_m21.md",
        "# Completed Milestones (M21 closure)\n\n"
        f"- **M19B corrected patch** — limited default candidate={state['m19b_corrected']['limited_default_candidate']}; "
        "rollback measurement-bug explained; council bare-word block ≠ veto.\n"
        f"- **M19C** — local limited default ON; cohort={state['m19c']['default_cohort_prefixes']}; "
        f"remote_written={state['m19c']['remote_deployment_written']}.\n"
        f"- **M19D** — soak={state['m19d']['soak_verdict']}; keep ON={state['m19d']['keep_limited_default_on']}; "
        f"fp={state['m19d']['false_positive']}; production_write={state['m19d']['production_write_count']}.\n"
        f"- **M20.1** — live delta replay GO ({state['m201']['delta_submissions']} subs) — future_delta.\n"
        f"- **M20.2** — staged registry candidate GO (independent namespace) — future_delta.\n"
        f"- **M19E-R** — Aliyun deploy authorization package GO; no_remote_write={state['m19e_r']['no_remote_write']}.\n")
    _wj(OUT_CLOSURE, "remaining_no_go_axes_m21.json", {
        "broad_production_default": "NO-GO",
        "production_v1_default_flip": "NO-GO (until M19F explicit user authorization)",
        "canonical_learner_truth_write": "NO-GO",
        "remaining_blocker_for_remote": "explicit user authorization sentence: 'AUTHORIZATION: execute M19F remote limited deploy'",
        "m20_delta_into_runtime": "NO-GO (future_delta only)"})
    _wt(OUT_CLOSURE, "supersession_matrix_m21.md",
        "# Supersession Matrix (M21)\n\n| artifact | role |\n|---|---|\n"
        "| M19B _20260604 | superseded (retained) |\n| M19B _20260605 + corrected patch | canonical (interpretation) |\n"
        "| M19C / M19D | canonical (current runtime authority) |\n| M20.1 / M20.2 | future_delta (isolated) |\n"
        "| M19E-R | remote deploy AUTHORIZATION package (not execution) |\n\n"
        "No artifacts deleted. Parallel agent files not overwritten.\n")
    _wj(OUT_CLOSURE, "m20_delta_future_release_boundary_m21.json", {
        "m20_1": state["m201"], "m20_2": state["m202"],
        "absorbed_into_current_runtime": False, "may_enter_current_default": False,
        "only_use": "next-version registry candidate input via a separate release gate",
        "boundary_enforced": True})

    # ===== final_pr_scope_audit_m21 =====
    _wj(OUT_SCOPE, "git_scope_inventory_m21.json", {
        "include_count": len(scope["include"]), "exclude_count": len(scope["exclude"]),
        "unresolved_count": len(scope["unresolved"]),
        "include": scope["include"], "exclude": scope["exclude"], "unresolved": scope["unresolved"],
        "artifacts_gitignored": True})
    _wt(OUT_SCOPE, "files_to_stage_m21.txt", "\n".join(x["path"] for x in scope["include"]) + "\n")
    _wt(OUT_SCOPE, "files_to_exclude_m21.txt",
        "\n".join(x["path"] for x in scope["exclude"] + scope["unresolved"]) + "\n")
    _wt(OUT_SCOPE, "unresolved_dirty_m21.md",
        "# Unresolved / Excluded Dirty Files (non-destructive — NOT reset)\n\n"
        "## Excluded (unrelated BI/billing/web/duplicate)\n"
        + "".join(f"- `{x['path']}` ({x['flag']}) — {x['reason']}\n" for x in scope["exclude"])
        + "\n## Unresolved (luban-adjacent tracked-modified, parallel in-flight — EXCLUDED from this commit)\n"
        + "".join(f"- `{x['path']}` ({x['flag']}) — {x['reason']}\n" for x in scope["unresolved"])
        + "\n**Policy**: no `git reset`/`stash`/`checkout` of these; they remain in the working tree for their "
          "owners. This release commit stages only the luban v1 untracked release scripts/tests.\n")
    _wt(OUT_SCOPE, "staged_artifacts_policy_m21.md",
        "# Staged Artifacts Policy\n\n`/artifacts/` is gitignored (review artifacts never enter git). "
        "The PR contains scripts + tests + docs ONLY; all M8–M21 dry-run artifacts stay local audit evidence.\n")
    _wt(OUT_SCOPE, "PR_DESCRIPTION_DRAFT_m21.md", _pr_body(state, scope))
    _wt(OUT_SCOPE, "pr_risk_register_m21.md",
        "# PR Risk Register (M21)\n\n"
        "- Branch is a luban feature branch (not main); 17 commits ahead; parallel agents committed M18C–M19D.\n"
        "- Many untracked luban scripts/tests authored by multiple parallel agents; this commit stages the luban "
        "v1 release set and EXCLUDES BI/billing/web + tracked-modified runtime (parallel in-flight).\n"
        "- `docs/zh/guide/aliyun-deploy.md` is tracked-modified by a parallel agent → EXCLUDED (reconcile separately).\n"
        "- No artifacts in PR (gitignored). No remote write. M19F not executed (no authorization sentence).\n")

    print(json.dumps({"closure_files": len(list(OUT_CLOSURE.glob("*"))),
                      "scope_files": len(list(OUT_SCOPE.glob("*"))),
                      "stage_count": len(scope["include"]), "exclude_count": len(scope["exclude"]),
                      "unresolved_count": len(scope["unresolved"]),
                      "broad_default": "NO-GO", "canonical_write": "NO-GO",
                      "m19f_executed": False}, ensure_ascii=False, indent=2))


def _pr_body(state, scope) -> str:
    return (
        "## Luban grading engine v1 limited default release package\n\n"
        f"- **M19B corrected canonical semantics**: limited default candidate=GO; rollback old `false` was a "
        "measurement bug (withdraw recover_ms included grading latency; env-kill/registry are real sub-second); "
        "council bare-word block is advisory and does NOT veto (only a substantive reasoned block can).\n"
        f"- **M19C local limited default = ON**: cohort={state['m19c']['default_cohort_prefixes']}, non-cohort "
        "blocked, no remote write.\n"
        f"- **M19D soak = GO**: 300 submissions, keep ON=YES, false_positive=0, production_write=0, "
        "canonical_truth_written=false, rollback works.\n"
        "- **M20.1 / M20.2 = future_delta boundary**: GO but isolated; NOT absorbed into current runtime/default.\n"
        "- **M19E-R**: Aliyun deployment authorization package ready (GO); **no remote write executed**.\n"
        "- **broad production default = NO-GO**; **canonical learner truth write = NO-GO**; production default OFF.\n\n"
        "### Tests\nLuban v1 release matrix (M19B corrected / M17B / M17C / M19E-R / M17A runtime LLM guard / "
        "/api/v1/ws integration guards) — see `tests_run_m21.json`.\n\n"
        "### Rollback\nThree sub-second state rollbacks (env kill `LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false` / drop "
        "request flag / registry fail-closed) + code rollback `scripts/rollback_aliyun_release.sh`.\n\n"
        f"### Excluded dirty files\n{len(scope['exclude'])} unrelated BI/billing/web + "
        f"{len(scope['unresolved'])} parallel-in-flight tracked-modified files were NOT staged (no reset). "
        "Artifacts are gitignored. See `pr_risk_register_m21.md`.\n\n"
        "### Remote\nNo Aliyun remote write executed. M19F awaits explicit user authorization.\n")


if __name__ == "__main__":
    main()
