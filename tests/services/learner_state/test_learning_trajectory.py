"""learning_trajectory 多跳轨迹查询契约（gbrain find_trajectory 的本项目版）。

- 纯只读组合层：所有事实来自 learning_synthesis 投影（weak_points /
  stale_claims / improvement_signals / typed_graph），本模块不计算新事实、
  不构成第二权威。
- 一次查通：错因 → 训练 → 改善证据 → 复测建议。
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.learner_state.learning_trajectory import (
    find_learning_trajectory,
    get_learning_trajectory_for_user,
    group_typed_edges,
)


def _edge(edge_type: str, from_id: str, to_id: str, *, evidence: str = "evt_edge") -> dict[str, Any]:
    return {
        "edge_type": edge_type,
        "from": {"type": "error", "id": from_id},
        "to": {"type": "training", "id": to_id},
        "evidence_event_id": evidence,
        "observed_at": "2026-06-10T00:00:00+08:00",
    }


def _projection() -> dict[str, Any]:
    # 形状钉在 learning_synthesis.synthesize_learning_truth 的真实输出上
    return {
        "schema_version": 2,
        "weak_points": [
            {
                "concept_id": "1A415000",
                "error_code": "M06",
                "concept_label": "屋面与防水工程施工",
                "evidence_level": "L1_repeated",
                "decay_state": "active",
                "claim_status": "confirmed",
                "supporting_event_ids": ["evt_1", "evt_2"],
            },
            {
                "concept_id": "1A432000",
                "error_code": "E02",
                "concept_label": "招标投标管理",
                "evidence_level": "L1_repeated",
                "decay_state": "active",
                "claim_status": "confirmed",
                "supporting_event_ids": ["evt_9"],
            },
        ],
        "stale_claims": [
            {
                "concept_id": "1A415000",
                "error_code": "M02",
                "reason": "later_training_improved",
                "supporting_event_ids": ["evt_0"],
                "evidence_level": "L1_repeated",
                "decay_state": "improving",
            }
        ],
        "improvement_signals": [
            {
                "concept_id": "1A415000",
                "error_code": "M02",
                "event_id": "evt_improve_1",
                "observed_at": "2026-06-11T00:00:00+08:00",
            }
        ],
        "typed_graph": {
            "schema_version": 1,
            "edges": [
                _edge("error_points_to_training", "1A415000:M06", "training_waterproof_terms", evidence="evt_2"),
                _edge("training_uses_question", "training_waterproof_terms", "Q-485", evidence="evt_2"),
                _edge("training_improved_error", "training_term_drill", "1A415000:M02", evidence="evt_improve_1"),
                _edge("error_points_to_training", "1A432000:E02", "training_bidding", evidence="evt_9"),
                "garbage-non-dict-edge",
            ],
        },
    }


def test_group_typed_edges_groups_by_type_and_tolerates_garbage() -> None:
    grouped = group_typed_edges(_projection())

    assert sorted(grouped.keys()) == [
        "error_points_to_training",
        "training_improved_error",
        "training_uses_question",
    ]
    assert len(grouped["error_points_to_training"]) == 2
    assert group_typed_edges({}) == {}
    assert group_typed_edges(None) == {}


def test_trajectory_walks_error_training_improvement_in_one_call() -> None:
    trajectory = find_learning_trajectory(_projection(), concept_id="1A415000")

    assert trajectory["status"] == "ok"
    assert trajectory["is_second_authority"] is False
    # 跳 1：错因（active 弱点 + improving 的旧错因都算该概念的轨迹节点）
    assert "1A415000:M06" in trajectory["errors"]
    assert "1A415000:M02" in trajectory["errors"]
    assert "1A432000:E02" not in trajectory["errors"]
    # 跳 2：训练
    training_ids = [item["training_id"] for item in trajectory["trainings"]]
    assert training_ids == ["training_waterproof_terms"]
    assert trajectory["trainings"][0]["error_id"] == "1A415000:M06"
    # 跳 2.5：训练用题
    assert trajectory["practice_question_ids"] == ["Q-485"]
    # 跳 3：改善证据（improvement_signals + improving decay_state）
    improved_errors = [item["error_id"] for item in trajectory["improvements"]]
    assert improved_errors == ["1A415000:M02"]
    # 跳 4：复测建议——已有改善证据 → 建议复测固化（real_retest 才能促升）
    assert trajectory["retest_recommendation"]["due_now"] is True
    assert "复测" in trajectory["retest_recommendation"]["reason"]
    # evidence 可溯源
    assert "evt_improve_1" in trajectory["evidence_event_ids"]
    assert "evt_2" in trajectory["evidence_event_ids"]


def test_trajectory_without_improvement_says_train_first() -> None:
    projection = _projection()
    projection["improvement_signals"] = []
    projection["stale_claims"] = []
    trajectory = find_learning_trajectory(projection, concept_id="1A432000")

    assert trajectory["errors"] == ["1A432000:E02"]
    assert [item["training_id"] for item in trajectory["trainings"]] == ["training_bidding"]
    assert trajectory["improvements"] == []
    assert trajectory["retest_recommendation"]["due_now"] is False
    assert "训练" in trajectory["retest_recommendation"]["reason"]


def test_trajectory_matches_by_label_query() -> None:
    trajectory = find_learning_trajectory(_projection(), concept_query="防水")

    assert "1A415000:M06" in trajectory["errors"]
    assert "1A432000:E02" not in trajectory["errors"]


def test_trajectory_requires_concept_or_query() -> None:
    trajectory = find_learning_trajectory(_projection())

    assert trajectory["status"] == "invalid_query"
    assert trajectory["errors"] == []


def test_trajectory_no_match_is_honest() -> None:
    trajectory = find_learning_trajectory(_projection(), concept_id="9Z999999")

    assert trajectory["status"] == "no_match"
    assert trajectory["retest_recommendation"]["due_now"] is False


class _FakeService:
    def __init__(self, *, cached: dict[str, Any] | None) -> None:
        self._cached = cached
        self.synthesize_calls: list[str] = []

    def read_compiled_learning_truth(self, user_id: str) -> dict[str, Any]:
        return dict(self._cached or {})

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool = True, event_limit: int | None = None):
        self.synthesize_calls.append(user_id)
        return {"projection": _projection()}


def test_user_trajectory_prefers_compiled_cache() -> None:
    service = _FakeService(cached=_projection())

    trajectory = get_learning_trajectory_for_user(service, "stu_1", concept_id="1A415000")

    assert trajectory["projection_source"] == "compiled_cache"
    assert service.synthesize_calls == []
    assert "1A415000:M06" in trajectory["errors"]


def test_user_trajectory_falls_back_to_dry_run_synthesis() -> None:
    service = _FakeService(cached=None)

    trajectory = get_learning_trajectory_for_user(service, "stu_1", concept_id="1A415000")

    assert trajectory["projection_source"] == "dry_run_synthesis"
    assert service.synthesize_calls == ["stu_1"]
    assert "1A415000:M06" in trajectory["errors"]
