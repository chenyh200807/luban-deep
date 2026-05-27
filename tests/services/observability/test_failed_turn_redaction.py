"""H4 production-feedback connector: failed turn -> PII-safe harness case seed.

Proves the redaction (roadmap C5) drops linkable identifiers and free-text that
can carry user content / PII, while keeping the structural failure signature.
"""

from __future__ import annotations

import json

from deeptutor.services.observability.failed_turn_promotion import (
    _candidate_from_event,
    build_redacted_harness_case_candidate,
    redacted_harness_case_candidates,
)


def _pii_event() -> dict:
    return {
        "session_id": "user-13800138000",
        "turn_id": "turn-secret-abc",
        "trace_id": "trace-secret-xyz",
        "status": "error",
        "capability": "chat",
        "route": "tutorbot",
        "error_type": "RAGTimeout",
        # free-text reason echoing user content + PII:
        "metadata": {"message": "用户张三说手机号是13800138000，问题没答出来"},
    }


def test_redaction_drops_pii_and_identifiers_keeps_structure() -> None:
    candidate = _candidate_from_event(_pii_event(), incident_id="inc-1")
    safe = build_redacted_harness_case_candidate(candidate)
    blob = json.dumps(safe, ensure_ascii=False)

    # No PII / user content survives.
    assert "13800138000" not in blob
    assert "张三" not in blob
    # No linkable identifiers survive.
    assert "secret" not in blob
    assert "user-13800138000" not in blob
    assert "session_id" not in safe and "turn_id" not in safe and "trace_id" not in safe
    assert "reason" not in safe  # free-text reason dropped entirely

    # Structural failure signature retained.
    assert safe["capability"] == "chat"
    assert safe["route"] == "tutorbot"
    assert safe["error_type"] == "RAGTimeout"
    assert safe["status"] == "error"
    assert safe["redacted"] is True
    assert safe["failure_signature"]  # non-empty dedupe key


def test_failure_signature_is_stable_and_shape_specific() -> None:
    a = build_redacted_harness_case_candidate({"capability": "chat", "route": "r", "error_type": "E"})
    b = build_redacted_harness_case_candidate({"capability": "chat", "route": "r", "error_type": "E"})
    c = build_redacted_harness_case_candidate({"capability": "chat", "route": "r", "error_type": "OTHER"})
    assert a["failure_signature"] == b["failure_signature"]
    assert a["failure_signature"] != c["failure_signature"]


def test_batch_mapping_over_incident_report() -> None:
    report = {
        "replay_candidates": [
            _candidate_from_event(_pii_event(), incident_id="inc-1"),
            "not-a-dict",  # ignored
        ]
    }
    seeds = redacted_harness_case_candidates(report)
    assert len(seeds) == 1
    assert seeds[0]["redacted"] is True
    assert "13800138000" not in json.dumps(seeds, ensure_ascii=False)
