#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_luban_agentic_grading_harness import _compact_for_span  # noqa: E402


DEFAULT_PACKET = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_typed_policy_packet.json"
)
DEFAULT_PREDICTIONS = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_predictions_template.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_predictions_span_guarded.json"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _student_answer_index(packet: dict[str, Any]) -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for task in packet.get("tasks") or []:
        index[(str(task.get("case_id")), str(task.get("student_id")))] = str(task.get("student_answer") or "")
    return index


def _span_is_supported(*, span: str, answer: str) -> bool:
    compact_span = _compact_for_span(span)
    if not compact_span:
        return False
    return compact_span in _compact_for_span(answer)


def enforce_span_guard(*, packet_path: Path, predictions_path: Path, output_path: Path) -> dict[str, Any]:
    packet = _read_json(packet_path)
    payload = _read_json(predictions_path)
    answers = _student_answer_index(packet)
    forced: list[dict[str, Any]] = []

    for prediction_set in payload.get("prediction_sets") or []:
        arm = str(prediction_set.get("arm") or "")
        for row in prediction_set.get("predictions") or []:
            hit = str(row.get("hit") or "").strip()
            if hit == "miss":
                row.setdefault("span_guard", {"status": "not_required_for_miss"})
                continue
            key = (str(row.get("case_id")), str(row.get("student_id")))
            answer = answers.get(key, "")
            span = str(row.get("evidence_span") or "")
            if _span_is_supported(span=span, answer=answer):
                row["span_guard"] = {"status": "passed"}
                continue

            original = {
                "arm": arm,
                "case_id": row.get("case_id"),
                "student_id": row.get("student_id"),
                "point_id": row.get("point_id"),
                "original_hit": row.get("hit"),
                "original_score": row.get("score"),
                "evidence_span": row.get("evidence_span"),
            }
            forced.append(original)
            row["span_guard"] = {
                "status": "forced_miss",
                "reason": "evidence_span_not_in_student_answer",
                **original,
            }
            row["hit"] = "miss"
            row["score"] = 0.0
            row["unsupported"] = True
            row["high_risk"] = True
            row["disposition"] = "span_guard_forced_miss"
            row["rationale"] = (
                str(row.get("rationale") or "")
                + " [span_guard: evidence_span not found in student answer; forced to miss/high_risk for shadow gate.]"
            ).strip()

    payload["span_guard_summary"] = {
        "status": "applied",
        "forced_count": len(forced),
        "forced": forced,
        "boundary": "offline_shadow_only_not_runtime",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["span_guard_summary"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce evidence span guard on offline Luban agentic predictions.")
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = enforce_span_guard(packet_path=args.packet, predictions_path=args.predictions, output_path=args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
