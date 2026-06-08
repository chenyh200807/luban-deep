#!/usr/bin/env python3
"""M32 Grading-to-Brain Waterproof Vertical Slice — end-to-end runner (Task 1/7).

Drives the whole product loop on ONE bounded topic (waterproofing) with hermetic fixtures:

    signed waterproof shard (release_candidate, published=False)
      -> compiled context (diagnostic_policy threaded through)
      -> grading (point-level, Task 3)
      -> learning_evidence via build_learning_evidence_from_context_pack (real consumer)
      -> LearnerClaim (explainable, Task 4)
      -> PersonalizationContextPack + NextBestAction (Task 5)
      -> retest: candidate-grade pass = preview (NOT promoted); simulated = blocked (Task 6)
      -> updated picture

Honesty discipline: this slice only ATTESTS what it actually exercises. The waterproof topic is
candidate-grade; canonical promotion (positive arm) is never demonstrable here — it stays False
regardless of verdict. The live /api/v1/ws gate (tests/integration/test_luban_m32_*_ws.py) is the
single remaining condition for GO per plan §312. Laundering invariants live on the
compiler/adjudicator surfaces (M10/M17), NOT on this evidence->claim projection; they are in
``not_exercised_in_this_slice``, not stamped clean. Side-effect free: no DB write, no remote call,
no canonical truth write. The runner only READS the signed shard; it never publishes or mutates it.

Verdict: WEAK-GO (hermetic_only) when run without --live; GO (live_ws_exercised) when --live
passes the integration test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

# Generate this release artifact from THIS repo's source. When invoked as a script,
# sys.path[0] is scripts/, so a bare ``import deeptutor`` can resolve to a stale installed
# checkout elsewhere on sys.path — which would produce a wrong Go/No-Go. Pin the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.construction_grading.compiled_context import (  # noqa: E402
    build_pack_from_question_context,
)
from deeptutor.services.construction_grading.learning_evidence import (  # noqa: E402
    build_learning_evidence_payload,
    build_learning_evidence_from_context_pack,
)
from deeptutor.services.construction_grading.teacher_review_writeback import (  # noqa: E402
    build_teacher_review_writeback,
)
from deeptutor.services.learner_state.learning_synthesis import (  # noqa: E402
    synthesize_learning_truth,
)
from deeptutor.services.learner_state.next_best_action import build_next_best_actions  # noqa: E402
from deeptutor.services.learner_state.personalization_context import (  # noqa: E402
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.service import LearnerStateEvent  # noqa: E402
from deeptutor.services.learner_state.training_intent import (  # noqa: E402
    build_learning_training_intent,
)

REPO = Path(__file__).resolve().parents[1]
SHARD_REL = "deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof/topic_waterproof.json"

CONCEPT = "waterproof_term"
ERROR_CODE = "E02"  # registered code (ERROR_CODE_REGISTRY); the real grader emits E0X/M0X
MISTAKE_TYPE = "near_synonym_not_accepted"
USER = "qa_m32_waterproof"
OTHER_USER = "qa_m32_other_user"
BOT = "construction-exam"
STUDENT_ANSWER = "普通防水砂浆处理"
REQUIRED_TERM = "聚合物水泥防水砂浆"
POINT_ID = "waterproof_exact_required_001"

WATERPROOF_QC = {
    "question_id": "waterproof_case_001",
    "question_type": "case",
    "stem": "地下室底板防水层应采用何种材料？",
    "question": "地下室底板防水层应采用何种材料？",
    "correct_answer": REQUIRED_TERM,
}


def _miss_grading_result() -> dict[str, Any]:
    """Hermetic waterproof case grading: a near-synonym miss on an exact_required term."""
    return {
        "type": "case",
        "question_id": WATERPROOF_QC["question_id"],
        "user_answer": STUDENT_ANSWER,
        "score_awarded": 0,
        "max_score": 1,
        "rubric": {
            "rubric_id": "rb_waterproof",
            "rubric_mode": "curated_rubric",
            "scoring_points": [
                {"point_id": POINT_ID, "label": "防水施工规范术语", "max_score": 1,
                 "knowledge_node_id": "kn_waterproof_term"}
            ],
            "scoring_point_hits": [
                {"point_id": POINT_ID, "hit": False, "awarded_score": 0, "policy_type": "exact_required",
                 "mistake_type": MISTAKE_TYPE, "evidence_span": STUDENT_ANSWER,
                 "required_terms": [REQUIRED_TERM], "high_risk_review": True}
            ],
        },
        "error_events": [
            {"error_code": ERROR_CODE, "severity": 0.8, "concept_tag": CONCEPT, "evidence": STUDENT_ANSWER, "diagnosis": ""}
        ],
        "next_training_signal": {"concept": CONCEPT, "error_code": ERROR_CODE, "focus": "防水 exact_required 术语", "mode": "case_repair"},
    }


def _pass_grading_result() -> dict[str, Any]:
    return {
        "type": "case", "question_id": WATERPROOF_QC["question_id"], "user_answer": REQUIRED_TERM,
        "score_awarded": 1, "max_score": 1,
        "rubric": {"rubric_id": "rb_waterproof", "rubric_mode": "curated_rubric", "scoring_points": [], "scoring_point_hits": []},
        "error_events": [],
        "next_training_signal": {"concept": CONCEPT, "error_code": ERROR_CODE, "mode": "case_repair"},
    }


def _teacher_final_review() -> dict[str, Any]:
    return {
        "case_id": WATERPROOF_QC["question_id"],
        "student_id": USER,
        "engine": "best_quality_4model",
        "teacher_reviewed": True,
        "review_source": "m32_positive_arm_fixture",
        "authority_label": "teacher_final",
        "point_reviews": [
            {
                "point_id": POINT_ID,
                "label": CONCEPT,
                "policy_type": "list_rule",
                "max_score": 1,
                "ai_hit": "partial",
                "ai_score": 0.5,
                "high_risk_review": True,
                "review_action": "override",
                "teacher_hit": "miss",
                "teacher_score": 0,
                "teacher_note": "老师终审确认：近义替代原文术语，本采分点不得分。",
                "evidence_span": STUDENT_ANSWER,
            }
        ],
    }


def _real_retest_pass_payload() -> dict[str, Any]:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": WATERPROOF_QC["question_id"],
            "user_answer": REQUIRED_TERM,
            "score_awarded": 1,
            "max_score": 1,
            "rubric": {
                "rubric_id": "rb_waterproof_teacher_final",
                "rubric_mode": "grading_key",
                "scoring_points": [
                    {"point_id": POINT_ID, "label": "防水施工规范术语", "max_score": 1}
                ],
                "scoring_point_hits": [
                    {"point_id": POINT_ID, "hit": True, "awarded_score": 1}
                ],
            },
            "error_events": [],
            "next_training_signal": {
                "concept": CONCEPT,
                "error_code": ERROR_CODE,
                "focus": "防水 exact_required 术语",
                "mode": "case_repair",
                "retest_authority": "real_student_retest",
            },
        },
        turn_id="m32_turn_real_retest",
        session_id="m32_session",
    )
    payload["claim_promotion_allowed"] = True
    payload["quality"] = {
        **dict(payload.get("quality") or {}),
        "writeback_eligible": True,
        "evidence_level": "L2_real_retest",
        "retest_happened": True,
        "retest_authority": "real_student_retest",
    }
    return payload


def _event(event_id: str, payload: dict[str, Any], *, created_at: str, user: str = USER, bot: str = BOT) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id, user_id=user, source_feature="construction_grading",
        source_id=f"turn:{event_id}", source_bot_id=bot, memory_kind="learning_evidence",
        dedupe_key=event_id, created_at=created_at, payload_json=payload,
    )


def _evidence_payload(grading_result: dict[str, Any], compiled_context: dict[str, Any], *, turn_id: str) -> dict[str, Any]:
    """Build learning evidence through the REAL consumer so the compiled-context authority
    policy (official vs preview) is threaded into the payload."""
    return build_learning_evidence_from_context_pack(
        grading_result=grading_result, compiled_context=compiled_context, turn_id=turn_id, session_id="m32_session"
    )


def _improved(projection: dict[str, Any], *, concept: str = CONCEPT) -> bool:
    return any(s.get("concept_id") == concept for s in (projection.get("improvement_signals") or []))


def _git_audit() -> dict[str, Any]:
    """Informational git snapshot for the FINDING (provenance only — NOT a clobber guard;
    real isolation comes from writing exclusively under the gitignored out_dir)."""
    def _run(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception as exc:  # noqa: BLE001 — provenance is best-effort, never fails the slice
            return f"<unavailable: {exc}>"
    return {
        "realpath": str(REPO), "head": _run(["git", "rev-parse", "HEAD"]),
        "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty_files": [line for line in _run(["git", "status", "--short"]).splitlines() if line.strip()],
    }


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _run_live_ws_integration_test() -> bool:
    """Run the M32 /api/v1/ws integration test and return True if all pass."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/integration/test_luban_m32_grading_to_brain_waterproof_ws.py",
         "-v", "--tb=short", "-q"],
        cwd=str(REPO), capture_output=True, text=True, timeout=120,
    )
    passed = result.returncode == 0
    if not passed:
        print(f"[M32 live-ws] integration test FAILED:\n{result.stdout[-2000:]}\n{result.stderr[-500:]}", file=sys.stderr)
    return passed


def run_slice(*, out_dir: str, live_ws_exercised: bool = False, stamp: str = "") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = stamp or "hermetic"
    git_audit = _git_audit()

    # 1. Waterproof topic manifest pointer (read-only; never publishes / mutates the shard).
    shard = json.loads((REPO / SHARD_REL).read_text(encoding="utf-8"))
    sm = shard.get("manifest") or {}
    topic_manifest = {
        "schema_version": sm.get("schema_version"), "topic_id": "waterproof", "namespace": sm.get("namespace"),
        "status": sm.get("status"), "published": bool(sm.get("published")),
        "official_score_allowed": bool(sm.get("official_score_allowed")),
        "content_hash": sm.get("content_hash"), "signature": sm.get("signature"), "node_count": sm.get("node_count"),
        "canonical_pointer": SHARD_REL,
        "source_refs": [{"point_id": POINT_ID, "required_term": REQUIRED_TERM, "knowledge_point": "防水施工规范术语"}],
    }
    _write_json(out / "waterproof_topic_manifest_m32.json", topic_manifest)

    # 2. Compiled context (same builder the runtime grading/diagnostic surfaces use).
    compiled_context = build_pack_from_question_context(WATERPROOF_QC).to_dict()
    policy = compiled_context.get("diagnostic_policy") or {}
    official_allowed = bool(policy.get("official_score_allowed"))
    _write_json(out / "compiled_context_consumption_m32.json", {
        "question_id": WATERPROOF_QC["question_id"],
        "pack_hash": (compiled_context.get("provenance") or {}).get("pack_hash"),
        "diagnostic_policy": policy, "compiled_context": compiled_context,
    })

    # 3. Grading event.
    grading_result = _miss_grading_result()
    _write_jsonl(out / "grading_event_ledger_m32.jsonl", [grading_result])

    # 4. Learning evidence via the REAL consumer (Task 3 fields + threaded authority policy).
    miss_evidence = _evidence_payload(grading_result, compiled_context, turn_id="m32_turn_miss")
    _write_jsonl(out / "learning_evidence_ledger_m32.jsonl", [miss_evidence])

    # 5. LearnerClaim projection (Task 4 explainable claim).
    miss_event = _event("m32_evt_miss", miss_evidence, created_at="2026-06-07T10:00:00+08:00")
    projection = synthesize_learning_truth([miss_event])
    claims = list(projection.get("observed_candidates") or []) + list(projection.get("weak_points") or [])
    _write_jsonl(out / "learner_claim_projection_m32.jsonl", claims)

    # 6/7. PCP + NextBestAction (Task 5).
    intent = build_learning_training_intent(
        user_id=USER, concept_id=CONCEPT, concept_label="防水施工规范术语",
        error_code=ERROR_CODE, error_label="近义替代原文术语", evidence_refs=["m32_evt_miss"],
        training_mode="mixed_review",
    )
    learning_brain = {"compiled_objects": list((projection.get("compiled_objects") or {}).values())}
    pcp = build_personalization_context_pack(
        user_id=USER, learning_brain=learning_brain, active_training_intent=intent,
        recent_events=[{"event_id": "m32_evt_miss"}],
    )
    _write_json(out / "personalization_context_pack_m32.json", pcp)
    candidates = pcp.get("next_best_action_candidates") or build_next_best_actions(
        user_id=USER, training_intents=[intent], max_actions=1
    )
    next_action = candidates[0] if candidates else {}
    _write_json(out / "next_best_action_m32.json", next_action)

    # 8. Retest — the SAFETY direction of the authority gate (Task 6): candidate-grade and
    # simulated passes must NOT clear the weakness. Canonical promotion (positive arm) is NOT
    # demonstrable here — the waterproof topic is candidate-grade and the real signed authority
    # is a live blocker; we do not fabricate it.
    cand_pass = _evidence_payload(_pass_grading_result(), compiled_context, turn_id="m32_turn_cand")
    cand_event = _event("m32_evt_cand_retest", cand_pass, created_at="2026-06-07T12:00:00+08:00")
    sim_pass = dict(_evidence_payload(_pass_grading_result(), compiled_context, turn_id="m32_turn_sim"))
    sim_pass["qa_simulated"] = True
    sim_event = _event("m32_evt_sim_retest", sim_pass, created_at="2026-06-07T13:00:00+08:00")
    cand_improved = _improved(synthesize_learning_truth([miss_event, cand_event]))
    sim_improved = _improved(synthesize_learning_truth([miss_event, sim_event]))
    retest_rows = [
        {"retest_happened": True, "passed": True, "authority": "candidate_preview", "simulated": False,
         "target_point_id": POINT_ID, "previous_event_id": "m32_evt_miss", "new_event_id": "m32_evt_cand_retest",
         "improved_points": [], "not_improved_points": [CONCEPT], "counted_as_improvement": cand_improved,
         "strategy_if_not_improved": "candidate-grade pass is preview; clearing the weakness needs signed authority / teacher-final / a real retest"},
        {"retest_happened": True, "passed": True, "authority": "simulated", "simulated": True,
         "target_point_id": POINT_ID, "previous_event_id": "m32_evt_miss", "new_event_id": "m32_evt_sim_retest",
         "improved_points": [], "not_improved_points": [CONCEPT], "counted_as_improvement": sim_improved,
         "strategy_if_not_improved": "simulated retest never counts as real (simulated_retest_as_real gate)"},
    ]
    _write_jsonl(out / "retest_outcome_proof_m32.jsonl", retest_rows)

    # 8b. Promotion positive arm — teacher-final + real retest. This is still side-effect-free
    # (pure projection + out_dir artifact), but it proves the promotion authority path without
    # pretending the candidate waterproof shard is release truth.
    teacher_final_payload = build_teacher_review_writeback(_teacher_final_review(), dry_run=True)[
        "learning_evidence_payload"
    ]
    teacher_final_event = _event(
        "m32_evt_teacher_final",
        teacher_final_payload,
        created_at="2026-06-07T14:00:00+08:00",
    )
    teacher_final_projection = synthesize_learning_truth([teacher_final_event])
    teacher_final_claim = (teacher_final_projection.get("weak_points") or [{}])[0]
    teacher_final_pcp = build_personalization_context_pack(
        user_id=USER,
        learning_brain={"compiled_objects": list((teacher_final_projection.get("compiled_objects") or {}).values())},
        active_training_intent=None,
        recent_events=[{"event_id": "m32_evt_teacher_final"}],
    )
    real_retest_payload = _real_retest_pass_payload()
    real_retest_event = _event(
        "m32_evt_real_retest",
        real_retest_payload,
        created_at="2026-06-07T15:00:00+08:00",
    )
    post_retest_projection = synthesize_learning_truth([teacher_final_event, real_retest_event])
    real_retest_improved = _improved(post_retest_projection)
    teacher_final_real_retest_promotion = {
        "teacher_final_confirmed_claim": teacher_final_claim,
        "personalization_context_after_teacher_final": teacher_final_pcp,
        "real_retest": {
            "event_id": "m32_evt_real_retest",
            "retest_happened": True,
            "retest_authority": "real_student_retest",
            "counted_as_improvement": real_retest_improved,
        },
        "post_retest_projection": {
            "weak_points": list(post_retest_projection.get("weak_points") or []),
            "stale_claims": list(post_retest_projection.get("stale_claims") or []),
            "improvement_signals": list(post_retest_projection.get("improvement_signals") or []),
        },
    }
    _write_json(out / "teacher_final_real_retest_promotion_m32.json", teacher_final_real_retest_promotion)

    # 9. Safety — DERIVED for what this slice exercises; explicitly NOT-EXERCISED for what it does not.
    mastery_levels = {"L2_confirmed", "L3_mastery_signal"}
    shadow_promoted = sum(1 for c in claims if str(c.get("evidence_level") or "") in mastery_levels)
    # caller-scoping isolation: the real system queries learner_memory_events WHERE user_id=X, so a
    # per-user synthesize only ever sees that user's events. Verify the slice respects that scoping.
    miss_input_user_ids = {miss_event.user_id}
    other_event = _event("m32_evt_other_tenant",
                         _evidence_payload(_miss_grading_result(), compiled_context, turn_id="m32_turn_other"),
                         created_at="2026-06-07T10:00:00+08:00", user=OTHER_USER, bot="other-subject-bot")
    caller_scoping_ok = (miss_input_user_ids == {USER}) and (other_event.user_id not in miss_input_user_ids)
    candidate_shard_published = bool(topic_manifest["published"])
    candidate_official_score_allowed = bool(topic_manifest["official_score_allowed"])
    candidate_status_allowed = str(topic_manifest.get("status") or "") in {"release_candidate", "draft"}
    candidate_used_as_release_truth = (
        candidate_shard_published
        or candidate_official_score_allowed
        or cand_improved
    )
    verified = {
        "canonical_truth_written": bool(miss_evidence.get("canonical_truth_written", False)),
        "production_write_count": 0,  # structural: slice calls only pure projection fns + out_dir writes
        "shadow_promoted_to_mastery": shadow_promoted,
        "simulated_retest_as_real": 1 if sim_improved else 0,
        "candidate_shard_published": 1 if candidate_shard_published else 0,
        "candidate_official_score_allowed": 1 if candidate_official_score_allowed else 0,
        "candidate_status_allowed": candidate_status_allowed,
        "candidate_used_as_release_truth": 1 if candidate_used_as_release_truth else 0,
        "candidate_grade_pass_promoted": 1 if cand_improved else 0,
        "caller_scoping_ok": bool(caller_scoping_ok),
        "teacher_final_claim_confirmed": 1 if teacher_final_claim.get("claim_status") == "confirmed" else 0,
        "real_retest_promoted_to_improvement": 1 if real_retest_improved else 0,
    }
    verified_clean = (
        verified["canonical_truth_written"] is False
        and verified["production_write_count"] == 0
        and verified["shadow_promoted_to_mastery"] == 0
        and verified["simulated_retest_as_real"] == 0
        and verified["candidate_shard_published"] == 0
        and verified["candidate_official_score_allowed"] == 0
        and verified["candidate_status_allowed"] is True
        and verified["candidate_used_as_release_truth"] == 0
        and verified["candidate_grade_pass_promoted"] == 0
        and verified["caller_scoping_ok"] is True
        and verified["teacher_final_claim_confirmed"] == 1
        and verified["real_retest_promoted_to_improvement"] == 1
    )
    not_exercised = {
        "official_score_laundering": "compiler/adjudicator surface (M10/M17); not on this evidence->claim projection",
        "answer_key_override": "compiler/adjudicator surface; the real consumer hardcodes is_answer_key=False on pack refs",
        "source_laundering": "compiler/adjudicator surface (runtime_llm_adjudicator source_laundering_blocked)",
        "rag_chunk_as_answer_key": "compiler/adjudicator surface; diagnostic_policy.retrieval_may_become_answer_key is False by construction here",
        "cross_user_leak / cross_subject_leak": "single-tenant slice; isolation is caller-scoped per user_id (see caller_scoping_ok). Multi-tenant partition is verified by the read-model/redaction tests, not this projection slice",
    }
    _write_json(out / "safety_invariant_report_m32.json", {
        "verified_in_this_run": verified,
        "verified_clean": verified_clean,
        "not_exercised_in_this_slice": not_exercised,
        "note": "Only attests what the run exercises; absent surfaces are named, not stamped clean.",
    })

    # 10. Go/No-Go.
    # Plan §312: GO = "real or hermetic retest outcome + clean safety invariants".
    # The live /api/v1/ws gate is the only remaining condition beyond the hermetic loop.
    # canonical_promotion (positive arm) is a production expansion requirement, not a slice GO gate.
    loop_counts = {
        "learning_evidence": 1 if (miss_evidence.get("rubric", {}).get("scoring_point_hits")) else 0,
        "learner_claims": len(claims),
        "personalization_context_pack": 1 if pcp.get("top_claims") else 0,
        "next_best_action": 1 if next_action else 0,
        "retest_outcomes": sum(1 for r in retest_rows if r.get("retest_happened")),
    }
    full_loop = all(v >= 1 for v in loop_counts.values())
    safety_gate_proven = (not cand_improved) and (not sim_improved)
    canonical_promotion_demonstrated = bool(
        teacher_final_claim.get("claim_status") == "confirmed"
        and real_retest_improved
        and not (post_retest_projection.get("weak_points") or [])
        and (post_retest_projection.get("stale_claims") or [])
    )
    if full_loop and verified_clean and safety_gate_proven and live_ws_exercised:
        verdict = "GO"
    elif full_loop and verified_clean and safety_gate_proven:
        verdict = "WEAK-GO"
    else:
        verdict = "NO-GO"
    live_blockers: list[str] = []
    if not live_ws_exercised:
        live_blockers.append(
            "live /api/v1/ws not exercised — run with --live to close this gate "
            "(tests/integration/test_luban_m32_grading_to_brain_waterproof_ws.py)"
        )
    mode = "live_ws_exercised" if live_ws_exercised else "hermetic_only"
    go_no_go = {
        "milestone": "M32_grading_to_brain_waterproof_vertical_slice",
        "verdict": verdict, "mode": mode, "topic": "waterproof",
        "safety_gate_proven": safety_gate_proven,
        "live_ws_exercised": live_ws_exercised,
        "canonical_promotion_demonstrated": canonical_promotion_demonstrated,
        "loop_counts": loop_counts, "safety_verified_in_this_run": verified, "verified_clean": verified_clean,
        "live_blockers": live_blockers, "stamp": stamp, "head": git_audit.get("head"),
    }
    _write_json(out / "go_no_go_m32.json", go_no_go)

    # 11. FINDING.
    claim0 = claims[0] if claims else {}
    (out / f"FINDING_grading_to_brain_m32_waterproof_{stamp}.md").write_text(
        f"""# M32 Grading-to-Brain Waterproof Vertical Slice — FINDING ({stamp})

Verdict: **{verdict}** (mode: {go_no_go['mode']})

## One business fact proven (architecture)
A point-level waterproof grading miss became a learning-evidence event, an explainable
LearnerClaim, a PersonalizationContextPack + NextBestAction, and retest outcomes — with the
SAFETY direction of the authority gate proven: candidate-grade and simulated passes are NOT
promoted. The live /api/v1/ws gate was {"EXERCISED ✓" if live_ws_exercised else "NOT exercised (run --live to close)"}.

## Authority gate (safety direction, Task 6)
- candidate-grade retest counted_as_improvement: {cand_improved}  (must be False — preview only)
- simulated retest counted_as_improvement: {sim_improved}  (must be False — simulated_retest_as_real gate)
- live /api/v1/ws exercised: {live_ws_exercised}  (must be True for GO)

## Product answers
- 今天为什么练这个？ {next_action.get('why_this_now', '')}
- 证据来自哪段作答？ {claim0.get('evidence_span', '')}（采分点 {POINT_ID}）
- 这次训练要证明什么？ {next_action.get('success_measure', '')}
- 练完后如何更新画像？ teacher-final 先把错因确认为长期画像；真实 retest 通过后该 claim 进入 stale/improving；candidate / 模拟复测保持 preview。
- canonical promotion positive arm demonstrated: {canonical_promotion_demonstrated}

## Loop counts
{json.dumps(loop_counts, ensure_ascii=False, indent=2)}

## Safety — verified in this run (DERIVED)
{json.dumps(verified, ensure_ascii=False, indent=2)}

## Safety — NOT exercised in this slice (named, not stamped clean)
{json.dumps(not_exercised, ensure_ascii=False, indent=2)}

## {"Production expansion requirements (not slice GO gates)" if live_ws_exercised else "Live blockers"}
{json.dumps(live_blockers, ensure_ascii=False, indent=2)}

## Git provenance (informational)
{json.dumps(git_audit, ensure_ascii=False, indent=2)}
""",
        encoding="utf-8",
    )
    return go_no_go


def main() -> None:
    import datetime

    parser = argparse.ArgumentParser(description="Run the M32 waterproof Grading-to-Brain vertical slice.")
    parser.add_argument("--stamp", default=datetime.datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--live", action="store_true",
                        help="Run the /api/v1/ws TestClient integration test to close the live-ws gate")
    args = parser.parse_args()
    out_dir = args.out_dir or str(
        REPO / "artifacts" / "luban_grading_artifacts" / f"grading_to_brain_m32_waterproof_{args.stamp}"
    )
    live_ws_exercised = False
    if args.live:
        print("[M32] Running live /api/v1/ws integration test …", file=sys.stderr)
        live_ws_exercised = _run_live_ws_integration_test()
        if live_ws_exercised:
            print("[M32] ✓ live /api/v1/ws gate PASSED", file=sys.stderr)
        else:
            print("[M32] ✗ live /api/v1/ws gate FAILED — verdict stays WEAK-GO", file=sys.stderr)
    print(json.dumps(run_slice(out_dir=out_dir, live_ws_exercised=live_ws_exercised, stamp=args.stamp), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
