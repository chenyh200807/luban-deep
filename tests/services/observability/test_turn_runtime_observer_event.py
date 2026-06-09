from __future__ import annotations

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot
from deeptutor.services.observability.oa_runner import build_oa_run
from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.session.turn_runtime import (
    _append_trace_link_event,
    _build_terminal_turn_observation_event,
    _summarize_assistant_events,
)


_RELEASE = {
    "release_id": "rel-1",
    "git_sha": "abc",
    "deployment_environment": "test",
    "prompt_version": "p1",
    "ff_snapshot_hash": "ff1",
}


def test_terminal_turn_observation_event_keeps_turn_identity_and_usage() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "execution_engine": "tutorbot_runtime",
            "bot_id": "bot-1",
            "context_route": "question_followup",
            "source": "authenticated_ws",
            "user_id": "user-1",
            "trace_id": "trace-1",
            "assistant_content_source": "final_content",
        },
        usage_summary={
            "total_input_tokens": 10,
            "total_output_tokens": 5,
            "total_tokens": 15,
            "total_calls": 2,
        },
    )

    assert event["type"] == "turn_observation"
    assert event["session_id"] == "session-1"
    assert event["turn_id"] == "turn-1"
    assert event["trace_id"] == "trace-1"
    assert event["status"] == "completed"
    assert event["capability"] == "tutorbot"
    assert event["route"] == "question_followup"
    assert event["surface"] == "authenticated_ws"
    assert event["user_id"] == "user-1"
    assert event["latency_ms"] == 1234.5
    assert event["token_total"] == 15
    assert event["metadata"]["source"] == "turn_runtime_terminal"
    assert event["metadata"]["total_calls"] == 2


def test_terminal_turn_observation_event_keeps_latency_stage_breakdown() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "context_route": "question_followup",
            "latency_stages_ms": {
                "context_build": 120.125,
                "capability_stream": 900,
                "negative_noise": -1,
                "bad_noise": "n/a",
            },
        },
        usage_summary={"total_tokens": 15},
    )

    assert event["metadata"]["latency_stages_ms"] == {
        "capability_stream": 900.0,
        "context_build": 120.12,
    }


def test_terminal_turn_observation_event_keeps_context_build_stage_breakdown() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "context_route": "question_followup",
            "context_build_stage_timings_ms": {
                "session_history": 12.345,
                "learner_state": 90,
                "negative_noise": -1,
                "bad_noise": "n/a",
            },
        },
        usage_summary={"total_tokens": 15},
    )

    assert event["metadata"]["context_build_stage_timings_ms"] == {
        "learner_state": 90.0,
        "session_history": 12.35,
    }


def test_terminal_turn_observation_event_keeps_start_turn_setup_stage_breakdown() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "context_route": "question_followup",
            "start_turn_setup_stage_timings_ms": {
                "ensure_session": 45.678,
                "create_turn": 20,
                "negative_noise": -1,
                "bad_noise": "n/a",
            },
        },
        usage_summary={"total_tokens": 15},
    )

    assert event["metadata"]["start_turn_setup_stage_timings_ms"] == {
        "create_turn": 20.0,
        "ensure_session": 45.68,
    }


def test_terminal_turn_observation_event_keeps_capability_stream_breakdown() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "context_route": "question_followup",
            "capability_stream_stage_timings_ms": {
                "first_event": 100.123,
                "first_content": 300,
                "event_persist_total": 25.555,
                "negative_noise": -1,
                "bad_noise": "n/a",
            },
            "capability_stream_event_counts": {
                "content": 2,
                "result": 1,
                "bad_noise": -1,
            },
        },
        usage_summary={"total_tokens": 15},
    )

    assert event["metadata"]["capability_stream_stage_timings_ms"] == {
        "event_persist_total": 25.55,
        "first_content": 300.0,
        "first_event": 100.12,
    }
    assert event["metadata"]["capability_stream_event_counts"] == {
        "content": 2,
        "result": 1,
    }


def test_terminal_turn_observation_event_keeps_llm_stream_telemetry() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "context_route": "question_followup",
            "llm_stream_telemetry": {
                "call_count": 1,
                "calls": [
                    {
                        "call_site": "fast_policy",
                        "provider_name": "openai",
                        "model": "gpt-test",
                        "stream_chunk_count": 3,
                        "stream_content_chunk_count": 2,
                        "stage_timings_ms": {
                            "provider_stream_create": 10.0,
                            "provider_first_chunk": 20.0,
                            "provider_first_content_delta": 21.0,
                            "provider_stream_read": 40.0,
                            "bad_noise": "n/a",
                            "negative_noise": -1,
                        },
                    }
                ],
            },
        },
        usage_summary={"total_tokens": 15},
    )

    assert event["metadata"]["llm_stream_telemetry"] == {
        "call_count": 1,
        "calls": [
            {
                "call_site": "fast_policy",
                "provider_name": "openai",
                "model": "gpt-test",
                "stream_chunk_count": 3,
                "stream_content_chunk_count": 2,
                "stage_timings_ms": {
                    "provider_first_chunk": 20.0,
                    "provider_first_content_delta": 21.0,
                    "provider_stream_create": 10.0,
                    "provider_stream_read": 40.0,
                },
            }
        ],
    }


def test_terminal_turn_observation_event_keeps_bi_identity_resolution_metadata() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=1234.5,
        trace_metadata={
            "execution_engine": "tutorbot_runtime",
            "source": "authenticated_ws",
            "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "raw_user_id": "legacy_chat_user_1",
            "member_user_id": "wx_live_alias",
            "identity_resolution_status": "resolved",
            "identity_resolution_source": "member_console",
            "identity_matched": "legacy_chat_user_1",
        },
        usage_summary={"total_tokens": 15},
    )

    assert event["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert event["metadata"]["raw_user_id"] == "legacy_chat_user_1"
    assert event["metadata"]["member_user_id"] == "wx_live_alias"
    assert event["metadata"]["identity_resolution_status"] == "resolved"
    assert event["metadata"]["identity_resolution_source"] == "member_console"
    assert event["metadata"]["identity_matched"] == "legacy_chat_user_1"
    assert "phone" not in event["metadata"]


def test_trace_link_event_persists_turn_trace_identity_for_feedback() -> None:
    events: list[dict] = []

    _append_trace_link_event(
        events,
        session_id="session-1",
        turn_id="turn-1",
        trace_id="trace-1",
    )

    assert events == [
        {
            "type": "trace_link",
            "source": "turn_runtime",
            "stage": "observability",
            "content": "",
            "metadata": {
                "session_id": "session-1",
                "turn_id": "turn-1",
                "trace_id": "trace-1",
            },
            "session_id": "session-1",
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "visibility": "internal",
        }
    ]


def test_assistant_event_summary_keeps_skill_observability_metadata() -> None:
    summary = _summarize_assistant_events(
        [
            {
                "type": "result",
                "metadata": {
                    "question_lifecycle_scene": "learning_summary",
                    "skill_stack": [
                        "construction-exam-tutor",
                        "construction-learning-evidence-story",
                    ],
                    "skill_trace": [
                        {
                            "name": "construction-learning-evidence-story",
                            "kind": "question_lifecycle",
                            "status": "loaded",
                            "source": "workspace",
                        }
                    ],
                    "loader_source": {"construction-learning-evidence-story": "workspace"},
                    "skill_source_status": {
                        "complete": True,
                        "missing_skills": [],
                        "missing_assets": [],
                    },
                },
            }
        ]
    )

    assert summary["question_lifecycle_scene"] == "learning_summary"
    assert summary["skill_stack"] == [
        "construction-exam-tutor",
        "construction-learning-evidence-story",
    ]
    assert summary["skill_trace"][0]["name"] == "construction-learning-evidence-story"
    assert summary["loader_source"]["construction-learning-evidence-story"] == "workspace"
    assert summary["skill_source_status"]["complete"] is True


def test_assistant_event_summary_keeps_lifecycle_decision_metadata() -> None:
    summary = _summarize_assistant_events(
        [
            {
                "type": "result",
                "metadata": {
                    "metadata": {
                        "question_lifecycle_decision": {
                            "scene": "question_review",
                            "decision_source": "llm",
                            "scene_confidence": 0.86,
                            "required_anchor_status": "satisfied",
                            "exact_question_blocked_reason": "",
                            "selected_skill_names": [
                                "construction-exam-tutor",
                                "construction-question-review",
                            ],
                        },
                        "decision_source": "llm",
                        "scene_confidence": 0.86,
                        "required_anchor_status": "satisfied",
                        "selected_skill_names": [
                            "construction-exam-tutor",
                            "construction-question-review",
                        ],
                        "llm_scene_candidate": {"intended_action": "question_review"},
                        "business_gate_result": {"accepted": True},
                        "question_lifecycle_scene": "question_review",
                    }
                },
            }
        ]
    )

    assert summary["question_lifecycle_decision"]["scene"] == "question_review"
    assert summary["decision_source"] == "llm"
    assert summary["scene_confidence"] == 0.86
    assert summary["required_anchor_status"] == "satisfied"
    assert summary["selected_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-review",
    ]
    assert summary["llm_scene_candidate"] == {"intended_action": "question_review"}
    assert summary["business_gate_result"] == {"accepted": True}


def test_assistant_event_summary_keeps_exact_authority_and_retrieval_metadata() -> None:
    summary = _summarize_assistant_events(
        [
            {
                "type": "result",
                "metadata": {
                    "authority_applied": True,
                    "execution_path": "tutorbot_exact_fast_path",
                    "exact_fast_path_hit": True,
                    "exact_question": {
                        "id": "historical:abc123",
                        "answer_kind": "mcq",
                        "question_type": "multi_choice",
                        "source_group": "historical_question_bank",
                        "correct_answer": "CDE",
                        "metadata": {
                            "source_file": "questions.json",
                            "source_path": "/Users/local/private/questions.json",
                            "content_hash": "hash-1",
                        },
                    },
                    "rag_retrieval_degraded": True,
                    "rag_retrieval_status": "provider_failed_exact_question_resolved",
                    "degraded_mcq_grading_guard_applied": False,
                    "degraded_exact_answer_guard_applied": False,
                },
            }
        ]
    )

    assert summary["authority_applied"] is True
    assert summary["execution_path"] == "tutorbot_exact_fast_path"
    assert summary["exact_fast_path_hit"] is True
    assert summary["exact_question"] == {
        "id": "historical:abc123",
        "answer_kind": "mcq",
        "question_type": "multi_choice",
        "source_group": "historical_question_bank",
        "correct_answer": "CDE",
        "source_file": "questions.json",
        "content_hash": "hash-1",
    }
    assert summary["rag_retrieval_degraded"] is True
    assert summary["rag_retrieval_status"] == "provider_failed_exact_question_resolved"
    assert summary["degraded_mcq_grading_guard_applied"] is False
    assert summary["degraded_exact_answer_guard_applied"] is False
    assert "source_path" not in summary["exact_question"]


def test_terminal_turn_observation_event_keeps_authority_retrieval_summary() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="tutorbot",
        duration_ms=900.0,
        trace_metadata={
            "execution_engine": "tutorbot_runtime",
            "context_route": "mcq_grading",
            "authority_applied": True,
            "exact_fast_path_hit": True,
            "execution_path": "tutorbot_exact_fast_path",
            "exact_question": {
                "id": "historical:abc123",
                "source_group": "historical_question_bank",
                "correct_answer": "CDE",
            },
            "rag_retrieval_degraded": True,
            "rag_retrieval_status": "provider_failed_exact_question_resolved",
            "degraded_mcq_grading_guard_applied": False,
        },
        usage_summary={"total_tokens": 12, "total_calls": 1},
    )

    assert event["metadata"]["authority_applied"] is True
    assert event["metadata"]["exact_fast_path_hit"] is True
    assert event["metadata"]["execution_path"] == "tutorbot_exact_fast_path"
    assert event["metadata"]["exact_question"]["correct_answer"] == "CDE"
    assert event["metadata"]["rag_retrieval_degraded"] is True
    assert event["metadata"]["rag_retrieval_status"] == "provider_failed_exact_question_resolved"
    assert event["metadata"]["degraded_mcq_grading_guard_applied"] is False


def test_terminal_turn_event_flows_to_snapshot_and_oa_via_persisted_latest(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path / "control_plane")
    event_log = TurnEventLog(events_dir=tmp_path / "events")
    event_log.append(
        _build_terminal_turn_observation_event(
            session_id="session-1",
            turn_id="turn-1",
            status="completed",
            capability_name="chat",
            duration_ms=900.0,
            trace_metadata={
                "source": "unified_ws",
                "context_route": "general_learning_query",
                "user_id": "user-1",
            },
            usage_summary={"total_tokens": 12},
        )
    )
    store.write_run(
        kind="om_runs",
        run_id="om-1",
        release_id="rel-1",
        payload={
            "run_id": "om-1",
            "release": _RELEASE,
            "health_summary": {"ready": True, "turn_success_ratio": 1.0},
        },
    )

    observer_payload = build_observer_snapshot(
        store=store,
        event_log=event_log,
        metrics_snapshot={"release": _RELEASE, "readiness": {"ready": True}},
    )
    store.write_run(
        kind="observer_snapshots",
        run_id=observer_payload["run_id"],
        release_id="rel-1",
        payload=observer_payload,
    )
    persisted_observer_payload = store.latest_payload("observer_snapshots")
    oa_payload = build_oa_run(
        mode="incident",
        om_payload=store.latest_payload("om_runs"),
        arr_payload=None,
        aae_payload=None,
        observer_payload=persisted_observer_payload,
    )

    assert persisted_observer_payload is not observer_payload
    assert persisted_observer_payload["turn_events"]["event_count"] == 1
    assert persisted_observer_payload["turn_events"]["status_distribution"]["completed"] == 1
    assert persisted_observer_payload["turn_events"]["error_ratio"] == 0.0
    assert oa_payload["raw_evidence_bundle"]["observer_snapshot_run_id"] == observer_payload["run_id"]
    assert any(item["kind"] == "observer_snapshot" for item in oa_payload["signals"])
