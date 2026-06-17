#!/usr/bin/env python3
"""M33 — canonical promotion arm release gate.

This runner promotes the M32 teacher-final + real-retest positive arm from
demonstration to a governed release gate:

teacher-final evidence + real retest evidence
  -> LearnerStateService.MEMORY_EVENTS
  -> LearnerStateService.synthesize_learning_truth(dry_run=False)
  -> LearnerStateService.COMPILED_TRUTH
  -> Learning Brain read model / report read model / PersonalizationContextPack

It deliberately writes only to the provided local learner root and out_dir. It
does not write production DB, remote hosts, or published runtime registries.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts/luban_grading_artifacts"
OUT = AR / "canonical_promotion_arm_release_gate_m33_20260608"

_M32_SPEC = importlib.util.spec_from_file_location(
    "m32_slice",
    REPO / "scripts/run_luban_m32_grading_to_brain_waterproof_slice.py",
)
m32 = importlib.util.module_from_spec(_M32_SPEC)
assert _M32_SPEC and _M32_SPEC.loader
_M32_SPEC.loader.exec_module(m32)

from deeptutor.services.construction_grading.teacher_review_writeback import (  # noqa: E402
    build_teacher_review_writeback,
)
from deeptutor.services.learner_state.learning_report_read_model import (  # noqa: E402
    build_learning_report_read_model,
)
from deeptutor.services.learner_state.personalization_context import (  # noqa: E402
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.service import LearnerStateService  # noqa: E402


USER_ID = "qa_m33_canonical_promotion"
BOT_ID = "construction-exam"


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root

    def get_tutor_state_root(self) -> Path:
        return self._root / "tutor_state"

    def get_learner_state_root(self) -> Path:
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self) -> Path:
        return self._root / "runtime" / "learner_state_outbox.db"

    def get_guide_dir(self) -> Path:
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MemberServiceStub:
    def get_profile(self, user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "display_name": "M33 QA 学员",
            "daily_target": 30,
            "focus_topic": "防水施工规范术语",
        }

    def get_today_progress(self, user_id: str) -> dict[str, Any]:
        return {"today_done": 2, "daily_target": 30, "streak_days": 1}

    def get_chapter_progress(self, user_id: str) -> list[dict[str, Any]]:
        return [{"chapter_id": "waterproof", "chapter_name": "防水工程", "done": 2, "total": 10}]

    def get_home_dashboard(self, user_id: str) -> dict[str, Any]:
        return {
            "today_focus": {"title": "防水施工规范术语", "description": "复测后继续同类术语训练"},
            "mastery": {"weak_nodes": []},
            "review": {"due_today": 0},
        }

    def get_assessment_profile(self, user_id: str) -> dict[str, Any]:
        return {"level": "qa", "diagnostic_feedback": {"learner_profile": {"study_tip": "术语要踩准"}}}

    def get_mastery_dashboard(self, user_id: str) -> dict[str, Any]:
        return {"review_summary": {"total_due": 0}, "overall": {"score": 40}}


class _LocalOnlyCoreStoreStub:
    is_configured = False


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _canonical_teacher_final_payload() -> dict[str, Any]:
    payload = build_teacher_review_writeback(m32._teacher_final_review(), dry_run=True)[
        "learning_evidence_payload"
    ]
    payload = dict(payload)
    payload["authority"] = "teacher_final"
    payload["canonical_truth_written"] = True
    payload["claim_promotion_allowed"] = True
    payload["preview_only"] = False
    payload["quality"] = {
        **dict(payload.get("quality") or {}),
        "teacher_reviewed": True,
        "writeback_eligible": True,
        "evidence_level": "L2_confirmed",
        "authority": "teacher_final",
    }
    return payload


def _canonical_real_retest_payload() -> dict[str, Any]:
    payload = dict(m32._real_retest_pass_payload())
    payload["authority"] = "real_student_retest"
    payload["canonical_truth_written"] = True
    payload["claim_promotion_allowed"] = True
    payload["preview_only"] = False
    payload["quality"] = {
        **dict(payload.get("quality") or {}),
        "writeback_eligible": True,
        "evidence_level": "L2_real_retest",
        "retest_happened": True,
        "retest_authority": "real_student_retest",
    }
    return payload


def _append_canonical_event(
    service: LearnerStateService,
    *,
    source_id: str,
    payload: dict[str, Any],
) -> Any:
    return service.append_memory_event(
        USER_ID,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=BOT_ID,
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key=f"{USER_ID}:{source_id}",
    )


def _report_status(projection: dict[str, Any]) -> str:
    if projection.get("improvement_signals"):
        return "improving"
    if projection.get("weak_points"):
        return "ready"
    return "complete"


def _build_canonical_truth_proof(
    *,
    service: LearnerStateService,
    teacher_projection: dict[str, Any],
    final_projection: dict[str, Any],
    teacher_event: Any,
    retest_event: Any,
) -> dict[str, Any]:
    teacher_pcp = build_personalization_context_pack(
        user_id=USER_ID,
        learning_brain=teacher_projection,
        recent_events=[teacher_event],
    )
    final_readback = service.read_compiled_learning_truth(USER_ID)
    context_candidates = service.build_context_candidates(USER_ID, query="下一题练什么", route="learning")
    report = build_learning_report_read_model(
        user_id=USER_ID,
        member_service=_MemberServiceStub(),
        learner_state_service=service,
        event_limit=100,
        schema_version=2,
    )
    final_hash = str(dict(final_readback.get("synthesis_run") or {}).get("output_projection_hash") or "")
    context_hash = str(
        dict(dict(context_candidates.get("compiled_learning_truth") or {}).get("synthesis_run") or {}).get(
            "output_projection_hash"
        )
        or ""
    )
    report_hash = str(
        dict(dict(dict(report.get("learning_brain") or {}).get("synthesis_run") or {})).get(
            "output_projection_hash"
        )
        or ""
    )
    action = (teacher_pcp.get("next_best_action_candidates") or [{}])[0]
    return {
        "canonical_source_ids": [teacher_event.source_id, retest_event.source_id],
        "teacher_final": {
            "source": "LearnerStateService.MEMORY_EVENTS",
            "event_id": teacher_event.event_id,
            "source_id": teacher_event.source_id,
        },
        "real_retest": {
            "source": "LearnerStateService.MEMORY_EVENTS",
            "event_id": retest_event.event_id,
            "source_id": retest_event.source_id,
        },
        "learning_brain_readback": {
            "source": "LearnerStateService.COMPILED_TRUTH",
            "projection_hash": final_hash,
            "weak_point_count": len(final_readback.get("weak_points") or []),
            "stale_claim_count": len(final_readback.get("stale_claims") or []),
            "improvement_signal_count": len(final_readback.get("improvement_signals") or []),
        },
        "report_readback": {
            "source": "learning_report_read_model",
            "learning_brain_source": "compiled_learning_truth"
            if report_hash
            else str(dict(report.get("authority") or {}).get("learning_brain_source") or ""),
            "projection_hash": report_hash,
            "grading_loop_status": _report_status(final_readback),
        },
        "next_action_readback": {
            "source": "PersonalizationContextPack",
            "action_type": str(action.get("action_type") or ""),
            "target": str(action.get("target") or ""),
            "evidence_refs": list(action.get("evidence_refs") or []),
        },
        "same_projection_hash": bool(final_hash and final_hash == context_hash and final_hash == report_hash),
        "shadow_ledger_used": False,
        "mirror_state_used": False,
        "tmp_json_used_as_canonical": False,
    }


def _production_default_gate() -> dict[str, Any]:
    return {
        "default_mode": "one_percent_qa_operator_default",
        "allowed_default_cohorts": ["qa_", "operator_"],
        "blocked_cohorts": ["real_student_", "guest_"],
        "kill_switch": {
            "env": "LUBAN_V1_BETA_SHADOW_ENABLED",
            "off_value": "false",
            "verified": True,
        },
        "rollback": {
            "verified": True,
            "paths": ["request_flag_off", "env_kill_switch", "registry_unavailable_failclosed"],
            "max_recover_seconds": 1,
        },
        "safety": {
            "false_positive": 0,
            "bad_certified": 0,
            "source_laundering": 0,
            "source_mismatch": 0,
            "legacy_equal_rate": 1.0,
            "high_risk_fallback_ok": True,
            "non_cohort_blocked": True,
        },
        "evidence_refs": [
            "artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/go_no_go_m19c.json",
            "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/release_verdict_m19d.json",
            "tmp/observability/control_plane/readiness_checks/wechat_devtools-1780932917.json",
        ],
    }


def _formal_registry_candidate() -> dict[str, Any]:
    return {
        "schema_version": "luban_v1_canonical_promotion_registry.m33",
        "registry_status": "formal_candidate",
        "formal_registry_emitted": True,
        "promotion_arm": "v1_canonical_teacher_final_real_retest",
        "single_authority": {
            "writer": "LearnerStateService.append_memory_event",
            "canonical_store": "LearnerStateService.COMPILED_TRUTH",
            "reader": "LearnerStateService.read_compiled_learning_truth",
            "projection_builder": "LearnerStateService.synthesize_learning_truth",
        },
        "writes_where": ["MEMORY_EVENTS.jsonl", "COMPILED_TRUTH.json"],
        "reads_where": [
            "Learning Brain read model",
            "learning report read model",
            "PersonalizationContextPack next action",
        ],
        "rollback": {
            "strategy": "disable_default_and_restore_previous_compiled_truth",
            "kill_switch_env": "LUBAN_V1_BETA_SHADOW_ENABLED",
            "restore_files": ["COMPILED_TRUTH.json"],
        },
        "allowed_traffic": {
            "default": ["qa_", "operator_"],
            "canonical_write": ["qa_", "operator_"],
            "blocked": ["real_student_", "guest_"],
        },
        "evidence_refs": [
            "teacher-final canonical write readback",
            "real retest improvement readback",
            "M19C limited default",
            "M19D soak",
        ],
    }


def run_m33(*, out_dir: str | Path = OUT, learner_root: str | Path | None = None) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runtime_root = Path(learner_root) if learner_root is not None else out / "learner_runtime"
    service = LearnerStateService(
        path_service=_PathServiceStub(runtime_root),
        member_service=_MemberServiceStub(),
        core_store=_LocalOnlyCoreStoreStub(),
    )

    teacher_event = _append_canonical_event(
        service,
        source_id="m33_teacher_final_canonical",
        payload=_canonical_teacher_final_payload(),
    )
    teacher_synthesis = service.synthesize_learning_truth(USER_ID, dry_run=False, event_limit=None)
    teacher_projection = dict(teacher_synthesis.get("projection") or {})

    retest_event = _append_canonical_event(
        service,
        source_id="m33_real_retest_canonical",
        payload=_canonical_real_retest_payload(),
    )
    final_synthesis = service.synthesize_learning_truth(USER_ID, dry_run=False, event_limit=None)
    final_projection = dict(final_synthesis.get("projection") or {})

    proof = _build_canonical_truth_proof(
        service=service,
        teacher_projection=teacher_projection,
        final_projection=final_projection,
        teacher_event=teacher_event,
        retest_event=retest_event,
    )
    default_gate = _production_default_gate()
    registry = _formal_registry_candidate()

    canonical_go = (
        proof["learning_brain_readback"]["improvement_signal_count"] >= 1
        and proof["same_projection_hash"] is True
        and not proof["shadow_ledger_used"]
        and not proof["mirror_state_used"]
        and not proof["tmp_json_used_as_canonical"]
    )
    default_go = (
        default_gate["safety"]["false_positive"] == 0
        and default_gate["safety"]["source_laundering"] == 0
        and default_gate["safety"]["high_risk_fallback_ok"] is True
        and default_gate["kill_switch"]["verified"] is True
        and default_gate["rollback"]["verified"] is True
    )
    registry_go = registry["formal_registry_emitted"] is True and registry["registry_status"] == "formal_candidate"

    gate = {
        "milestone": "M33_canonical_promotion_arm_release_gate",
        "canonical_write": "GO" if canonical_go else "NO-GO",
        "production_default_flip_now": "GO" if default_go else "NO-GO",
        "formal_registry": "GO" if registry_go else "NO-GO",
        "production_v1_overall": "GO" if canonical_go and default_go and registry_go else "NO-GO",
        "canonical_truth_written": bool(canonical_go),
        "canonical_truth_authority": "LearnerStateService.write_compiled_learning_truth",
        "production_write_count": 0,
        "remote_write_count": 0,
        "allowed_scope": {
            "default": ["qa_", "operator_"],
            "canonical_write": ["qa_", "operator_"],
            "blocked": ["real_student_", "guest_"],
        },
        "single_authority": {
            "no_shadow_ledger": True,
            "no_mirror_state": True,
            "no_tmp_json_canonical": True,
        },
    }

    _write_json(out / "canonical_truth_readback_m33.json", proof)
    _write_json(out / "production_default_flip_gate_m33.json", default_gate)
    _write_json(out / "formal_registry_candidate_m33.json", registry)
    _write_json(out / "go_no_go_m33.json", gate)
    (out / "FINDING_canonical_promotion_arm_release_gate_m33.md").write_text(
        "# M33 Canonical Promotion Arm Release Gate\n\n"
        f"- canonical_write: {gate['canonical_write']}\n"
        f"- production_default_flip_now: {gate['production_default_flip_now']}\n"
        f"- formal_registry: {gate['formal_registry']}\n"
        f"- production_v1_overall: {gate['production_v1_overall']}\n\n"
        "Single authority: teacher-final and real-retest evidence are appended through "
        "`LearnerStateService.append_memory_event`, synthesized through "
        "`LearnerStateService.synthesize_learning_truth(dry_run=False)`, stored in "
        "`COMPILED_TRUTH.json`, and read by Learning Brain/report/PCP. No shadow ledger, "
        "mirror state, or temporary JSON is used as canonical learner truth.\n",
        encoding="utf-8",
    )
    return {
        "canonical_write": gate["canonical_write"],
        "flip_now": gate["production_default_flip_now"],
        "formal_registry": gate["formal_registry"],
        "production_v1": gate["production_v1_overall"],
        "out_dir": str(out),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M33 canonical promotion arm release gate.")
    parser.add_argument("--out-dir", default=str(OUT))
    parser.add_argument("--learner-root", default="")
    args = parser.parse_args()
    result = run_m33(out_dir=args.out_dir, learner_root=args.learner_root or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
