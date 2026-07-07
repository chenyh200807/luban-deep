from __future__ import annotations

from typing import Any

PRODUCT_BEHAVIOR_EVENT_NAMES = frozenset(
    {
        "module_viewed",
        "section_viewed",
        "section_expanded",
        "note_card_suggested",
        "note_card_saved",
        "note_card_rejected",
        "note_action_started",
        "probe_requested_from_note",
        "today_task_rendered",
        "today_task_started",
        "learning_action_started",
        "learning_action_completed",
        "module_returned",
        "module_exited",
        "event_error",
        # 双轮 spike D15（2026-07-02 登记）：交接曝光/变体命中/订阅授权结果。
        # 维度约定: object_type=station|variant|retest, object_id=pack_id|variant_id,
        # result=granted|red_dot|correct|incorrect|"<n>/<N>"。其余 D15 指标复用既有名:
        # 站进入=module_viewed, 档位=learning_action_started(start_training,
        # object_id="<pack>:<tier>"), 站完成/复测完成=learning_action_completed。
        # practice_mode 判别位（2026-07-07 登记，spike 命门）：变体练题两取题模式
        # (forward=学习轮当天正向轻练 / review=复习轮次日换皮复测) 在埋点里必须可分——
        # 否则 D1 留存(GO 门=人次日回来做换皮复测)读不出。给 retest_item_answered /
        # learning_action_completed(object_type=retest) 加 property practice_mode,
        # 不新造事件名。
        "handoff_rendered",
        "retest_item_answered",
        "subscribe_prompt_result",
    }
)

# practice_mode 允许值(register-before-use，单一 authority)：forward=学习轮 2 分钟
# 正向轻练(build_retest_items mode=forward)、review=复习轮次日换皮复测(mode=review)。
# 与 read_model.build_retest_items 的 mode 同口径;白名单外值 ingest 拒收(防拼写漂移)。
PRODUCT_BEHAVIOR_PRACTICE_MODES = frozenset({"forward", "review"})

PRODUCT_BEHAVIOR_MODULES = frozenset(
    {
        "learning",
        "history",
        "chat",
        "learning_report",
        "notebook",
        "practice",
        "assessment",
        "profile",
    }
)

LEARNING_REPORT_SECTIONS = frozenset(
    {
        "current_state",
        "why",
        "next_action",
        "evidence",
        "note_assets",
        "wrong_items",
        "score_points",
        "weakness_map",
        "trend",
        "study_plan",
        "retest",
        "today_tasks",
    }
)

PRODUCT_BEHAVIOR_ACTIONS = frozenset(
    {
        "view",
        "expand",
        "open_detail",
        "render",
        "suggest",
        "start_training",
        "start_review",
        "start_retest",
        "start_probe",
        "save_note",
        "reject",
        "dismiss",
        "return",
        "complete",
        "error",
    }
)

ALLOWED_SURFACES = frozenset({"web", "wechat_miniprogram", "wechat_yousenwebview"})

FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS = frozenset(
    {
        "password",
        "verification_code",
        "id_card",
        "bank_card",
        "payment_credential",
        "full_chat_text",
        "full_answer_text",
        "complete_subjective_answer",
    }
)


def find_forbidden_product_behavior_field(value: Any) -> str:
    if isinstance(value, dict):
        forbidden = sorted(set(value) & FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS)
        if forbidden:
            return forbidden[0]
        for item in value.values():
            nested = find_forbidden_product_behavior_field(item)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = find_forbidden_product_behavior_field(item)
            if nested:
                return nested
    return ""


def _clean_string(value: Any, *, max_length: int = 128) -> str:
    return str(value or "").strip()[:max_length]


def validate_product_behavior_event(event_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    normalized_event = _clean_string(event_name, max_length=64)
    if normalized_event not in PRODUCT_BEHAVIOR_EVENT_NAMES:
        raise ValueError(f"Unsupported product behavior event_name: {event_name!r}")

    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    forbidden = find_forbidden_product_behavior_field(metadata)
    if forbidden:
        raise ValueError(f"Forbidden product behavior field: {forbidden}")

    module = _clean_string(metadata.get("module"), max_length=64)
    if module not in PRODUCT_BEHAVIOR_MODULES:
        raise ValueError(f"Unsupported module: {module!r}")

    action = _clean_string(metadata.get("action"), max_length=64)
    if action not in PRODUCT_BEHAVIOR_ACTIONS:
        raise ValueError(f"Unsupported action: {action!r}")

    surface = _clean_string(metadata.get("surface"), max_length=64)
    if surface and surface not in ALLOWED_SURFACES:
        raise ValueError(f"Unsupported surface: {surface!r}")

    section = _clean_string(metadata.get("section"), max_length=64)
    if module == "learning_report" and section and section not in LEARNING_REPORT_SECTIONS:
        raise ValueError(f"Unsupported learning_report section: {section!r}")

    visit_id = _clean_string(metadata.get("visit_id"), max_length=128)
    if not visit_id and normalized_event != "event_error":
        raise ValueError("visit_id is required for product behavior events")

    practice_mode = _clean_string(metadata.get("practice_mode"), max_length=32)
    if practice_mode and practice_mode not in PRODUCT_BEHAVIOR_PRACTICE_MODES:
        raise ValueError(f"Unsupported practice_mode: {practice_mode!r}")

    return {
        "event_name": normalized_event,
        "visit_id": visit_id,
        "module": module,
        "section": section,
        "action": action,
        "surface": surface,
        "practice_mode": practice_mode,
        "object_type": _clean_string(metadata.get("object_type"), max_length=64),
        "object_id": _clean_string(metadata.get("object_id"), max_length=128),
        "entry_source": _clean_string(metadata.get("entry_source"), max_length=64),
        "referrer_module": _clean_string(metadata.get("referrer_module"), max_length=64),
        "duration_ms": int(metadata.get("duration_ms") or 0),
        "visible_ms": int(metadata.get("visible_ms") or 0),
        "result": _clean_string(metadata.get("result"), max_length=64),
        "error_code": _clean_string(metadata.get("error_code"), max_length=64),
        "release_id": _clean_string(metadata.get("release_id"), max_length=128),
        "app_version": _clean_string(metadata.get("app_version"), max_length=64),
        "platform": _clean_string(metadata.get("platform"), max_length=64),
        "device_model": _clean_string(metadata.get("device_model"), max_length=128),
        "network_type": _clean_string(metadata.get("network_type"), max_length=64),
    }
