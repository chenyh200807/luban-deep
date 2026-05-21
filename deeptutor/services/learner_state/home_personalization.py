from __future__ import annotations

from typing import Any

from deeptutor.services.learner_state.training_intent import build_learning_training_intent


_STARTER_PROMPTS = {
    "construction_exam_1": ["主体结构验收怎么判断？", "钢筋进场检验有哪些要点？", "防水分类怎么记？"],
    "construction_exam_2": ["主体结构常考点怎么抓？", "材料检验题怎么避坑？", "防水构造题怎么练？"],
}
_PROMPT_TYPES = ["concept_explain", "knowledge_map", "misconception_compare", "practice_prompt", "mistake_review"]


def build_home_dashboard_learning_projection(
    *,
    weak_nodes: list[dict[str, Any]] | None = None,
    conversation_events: list[dict[str, Any]] | None = None,
    subject_id: str = "construction_exam_1",
) -> dict[str, Any]:
    weak = [dict(item) for item in list(weak_nodes or []) if isinstance(item, dict)]
    events = [dict(item) for item in list(conversation_events or []) if isinstance(item, dict)]
    focus_label = _focus_label(weak, events)
    if focus_label:
        intent = build_learning_training_intent(
            user_id="",
            concept_label=focus_label,
            error_label=_error_label(weak, events),
            training_mode="mixed_review",
            source="home_dashboard",
            reason="weak_point_or_recent_confusion",
        )
        prompts = [
            _prompt(focus_label, prompt_type, intent)
            for prompt_type in _PROMPT_TYPES[:4]
        ]
        return {
            "source_status": {"fallback_used": False, "learning_report": "projection"},
            "today_focus": {"title": f"今日焦点：{focus_label}", "meta": intent.get("error_label", ""), "intent": intent},
            "recommended_prompts": prompts,
        }

    starters = _STARTER_PROMPTS.get(str(subject_id or ""), [])
    if not starters:
        intent = build_learning_training_intent(source="home_dashboard", reason="starter", training_mode="mixed_review", user_id="")
        return {
            "source_status": {"fallback_used": True, "learning_report": "stale"},
            "today_focus": {"title": "先做一次摸底测评", "meta": "需要第一份学习证据", "intent": intent},
            "recommended_prompts": [{"prompt_type": "assessment", "text": "先做一次摸底测评", "intent": intent}],
        }
    prompts = []
    for index, text in enumerate(starters[:3]):
        intent = build_learning_training_intent(source="home_dashboard", reason="starter", training_mode="mixed_review", user_id="")
        prompts.append({"prompt_type": "starter", "text": text, "intent": intent})
    return {
        "source_status": {"fallback_used": True, "learning_report": "stale"},
        "today_focus": {"title": "先做一题，给系统第一份学习证据", "meta": "starter", "intent": prompts[0]["intent"]},
        "recommended_prompts": prompts,
    }


def _focus_label(weak: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    for item in weak:
        text = str(item.get("name") or item.get("concept_label") or item.get("concept") or "").strip()
        if text:
            return text
    for item in events:
        concept = item.get("concept") if isinstance(item.get("concept"), dict) else {}
        text = str(concept.get("label") or item.get("concept_label") or "").strip()
        if text:
            return text
    return ""


def _error_label(weak: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    for item in [*weak, *events]:
        text = str(item.get("error_label") or item.get("error") or "").strip()
        if text:
            return text
    return ""


def _prompt(concept: str, prompt_type: str, intent: dict[str, Any]) -> dict[str, Any]:
    text_by_type = {
        "concept_explain": f"把{concept}讲清楚",
        "knowledge_map": f"整理{concept}考点地图",
        "misconception_compare": f"对比{concept}易混淆点",
        "practice_prompt": f"围绕{concept}出 3 道题",
        "mistake_review": f"回看{concept}相关错题",
    }
    return {"prompt_type": prompt_type, "text": text_by_type[prompt_type], "intent": {**intent, "prompt_type": prompt_type}}


__all__ = ["build_home_dashboard_learning_projection"]
