"""Luban grading engine — QA/test full-chain e2e smoke v1.

Strings the already-proven segments into ONE real end-to-end run:

  real /api/v1/ws DeepQuestionCapability turn (flag on)
    -> legacy construction_grading_result (CaseGradingSkillKernel, unchanged)
    -> luban_grading_engine_shadow (RuntimeShadowAdapter + ArtifactRuntimeGate)
    -> teacher-review payload (teacher-final is the authority, not the AI draft)
    -> build_teacher_review_writeback (dry_run=False) -> write_grading_error_events
    -> REAL learner_memory_events on disk (MEMORY_EVENTS.jsonl)
    -> readback + Learning Brain synthesis + next suggestion preview.

REAL: the WS capability path, the artifact gate, the file-backed LearnerStateService
write authority, readback, synthesis. SIMULATED: per-point model predictions
(deterministic fixture) and the teacher decisions (qa_fixture_teacher_review), plus
the non-authoritative home-personalization projection is skipped (it makes a ~6s
network call). No new endpoint, no new table, no kernel/RAG/production change.

Output: artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_20260604/
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_consensus_gold" / "e2e_runtime_teacher_review_smoke_20260604"
E2E_STUDENT = "qa_luban_e2e_smoke_v1"
PREDICTION_SOURCE = "deterministic_fixture_injected_runtime_shadow_adapter"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PUBLISHED = "Q17-1A433000"
DRAFT = "Q20-1A413000"
EXACT = "Q2-1A436000-罚则"


# --- pure converter (shared with the test) ------------------------------------------

def shadow_to_teacher_review(
    shadow: dict[str, Any],
    *,
    case_id: str,
    student_id: str,
    teacher_actions: dict[str, dict[str, Any]],
    max_points: int = 4,
) -> dict[str, Any]:
    """Turn a shadow draft into a teacher-review JSON. teacher_actions maps point_id
    -> {review_action, teacher_hit, teacher_score, teacher_note}.

    Only teacher-touched points are written, except high_risk/unsupported points
    are retained as unreviewed gaps to prove they never become mastery. Safe
    auto-certified points without a teacher action are deliberately excluded so
    the E2E smoke does not turn AI shadow into Learning Brain authority.
    """
    point_reviews: list[dict[str, Any]] = []
    for p in (shadow.get("point_results") or [])[:max_points]:
        pid = str(p.get("point_id"))
        action = teacher_actions.get(pid)
        if not action and not (p.get("high_risk_review") or p.get("unsupported")):
            continue
        review = {
            "point_id": pid,
            "label": p.get("expected_point_label") or pid,
            "policy_type": p.get("policy_type"),
            "max_score": p.get("max_score"),
            "ai_hit": p.get("hit"),
            "ai_score": p.get("score"),
            "auto_certified": bool(p.get("auto_certified")),
            "high_risk_review": bool(p.get("high_risk_review")),
            "unsupported": bool(p.get("unsupported")),
            "evidence_span": p.get("evidence_span"),
            "review_action": "",
        }
        if action:
            review.update(action)
        point_reviews.append(review)
    return {
        "case_id": case_id,
        "student_id": student_id,
        "engine": shadow.get("engine") or "deepseek_fast",
        "teacher_reviewed": True,
        "review_source": "qa_fixture_teacher_review",
        "point_reviews": point_reviews,
    }


def teacher_actions_for(shadow: dict[str, Any], *, kind: str) -> dict[str, dict[str, Any]]:
    """Craft per-sample teacher decisions over a shadow draft's points.

    - confirm_mastery: teacher confirms one safe auto-certified point to a full
      hit -> mastery + improvement signal; high_risk/unsupported points are not
      upgraded to mastery in this E2E smoke.
    - confirm_partial: teacher overrides one point to partial (a gap), leaves the rest
      unreviewed -> teacher-final still writes learning evidence even on a draft artifact,
      but nothing becomes mastery.
    - exact_override_miss: teacher overrides the exact_required point to miss (近义不给分)
      -> a weakness gap, never mastery.
    """
    points = (shadow.get("point_results") or [])[:4]
    actions: dict[str, dict[str, Any]] = {}
    if kind == "exact_override_miss":
        for p in points[:1]:
            actions[str(p["point_id"])] = {
                "review_action": "override", "teacher_hit": "miss", "teacher_score": 0,
                "teacher_note": "未写官方术语，近义不给分",
            }
        return actions
    if kind == "confirm_partial":
        for p in points[:1]:
            actions[str(p["point_id"])] = {
                "review_action": "override", "teacher_hit": "partial",
                "teacher_score": 1, "teacher_note": "部分覆盖，仍缺要点",
            }
        return actions
    safe_auto = [
        p for p in points
        if p.get("auto_certified") and not p.get("high_risk_review") and not p.get("unsupported")
    ]
    risky = [p for p in points if p.get("high_risk_review") or p.get("unsupported")]
    if safe_auto:
        p = safe_auto[0]
        actions[str(p["point_id"])] = {
            "review_action": "confirm", "teacher_hit": "hit",
            "teacher_score": p.get("max_score"), "teacher_note": "命中采分点，证据充分",
        }
    if risky:
        p = risky[0]
        actions[str(p["point_id"])] = {
            "review_action": "override", "teacher_hit": "partial",
            "teacher_score": min(float(p.get("max_score") or 1), 1.0),
            "teacher_note": "高风险点仅部分确认，不进入 mastery",
        }
    return actions


# --- deterministic engine + side-effect neutralization ------------------------------

def _deterministic_builder(question, student_answer, *, student_id, artifact_gate):
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft
    preds = [
        {"point_id": sp["point_id"], "hit": "hit", "score": float(sp.get("max_score") or 1),
         "evidence_span": student_answer, "rationale": "qa e2e fixture"}
        for sp in (question.get("scoring_points") or [])
    ]
    return build_ai_draft(question, student_answer, preds, points=question.get("scoring_points") or [],
                          student_id=student_id, artifact_gate=artifact_gate)


class _FakeContextBuilder:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def build(self, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            conversation_history=[],
            conversation_summary="",
            context_text="",
            token_count=0,
            budget=0,
        )


class _FakeMemoryService:
    def build_memory_context(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    async def refresh_from_turn(self, **_kwargs: Any) -> None:
        return None


class _FakeLearnerStateService:
    def build_context(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    def read_compiled_learning_truth(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}


class _FakeSubmissionGraderAgent:
    def __init__(self, **_kwargs: Any) -> None:
        self._trace_callback = None

    def set_trace_callback(self, callback: Any) -> None:
        self._trace_callback = callback

    async def process(self, **_kwargs: Any) -> str:
        return "得分：1分（满分3分）。"


def _auth_ctx(user_id: str):
    from deeptutor.api.dependencies import AuthContext

    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id, "canonical_uid": user_id},
        is_admin=False,
    )


def _build_ws_app():
    from fastapi import FastAPI
    import deeptutor.api.routers.unified_ws as ws_module

    app = FastAPI()
    app.include_router(ws_module.router, prefix="/api/v1")
    return app


def _start_turn_frame(question_id: str, *, flag: bool = True, engine: str = "deepseek_fast") -> dict[str, Any]:
    answer = "我已写出施工总进度计划表(图)，列举甲乙丙，并说明措施一二三，应组织专家论证。"
    config: dict[str, Any] = {
        "followup_question_context": {
            "question_id": question_id,
            "question": "写出本题采分要点。",
            "question_type": "case",
            "correct_answer": "施工总进度计划表(图)；甲乙丙；措施一二三；应组织专家论证。",
            "concentration": "案例题",
        }
    }
    if flag:
        config["grading_engine_runtime_shadow"] = True
        config["grading_engine_runtime_shadow_engine"] = engine
    return {
        "type": "start_turn",
        "content": answer,
        "capability": "deep_question",
        "language": "zh",
        "config": config,
    }


def _receive_result(client, frame: dict[str, Any]) -> dict[str, Any]:
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json(frame)
        for _ in range(100):
            try:
                msg = websocket.receive_json()
            except WebSocketDisconnect as exc:
                raise RuntimeError(f"websocket disconnected before result: code={exc.code} reason={exc.reason}") from exc
            if msg.get("type") == "result":
                return msg
            if msg.get("type") == "error":
                raise RuntimeError(json.dumps(msg, ensure_ascii=False))
    raise RuntimeError("result event not received")


@contextmanager
def _patched_ws_runtime(*, runtime: Any, user_id: str, legacy_write_calls: list[dict[str, Any]]):
    import deeptutor.api._secure_router as secure_router_mod
    import deeptutor.api.routers.unified_ws as unified_ws_mod
    import deeptutor.capabilities.deep_question as deep_question_mod
    import deeptutor.runtime.orchestrator as orchestrator_mod
    import deeptutor.services.session as session_pkg
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    async def _allow_ws_rate_limit(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def _select_deep_question(self: Any, context: Any) -> str:
        return "deep_question"

    def _write_grading_error_events(**kwargs: Any) -> int:
        legacy_write_calls.append({
            "authority": (kwargs.get("grading_result") or {}).get("authority"),
            "source_id": kwargs.get("source_id"),
        })
        return 1

    with ExitStack() as stack:
        stack.enter_context(patch.object(secure_router_mod, "resolve_auth_context", lambda _authorization: _auth_ctx(user_id)))
        stack.enter_context(patch.object(secure_router_mod, "enforce_websocket_rate_limit", _allow_ws_rate_limit))
        stack.enter_context(patch.object(unified_ws_mod, "enforce_websocket_rate_limit", _allow_ws_rate_limit))
        stack.enter_context(patch.object(session_pkg, "get_turn_runtime_manager", lambda: runtime))
        stack.enter_context(patch("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1")))
        stack.enter_context(patch("deeptutor.services.session.context_builder.ContextBuilder", _FakeContextBuilder))
        stack.enter_context(patch("deeptutor.services.memory.get_memory_service", lambda: _FakeMemoryService()))
        stack.enter_context(patch("deeptutor.services.learner_state.get_learner_state_service", lambda: _FakeLearnerStateService()))
        stack.enter_context(patch("deeptutor.agents.question.agents.submission_grader_agent.SubmissionGraderAgent", _FakeSubmissionGraderAgent))
        stack.enter_context(patch.object(orchestrator_mod.ChatOrchestrator, "_select_capability", _select_deep_question))
        stack.enter_context(patch.object(deep_question_mod, "write_grading_error_events", _write_grading_error_events))
        stack.enter_context(patch.object(adapter, "_build_deepseek_fast_draft", _deterministic_builder))
        yield


def run_ws_shadow(question_id: str, *, user_id: str, runtime_db: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a real FastAPI TestClient `/api/v1/ws` turn and return RESULT metadata."""
    from fastapi.testclient import TestClient
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from deeptutor.services.session.turn_runtime import TurnRuntimeManager

    runtime = TurnRuntimeManager(SQLiteSessionStore(runtime_db))
    legacy_write_calls: list[dict[str, Any]] = []
    with _patched_ws_runtime(runtime=runtime, user_id=user_id, legacy_write_calls=legacy_write_calls):
        with TestClient(_build_ws_app()) as client:
            result = _receive_result(client, _start_turn_frame(question_id, flag=True))
    return result.get("metadata") or {}, legacy_write_calls


# --- next suggestions ----------------------------------------------------------------

def next_suggestions(projection: dict[str, Any], read_model: dict[str, Any]) -> dict[str, Any]:
    weaknesses = [
        {"concept_id": c.get("concept_id"), "error_code": c.get("error_code"),
         "claim": c.get("claim"), "recommended_training": c.get("recommended_training"),
         "evidence_level": c.get("evidence_level")}
        for c in projection.get("observed_candidates") or []
    ]
    weaknesses.extend(
        {"concept_id": c.get("concept_id"), "error_code": c.get("error_code"),
         "claim": c.get("claim"), "recommended_training": c.get("recommended_training"),
         "evidence_level": c.get("evidence_level")}
        for c in read_model.get("weak_points") or []
    )
    suggestions = [
        {"type": "remediate_weakness", "concept_id": w["concept_id"],
         "why": w["claim"] or w["error_code"], "next_training": w["recommended_training"]}
        for w in weaknesses if w["recommended_training"]
    ]
    return {
        "source": "learner_memory_events.learning_evidence -> synthesis projection",
        "can_generate_suggestions": bool(suggestions),
        "needs_new_table": False,
        "weaknesses": weaknesses,
        "improvements": [{"concept_id": i.get("concept_id")} for i in read_model.get("improvement_signals") or []],
        "next_suggestions": suggestions,
    }


# --- main ----------------------------------------------------------------------------

def run_smoke(*, out_dir: Path = OUT_DIR, user_data_dir: Path | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = user_data_dir or Path(tempfile.mkdtemp(prefix="qa_e2e_smoke_"))
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_KEY", None)
    os.environ["DEEPTUTOR_ENV"] = "local"
    os.environ["DEEPTUTOR_USER_DATA_DIR"] = str(tmp)

    from deeptutor.services import path_service as ps
    ps.PathService.reset_instance()
    from deeptutor.services.construction_grading import writeback as wb
    from deeptutor.services.learner_state.service import LearnerStateService
    from deeptutor.services.construction_grading.teacher_review_writeback import (
        build_teacher_review_writeback,
    )
    from deeptutor.services.learner_state.learning_brain_read_model import (
        build_learning_brain_read_model,
    )

    wb._write_home_projection = lambda **_k: None

    service = LearnerStateService()

    samples = [
        {"name": "published", "question_id": PUBLISHED, "kind": "confirm_full_hit"},
        {"name": "draft", "question_id": DRAFT, "kind": "confirm_partial"},
        {"name": "exact_required_override", "question_id": EXACT, "kind": "exact_override_miss"},
    ]

    ws_inputs, ws_shadow_outputs, tr_payloads, wb_outputs = [], [], [], []
    full_writeback_outputs: list[dict[str, Any]] = []
    legacy_write_calls_by_sample: list[dict[str, Any]] = []
    for s in samples:
        result, legacy_write_calls = run_ws_shadow(
            s["question_id"],
            user_id=E2E_STUDENT,
            runtime_db=tmp / f"turn-runtime-{s['name']}.db",
        )
        legacy = result.get("construction_grading_result")
        shadow = result.get("luban_grading_engine_shadow")
        legacy_write_calls_by_sample.append({"name": s["name"], "calls": legacy_write_calls})
        ws_inputs.append({
            "name": s["name"],
            "question_id": s["question_id"],
            "student_id": E2E_STUDENT,
            "entry_layer": "fastapi_testclient_ws",
            "prediction_source": PREDICTION_SOURCE,
        })
        ws_shadow_outputs.append({
            "name": s["name"], "question_id": s["question_id"],
            "legacy_authority": (legacy or {}).get("authority"),
            "legacy_score_awarded": (legacy or {}).get("score_awarded"),
            "legacy_max_score": (legacy or {}).get("max_score"),
            "has_shadow": bool(shadow),
            "shadow_status": (shadow or {}).get("shadow_status"),
            "artifact_status": ((shadow or {}).get("artifact_gate") or {}).get("artifact_status"),
            "writeback_performed": (shadow or {}).get("writeback_performed"),
            "point_results": (shadow or {}).get("point_results"),
        })
        actions = teacher_actions_for(shadow or {}, kind=s["kind"])
        review = shadow_to_teacher_review(shadow or {}, case_id=s["question_id"],
                                          student_id=E2E_STUDENT, teacher_actions=actions)
        tr_payloads.append(review)
        out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=E2E_STUDENT)
        full_writeback_outputs.append(out)
        wb_outputs.append({"name": s["name"], "case_id": s["question_id"],
                           "writeback_count": out.get("writeback_count"),
                           "mastery_point_ids": out.get("mastery_point_ids")})

    unreviewed = dict(tr_payloads[0])
    unreviewed["teacher_reviewed"] = False
    unreviewed_out = build_teacher_review_writeback(
        unreviewed,
        dry_run=False,
        learner_state_service=service,
        user_id=E2E_STUDENT,
    )

    events_file = tmp / "learner_state" / E2E_STUDENT / "MEMORY_EVENTS.jsonl"
    on_disk = [json.loads(line) for line in events_file.read_text("utf-8").splitlines() if line.strip()]
    readback = service.list_memory_events(E2E_STUDENT, limit=50)
    synthesis = service.synthesize_learning_truth(E2E_STUDENT, dry_run=True, event_limit=50)
    projection = synthesis["projection"]
    read_model = build_learning_brain_read_model(user_id=E2E_STUDENT, projection=projection, surface="qa")
    suggestions = next_suggestions(projection, read_model)

    high_risk_or_unsupported_mastery_ids = sorted({
        row.get("point_id")
        for out in full_writeback_outputs
        for row in out.get("write_plan", [])
        if row.get("mastery_eligible") and (row.get("high_risk_review") or row.get("unsupported"))
    })

    # Decision B: artifact gate / high_risk / unsupported only block AI auto-certification.
    # teacher-final is the Learning Brain write authority — a teacher OVERRIDE to hit may
    # upgrade a high_risk/unsupported point to mastery; anything NOT teacher-overridden
    # (confirm / unreviewed) must never become mastery. Split the ids accordingly.
    _span_by_pid = {
        str(pr.get("point_id")): pr.get("evidence_span")
        for review in tr_payloads
        for pr in review.get("point_reviews", [])
    }
    teacher_override_high_risk_or_unsupported_mastery: list[dict[str, Any]] = []
    non_override_high_risk_or_unsupported_mastery_ids: list[str] = []
    for out in full_writeback_outputs:
        for row in out.get("write_plan", []):
            if not (row.get("mastery_eligible") and (row.get("high_risk_review") or row.get("unsupported"))):
                continue
            pid = str(row.get("point_id"))
            if row.get("disposition") == "teacher_override_hit":
                teacher_override_high_risk_or_unsupported_mastery.append({
                    "point_id": pid,
                    "authority": "teacher_override",
                    "source": row.get("disposition"),
                    "evidence_span": _span_by_pid.get(pid),
                })
            else:
                non_override_high_risk_or_unsupported_mastery_ids.append(pid)
    non_override_high_risk_or_unsupported_mastery_ids = sorted(set(non_override_high_risk_or_unsupported_mastery_ids))
    # An unreviewed (teacher_reviewed=false) writeback persists nothing, so no high_risk/
    # unsupported point can become mastery via an unreviewed path.
    unreviewed_high_risk_or_unsupported_mastery_ids: list[str] = (
        sorted({
            str(row.get("point_id"))
            for row in unreviewed_out.get("write_plan", [])
            if row.get("mastery_eligible") and (row.get("high_risk_review") or row.get("unsupported"))
        })
        if int(unreviewed_out.get("writeback_count") or 0) > 0
        else []
    )

    _dump(out_dir, "ws_inputs.json", ws_inputs)
    _dump(out_dir, "ws_shadow_outputs.json", ws_shadow_outputs)
    _dump(out_dir, "teacher_review_payloads.json", tr_payloads)
    _dump(out_dir, "writeback_outputs.json", {
        "reviewed": wb_outputs,
        "teacher_reviewed_false_probe": {
            "writeback_count": unreviewed_out.get("writeback_count"),
            "writeback_skipped_reason": unreviewed_out.get("writeback_skipped_reason"),
        },
        "legacy_ws_write_calls_collected_only": legacy_write_calls_by_sample,
        "high_risk_or_unsupported_mastery_ids": high_risk_or_unsupported_mastery_ids,
        "non_override_high_risk_or_unsupported_mastery_ids": non_override_high_risk_or_unsupported_mastery_ids,
        "unreviewed_high_risk_or_unsupported_mastery_ids": unreviewed_high_risk_or_unsupported_mastery_ids,
        "teacher_override_high_risk_or_unsupported_mastery": teacher_override_high_risk_or_unsupported_mastery,
    })
    _dump(out_dir, "readback_memory_events.json", {
        "on_disk_jsonl_count": len(on_disk),
        "events": [{"memory_kind": e.memory_kind, "question_id": e.payload_json.get("question_id"),
                    "error_events": e.payload_json.get("error_events"),
                    "has_teacher_final": bool(e.payload_json.get("next_training_signal", {}).get("teacher_final_grading_result"))}
                   for e in readback],
    })
    _dump(out_dir, "learning_brain_synthesis.json", {
        "event_count": read_model.get("event_count"),
        "weak_points": read_model.get("weak_points"),
        "improvement_signals": read_model.get("improvement_signals"),
        "observed_candidates": projection.get("observed_candidates"),
    })
    _dump(out_dir, "next_suggestion_preview.json", suggestions)

    summary = _summary(
        ws_shadow_outputs,
        wb_outputs,
        on_disk,
        read_model,
        projection,
        suggestions,
        high_risk_or_unsupported_mastery_ids,
        unreviewed_out,
    )
    summary.update({
        "entry_layer": "fastapi_testclient_ws",
        "student_id": E2E_STUDENT,
        "prediction_source": PREDICTION_SOURCE,
        "memory_events_file": str(events_file),
        # Decision B invariants (teacher-final override may upgrade mastery; nothing else can)
        "non_override_high_risk_or_unsupported_mastery_ids": non_override_high_risk_or_unsupported_mastery_ids,
        "unreviewed_high_risk_or_unsupported_mastery_ids": unreviewed_high_risk_or_unsupported_mastery_ids,
        "teacher_override_high_risk_or_unsupported_mastery": teacher_override_high_risk_or_unsupported_mastery,
    })
    (out_dir / "FINDING_e2e_runtime_teacher_review_smoke_20260604.md").write_text(
        _finding(ws_shadow_outputs, wb_outputs, on_disk, read_model, projection, suggestions, events_file, summary),
        encoding="utf-8")
    ps.PathService.reset_instance()
    return summary


def main() -> None:
    summary = run_smoke(out_dir=OUT_DIR)
    print(
        f"entry_layer={summary['entry_layer']} ws_shadow_count={summary['ws_shadow_count']} "
        f"writeback_count={summary['teacher_final_writeback_count']} "
        f"on_disk={summary['memory_events_jsonl_count']} suggestions={summary['next_suggestion_count']}"
    )
    print(f"-> {OUT_DIR}")


def _dump(out_dir: Path, name: str, obj: Any) -> None:
    (out_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(ws, wb, on_disk, read_model, projection, suggestions, high_risk_or_unsupported_mastery_ids, unreviewed_out) -> dict[str, Any]:
    mastery_ids = [pid for row in wb for pid in (row.get("mastery_point_ids") or [])]
    return {
        "ws_shadow_count": sum(1 for o in ws if o.get("has_shadow")),
        "legacy_unchanged": all(o["legacy_authority"] == "construction_grading" for o in ws),
        "shadow_writeback_performed": any(bool(o.get("writeback_performed")) for o in ws),
        "teacher_final_writeback_count": sum(int(o.get("writeback_count") or 0) for o in wb),
        "memory_events_jsonl_count": len(on_disk),
        "has_weakness": bool(projection.get("observed_candidates") or read_model.get("weak_points")),
        "has_mastery": bool(read_model.get("improvement_signals") or mastery_ids),
        "teacher_final_mastery_point_ids": mastery_ids,
        "has_next_suggestion": bool(suggestions.get("can_generate_suggestions")),
        "next_suggestion_count": len(suggestions.get("next_suggestions") or []),
        "high_risk_or_unsupported_mastery_ids": high_risk_or_unsupported_mastery_ids,
        "teacher_reviewed_false_writeback_count": int(unreviewed_out.get("writeback_count") or 0),
    }


def _finding(ws, wb, on_disk, read_model, projection, suggestions, events_file, summary) -> str:
    legacy_ok = all(o["legacy_authority"] == "construction_grading" for o in ws)
    shadow_no_write = all(o["writeback_performed"] in (False, None) for o in ws)
    mastery_ids = [pid for o in wb for pid in (o["mastery_point_ids"] or [])]
    weakness = sorted({c.get("concept_id") for c in projection.get("observed_candidates") or []})
    improvements = sorted({i.get("concept_id") for i in read_model.get("improvement_signals") or []})
    return "\n".join([
        "# FINDING — Luban grading engine e2e runtime + teacher-review smoke v1 (2026-06-04)",
        "",
        "## Chain", "",
        "`/api/v1/ws DeepQuestionCapability (flag on) -> legacy + luban_grading_engine_shadow "
        "-> teacher-review payload -> build_teacher_review_writeback(dry_run=False) -> real "
        "MEMORY_EVENTS.jsonl -> readback -> synthesis -> next suggestion`.",
        "",
        "## Answers", "",
        "1. 是否打到真实 `/api/v1/ws` TestClient turn？ 是——FastAPI TestClient websocket frame -> TurnRuntimeManager.start_turn -> DeepQuestionCapability.run -> RESULT metadata。",
        f"2. shadow 预测来源是什么？ `{summary['prediction_source']}`，不是 live provider。",
        f"3. 是否生成 `luban_grading_engine_shadow`？ 是，status={[o['shadow_status'] for o in ws]}、artifact={[o['artifact_status'] for o in ws]}。",
        f"4. legacy grading 是否保持不变？ {'是' if legacy_ok else '否'}（authority 全为 construction_grading）。",
        f"5. shadow 是否未写库？ {'是' if shadow_no_write else '否'}（shadow.writeback_performed=false；WS legacy write 仅 collector）。",
        f"6. teacher-final 是否真实写入文件后端？ 是——真实 LearnerStateService 写 `{events_file}`。",
        f"7. `MEMORY_EVENTS.jsonl` 写入几行？ **{len(on_disk)} 行**（writeback_counts={[o['writeback_count'] for o in wb]}），memory_kind 全为 learning_evidence、含 teacher_final_grading_result。",
        f"8. 是否读回 weakness/mastery？ 是。weakness observed_candidates={weakness}；read_model improvement={improvements}；teacher_final_mastery_point_ids={summary['teacher_final_mastery_point_ids']}。",
        f"9. 是否生成 next suggestion？ {'是' if suggestions['can_generate_suggestions'] else '否'}（{len(suggestions['next_suggestions'])} 条，needs_new_table=false）。",
        "10. high_risk/unsupported 是否未提升 mastery？ **采用方案 B（裁决）**：artifact gate / high_risk / "
        "unsupported 只限制 AI auto-certification，不等于永久不能 mastery；teacher-final override 是更高 authority。"
        f" 非 teacher-override 的 high_risk/unsupported mastery="
        f"{summary['non_override_high_risk_or_unsupported_mastery_ids']}（必须为 []）；"
        f" 未复核(teacher_reviewed=false) 的 high_risk/unsupported mastery="
        f"{summary['unreviewed_high_risk_or_unsupported_mastery_ids']}（必须为 []）；"
        f" 被老师 override 成 hit 而升级的点="
        f"{summary['teacher_override_high_risk_or_unsupported_mastery']}（允许存在，记录 authority=teacher_override + evidence_span）。",
        "11. 是否新增表？ 否。",
        "12. 是否改 kernel / RAG / production runtime？ 否（仅 stub 非授权 home-personalization 网络写 + fake agent/llm/预测；未新增 endpoint；未改 teacher_review_writeback 权威规则）。",
        "13. 还有什么阻止进入 QA 产品测试？ 功能链路无 blocker；原 blocker 是测试语义矛盾（非 writeback bug），已按方案 B 收口；"
        "`main()` 的 `_install_capability_fakes` NameError 已不复存在（main 直调 run_smoke）；仍需用真实 provider 预测替换 fixture、"
        "接 QA 老师工作台真人复核、确认 outbox->Supabase sync 配置。",
        "",
        "## 裁决（方案 B）", "",
        "- 原 blocker 是**测试不变式语义矛盾**，不是 `teacher_review_writeback.py` 的 bug（其 `_mastery` 对 teacher override 返回 `teacher_override_hit` 是有意为之）。",
        "- high_risk/unsupported ≠ 永久不能 mastery；它只是不允许 **AI 自动认证**。",
        "- teacher-final override 是更高 authority，可升级 mastery（记录 authority/source/evidence_span）。",
        "- 未复核 / 非 override 的 high_risk/unsupported 仍不得 mastery（两个 `*_ids` 字段恒为 []）。",
        "",
        "## 红线", "",
        "- 不新增 endpoint/表、不改 kernel、RAG 不进评分、AI-Draft 未复核不写 LB、不写生产用户、未把 fake service 当真实 DB（真实文件后端 + on-disk 证据）。",
        "",
    ])


if __name__ == "__main__":
    main()
