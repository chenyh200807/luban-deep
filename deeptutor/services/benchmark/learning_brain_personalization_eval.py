from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deeptutor.services.learner_state.learning_brain_lint import lint_learning_brain_projection
from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.personalization_context import build_personalization_context_pack


def evaluate_personalization_cases(fixture: Path) -> dict[str, Any]:
    payload = _read_json(fixture)
    cases = [case for case in list(payload.get("cases") or []) if isinstance(case, dict)]
    results = [_evaluate_case(case) for case in cases]
    evidence_required = [item for item in results if item["must_reference_evidence"]]
    evidence_backed = [item for item in evidence_required if item["evidence_backed"]]
    generic_with_evidence = [
        item for item in evidence_required if item["action_type"] in {"generic_encouragement", "starter_action"}
    ]
    unsupported = [item for item in results if item["unsupported_claim"]]
    stale = [item for item in results if item["stale_claim"]]
    hit_count = sum(1 for item in results if item["hit"])
    metrics = {
        "personalization_hit_rate": _rate(hit_count, len(results)),
        "evidence_coverage": _rate(len(evidence_backed), len(evidence_required)) if evidence_required else 1.0,
        "generic_fallback_rate": _rate(len(generic_with_evidence), len(evidence_required)) if evidence_required else 0.0,
        "unsupported_claim_rate": _rate(len(unsupported), len(results)),
        "stale_claim_rate": _rate(len(stale), len(results)),
    }
    return {
        "verdict": "pass"
        if metrics["personalization_hit_rate"] == 1.0
        and metrics["unsupported_claim_rate"] == 0.0
        and metrics["evidence_coverage"] >= 0.95
        and metrics["generic_fallback_rate"] <= 0.05
        else "fail",
        "case_count": len(results),
        "metrics": metrics,
        "results": results,
    }


def evaluate_golden_projection(path: Path) -> dict[str, Any]:
    projection = _read_json(path)
    weak_points = [item for item in list(projection.get("weak_points") or []) if isinstance(item, dict)]
    intents = [
        {
            "training_intent_id": f"golden_{index}",
            "concept_id": str(item.get("concept_id") or "").strip(),
            "error_code": str(item.get("error_code") or "").strip(),
            "evidence_refs": _refs(item.get("evidence_refs")) or _refs(item.get("supporting_event_ids")),
            "status": "active",
        }
        for index, item in enumerate(weak_points, start=1)
    ]
    graph = _graph_chain(projection)
    actions = build_next_best_actions(
        user_id=str(projection.get("user_id") or "golden"),
        training_intents=intents,
        graph_chain=graph,
    )
    evidence_actions = [item for item in actions if _refs(item.get("evidence_refs"))]
    unsupported = [item for item in weak_points if not (_refs(item.get("evidence_refs")) or _refs(item.get("supporting_event_ids")))]
    return {
        "action_count": len(actions),
        "unsupported_claim_rate": _rate(len(unsupported), len(weak_points)),
        "evidence_coverage": _rate(len(evidence_actions), len(actions)) if actions else 1.0,
    }


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    learning_brain = case.get("learning_brain") if isinstance(case.get("learning_brain"), dict) else {}
    active_intent = case.get("active_training_intent") if isinstance(case.get("active_training_intent"), dict) else {}
    authority_context = case.get("authority_context") if isinstance(case.get("authority_context"), dict) else {}
    pack = build_personalization_context_pack(
        user_id=str(case.get("learner_id") or ""),
        learning_brain=learning_brain,
        active_training_intent=active_intent,
    )
    action_type = _classify_action(
        learning_brain=learning_brain,
        active_intent=active_intent,
        authority_context=authority_context,
    )
    evidence_refs = _action_evidence_refs(pack, active_intent, learning_brain)
    issues = lint_learning_brain_projection({
        **learning_brain,
        "next_best_actions": pack.get("next_best_action_candidates"),
    })
    expected_type = str(expected.get("expected_action_type") or "").strip()
    forbidden = {str(item or "").strip() for item in list(expected.get("forbidden_action_types") or [])}
    return {
        "case_id": str(case.get("case_id") or "").strip(),
        "action_type": action_type,
        "expected_action_type": expected_type,
        "hit": action_type == expected_type and action_type not in forbidden,
        "must_reference_evidence": bool(expected.get("must_reference_evidence")),
        "evidence_backed": bool(evidence_refs),
        "unsupported_claim": any(issue.get("code") == "unsupported_claim" for issue in issues),
        "stale_claim": any(issue.get("code") == "stale_claim_needs_retest" for issue in issues),
    }


def _classify_action(
    *,
    learning_brain: dict[str, Any],
    active_intent: dict[str, Any],
    authority_context: dict[str, Any],
) -> str:
    if authority_context.get("exact_question_conflict"):
        return "exact_question_authority"
    if authority_context.get("standard_authority_conflict"):
        return "standard_authority"
    weak_points = [item for item in list(learning_brain.get("weak_points") or []) if isinstance(item, dict)]
    if not weak_points:
        if learning_brain.get("notebook_focus"):
            return "review_saved_note"
        return "starter_action"
    actionable = [item for item in weak_points if not _is_blocked_claim(item)]
    if not actionable:
        if any(str(item.get("claim_status") or "") == "contradicted" for item in weak_points):
            return "review_needed"
        return "maintenance_review"
    top = actionable[0]
    status = str(top.get("claim_status") or "").strip()
    if status == "stale" or (isinstance(top.get("lifecycle"), dict) and top["lifecycle"].get("needs_retest")):
        return "retest_training"
    if str(top.get("evidence_level") or "").strip() == "L3_mastery_signal":
        return "maintenance_review"
    if not active_intent:
        return "create_training_intent_candidate"
    if status == "confirmed":
        return "retest_training"
    return "targeted_practice"


def _is_blocked_claim(item: dict[str, Any]) -> bool:
    status = str(item.get("claim_status") or "").strip()
    return status in {"contradicted", "rejected", "superseded"} or bool(_refs(item.get("conflicting_event_ids")))


def _action_evidence_refs(
    pack: dict[str, Any],
    active_intent: dict[str, Any],
    learning_brain: dict[str, Any],
) -> list[str]:
    refs = _refs(active_intent.get("evidence_refs"))
    for action in list(pack.get("next_best_action_candidates") or []):
        if isinstance(action, dict):
            refs.extend(_refs(action.get("evidence_refs")))
    for weak_point in list(learning_brain.get("weak_points") or []):
        if isinstance(weak_point, dict):
            refs.extend(_refs(weak_point.get("evidence_refs")) or _refs(weak_point.get("supporting_event_ids")))
    return _dedupe(refs)


def _graph_chain(projection: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    graph = projection.get("typed_graph") if isinstance(projection.get("typed_graph"), dict) else {}
    chain: dict[str, list[dict[str, Any]]] = {}
    for edge in list(graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        edge_type = str(edge.get("edge_type") or "").strip()
        if edge_type:
            chain.setdefault(edge_type, []).append(edge)
    return chain


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _refs(value: Any) -> list[str]:
    return [str(item or "").strip() for item in list(value or []) if str(item or "").strip()]


def _dedupe(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Learning Brain personalization eval gate.")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--min-evidence-coverage", type=float, default=0.95)
    parser.add_argument("--max-generic-fallback-rate", type=float, default=0.05)
    args = parser.parse_args(argv)

    result = evaluate_personalization_cases(args.fixture)
    metrics = result["metrics"]
    verdict = result["verdict"]
    if metrics["evidence_coverage"] < args.min_evidence_coverage:
        verdict = "fail"
    if metrics["generic_fallback_rate"] > args.max_generic_fallback_rate:
        verdict = "fail"
    print(
        " ".join(
            [
                f"verdict={verdict}",
                f"case_count={result['case_count']}",
                f"evidence_coverage={metrics['evidence_coverage']:.4f}",
                f"generic_fallback_rate={metrics['generic_fallback_rate']:.4f}",
                f"unsupported_claim_rate={metrics['unsupported_claim_rate']:.4f}",
            ]
        )
    )
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate_golden_projection", "evaluate_personalization_cases"]
