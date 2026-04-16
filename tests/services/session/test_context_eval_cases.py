from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.session.context_router import ContextRouteInput, decide_context_route


def test_context_orchestration_eval_cases_cover_expected_routes() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2] / "fixtures" / "context_orchestration_eval_cases.json"
    )
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert len(cases) >= 8
    for case in cases:
        decision = decide_context_route(
            ContextRouteInput(
                user_message=case["user_message"],
                has_active_question=bool(case.get("has_active_question", False)),
                has_active_plan=bool(case.get("has_active_plan", False)),
                notebook_references=tuple(case.get("notebook_references", []) or []),
                history_references=tuple(case.get("history_references", []) or []),
                personal_recall_hint=bool(case.get("personal_recall_hint", False)),
            )
        )
        assert decision.route_label == case["expected_route"], case["name"]
