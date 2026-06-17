from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_luban_e2e_runtime_teacher_review_smoke_v2 import E2E_V2_STUDENT, run_smoke_v2


def test_luban_e2e_v2_uses_real_model_cache_not_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "artifact"
    user_data_dir = tmp_path / "user-data"

    summary = run_smoke_v2(out_dir=out_dir, user_data_dir=user_data_dir)

    assert summary["entry_layer"] == "fastapi_testclient_ws"
    assert summary["student_id"] == E2E_V2_STUDENT
    assert summary["prediction_source"] == "model_cache"
    assert summary["fixture_used"] is False
    assert summary["cache_hit"] is True
    assert summary["provider"] == "cached_4model_jury"
    assert summary["model"] == "gpt55+opus48+deepseek_v4+qwen37"
    assert summary["ws_shadow_count"] == 3
    assert summary["legacy_unchanged"] is True
    assert summary["shadow_writeback_performed"] is False
    assert summary["teacher_final_writeback_count"] == 3
    assert summary["memory_events_jsonl_count"] == 3
    assert summary["has_weakness"] is True
    assert summary["has_mastery"] is True
    assert summary["has_next_suggestion"] is True
    assert summary["high_risk_or_unsupported_mastery_ids"] == []

    events_file = user_data_dir / "learner_state" / E2E_V2_STUDENT / "MEMORY_EVENTS.jsonl"
    rows = [json.loads(line) for line in events_file.read_text("utf-8").splitlines() if line.strip()]
    assert len(rows) == 3
    assert all(
        row["payload_json"]["next_training_signal"]["teacher_final_grading_result"]["teacher_reviewed"]
        for row in rows
    )

    ws_outputs = json.loads((out_dir / "ws_shadow_outputs.json").read_text("utf-8"))
    assert [row["artifact_status"] for row in ws_outputs] == ["published", "draft", "published"]
    assert all(row["prediction_source"] == "model_cache" for row in ws_outputs)
    assert all(row["fixture_used"] is False for row in ws_outputs)
    assert all(row["cache_hit"] is True for row in ws_outputs)

    audit = (out_dir / "prediction_source_audit.md").read_text("utf-8")
    assert "live provider path: not implemented in runtime_shadow_adapter" in audit
    assert "cache file" in audit
