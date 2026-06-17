from __future__ import annotations

from deeptutor.core.trace import build_trace_metadata, derive_trace_metadata


def test_build_trace_metadata_ignores_blank_trace_fields() -> None:
    metadata = build_trace_metadata(
        call_id="call-1",
        phase="phase",
        label="label",
        call_kind="llm",
        trace_id="",
        trace_role="",
        trace_group="",
        trace_kind="",
    )

    assert "trace_id" not in metadata
    assert "trace_role" not in metadata
    assert "trace_group" not in metadata
    assert "trace_kind" not in metadata


def test_derive_trace_metadata_blank_trace_fields_do_not_clear_existing_values() -> None:
    metadata = derive_trace_metadata(
        {
            "trace_id": "old-id",
            "trace_role": "old-role",
            "trace_group": "old-group",
            "trace_kind": "old-kind",
        },
        trace_id="",
        trace_role="",
        trace_group="",
        trace_kind="",
    )

    assert metadata["trace_id"] == "old-id"
    assert metadata["trace_role"] == "old-role"
    assert metadata["trace_group"] == "old-group"
    assert metadata["trace_kind"] == "old-kind"


def test_derive_trace_metadata_preserves_non_trace_falsy_extra_values() -> None:
    metadata = derive_trace_metadata({}, count=0, enabled=False, label="")

    assert metadata["count"] == 0
    assert metadata["enabled"] is False
    assert metadata["label"] == ""
