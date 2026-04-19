from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.semantic_router import resolve_question_semantic_routing
from deeptutor.services.question_followup import (
    looks_like_question_followup,
    resolve_submission_attempt,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


@pytest.mark.asyncio
async def test_semantic_router_eval_cases_cover_expected_decisions() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "semantic_router_eval_cases.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert len(cases) >= 6

    for case in cases:
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

        assert (
            routing.turn_semantic_decision["relation_to_active_object"]
            == case["expected_relation"]
        ), case["name"]
        assert (
            routing.turn_semantic_decision["next_action"]
            == case["expected_next_action"]
        ), case["name"]
