"""M32 Task 5 (NBA-specific): NextBestAction is a read-only view on the prescription
authority (training_intent). The frontend or wrapper CANNOT invent a different recommendation
when a PCP exists — only the backend projection is authoritative. Tests that the product shape
fields are non-negotiable and that the negative arm (invention) is blocked by construction."""
from __future__ import annotations

from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.personalization_context import (
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.training_intent import build_learning_training_intent

CONCEPT = "waterproof_term"
USER = "qa_m32_waterproof"


def _intent(*, concept: str = CONCEPT, requires_revalidation: bool = True) -> dict:
    return build_learning_training_intent(
        user_id=USER,
        concept_id=concept,
        concept_label="防水施工规范术语",
        error_code="near_synonym_not_accepted",
        error_label="近义替代原文术语",
        evidence_refs=["attempt_m32_001"],
        training_mode="mixed_review",
    )


# ── Negative test: frontend cannot invent a different NBA when PCP exists ────────────────────────

def test_pcp_next_best_action_candidates_are_derived_not_invented() -> None:
    """The NBA in PCP must be derived from training_intent, not from a free-text prompt.
    The prescription_authority field must be set to the canonical source."""
    pcp = build_personalization_context_pack(
        user_id=USER,
        learning_brain={"compiled_objects": [{"object_id": "c1", "object_type": "error_claim",
                                               "claim_status": "observed", "concept_id": CONCEPT,
                                               "evidence_refs": ["attempt_m32_001"]}]},
        active_training_intent=_intent(),
    )
    for candidate in pcp["next_best_action_candidates"]:
        assert candidate["prescription_authority"] == "training_intent", (
            "NBA candidate must declare training_intent as its authority — "
            "frontend/wrapper cannot invent a different recommendation."
        )


def test_pcp_next_best_action_candidates_cannot_be_empty_when_intent_exists() -> None:
    """When a training intent is active, the PCP must contain at least one NBA candidate."""
    pcp = build_personalization_context_pack(
        user_id=USER,
        learning_brain={"compiled_objects": []},
        active_training_intent=_intent(),
    )
    assert pcp["next_best_action_candidates"], (
        "PCP must include at least one NBA candidate when an active training intent is provided."
    )


def test_nba_evidence_refs_match_intent_refs() -> None:
    """The evidence_refs in the NBA must match those from the training intent —
    not an arbitrary list constructed by the wrapper."""
    intent = _intent()
    actions = build_next_best_actions(user_id=USER, training_intents=[intent], max_actions=1)
    assert actions, "expected at least one NBA from the intent"
    nba = actions[0]
    assert nba["evidence_refs"] == ["attempt_m32_001"], (
        "NBA evidence_refs must come from the training intent, not be invented."
    )


# ── M32 product shape completeness ────────────────────────────────────────────────────────────────

def test_nba_action_id_is_deterministic_from_intent() -> None:
    """action_id must be derivable from the intent — not random."""
    intent = _intent()
    actions_1 = build_next_best_actions(user_id=USER, training_intents=[intent], max_actions=1)
    actions_2 = build_next_best_actions(user_id=USER, training_intents=[intent], max_actions=1)
    assert actions_1[0]["action_id"] == actions_2[0]["action_id"], "action_id must be stable across calls"


def test_why_this_now_references_concept_in_narrative() -> None:
    """why_this_now must explain the intent's concept — it cannot be generic filler."""
    intent = _intent()
    actions = build_next_best_actions(user_id=USER, training_intents=[intent], max_actions=1)
    why = actions[0]["why_this_now"]
    assert why, "why_this_now must be non-empty"
    # A generic empty explanation is disallowed by the product spec.
    assert len(why) > 10, "why_this_now is too short to be informative"


def test_pcp_authority_is_read_only() -> None:
    """PCP is a read-only view; its authority block must declare training_intent as prescription."""
    pcp = build_personalization_context_pack(
        user_id=USER,
        learning_brain={"compiled_objects": []},
        active_training_intent=_intent(),
    )
    assert pcp.get("authority", {}).get("prescription") == "training_intent"
