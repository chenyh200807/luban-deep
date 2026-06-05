from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.best_quality_ai_draft import best_quality_for_golden
from deeptutor.services.construction_grading.question_grading_artifacts import build_question_grading_artifact
from deeptutor.services.construction_grading.teacher_review_writeback import build_teacher_review_writeback
from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent

GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
PILOT_DIR = REPO / "artifacts/luban_consensus_gold/real_answer_teacher_review_pilot_20260604"

PILOT_SAMPLE_SPECS: list[dict[str, Any]] = [
    {
        "case_id": "Q10-1A422000",
        "student_id": "S2",
        "coverage": "exact_required_near_term",
        "pilot_user_id": "test_real_answer_pilot_20260604",
        "review_overrides": {},
    },
    {
        "case_id": "Q3-1A433000",
        "student_id": "S2",
        "coverage": "list_rule_incomplete",
        "pilot_user_id": "test_real_answer_pilot_20260604",
        "review_overrides": {
            "P1": {
                "teacher_hit": "partial",
                "teacher_score": 1.0,
                "teacher_note": "pilot_teacher_review: 列举项部分命中，但少写关键资源项，按 1 分确认",
            }
        },
    },
    {
        "case_id": "Q20-1A413000",
        "student_id": "S3",
        "coverage": "calculation_error",
        "pilot_user_id": "test_real_answer_pilot_20260604",
        "review_overrides": {},
    },
    {
        "case_id": "Q13-1A421000",
        "student_id": "S1",
        "coverage": "mostly_correct",
        "pilot_user_id": "test_real_answer_pilot_20260604",
        "review_overrides": {},
    },
    {
        "case_id": "Q12-1A412000-罚则",
        "student_id": "S2",
        "coverage": "penalty_or_direction_error",
        "pilot_user_id": "test_real_answer_pilot_20260604",
        "review_overrides": {
            "P3": {
                "teacher_hit": "partial",
                "teacher_score": 1.0,
                "teacher_note": "pilot_teacher_review: 方向基本对，但罚则/列举项不完整，降为 1 分",
            }
        },
    },
]


class PilotFakeLearnerStateService:
    def __init__(self) -> None:
        self.events: list[LearnerStateEvent] = []
        self.progress_patches: list[dict[str, Any]] = []

    def append_memory_event(self, user_id: str, **kwargs: Any) -> LearnerStateEvent:
        event = LearnerStateEvent(
            event_id=f"pilot-event-{len(self.events) + 1:03d}",
            user_id=str(user_id or "").strip(),
            source_feature=str(kwargs.get("source_feature") or ""),
            source_id=str(kwargs.get("source_id") or ""),
            source_bot_id=kwargs.get("source_bot_id"),
            memory_kind=str(kwargs.get("memory_kind") or ""),
            payload_json=dict(kwargs.get("payload_json") or {}),
            dedupe_key=str(kwargs.get("dedupe_key") or f"pilot-dedupe-{len(self.events) + 1}"),
            created_at=f"2026-06-04T10:{len(self.events):02d}:00+08:00",
        )
        self.events.append(event)
        return event

    def merge_progress(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.progress_patches.append({"user_id": user_id, "patch": patch})
        return patch

    def list_memory_events(self, user_id: str, limit: int | None = None) -> list[LearnerStateEvent]:
        events = [event for event in self.events if event.user_id == user_id]
        if isinstance(limit, int) and limit >= 0:
            return events[-limit:]
        return events

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool = True, event_limit: int | None = None) -> dict[str, Any]:
        return {"projection": synthesize_learning_truth(self.list_memory_events(user_id, limit=event_limit))}


def run_real_answer_teacher_review_pilot(
    *,
    learner_state_service: PilotFakeLearnerStateService | None = None,
    teacher_reviewed: bool = True,
) -> dict[str, Any]:
    service = learner_state_service or PilotFakeLearnerStateService()
    cases_by_id = _golden_cases_by_id()
    pilot_cases: list[dict[str, Any]] = []
    ai_draft_outputs: list[dict[str, Any]] = []
    teacher_review_payloads: list[dict[str, Any]] = []
    dry_run_outputs: list[dict[str, Any]] = []
    writeback_outputs: list[dict[str, Any]] = []

    for spec in PILOT_SAMPLE_SPECS:
        case = cases_by_id[spec["case_id"]]
        eval_sample = _eval_sample(case, spec["student_id"])
        artifact = build_question_grading_artifact(spec["case_id"])
        draft = best_quality_for_golden(case, spec["student_id"])
        review = _build_teacher_review(case=case, spec=spec, draft=draft, artifact=artifact, teacher_reviewed=teacher_reviewed)
        dry_run = build_teacher_review_writeback(review, dry_run=True, learner_state_service=None, user_id=spec["pilot_user_id"])

        if teacher_reviewed:
            writeback = build_teacher_review_writeback(
                review,
                dry_run=False,
                learner_state_service=service,
                user_id=spec["pilot_user_id"],
            )
            blocked_reason = ""
        else:
            writeback = {"dry_run": True, "writeback_count": 0}
            blocked_reason = "teacher_reviewed_required"

        written_count = int(writeback.get("writeback_count", 0))
        new_events = service.events[-written_count:] if written_count else []

        pilot_cases.append(_case_record(spec=spec, case=case, eval_sample=eval_sample, artifact=artifact))
        ai_draft_outputs.append(_draft_record(spec=spec, draft=draft))
        teacher_review_payloads.append(review)
        dry_run_outputs.append(_dry_run_record(spec=spec, dry_run=dry_run))
        writeback_outputs.append({
            "case_id": spec["case_id"],
            "student_id": spec["student_id"],
            "pilot_user_id": spec["pilot_user_id"],
            "teacher_reviewed": teacher_reviewed,
            "written_event_count": written_count,
            "blocked_reason": blocked_reason,
            "captured_memory_events": [_event_to_dict(event) for event in new_events],
        })

    user_id = PILOT_SAMPLE_SPECS[0]["pilot_user_id"]
    readback_events = [_event_to_dict(event) for event in service.list_memory_events(user_id, limit=None)]
    projection = synthesize_learning_truth(service.list_memory_events(user_id, limit=None))
    read_model = build_learning_brain_read_model(user_id=user_id, projection=projection, surface="qa")
    synthesis_preview = _synthesis_preview(
        user_id=user_id,
        events=service.list_memory_events(user_id, limit=None),
        teacher_reviews=teacher_review_payloads,
        read_model=read_model,
    )

    return {
        "pilot_cases": pilot_cases,
        "ai_draft_outputs": ai_draft_outputs,
        "teacher_review_payloads": teacher_review_payloads,
        "dry_run_outputs": dry_run_outputs,
        "writeback_outputs": writeback_outputs,
        "readback_learning_events": readback_events,
        "learning_brain_synthesis": synthesis_preview,
        "safety": {
            "fake_service_used": True,
            "real_db_written": False,
            "kernel_called": False,
            "rag_called": False,
            "new_tables": [],
        },
    }


def build_missing_artifact_case_record(*, case_id: str, student_id: str) -> dict[str, Any]:
    artifact = build_question_grading_artifact(case_id)
    return {
        "case_id": case_id,
        "student_id": student_id,
        "answer_type": "missing",
        "artifact_status": "artifact_missing" if artifact.get("artifact_missing") else artifact.get("status"),
        "auto_certified_score": 0,
        "writeback_candidate": False,
    }


def write_pilot_artifacts(output: dict[str, Any], *, out_dir: Path = PILOT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "pilot_cases.json", output["pilot_cases"])
    _write_json(out_dir / "ai_draft_outputs.json", output["ai_draft_outputs"])
    _write_json(out_dir / "teacher_review_payloads.json", output["teacher_review_payloads"])
    _write_json(out_dir / "writeback_outputs.json", output["writeback_outputs"])
    _write_json(out_dir / "readback_learning_events.json", output["readback_learning_events"])
    _write_json(out_dir / "learning_brain_synthesis.json", output["learning_brain_synthesis"])
    (out_dir / "FINDING_real_answer_teacher_review_pilot_20260604.md").write_text(
        _finding_markdown(output),
        encoding="utf-8",
    )


def _golden_cases_by_id() -> dict[str, dict[str, Any]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return {case["case_id"]: case for case in data.get("cases", [])}


def _eval_sample(case: dict[str, Any], student_id: str) -> dict[str, Any]:
    return next(sample for sample in case.get("eval_samples", []) if sample.get("student_id") == student_id)


def _case_record(*, spec: dict[str, Any], case: dict[str, Any], eval_sample: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": spec["case_id"],
        "student_id": spec["student_id"],
        "pilot_user_id": spec["pilot_user_id"],
        "coverage": spec["coverage"],
        "answer_type": "existing_fixture",
        "simulated_student_answer": False,
        "student_answer": eval_sample.get("answer_text", ""),
        "artifact_status": artifact.get("status", "artifact_missing"),
        "artifact_id": artifact.get("artifact_id"),
        "artifact_source_profile": artifact.get("source_profile"),
        "question_stem": case.get("stem", ""),
    }


def _draft_record(*, spec: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": spec["case_id"],
        "student_id": spec["student_id"],
        "engine": draft.get("engine"),
        "authority": draft.get("authority"),
        "prediction_source": draft.get("prediction_source"),
        "draft_score": draft.get("model_draft_score"),
        "auto_certified_score": draft.get("auto_certified_score"),
        "pending_review_score": draft.get("pending_review_score"),
        "bad_certified_count": draft.get("bad_certified_count"),
        "point_results": draft.get("point_results", []),
    }


def _build_teacher_review(
    *,
    case: dict[str, Any],
    spec: dict[str, Any],
    draft: dict[str, Any],
    artifact: dict[str, Any],
    teacher_reviewed: bool,
) -> dict[str, Any]:
    artifact_points = {point["point_id"]: point for point in artifact.get("scoring_points", [])}
    overrides = dict(spec.get("review_overrides") or {})
    point_reviews = []
    for point in draft.get("point_results", []):
        point_id = point.get("point_id")
        policy = artifact_points.get(point_id, {})
        override = overrides.get(point_id)
        if override:
            action = "override"
            teacher_hit = override["teacher_hit"]
            teacher_score = override["teacher_score"]
            teacher_note = override["teacher_note"]
        elif point.get("high_risk_review") or point.get("unsupported"):
            action = "confirm"
            teacher_hit = "miss"
            teacher_score = 0
            teacher_note = "pilot_teacher_review: 高风险或证据不足，未人工升级为 mastery"
        else:
            action = "confirm"
            teacher_hit = point.get("hit") or "miss"
            teacher_score = float(point.get("score") or 0)
            teacher_note = "pilot_teacher_review: 按 Best-Quality draft 确认"
        point_reviews.append({
            "point_id": point_id,
            "label": point.get("expected_point_label") or policy.get("label") or point_id,
            "policy_type": point.get("policy_type") or policy.get("policy_type"),
            "max_score": point.get("max_score") if point.get("max_score") is not None else policy.get("max_score"),
            "ai_hit": point.get("hit"),
            "ai_score": float(point.get("score") or 0),
            "high_risk_review": bool(point.get("high_risk_review")),
            "unsupported": bool(point.get("unsupported")),
            "auto_certified": bool(point.get("auto_certified")),
            "model_votes": point.get("model_votes"),
            "adjudication_reason": point.get("adjudication_reason"),
            "review_action": action,
            "teacher_hit": teacher_hit,
            "teacher_score": teacher_score,
            "teacher_note": teacher_note,
            "reviewer_type": "pilot_teacher_review",
        })
    return {
        "engine": "best_quality_4model",
        "authority": "teacher_reviewed_grading",
        "prediction_source": draft.get("prediction_source"),
        "teacher_reviewed": bool(teacher_reviewed),
        "reviewer_type": "pilot_teacher_review",
        "case_id": spec["case_id"],
        "student_id": spec["student_id"],
        "pilot_user_id": spec["pilot_user_id"],
        "student_answer": _eval_sample(case, spec["student_id"]).get("answer_text", ""),
        "ai_draft_summary": {
            "model_draft_score": draft.get("model_draft_score"),
            "auto_certified_score": draft.get("auto_certified_score"),
            "pending_review_score": draft.get("pending_review_score"),
            "bad_certified_count": draft.get("bad_certified_count"),
        },
        "point_reviews": point_reviews,
        "not_production_grade": True,
    }


def _dry_run_record(*, spec: dict[str, Any], dry_run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(dry_run.get("learning_evidence_payload") or {})
    return {
        "case_id": spec["case_id"],
        "student_id": spec["student_id"],
        "dry_run": dry_run.get("dry_run", True),
        "teacher_final_score": payload.get("score_awarded"),
        "teacher_final_max_score": payload.get("max_score"),
        "error_event_count": len(payload.get("error_events") or []),
        "mastery_point_ids": dry_run.get("mastery_point_ids", []),
        "learning_evidence_payload_preview": payload,
    }


def _event_to_dict(event: LearnerStateEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "user_id": event.user_id,
        "source_feature": event.source_feature,
        "source_id": event.source_id,
        "source_bot_id": event.source_bot_id,
        "memory_kind": event.memory_kind,
        "dedupe_key": event.dedupe_key,
        "created_at": event.created_at,
        "payload_json": event.payload_json,
    }


def _synthesis_preview(
    *,
    user_id: str,
    events: list[LearnerStateEvent],
    teacher_reviews: list[dict[str, Any]],
    read_model: dict[str, Any],
) -> dict[str, Any]:
    policy_by_case_point = {
        (review["case_id"], point["point_id"]): point.get("policy_type")
        for review in teacher_reviews
        for point in review.get("point_reviews", [])
    }
    weaknesses = []
    mastery_signals = []
    for event in events:
        payload = event.payload_json
        case_id = str(payload.get("question_id") or "")
        point_events = list((payload.get("next_training_signal") or {}).get("teacher_review_points") or [])
        for point in point_events:
            item = {
                "case_id": case_id,
                "point_id": point.get("point_id"),
                "policy_type": policy_by_case_point.get((case_id, point.get("point_id")), ""),
                "diagnosis": point.get("diagnosis", ""),
                "evidence": point.get("authority", ""),
            }
            if point.get("mastery_eligible"):
                mastery_signals.append(item)
            else:
                weaknesses.append(item)
    return {
        "student_id": user_id,
        "weaknesses": weaknesses,
        "mastery_signals": mastery_signals,
        "next_suggestions": _next_suggestions(weaknesses=weaknesses, mastery_signals=mastery_signals),
        "read_model": read_model,
    }


def _next_suggestions(*, weaknesses: list[dict[str, Any]], mastery_signals: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    policies = {item.get("policy_type") for item in weaknesses}
    if "exact_required" in policies:
        suggestions.append("复习对应教材术语，按官方表述重写关键采分句")
    if "list_rule" in policies:
        suggestions.append("补练列举型采分点，按清单逐项覆盖")
    if "calculation" in policies:
        suggestions.append("重做同类计算题，先列公式再代数验算")
    if not suggestions and mastery_signals:
        suggestions.append("保留本次已掌握点，下一轮做同主题变式题验证稳定性")
    return suggestions


def _finding_markdown(output: dict[str, Any]) -> str:
    synthesis = output["learning_brain_synthesis"]
    lines = [
        "# real-answer teacher-review pilot 2026-06-04",
        "",
        "DB mode: fake learner_state_service; no real DB was written.",
        "",
        "| case_id | student_id | answer_type | artifact_status | engine | draft_score | teacher_final_score | written_event_count | weaknesses | mastery_signals | next_suggestion | risk_notes |",
        "|---|---|---|---|---|---:|---:|---:|---|---|---|---|",
    ]
    cases = {item["case_id"]: item for item in output["pilot_cases"]}
    drafts = {item["case_id"]: item for item in output["ai_draft_outputs"]}
    dry_runs = {item["case_id"]: item for item in output["dry_run_outputs"]}
    writes = {item["case_id"]: item for item in output["writeback_outputs"]}
    for case_id, case in cases.items():
        case_weaknesses = [item for item in synthesis["weaknesses"] if item["case_id"] == case_id]
        case_mastery = [item for item in synthesis["mastery_signals"] if item["case_id"] == case_id]
        weak = [item["point_id"] for item in case_weaknesses]
        mastery = [item["point_id"] for item in case_mastery]
        case_suggestions = _next_suggestions(weaknesses=case_weaknesses, mastery_signals=case_mastery)
        risk_notes = []
        if case["artifact_status"] != "published":
            risk_notes.append(f"artifact={case['artifact_status']}")
        if any(item for item in synthesis["weaknesses"] if item["case_id"] == case_id and item.get("policy_type") == "exact_required"):
            risk_notes.append("exact_required gap")
        lines.append(
            "| {case_id} | {student_id} | {answer_type} | {artifact_status} | {engine} | {draft_score} | {teacher_final_score} | {written_event_count} | {weaknesses} | {mastery_signals} | {next_suggestion} | {risk_notes} |".format(
                case_id=case_id,
                student_id=case["student_id"],
                answer_type=case["answer_type"],
                artifact_status=case["artifact_status"],
                engine=drafts[case_id]["engine"],
                draft_score=drafts[case_id]["draft_score"],
                teacher_final_score=dry_runs[case_id]["teacher_final_score"],
                written_event_count=writes[case_id]["written_event_count"],
                weaknesses=",".join(weak) or "-",
                mastery_signals=",".join(mastery) or "-",
                next_suggestion="; ".join(case_suggestions[:2]),
                risk_notes="; ".join(risk_notes) or "-",
            )
        )
    lines.extend([
        "",
        "## Boundary",
        "",
        "- No new table.",
        "- No production endpoint/runtime.",
        "- No CaseGradingSkillKernel change.",
        "- No RAG authority.",
        "- Reviewer type is `pilot_teacher_review`; not a human teacher.",
    ])
    return "\n".join(lines) + "\n"


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    output = run_real_answer_teacher_review_pilot()
    write_pilot_artifacts(output)
    print(json.dumps({"out_dir": str(PILOT_DIR), "cases": len(output["pilot_cases"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
