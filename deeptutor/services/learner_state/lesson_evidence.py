"""学-evidence 唯一 writer：luban_lesson 观看进度（融合计划 §2.1 v1.1 修正版）。

照 ``learner_signal.py`` 固化的「新非掌握信号」模板执行：
``memory_kind="learning_evidence"``（supabase outbox 白名单已含，零改）+
新 ``source_feature="luban_lesson"``（保持在 ``learning_synthesis._is_learning_evidence``
白名单 **之外**——学-evidence 绝不进证据编译器/claim）+ 只被定向读侧消费
（生命周期投影的「已学·待验证」态）。

契约硬要求（contracts/learner-state.md:397-404）：payload **必须**带
``event_type="learning_evidence"``。带上它的代价 = 两个显式小改（都已做）：
① ``home_personalization`` 的最近事件选择器过滤 ``lesson_viewed``（看动画
不顶替 today_focus）；② ``learning_state_projection`` 给 luban_lesson 显式
分类（不虚高 legacy_count）。

防污染旋钮：``quality.progress_countable=false`` → learning report 的
attempt/streak 聚合与 mastery attempts 归一都跳过——看视频不刷练习数、
不拉低/抬高掌握分（M0 红线：看动画绝不算掌握、绝不进红黄绿）。

``evidence_level="exposed"`` 复用既有 ladder 外 level（conversation 证据
先例）；exposed 故意不在 ``memory_lifecycle.EVIDENCE_LEVEL_RANK`` 里，
接触不参与掌握排序。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

SOURCE_FEATURE = "luban_lesson"
LESSON_VIEWED_SIGNAL = "lesson_viewed"

# 讲懂幕 = lesson（图解微课讲懂卡）；闯关幕 = practice（练习卡）。
WATCHED_STAGES = frozenset({"lesson", "practice"})

_BUSINESS_TZ = timezone(timedelta(hours=8))


def _date_key(now: datetime | None = None) -> str:
    moment = now.astimezone(_BUSINESS_TZ) if now else datetime.now(_BUSINESS_TZ)
    return moment.strftime("%Y-%m-%d")


def record_lesson_view_evidence(
    learner_state_service: Any,
    *,
    user_id: str,
    pack_id: str,
    watched_stage: str,
    card_sha: str = "",
    now: datetime | None = None,
) -> Any:
    """追加一条学-evidence（lesson_viewed），返回写入的事件。

    dedupe 初始方案：按（用户, pack, watched_stage, 日）去重——同日重看同幕
    折叠为一条；跨幕/跨日各自成条（dedupe 语义 = 计划 U2 开放项）。
    """
    normalized_user = str(user_id or "").strip()
    if not normalized_user:
        raise ValueError("user_id is required")
    pack = str(pack_id or "").strip()
    if not pack:
        raise ValueError("pack_id is required")
    stage = str(watched_stage or "").strip()
    if stage not in WATCHED_STAGES:
        raise ValueError(f"unsupported watched_stage: {watched_stage!r}")

    payload: dict[str, Any] = {
        "event_type": "learning_evidence",  # contract 硬要求，不许省
        "learning_signal_type": LESSON_VIEWED_SIGNAL,
        "pack_id": pack,
        "card_sha": str(card_sha or "").strip(),
        "watched_stage": stage,
        "evidence_level": "exposed",  # 既有 ladder 外 level，不发明新 level
        "quality": {"progress_countable": False},  # 唯一必需的防污染旋钮
    }
    return learner_state_service.append_memory_event(
        normalized_user,
        source_feature=SOURCE_FEATURE,
        source_id=f"{LESSON_VIEWED_SIGNAL}:{pack}:{stage}",
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key=f"{LESSON_VIEWED_SIGNAL}:{normalized_user}:{pack}:{stage}:{_date_key(now)}",
    )


def is_lesson_view_event(event: Any) -> bool:
    """定向读侧的统一判别：这条事件是不是学-evidence（lesson_viewed）。"""
    if str(getattr(event, "source_feature", "") or "").strip() != SOURCE_FEATURE:
        return False
    payload = getattr(event, "payload_json", None) or {}
    if not isinstance(payload, dict):
        return False
    return str(payload.get("learning_signal_type") or "").strip() == LESSON_VIEWED_SIGNAL


__all__ = [
    "LESSON_VIEWED_SIGNAL",
    "SOURCE_FEATURE",
    "WATCHED_STAGES",
    "is_lesson_view_event",
    "record_lesson_view_evidence",
]
