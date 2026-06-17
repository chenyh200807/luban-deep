from __future__ import annotations

import json
from typing import Any


PROTOCOL_VERSION = "m35_ai_governed_gold.v1"
LABEL_AUTHORITY = "ai_governed_gold"


def validate_ai_governed_gold_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Validate AI-governed gold label authority.

    The protocol can replace human label authority only as a quality-label gate.
    It never grants release truth, official score, DB writes, or canonical
    learner truth writes.
    """
    blocking_reasons: list[str] = []

    if protocol.get("protocol_version") != PROTOCOL_VERSION:
        blocking_reasons.append("invalid_protocol_version")

    blind_votes = [
        vote for vote in list(protocol.get("blind_model_votes") or [])
        if isinstance(vote, dict)
    ]
    independent_accepts = {
        str(vote.get("model_id") or "").strip()
        for vote in blind_votes
        if vote.get("independent") is True and str(vote.get("verdict") or "") == "accept"
    }
    if len(independent_accepts) < 3:
        blocking_reasons.append("blind_panel_too_small")

    source_anchor = protocol.get("source_anchor") if isinstance(protocol.get("source_anchor"), dict) else {}
    if int(source_anchor.get("source_ref_count") or 0) <= 0 or source_anchor.get("field_level_citations") is not True:
        blocking_reasons.append("source_anchor_missing")

    adversarial = (
        protocol.get("adversarial_review")
        if isinstance(protocol.get("adversarial_review"), dict)
        else {}
    )
    if str(adversarial.get("role") or "") != "adversarial_prosecutor":
        blocking_reasons.append("missing_adversarial_prosecutor")
    if int(adversarial.get("unresolved_objection_count") or 0) > 0:
        blocking_reasons.append("unresolved_adversarial_objections")

    mutation = protocol.get("mutation_test") if isinstance(protocol.get("mutation_test"), dict) else {}
    if mutation.get("passed") is not True or int(mutation.get("case_count") or 0) < 5:
        blocking_reasons.append("mutation_test_not_passed")

    if not str(protocol.get("reproducibility_hash") or "").startswith("sha256:"):
        blocking_reasons.append("reproducibility_hash_missing")

    deterministic_gate = (
        protocol.get("deterministic_gate")
        if isinstance(protocol.get("deterministic_gate"), dict)
        else {}
    )
    if deterministic_gate.get("passed") is not True:
        blocking_reasons.append("deterministic_gate_not_passed")

    valid = not blocking_reasons
    return {
        "valid": valid,
        "label_authority": LABEL_AUTHORITY,
        "quality_claim_allowed": valid,
        "official_score_allowed": False,
        "is_release_truth": False,
        "blocking_reasons": blocking_reasons,
    }


def normalize_deepseek_adversarial_report(
    payload: dict[str, Any],
    *,
    model_id: str,
) -> dict[str, Any]:
    """Normalize DeepSeek-v4-pro prosecutor output as candidate evidence only."""
    return {
        "origin": "deepseek_v4_pro_adversarial",
        "model_id": str(model_id or "").strip(),
        "role": "adversarial_prosecutor",
        "runtime_usable_as_truth": False,
        "promote_to_release": False,
        "source_challenges": list(payload.get("source_challenges") or []),
        "rubric_attacks": list(payload.get("rubric_attacks") or []),
        "suggested_demotions": list(payload.get("suggested_demotions") or []),
        "unresolved_objection_count": int(payload.get("unresolved_objection_count") or 0),
    }


def build_deepseek_adversarial_prompt(
    *,
    question: dict[str, Any],
    artifact: dict[str, Any],
    student_answer: str,
) -> str:
    """Build the DeepSeek-v4-pro adversarial prosecutor prompt."""
    payload = {
        "question": question,
        "scoring_artifact": artifact,
        "student_answer": student_answer,
    }
    return (
        "You are DeepSeek-v4-pro acting as an adversarial prosecutor for M35 grading.\n"
        "You are not the final judge and you must not grant official score or release truth.\n"
        "Attack the rubric, source anchoring, over-grading, slogan answers, near-synonym mistakes, "
        "wrong-path evidence, and unsupported positive matches.\n"
        "Return strict JSON with keys: source_challenges, rubric_attacks, suggested_demotions, "
        "unresolved_objection_count. Do not include markdown.\n\n"
        f"INPUT_JSON={json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )
