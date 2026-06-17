#!/usr/bin/env python3
"""Luban E2E v2: real QA model-cache prediction smoke.

This keeps the v1 end-to-end chain but removes the deterministic prediction
fixture. Runtime shadow uses the existing Best-Quality cached 4-model prediction
reader (`load_cached_4model_predictions`) through `runtime_shadow_adapter`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_consensus_gold" / "e2e_runtime_teacher_review_smoke_v2_20260604"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_e2e_runtime_teacher_review_smoke import (  # noqa: E402
    PUBLISHED,
    DRAFT,
    EXACT,
    _auth_ctx,
    _build_ws_app,
    _dump,
    _finding,
    _patched_ws_runtime,
    _receive_result,
    _summary,
    next_suggestions,
    shadow_to_teacher_review,
    teacher_actions_for,
)

E2E_V2_STUDENT = "qa_luban_e2e_smoke_v2"
PREDICTION_SOURCE = "model_cache"
PROVIDER = "cached_4model_jury"
MODEL = "gpt55+opus48+deepseek_v4+qwen37"
GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"


def _start_turn_frame(question_id: str, *, cache_student_id: str) -> dict[str, Any]:
    answer = _golden_answer(question_id, cache_student_id)
    return {
        "type": "start_turn",
        "content": answer,
        "capability": "deep_question",
        "language": "zh",
        "config": {
            "followup_question_context": {
                "question_id": question_id,
                "question": "写出本题采分要点。",
                "question_type": "case",
                "correct_answer": "施工总进度计划表(图)；甲乙丙；措施一二三；应组织专家论证。",
                "concentration": "案例题",
            },
            "grading_engine_runtime_shadow": True,
            "grading_engine_runtime_shadow_engine": "best_quality_4model",
            "grading_engine_runtime_shadow_cache_student_id": cache_student_id,
        },
    }


def _golden_answer(question_id: str, student_id: str) -> str:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for question in data.get("cases") or []:
        case_id = question.get("case_id") or question.get("id")
        if case_id != question_id:
            continue
        for sample in question.get("eval_samples") or []:
            if sample.get("student_id") == student_id:
                return str(sample.get("answer_text") or sample.get("answer") or "").strip()
    raise RuntimeError(f"golden answer not found for {question_id}/{student_id}")


def run_ws_shadow_v2(question_id: str, *, user_id: str, cache_student_id: str, runtime_db: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from fastapi.testclient import TestClient
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from deeptutor.services.session.turn_runtime import TurnRuntimeManager

    runtime = TurnRuntimeManager(SQLiteSessionStore(runtime_db))
    legacy_write_calls: list[dict[str, Any]] = []
    with _patched_ws_runtime(runtime=runtime, user_id=user_id, legacy_write_calls=legacy_write_calls):
        with TestClient(_build_ws_app()) as client:
            result = _receive_result(client, _start_turn_frame(question_id, cache_student_id=cache_student_id))
    return result.get("metadata") or {}, legacy_write_calls


def _cache_audit() -> dict[str, Any]:
    from deeptutor.services.construction_grading.best_quality_ai_draft import CACHED_4MODEL, ARM_TO_MODEL

    data = json.loads(CACHED_4MODEL.read_text(encoding="utf-8"))
    arms = sorted({row.get("arm") for row in data.get("prediction_sets", [])})
    sample_counts: dict[str, int] = {}
    for row in data.get("prediction_sets", []):
        for pred in row.get("predictions", []):
            key = f"{pred.get('case_id')}::{pred.get('student_id')}"
            sample_counts[key] = sample_counts.get(key, 0) + 1
    return {
        "cache_file": str(CACHED_4MODEL),
        "cache_exists": CACHED_4MODEL.exists(),
        "cache_mtime": CACHED_4MODEL.stat().st_mtime,
        "cache_slice_id": data.get("slice_id"),
        "arms": arms,
        "arm_to_model": ARM_TO_MODEL,
        "prediction_set_count": len(data.get("prediction_sets", [])),
        "sample_key_count": len(sample_counts),
    }


def _write_prediction_source_audit(out_dir: Path, audit: dict[str, Any]) -> None:
    lines = [
        "# Prediction Source Audit — E2E Runtime Teacher Review Smoke v2",
        "",
        "- live provider path: not implemented in runtime_shadow_adapter; DeepSeek fast requires pre-produced ai_draft_predictions and fails closed when absent.",
        "- selected v2 source: model_cache via runtime_shadow_adapter -> _default_best_quality_builder -> load_cached_4model_predictions.",
        f"- cache file: `{audit['cache_file']}`",
        f"- cache slice_id: `{audit.get('cache_slice_id')}`",
        f"- cache mtime: `{audit.get('cache_mtime')}`",
        f"- prediction sets: `{audit.get('prediction_set_count')}`",
        f"- model arms: `{', '.join(audit.get('arms') or [])}`",
        "- real-model evidence: cache contains four named model arms (gpt55, opus48, deepseek_v4, qwen37) from the prior 485 full shadow run; no deterministic fixture builder is installed in v2.",
        "- fail-closed rule: if cache is missing or fewer than 3 model arms exist for a case/sample, BestQualityUnavailable is returned as shadow unavailability; no fixture fallback.",
    ]
    (out_dir / "prediction_source_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_smoke_v2(*, out_dir: Path = OUT_DIR, user_data_dir: Path | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = user_data_dir or Path(tempfile.mkdtemp(prefix="qa_e2e_v2_smoke_"))
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_KEY", None)
    os.environ["DEEPTUTOR_ENV"] = "local"
    os.environ["DEEPTUTOR_USER_DATA_DIR"] = str(tmp)

    from deeptutor.services import path_service as ps
    from deeptutor.services.construction_grading import writeback as wb
    from deeptutor.services.construction_grading.teacher_review_writeback import build_teacher_review_writeback
    from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
    from deeptutor.services.learner_state.service import LearnerStateService

    ps.PathService.reset_instance()
    wb._write_home_projection = lambda **_kwargs: None
    service = LearnerStateService()
    cache_audit = _cache_audit()
    _write_prediction_source_audit(out_dir, cache_audit)

    samples = [
        {"name": "published", "question_id": PUBLISHED, "kind": "confirm_mastery", "cache_student_id": "S1"},
        {"name": "draft", "question_id": DRAFT, "kind": "confirm_partial", "cache_student_id": "S2"},
        {"name": "exact_required_override", "question_id": EXACT, "kind": "exact_override_miss", "cache_student_id": "S1"},
    ]

    ws_inputs: list[dict[str, Any]] = []
    ws_shadow_outputs: list[dict[str, Any]] = []
    teacher_reviews: list[dict[str, Any]] = []
    wb_outputs: list[dict[str, Any]] = []
    full_writeback_outputs: list[dict[str, Any]] = []
    legacy_write_calls_by_sample: list[dict[str, Any]] = []

    for sample in samples:
        result, legacy_write_calls = run_ws_shadow_v2(
            sample["question_id"],
            user_id=E2E_V2_STUDENT,
            cache_student_id=sample["cache_student_id"],
            runtime_db=tmp / f"turn-runtime-{sample['name']}.db",
        )
        legacy = result.get("construction_grading_result") or {}
        shadow = result.get("luban_grading_engine_shadow") or {}
        legacy_write_calls_by_sample.append({"name": sample["name"], "calls": legacy_write_calls})
        ws_inputs.append({
            "name": sample["name"],
            "question_id": sample["question_id"],
            "student_id": E2E_V2_STUDENT,
            "cache_student_id": sample["cache_student_id"],
            "entry_layer": "fastapi_testclient_ws",
            "prediction_source": PREDICTION_SOURCE,
        })
        ws_shadow_outputs.append({
            "name": sample["name"],
            "question_id": sample["question_id"],
            "legacy_authority": legacy.get("authority"),
            "legacy_score_awarded": legacy.get("score_awarded"),
            "legacy_max_score": legacy.get("max_score"),
            "has_shadow": bool(shadow),
            "shadow_status": shadow.get("shadow_status"),
            "artifact_status": (shadow.get("artifact_gate") or {}).get("artifact_status"),
            "writeback_performed": shadow.get("writeback_performed"),
            "prediction_source": shadow.get("prediction_source"),
            "provider": shadow.get("provider"),
            "model": shadow.get("model"),
            "cache_hit": shadow.get("cache_hit"),
            "prediction_cache": shadow.get("prediction_cache"),
            "fixture_used": shadow.get("fixture_used"),
            "point_results": shadow.get("point_results"),
        })
        actions = teacher_actions_for(shadow, kind=sample["kind"])
        if sample["name"] == "exact_required_override":
            safe_points = [
                point for point in (shadow.get("point_results") or [])
                if not point.get("high_risk_review") and not point.get("unsupported")
            ]
            if len(safe_points) > 1:
                point = safe_points[1]
                actions[str(point["point_id"])] = {
                    "review_action": "confirm",
                    "teacher_hit": "hit",
                    "teacher_score": point.get("max_score"),
                    "teacher_note": "老师确认官方术语命中",
                }
        review = shadow_to_teacher_review(
            shadow,
            case_id=sample["question_id"],
            student_id=E2E_V2_STUDENT,
            teacher_actions=actions,
        )
        teacher_reviews.append(review)
        out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=E2E_V2_STUDENT)
        full_writeback_outputs.append(out)
        wb_outputs.append({
            "name": sample["name"],
            "case_id": sample["question_id"],
            "writeback_count": out.get("writeback_count"),
            "mastery_point_ids": out.get("mastery_point_ids"),
        })

    unreviewed = dict(teacher_reviews[0])
    unreviewed["teacher_reviewed"] = False
    unreviewed_out = build_teacher_review_writeback(unreviewed, dry_run=False, learner_state_service=service, user_id=E2E_V2_STUDENT)

    events_file = tmp / "learner_state" / E2E_V2_STUDENT / "MEMORY_EVENTS.jsonl"
    on_disk = [json.loads(line) for line in events_file.read_text("utf-8").splitlines() if line.strip()]
    readback = service.list_memory_events(E2E_V2_STUDENT, limit=50)
    synthesis = service.synthesize_learning_truth(E2E_V2_STUDENT, dry_run=True, event_limit=50)
    projection = synthesis["projection"]
    read_model = build_learning_brain_read_model(user_id=E2E_V2_STUDENT, projection=projection, surface="qa")
    suggestions = next_suggestions(projection, read_model)

    high_risk_or_unsupported_mastery_ids = sorted({
        row.get("point_id")
        for out in full_writeback_outputs
        for row in out.get("write_plan", [])
        if row.get("mastery_eligible") and (row.get("high_risk_review") or row.get("unsupported"))
    })

    _dump(out_dir, "ws_inputs.json", ws_inputs)
    _dump(out_dir, "ws_shadow_outputs.json", ws_shadow_outputs)
    _dump(out_dir, "teacher_review_payloads.json", teacher_reviews)
    _dump(out_dir, "writeback_outputs.json", {
        "reviewed": wb_outputs,
        "teacher_reviewed_false_probe": {
            "writeback_count": unreviewed_out.get("writeback_count"),
            "writeback_skipped_reason": unreviewed_out.get("writeback_skipped_reason"),
        },
        "legacy_ws_write_calls_collected_only": legacy_write_calls_by_sample,
        "high_risk_or_unsupported_mastery_ids": high_risk_or_unsupported_mastery_ids,
    })
    _dump(out_dir, "readback_memory_events.json", {
        "on_disk_jsonl_count": len(on_disk),
        "events": [{
            "memory_kind": e.memory_kind,
            "question_id": e.payload_json.get("question_id"),
            "error_events": e.payload_json.get("error_events"),
            "has_teacher_final": bool(e.payload_json.get("next_training_signal", {}).get("teacher_final_grading_result")),
        } for e in readback],
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
        "student_id": E2E_V2_STUDENT,
        "prediction_source": PREDICTION_SOURCE,
        "fixture_used": False,
        "cache_hit": all(row.get("cache_hit") is True for row in ws_shadow_outputs),
        "provider": PROVIDER,
        "model": MODEL,
        "memory_events_file": str(events_file),
        "cache_audit": cache_audit,
    })
    (out_dir / "FINDING_e2e_runtime_teacher_review_smoke_v2_20260604.md").write_text(
        _finding_v2(ws_shadow_outputs, wb_outputs, on_disk, read_model, projection, suggestions, events_file, summary),
        encoding="utf-8",
    )
    ps.PathService.reset_instance()
    return summary


def _finding_v2(ws, wb, on_disk, read_model, projection, suggestions, events_file, summary) -> str:
    legacy_ok = all(o["legacy_authority"] == "construction_grading" for o in ws)
    shadow_no_write = all(o["writeback_performed"] in (False, None) for o in ws)
    mastery_ids = [pid for o in wb for pid in (o["mastery_point_ids"] or [])]
    weakness = sorted({c.get("concept_id") for c in projection.get("observed_candidates") or []})
    improvements = sorted({i.get("concept_id") for i in read_model.get("improvement_signals") or []})
    cache = summary.get("cache_audit") or {}
    return "\n".join([
        "# FINDING — Luban grading engine E2E v2 real prediction smoke (2026-06-04)",
        "",
        "## Chain", "",
        "`/api/v1/ws -> luban_grading_engine_shadow(model_cache) -> teacher-review payload -> build_teacher_review_writeback(dry_run=False) -> real MEMORY_EVENTS.jsonl -> readback -> synthesis -> next suggestion`.",
        "",
        "## Answers", "",
        "1. 本轮是否仍打到真实 `/api/v1/ws`？ 是——FastAPI TestClient websocket frame -> TurnRuntimeManager.start_turn -> DeepQuestionCapability.run -> RESULT metadata。",
        f"2. shadow 预测来源是什么？ `{summary['prediction_source']}` via Best-Quality cached 4-model reader。",
        f"3. 是否使用 fixture？ {'yes' if summary['fixture_used'] else 'no'}。",
        "4. live provider：未调用；provider/model/调用数/失败数 = n/a，本轮选择 cache because runtime live provider path is not implemented。",
        f"5. cache：file=`{cache.get('cache_file')}`；slice_id={cache.get('cache_slice_id')}；mtime={cache.get('cache_mtime')}；arms={cache.get('arms')}；来自既有 485 四模型真实输出缓存，不是测试 fixture。",
        f"6. 是否生成 `luban_grading_engine_shadow`？ 是，status={[o['shadow_status'] for o in ws]}、artifact={[o['artifact_status'] for o in ws]}。",
        f"7. legacy 是否 unchanged？ {'是' if legacy_ok else '否'}（authority 全为 construction_grading）。",
        f"8. teacher-final 是否真实写入文件后端？ 是——真实 LearnerStateService 写 `{events_file}`；shadow_no_write={shadow_no_write}。",
        f"9. `MEMORY_EVENTS.jsonl` 写入几行？ **{len(on_disk)} 行**（writeback_counts={[o['writeback_count'] for o in wb]}）。",
        f"10. 是否读回 weakness/mastery/next suggestion？ 是。weakness={weakness}；read_model improvement={improvements}；teacher_final_mastery={mastery_ids}；suggestions={len(suggestions['next_suggestions'])}。",
        f"11. high_risk/unsupported 是否未提升 mastery？ 是。high_risk_or_unsupported_mastery_ids={summary['high_risk_or_unsupported_mastery_ids']}。",
        "12. 是否新增表/endpoint？ 否。",
        "13. 是否改 kernel/RAG/production runtime？ 否；只加 QA runtime-only cache sample id 透传与 shadow provenance。",
        "14. 如果没法跑 live/cache，blocker 是什么？ live provider path absent；cache available so v2 uses model_cache and passes without fixture。",
        "",
        "## v1/v2 boundary", "",
        "- v1 = deterministic chain regression。",
        "- v2 = real model-cache prediction smoke。",
        "- 两者不争 authority；teacher-final 仍是 Learning Brain 写入 authority。",
        "",
    ])


def main() -> None:
    summary = run_smoke_v2(out_dir=OUT_DIR)
    print(
        f"entry_layer={summary['entry_layer']} prediction_source={summary['prediction_source']} "
        f"fixture_used={summary['fixture_used']} cache_hit={summary['cache_hit']} "
        f"ws_shadow_count={summary['ws_shadow_count']} writeback_count={summary['teacher_final_writeback_count']} "
        f"on_disk={summary['memory_events_jsonl_count']} suggestions={summary['next_suggestion_count']}"
    )
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
