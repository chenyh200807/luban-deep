"""学员主动信号写入：subjective_focus / user_dispute（+ plan_preference 意志族）。

写 ``memory_kind="learning_evidence"``（``supabase_writer._supports_event_type``
白名单已含，零改）+ ``source_feature="learner_signal"``。后者是关键不变量守卫：
``_is_learning_evidence`` 要求 ``source_feature ∈ {construction_grading,
assessment_testset}``，故 learner_signal 事件被**排除在证据编译器之外**（守"编译严"
/"关注不进证据编译器"），但读侧（``subjective_focus_projection`` /
``dispute_candidates_from_events`` 按 ``payload.learning_signal_type``）照常消费。

这一处把已合的读侧（Stage1/Stage3）从 inert 点亮为真功能。

plan_preference 意志族（AI 学习计划体系计划 §3.1/§3.3，意志通道收敛——禁四通道
并存）：``pin`` / ``defer`` / ``time_budget`` 同走本唯一写器、同一 source_feature，
天然被 ``evidence_lifecycle.is_learning_evidence_record`` 排除——学员意志作用于
排序与日程，**绝不进掌握度/得分**。复习任务的 defer（带 ``probe_id``）由
``revalidation_queue.declined_probe_ids_from_events`` 落到既有 declined 机制，
不另记状态。灰度：``LUBAN_EXAM_PREP_PLAN_ENABLED``（register-before-use，
旗标关 = 与收权前逐字节同行为，该三类被拒）。命名纪律：禁 ``learning_plan_*``
前缀（Guided Learning 已占）。
"""
from __future__ import annotations

import os
from typing import Any

from deeptutor.services.runtime_env import env_flag

SOURCE_FEATURE = "learner_signal"
_SIGNAL_TYPES = frozenset({"subjective_focus", "user_dispute"})
# station_completed: 站点完成(交接时刻/复测完成)——复习到期调度的触发事实
# (concept_id=pack_id)。仍非 promoting: 不写掌握、不进证据编译器。
# 在复习模块灰度旗标后(register-before-use): 旗标关 = 与收权前逐字节同行为(该类型被拒)。
_STATION_COMPLETED_SIGNAL = "station_completed"
_REVIEW_MODULE_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
# plan_preference 意志族(计划 §3.1): 学员意志=排序/日程输入, 非证据。
PLAN_PREFERENCE_SIGNAL_TYPES = frozenset({"pin", "defer", "time_budget"})
_EXAM_PREP_PLAN_FLAG = "LUBAN_EXAM_PREP_PLAN_ENABLED"
_TIME_BUDGET_MAX_MINUTES = 600
_USER_SAYS = frozenset({"mastered", "not_mastered"})


def _review_module_enabled() -> bool:
    return str(os.getenv(_REVIEW_MODULE_FLAG, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def record_learner_signal(
    learner_state_service: Any,
    *,
    user_id: str,
    signal_type: str,
    concept_id: str = "",
    concept_label: str = "",
    error_code: str = "",
    ability_dimension: str = "",
    user_says: str = "",
    completion_id: str = "",
    practice_mode: str = "",
    training_intent_id: str = "",
    probe_id: str = "",
    time_budget_minutes: int = 0,
) -> Any:
    """追加一条学员主动信号事件，返回写入的事件。

    A 层（关注/订正）：绝不直接写掌握；user_dispute 双向触发复测、不置 mastered。
    plan_preference（pin/defer/time_budget）：意志输入，绝不进证据编译器/掌握度。
    """
    signal = str(signal_type or "").strip()
    allowed = (
        _SIGNAL_TYPES
        | ({_STATION_COMPLETED_SIGNAL} if _review_module_enabled() else frozenset())
        | (PLAN_PREFERENCE_SIGNAL_TYPES if env_flag(_EXAM_PREP_PLAN_FLAG) else frozenset())
    )
    if signal not in allowed:
        raise ValueError(f"unsupported learner signal_type: {signal_type!r}")
    cid = str(concept_id or "").strip()
    # time_budget 是全局日程意志(每天 N 分钟), 无 concept 目标, concept_id 可空。
    if not cid and signal != "time_budget":
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
    if signal == "defer":
        # 复习任务的 defer 带 probe_id → declined 机制唯一入口(读侧
        # declined_probe_ids_from_events); 非复习任务 defer 无 probe_id,
        # 由 exam_prep_plan 读面承载。
        normalized_probe = str(probe_id or "").strip()
        if normalized_probe:
            payload["probe_id"] = normalized_probe
    if signal == "time_budget":
        try:
            minutes = int(time_budget_minutes)
        except (TypeError, ValueError):
            minutes = 0
        if not 1 <= minutes <= _TIME_BUDGET_MAX_MINUTES:
            raise ValueError(
                f"time_budget_minutes must be 1..{_TIME_BUDGET_MAX_MINUTES}"
            )
        payload["time_budget_minutes"] = minutes

    completion = str(completion_id or "").strip()
    if signal == _STATION_COMPLETED_SIGNAL:
        if not completion:
            raise ValueError("completion_id is required for station_completed")
        payload.update({
            "completion_id": completion,
            "practice_mode": str(practice_mode or "").strip(),
            "training_intent_id": str(training_intent_id or "").strip(),
            "probe_id": str(probe_id or "").strip(),
        })

    source_cid = cid or "global"
    return learner_state_service.append_memory_event(
        normalized_user,
        source_feature=SOURCE_FEATURE,
        source_id=f"{signal}:{source_cid}:{completion}" if completion else f"{signal}:{source_cid}",
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key=(
            f"learner_signal:{normalized_user}:{signal}:{source_cid}:{completion}"
            if completion
            else None
        ),
    )


__all__ = ["PLAN_PREFERENCE_SIGNAL_TYPES", "record_learner_signal", "SOURCE_FEATURE"]
