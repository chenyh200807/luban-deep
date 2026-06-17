from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_luban_e2e_runtime_teacher_review_smoke import E2E_STUDENT, run_smoke


def test_luban_e2e_runtime_teacher_review_smoke_uses_ws_and_real_file_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "artifact"
    user_data_dir = tmp_path / "user-data"

    summary = run_smoke(out_dir=out_dir, user_data_dir=user_data_dir)

    assert summary["entry_layer"] == "fastapi_testclient_ws"
    assert summary["student_id"] == E2E_STUDENT
    assert summary["prediction_source"] == "deterministic_fixture_injected_runtime_shadow_adapter"
    assert summary["ws_shadow_count"] == 3
    assert summary["legacy_unchanged"] is True
    assert summary["shadow_writeback_performed"] is False
    assert summary["teacher_final_writeback_count"] == 3
    assert summary["memory_events_jsonl_count"] == 3
    assert summary["has_weakness"] is True
    assert summary["has_next_suggestion"] is True
    # Decision B: artifact gate / high_risk / unsupported only block AI auto-certification;
    # teacher-final override is the higher authority and MAY upgrade mastery, but anything
    # NOT teacher-overridden (confirm / unreviewed) must never become mastery.
    assert summary["non_override_high_risk_or_unsupported_mastery_ids"] == []
    assert summary["unreviewed_high_risk_or_unsupported_mastery_ids"] == []
    assert all(
        item["authority"] == "teacher_override"
        for item in summary["teacher_override_high_risk_or_unsupported_mastery"]
    )
    assert summary["teacher_reviewed_false_writeback_count"] == 0

    events_file = user_data_dir / "learner_state" / E2E_STUDENT / "MEMORY_EVENTS.jsonl"
    assert events_file.exists()
    rows = [json.loads(line) for line in events_file.read_text("utf-8").splitlines() if line.strip()]
    assert len(rows) == 3
    assert {row["memory_kind"] for row in rows} == {"learning_evidence"}
    assert all(
        row["payload_json"]["next_training_signal"]["teacher_final_grading_result"]["teacher_reviewed"]
        for row in rows
    )

    ws_outputs = json.loads((out_dir / "ws_shadow_outputs.json").read_text("utf-8"))
    assert [row["artifact_status"] for row in ws_outputs] == ["published", "draft", "published"]
    assert all(row["has_shadow"] for row in ws_outputs)
    assert all(row["writeback_performed"] is False for row in ws_outputs)

    reviews = json.loads((out_dir / "teacher_review_payloads.json").read_text("utf-8"))
    assert any(
        point["review_action"] == "override"
        and point["teacher_hit"] == "miss"
        and point["teacher_note"] == "未写官方术语，近义不给分"
        for review in reviews
        for point in review["point_reviews"]
    )

    preview = json.loads((out_dir / "next_suggestion_preview.json").read_text("utf-8"))
    assert preview["can_generate_suggestions"] is True
    assert preview["needs_new_table"] is False
