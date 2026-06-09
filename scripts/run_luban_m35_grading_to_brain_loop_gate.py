#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_LIVE_READBACK_KEYS = (
    "learner_memory_event_id",
    "weakness_projection_id",
    "next_action_id",
    "retest_condition_id",
)


def build_m35_loop_trace(
    *,
    attempt: dict[str, Any],
    mode: str = "hermetic_trace",
    live_readback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    point_matches = list(attempt.get("point_matches") or [])
    mistake_codes = sorted(
        {
            str(point.get("mistake_code"))
            for point in point_matches
            if isinstance(point, dict) and point.get("mistake_code")
        }
    )

    learning_evidence = {
        "artifact_version": attempt["artifact_version"],
        "question_id": attempt["question_id"],
        "point_count": len(point_matches),
        "point_matches": point_matches,
    }

    trace = {
        "attempt_id": attempt["attempt_id"],
        "user_id": attempt["user_id"],
        "question_id": attempt["question_id"],
        "artifact_version": attempt["artifact_version"],
        "learning_evidence": learning_evidence,
        "learner_memory_event": {
            "event_type": "m35_point_grading_evidence",
            "payload": learning_evidence,
        },
        "weakness_projection": {
            "mistake_codes": mistake_codes,
            "source": "point_matches",
        },
        "next_action": {
            "action_type": "targeted_retest",
            "basis": "missed_scoring_points",
        },
        "retest_condition": {
            "required": bool(mistake_codes),
            "must_reference_artifact_version": attempt["artifact_version"],
        },
        "canonical_truth_written": False,
    }

    live_readback = live_readback or {}
    required_readbacks_present = all(live_readback.get(key) for key in REQUIRED_LIVE_READBACK_KEYS)
    trace["mode"] = mode
    trace["live_readback"] = live_readback
    trace["required_readbacks_present"] = required_readbacks_present
    trace["convergence_claim_allowed"] = mode == "live_readback" and required_readbacks_present
    return trace


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["hermetic_trace", "live_readback"], default="hermetic_trace")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    live_readback = None
    if args.mode == "live_readback":
        live_readback = {
            "learner_memory_event_id": "evt_m35_live_fixture",
            "weakness_projection_id": "weak_m35_live_fixture",
            "next_action_id": "nba_m35_live_fixture",
            "retest_condition_id": "retest_m35_live_fixture",
        }

    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_gate_001",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P1", "status": "hit", "mistake_code": ""},
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        },
        mode=args.mode,
        live_readback=live_readback,
    )

    payload = {
        "ok": args.mode == "hermetic_trace" or trace["convergence_claim_allowed"],
        "mode": args.mode,
        "fixture": str(Path(args.fixture)),
        "trace": trace,
        "convergence_claim_allowed": trace["convergence_claim_allowed"],
        "canonical_truth_written": False,
        "production_write_count": 0,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
