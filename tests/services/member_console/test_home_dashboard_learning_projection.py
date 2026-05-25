from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import deeptutor.services.learner_state.home_personalization as home_personalization_module
from deeptutor.services.learner_state.home_personalization import (
    build_home_dashboard_learning_projection,
    build_home_personalization_projection_from_learning_signal,
)
from deeptutor.services.member_console.service import MemberConsoleService


_TZ = timezone(timedelta(hours=8))


def test_home_dashboard_uses_fresh_home_personalization_projection() -> None:
    generated_at = datetime(2026, 5, 21, 9, 0, tzinfo=_TZ).isoformat()
    projection = {
        "generated_at": generated_at,
        "source_status": {"fallback_used": False, "learning_report": "projection"},
        "today_focus": {
            "title": "今日焦点：流水施工",
            "meta": "刚生成的学情投影",
            "intent": {"source": "learner_state.home_personalization", "concept_label": "流水施工"},
        },
        "recommended_prompts": [
            {
                "prompt_type": "mistake_review",
                "text": "复盘流水施工错因",
                "intent": {"source": "learner_state.home_personalization"},
            }
        ],
    }

    dashboard = build_home_dashboard_learning_projection(
        projection=projection,
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert dashboard["today_focus"]["title"] == "今日焦点：流水施工"
    assert dashboard["recommended_prompts"][0]["text"] == "复盘流水施工错因"
    assert dashboard["source_status"]["fallback_used"] is False
    assert dashboard["source_status"]["learning_report"] == "projection"


def test_learning_signal_projection_makes_today_focus_clickable() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": "construction_exam_1",
            "concept": {"label": "主体结构验收"},
            "error": {"label": "验收程序混淆"},
            "training_intent_id": "intent-1",
            "event_id": "evt-home-1",
            "attempt_ref": "attempt-ref-1",
            "learning_state_ref": "knowledge:1A432000",
            "suggested_mode": "deep",
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert projection is not None
    assert projection["today_focus"]["prompt"] == projection["recommended_prompts"][0]["text"]
    assert projection["today_focus"]["intent"] == projection["recommended_prompts"][0]["intent"]
    first_prompt = projection["recommended_prompts"][0]
    assert first_prompt["evidence_refs"] == ["evt-home-1", "attempt-ref-1"]
    assert first_prompt["learning_state_ref"] == "knowledge:1A432000"
    assert first_prompt["suggested_mode"] == "deep"
    assert first_prompt["intent"]["evidence_refs"] == ["evt-home-1", "attempt-ref-1"]


def test_stale_or_missing_projection_falls_back_to_seed_starters() -> None:
    stale_projection = {
        "generated_at": datetime(2026, 5, 21, 2, 0, tzinfo=_TZ).isoformat(),
        "today_focus": {"title": "旧焦点"},
        "recommended_prompts": [{"prompt_type": "mistake_review", "text": "旧推荐"}],
    }

    stale_dashboard = build_home_dashboard_learning_projection(
        projection=stale_projection,
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )
    missing_dashboard = build_home_dashboard_learning_projection(
        projection=None,
        subject_id="construction_exam_2",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert stale_dashboard["source_status"]["fallback_used"] is True
    assert stale_dashboard["source_status"]["fallback_reason"] == "stale"
    assert stale_dashboard["source_status"]["learning_report"] == "stale"
    assert stale_dashboard["recommended_prompts"][0]["text"] != "旧推荐"
    assert missing_dashboard["source_status"]["fallback_reason"] == "missing"
    assert missing_dashboard["source_status"]["learning_report"] == "stale"
    assert len({item["prompt_type"] for item in missing_dashboard["recommended_prompts"]}) >= 3


def test_malformed_projection_falls_back_instead_of_leaking_bad_shape() -> None:
    malformed_projection = {
        "generated_at": datetime(2026, 5, 21, 9, 0, tzinfo=_TZ).isoformat(),
        "today_focus": "not-a-focus",
        "recommended_prompts": "not-a-list",
    }

    dashboard = build_home_dashboard_learning_projection(
        projection=malformed_projection,
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert dashboard["source_status"]["fallback_used"] is True
    assert dashboard["source_status"]["fallback_reason"] == "stale"
    assert isinstance(dashboard["today_focus"], dict)
    assert isinstance(dashboard["recommended_prompts"], list)


def test_seed_starter_files_exist_and_are_used() -> None:
    base = Path("data/seed")
    for subject_id in ["construction_exam_1", "construction_exam_2"]:
        seed_path = base / subject_id / "starter_prompts.json"
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        assert len(payload["prompts"]) >= 3
        assert len({item["prompt_type"] for item in payload["prompts"]}) >= 3

        dashboard = build_home_dashboard_learning_projection(
            projection=None,
            subject_id=subject_id,
            now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
        )
        assert dashboard["recommended_prompts"][0]["text"] == payload["prompts"][0]["text"]
        assert dashboard["today_focus"]["prompt"] == payload["prompts"][0]["text"]
        assert "给系统" not in dashboard["today_focus"]["title"]
        assert dashboard["today_focus"]["meta"] == "生成学情基线"


def test_home_dashboard_keeps_v1_shape_when_home_personalization_flag_off(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPTUTOR_HOME_PERSONALIZATION_ENABLED", raising=False)
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("flag_off_user")

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "flag_off_user"
            return SimpleNamespace(
                profile={
                    "home_personalization": {
                        "generated_at": datetime.now(tz=_TZ).isoformat(),
                        "source_status": {"fallback_used": False, "learning_report": "projection"},
                        "today_focus": {"title": "不应覆盖 v1 首页"},
                        "recommended_prompts": [{"text": "不应出现在 flag off 首页"}],
                    }
                },
                progress={},
                summary="",
                memory_events=[],
            )

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, limit: int = 3):
            return []

    service._get_learner_state_service = lambda: _FakeLearnerStateService()  # type: ignore[method-assign]

    dashboard = service.get_home_dashboard("flag_off_user")

    assert "home_projection" not in dashboard
    assert "recommended_prompts" not in dashboard
    assert dashboard["today_focus"]["title"] != "不应覆盖 v1 首页"


def test_dashboard_reads_projection_from_learner_snapshot_not_weak_nodes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME_PERSONALIZATION_ENABLED", "true")
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("projection_user")
    generated_at = datetime.now(tz=_TZ).isoformat()

    projection = {
        "generated_at": generated_at,
        "source_status": {"fallback_used": False, "learning_report": "projection"},
        "today_focus": {
            "title": "今日焦点：施工进度索赔",
            "meta": "来自 learner_state.home_personalization",
            "intent": {"source": "learner_state.home_personalization", "concept_label": "施工进度索赔"},
        },
        "recommended_prompts": [
            {
                "prompt_type": "practice_prompt",
                "text": "用案例题练施工进度索赔",
                "intent": {"source": "learner_state.home_personalization"},
            }
        ],
    }

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "projection_user"
            return SimpleNamespace(
                profile={"home_personalization": projection},
                progress={"knowledge_map": {"weak_points": ["不应现场合成"]}},
                summary="",
                memory_events=[],
            )

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, limit: int = 3):
            return []

    service._get_learner_state_service = lambda: _FakeLearnerStateService()  # type: ignore[method-assign]

    dashboard = service.get_home_dashboard("projection_user")

    assert dashboard["today_focus"]["title"] == "今日焦点：施工进度索赔"
    assert dashboard["today"]["focus"] == dashboard["today_focus"]
    assert dashboard["recommended_prompts"][0]["text"] == "用案例题练施工进度索赔"
    assert dashboard["recommended_prompts"][0]["prompt_type"] == "practice_prompt"
    assert dashboard["home_projection"]["today_focus"]["title"] == "今日焦点：施工进度索赔"
    assert dashboard["home_projection"]["recommended_prompts"][0]["text"] == "用案例题练施工进度索赔"
    assert dashboard["home_projection"]["recommended_prompts"][0]["prompt_type"] == "practice_prompt"


def test_dashboard_seed_fallback_uses_subject_from_learner_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME_PERSONALIZATION_ENABLED", "true")
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("subject_user")
    seed_payload = json.loads(
        Path("data/seed/construction_exam_2/starter_prompts.json").read_text(encoding="utf-8")
    )

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "subject_user"
            return SimpleNamespace(
                profile={"active_subject_id": "construction_exam_2"},
                progress={},
                summary="",
                memory_events=[],
            )

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, limit: int = 3):
            return []

    service._get_learner_state_service = lambda: _FakeLearnerStateService()  # type: ignore[method-assign]

    dashboard = service.get_home_dashboard("subject_user")

    assert dashboard["home_projection"]["recommended_prompts"][0]["text"] == seed_payload["prompts"][0]["text"]


def test_weak_nodes_do_not_synthesize_fake_personalization() -> None:
    dashboard = build_home_dashboard_learning_projection(
        weak_nodes=[{"name": "主体结构", "error_label": "多选漏选"}],
        conversation_events=[],
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert dashboard["source_status"]["fallback_used"] is True
    assert dashboard["source_status"]["fallback_reason"] == "missing"
    assert "主体结构" not in dashboard["today_focus"]["title"]
    assert dashboard["recommended_prompts"][0]["intent"]["source"] == "home_dashboard"


def test_home_dashboard_falls_back_when_no_learning_facts() -> None:
    dashboard = build_home_dashboard_learning_projection(
        weak_nodes=[],
        conversation_events=[],
        subject_id="unknown",
    )

    assert dashboard["source_status"]["fallback_used"] is True
    assert dashboard["recommended_prompts"][0]["intent"]["reason"] == "starter"


def test_module_does_not_keep_hardcoded_starter_prompt_pool() -> None:
    assert not hasattr(home_personalization_module, "_STARTER_PROMPTS")
