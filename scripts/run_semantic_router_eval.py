#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.question_followup import (
    looks_like_question_followup,
    resolve_submission_attempt,
)
from deeptutor.services.semantic_router import resolve_question_semantic_routing
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "semantic_router_eval_cases.json"
)


async def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    llm_action = case.get("llm_action")
    metadata = dict(case.get("metadata") or {})
    if "active_object" not in metadata and "active_object" in case:
        metadata["active_object"] = case["active_object"]

    async def fake_interpret(
        _message: str,
        _context: dict[str, object] | None,
    ) -> dict[str, object] | None:
        return llm_action

    routing = await resolve_question_semantic_routing(
        user_message=case["user_message"],
        metadata=metadata,
        history_context="",
        interpret_followup_action=fake_interpret,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )
    decision = routing.turn_semantic_decision
    actual_relation = str(decision.get("relation_to_active_object") or "")
    actual_next_action = str(decision.get("next_action") or "")
    active_object = metadata.get("active_object") if isinstance(metadata.get("active_object"), dict) else {}
    object_type = str(active_object.get("object_type") or "")
    passed = (
        actual_relation == case["expected_relation"]
        and actual_next_action == case["expected_next_action"]
    )
    return {
        "name": case["name"],
        "object_type": object_type or "unknown",
        "expected_relation": case["expected_relation"],
        "actual_relation": actual_relation,
        "expected_next_action": case["expected_next_action"],
        "actual_next_action": actual_next_action,
        "passed": passed,
    }


async def _run_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [await _run_case(case) for case in cases]
    by_object_type = Counter(result["object_type"] for result in results)
    by_next_action = Counter(result["actual_next_action"] for result in results)
    failures = [result for result in results if not result["passed"]]
    return {
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "by_object_type": dict(sorted(by_object_type.items())),
        "by_next_action": dict(sorted(by_next_action.items())),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed semantic-router eval set.")
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE),
        help="Path to semantic-router eval fixture JSON.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary instead of plain text.",
    )
    args = parser.parse_args()

    fixture_path = Path(args.fixture).resolve()
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    summary = asyncio.run(_run_cases(cases))

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Semantic Router Eval: total={summary['total']} passed={summary['passed']} failed={summary['failed']}")
        print("By object type:")
        for key, value in summary["by_object_type"].items():
            print(f"  - {key}: {value}")
        print("By next action:")
        for key, value in summary["by_next_action"].items():
            print(f"  - {key}: {value}")
        if summary["failures"]:
            print("Failures:")
            for failure in summary["failures"]:
                print(
                    "  - {name}: expected ({expected_relation}, {expected_next_action}) "
                    "got ({actual_relation}, {actual_next_action})".format(**failure)
                )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
