"""学员主动信号写入：subjective_focus / user_dispute。

写 ``memory_kind="learning_evidence"``（``supabase_writer._supports_event_type``
白名单已含，零改）+ ``source_feature="learner_signal"``。后者是关键不变量守卫：
``_is_learning_evidence`` 要求 ``source_feature ∈ {construction_grading,
assessment_testset}``，故 learner_signal 事件被**排除在证据编译器之外**（守"编译严"
/"关注不进证据编译器"），但读侧（``subjective_focus_projection`` /
``dispute_candidates_from_events`` 按 ``payload.learning_signal_type``）照常消费。

这一处把已合的读侧（Stage1/Stage3）从 inert 点亮为真功能。
"""
from __future__ import annotations

import os
from typing import Any

SOURCE_FEATURE = "learner_signal"
_SIGNAL_TYPES = frozenset({"subjective_focus", "user_dispute"})
# station_completed: 站点完成(交接时刻/复测完成)——复习到期调度的触发事实
# (concept_id=pack_id)。仍非 promoting: 不写掌握、不进证据编译器。
# 在复习模块灰度旗标后(register-before-use): 旗标关 = 与收权前逐字节同行为(该类型被拒)。
_STATION_COMPLETED_SIGNAL = "station_completed"
_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
_USER_SAYS = frozenset({"mastered", "not_mastered"})


def _review_module_enabled() -> bool:
    return str(os.getenv(_REVIEW_MODULE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def record_learner_signal(
    learner_state_service: Any,
    *,
    user_id: str,
    signal_type: str,
    concept_id: str,
    concept_label: str = "",
    error_code: str = "",
    ability_dimension: str = "",
    user_says: str = "",
) -> Any:
    """追加一条学员主动信号事件，返回写入的事件。

    A 层（关注/订正）：绝不直接写掌握；user_dispute 双向触发复测、不置 mastered。
    """
    signal = str(signal_type or "").strip()
    allowed = _SIGNAL_TYPES | ({_STATION_COMPLETED_SIGNAL} if _review_module_enabled() else frozenset())
    if signal not in allowed:
        raise ValueError(f"unsupported learner signal_type: {signal_type!r}")
    cid = str(concept_id or "").strip()
    if not cid:
        raise ValueError("concept_id is required")
    normalized_user = str(user_id or "").strip()
    if not normalized_user:
        raise ValueError("user_id is required")

    payload: dict[str, Any] = {
        "learning_signal_type": signal,
        "concept_id": cid,
        "concept_label": str(concept_label or "").strip(),
        "error_code": str(error_code or "").strip(),
        "ability_dimension": str(ability_dimension or "").strip(),
    }
    if signal == "user_dispute":
        says = str(user_says or "").strip()
        payload["user_says"] = says if says in _USER_SAYS else "mastered"

    return learner_state_service.append_memory_event(
        normalized_user,
        source_feature=SOURCE_FEATURE,
        source_id=f"{signal}:{cid}",
        memory_kind="learning_evidence",
        payload_json=payload,
    )


__all__ = ["record_learner_signal", "SOURCE_FEATURE"]
