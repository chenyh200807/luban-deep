"""learner_state 测试共享工厂（评审项 8：去重 ``_lesson_event`` 复制体）。

唯一构造路径：事件 payload/dedupe_key 一律经真 writer
``record_lesson_view_evidence`` 派生，不手搓形状（防测试假形状漂移，
参照 error_events 教训）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from deeptutor.services.learner_state.lesson_evidence import record_lesson_view_evidence
from deeptutor.services.learner_state.service import LearnerStateEvent


class RecordingLearnerState:
    """最小 append_memory_event 记录桩（只记 kwargs，不判断语义）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def append_memory_event(self, user_id: str, **kwargs: Any) -> Any:
        self.calls.append({"user_id": user_id, **kwargs})
        return type("Event", (), {"event_id": f"evt_{len(self.calls)}", **kwargs})()


def lesson_event(
    event_id: str = "lesson_evt_1",
    *,
    user_id: str = "student_demo",
    pack_id: str = "N01",
    stage: str = "lesson",
    card_sha: str = "sha256:card",
    now: datetime | None = None,
) -> LearnerStateEvent:
    """经真 writer 派生一条学-evidence（lesson_viewed）LearnerStateEvent。"""
    recorder = RecordingLearnerState()
    record_lesson_view_evidence(
        recorder,
        user_id=user_id,
        pack_id=pack_id,
        watched_stage=stage,
        card_sha=card_sha,
        now=now or datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc),
    )
    call = recorder.calls[0]
    return LearnerStateEvent(
        event_id=event_id,
        user_id=user_id,
        source_feature=call["source_feature"],
        source_id=call["source_id"],
        source_bot_id=None,
        memory_kind=call["memory_kind"],
        dedupe_key=call["dedupe_key"],
        created_at="2026-07-03T18:00:00+08:00",
        payload_json=call["payload_json"],
    )


__all__ = ["RecordingLearnerState", "lesson_event"]
