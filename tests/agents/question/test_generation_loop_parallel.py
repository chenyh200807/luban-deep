"""2026-08-10 F3 生产事故回归钉:_generation_loop 并发化 + 预算收束部分交付。

事故形态(trace 7c27fcb0):「出10道」走重路径完全串行,180s turn deadline 处决时
q_1..q_8 已生成完毕且合格却被全量丢弃。合同:预算内完成的题必须交付;超预算的
未完成题被取消并以 generation_shortfall typed marker 发声。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator
from deeptutor.agents.question.models import QAPair, QuestionTemplate


def _templates(count: int) -> list[QuestionTemplate]:
    return [
        QuestionTemplate(
            question_id=f"q_{i}",
            concentration=f"考点{i}",
            question_type="choice",
            difficulty="medium",
        )
        for i in range(1, count + 1)
    ]


class _FakeGenerator:
    """q_3 挂死(模拟慢 provider),其余秒回。"""

    def __init__(self, hang_question_id: str | None = None) -> None:
        self.hang_question_id = hang_question_id

    async def process(self, *, template: QuestionTemplate, **_kwargs: Any) -> QAPair:
        if template.question_id == self.hang_question_id:
            await asyncio.sleep(3600)
        return QAPair(
            question_id=template.question_id,
            question=f"题干 {template.question_id}",
            correct_answer="A",
            explanation="解析",
            question_type=template.question_type,
            concentration=template.concentration,
            difficulty=template.difficulty,
        )


def _make_coordinator(
    monkeypatch: pytest.MonkeyPatch,
    ws_events: list[tuple[str, dict[str, Any]]],
    generator: _FakeGenerator,
) -> AgentCoordinator:
    coordinator = AgentCoordinator.__new__(AgentCoordinator)

    class _Logger:
        def warning(self, *args: Any, **kwargs: Any) -> None:
            return None

    coordinator.logger = _Logger()  # type: ignore[assignment]
    monkeypatch.setattr(coordinator, "_create_generator", lambda: generator, raising=False)

    async def _capture_ws(event: str, payload: dict[str, Any]) -> None:
        ws_events.append((event, payload))

    monkeypatch.setattr(coordinator, "_send_ws_update", _capture_ws, raising=False)
    return coordinator


@pytest.mark.asyncio
async def test_generation_loop_delivers_all_when_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_events: list[tuple[str, dict[str, Any]]] = []
    coordinator = _make_coordinator(monkeypatch, ws_events, _FakeGenerator())
    results = await coordinator._generation_loop(
        templates=_templates(10), user_topic="t", preference=""
    )
    assert len(results) == 10
    # 顺序按模板原序(q_1..q_10),并发不打乱交付序。
    assert [r["qa_pair"]["question_id"] for r in results] == [f"q_{i}" for i in range(1, 11)]
    complete = [p for e, p in ws_events if e == "progress" and p.get("stage") == "complete"]
    assert complete and complete[-1]["completed"] == 10
    assert "generation_shortfall" not in complete[-1]


@pytest.mark.asyncio
async def test_generation_loop_partial_delivery_on_budget_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一题挂死不得拖垮整批:预算收束后交付其余 9 题 + shortfall typed marker。"""
    monkeypatch.setattr(AgentCoordinator, "_GENERATION_COLLECT_BUDGET_S", 1.0)
    ws_events: list[tuple[str, dict[str, Any]]] = []
    coordinator = _make_coordinator(
        monkeypatch, ws_events, _FakeGenerator(hang_question_id="q_3")
    )
    results = await coordinator._generation_loop(
        templates=_templates(10), user_topic="t", preference=""
    )
    delivered_ids = [r["qa_pair"]["question_id"] for r in results]
    assert len(results) == 9
    assert "q_3" not in delivered_ids
    complete = [p for e, p in ws_events if e == "progress" and p.get("stage") == "complete"]
    shortfall = complete[-1]["generation_shortfall"]
    assert shortfall["kind"] == "generation_collect_budget_exhausted"
    assert shortfall["requested"] == 10
    assert shortfall["delivered"] == 9
    assert shortfall["dropped_question_ids"] == ["q_3"]
