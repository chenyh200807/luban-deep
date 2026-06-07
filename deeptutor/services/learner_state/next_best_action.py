from __future__ import annotations

from typing import Any

from deeptutor.services.learner_state.training_intent import (
    PRESCRIPTION_AUTHORITY,
    prioritize_training_intents,
)

ACTIONABLE_EDGE_TYPES = frozenset({
    "error_points_to_training",
    "training_uses_question",
    "training_improved_error",
})


def build_next_best_actions(
    *,
    user_id: str,
    training_intents: list[dict[str, Any]] | None,
    graph_chain: dict[str, Any] | None = None,
    max_actions: int = 3,
) -> list[dict[str, Any]]:
    del user_id
    ranked = prioritize_training_intents(training_intents, max_active=max_actions)
    graph = dict(graph_chain or {})
    return [_action_from_intent(intent, graph=graph, index=index) for index, intent in enumerate(ranked[:max_actions])]


def _action_from_intent(intent: dict[str, Any], *, graph: dict[str, Any], index: int) -> dict[str, Any]:
    evidence_refs = _refs(intent.get("evidence_refs")) or _refs(intent.get("attempt_refs"))
    why = _why_this_now(intent, graph=graph, evidence_refs=evidence_refs)
    success_criteria = intent.get("success_criteria") if isinstance(intent.get("success_criteria"), dict) else {}
    requires_revalidation = bool(success_criteria.get("requires_revalidation"))
    return {
        "action_id": f"nba_{index + 1}_{str(intent.get('training_intent_id') or '').strip()}",
        "training_intent_id": str(intent.get("training_intent_id") or "").strip(),
        "source": PRESCRIPTION_AUTHORITY,
        "prescription_authority": PRESCRIPTION_AUTHORITY,
        "status": str(intent.get("status") or "").strip(),
        "title": _title(intent),
        # M32 Task 5: product-facing view fields. They EXPLAIN the prescription (which stays the
        # single authority in training_intent); they never become a second prescription source.
        "action_type": "retest_or_targeted_practice" if requires_revalidation else "diagnostic_probe",
        "target": _target(intent),
        "why_this_now": why,
        "materials": _materials(intent),
        "success_measure": _success_measure(requires_revalidation),
        "evidence_refs": evidence_refs,
        "intent": dict(intent),
    }


def _target(intent: dict[str, Any]) -> str:
    parts = [str(intent.get("concept_label") or "").strip(), str(intent.get("error_label") or "").strip()]
    return " · ".join(part for part in parts if part) or "诊断练习"


def _materials(intent: dict[str, Any]) -> list[str]:
    materials: list[str] = []
    concept = str(intent.get("concept_label") or "").strip()
    error = str(intent.get("error_label") or "").strip()
    if concept:
        materials.append(f"教材：{concept}相关章节")
    materials.append("相似真题")
    if error:
        materials.append(f"错因清单：{error}")
    return materials


def _success_measure(requires_revalidation: bool) -> str:
    if requires_revalidation:
        return "复测命中目标采分点，且不再重复该错误"
    return "完成诊断题，补齐可靠学习证据"


def _title(intent: dict[str, Any]) -> str:
    concept = str(intent.get("concept_label") or "").strip()
    error = str(intent.get("error_label") or "").strip()
    if concept and error:
        return f"先练{concept}：{error}"
    if concept:
        return f"先练{concept}"
    return "先补一题可诊断练习"


def _why_this_now(intent: dict[str, Any], *, graph: dict[str, Any], evidence_refs: list[str]) -> str:
    concept_id = str(intent.get("concept_id") or "").strip()
    error_code = str(intent.get("error_code") or "").strip()
    error_id = f"{concept_id}:{error_code}" if concept_id and error_code else ""
    for edge in list(graph.get("error_points_to_training") or []):
        from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
        if error_id and str(from_node.get("id") or "").strip() == error_id:
            return "真实错因图已把该薄弱点连接到下一轮训练。"
    if evidence_refs:
        return f"该训练意图有 {len(evidence_refs)} 条学习证据支持。"
    return "当前证据不足，先用诊断题补齐可靠学习事实。"


def _refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item or "").strip() for item in list(value or []) if str(item or "").strip()]


__all__ = ["ACTIONABLE_EDGE_TYPES", "build_next_best_actions"]
