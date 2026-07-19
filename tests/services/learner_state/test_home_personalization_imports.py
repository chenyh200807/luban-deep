"""Regression: home_personalization 必须能解析 ResolvedLearningTopic（F821 修复）。

origin/main 的一次 merge 在 ``home_personalization.py`` 用 ``ResolvedLearningTopic``
作类型注解却漏了 import，因 ``from __future__ import annotations`` 运行时不崩，但
CI 的 ruff F821 NameError gate（``ruff check --select F821,F811``）会 FAIL，卡住所有
PR 的 Contract Guard。本测试钉住该 import 存在，防复发。
"""

from __future__ import annotations


def test_home_personalization_imports_resolved_learning_topic() -> None:
    import deeptutor.services.learner_state.home_personalization as home
    from deeptutor.services.taxonomy.learning_topic_resolver import (
        ResolvedLearningTopic,
    )

    assert home.ResolvedLearningTopic is ResolvedLearningTopic


def test_dashboard_event_recovery_never_runs_llm_topic_inference(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    import deeptutor.services.learner_state.home_personalization as home

    original_resolver = home.resolve_learning_topic_from_payload
    resolver_inferers: list[object | None] = []

    def guarded_resolver(payload, *, llm_topic_inferer=None):
        resolver_inferers.append(llm_topic_inferer)
        assert llm_topic_inferer is None
        return original_resolver(payload, llm_topic_inferer=None)

    monkeypatch.setattr(home, "resolve_learning_topic_from_payload", guarded_resolver)
    unresolved_event = SimpleNamespace(
        event_id="evt_read_path_must_not_infer",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
        payload_json={
            "event_type": "learning_evidence",
            "knowledge_points": ["请判断这道综合题的正确做法"],
            "attempt_ref": "attempt-read-path-must-not-infer",
        },
    )

    dashboard = home.build_home_dashboard_learning_projection(
        projection=None,
        conversation_events=[unresolved_event],
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=timezone(timedelta(hours=8))),
    )

    assert resolver_inferers
    assert dashboard["source_status"]["fallback_used"] is True
    assert dashboard["source_status"]["fallback_reason"] == "missing"
