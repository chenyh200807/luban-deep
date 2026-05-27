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


def test_fresh_legacy_three_prompt_projection_upgrades_to_six_actions() -> None:
    generated_at = datetime(2026, 5, 21, 9, 0, tzinfo=_TZ).isoformat()
    projection = {
        "generated_at": generated_at,
        "source_status": {"fallback_used": False, "learning_report": "projection"},
        "today_focus": {
            "title": "今日焦点：项目质量计划管理",
            "meta": "来自 learner_state.home_personalization",
        },
        "recommended_prompts": [
            {
                "prompt_type": "practice_prompt",
                "text": "用 3 道题训练项目质量计划管理",
                "intent": {
                    "source": "home_dashboard",
                    "concept_label": "项目质量计划管理",
                    "error_label": "质量计划和质量保证混淆",
                    "evidence_refs": ["evt-quality-plan"],
                },
            },
            {
                "prompt_type": "mistake_review",
                "text": "复盘项目质量计划管理里的质量计划和质量保证混淆",
                "intent": {
                    "source": "home_dashboard",
                    "concept_label": "项目质量计划管理",
                    "error_label": "质量计划和质量保证混淆",
                    "evidence_refs": ["evt-quality-plan"],
                },
            },
            {
                "prompt_type": "concept_explain",
                "text": "讲清楚项目质量计划管理的关键判断",
                "intent": {
                    "source": "home_dashboard",
                    "concept_label": "项目质量计划管理",
                    "error_label": "质量计划和质量保证混淆",
                    "evidence_refs": ["evt-quality-plan"],
                },
            },
        ],
    }

    dashboard = build_home_dashboard_learning_projection(
        projection=projection,
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert [item["prompt_type"] for item in dashboard["recommended_prompts"]] == [
        "practice_prompt",
        "mistake_review",
        "concept_explain",
        "exam_transfer",
        "knowledge_map",
        "quick_check",
    ]
    assert dashboard["recommended_prompts"][3]["text"] == "用一道真题场景理解项目质量计划管理"
    assert dashboard["source_status"]["upgraded_from"] == "legacy_home_projection"


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


def test_learning_signal_projection_rejects_deictic_focus_labels() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": "construction_exam_1",
            "next_training_signal": {"focus": "这题", "concept": "本题"},
            "concept": {"label": "这道题"},
            "error": {"label": "这题"},
            "learning_state_ref": "knowledge:1A413053",
            "knowledge_points": ["这题"],
            "error_codes": ["M01"],
            "event_id": "evt-home-deictic",
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert projection is not None
    assert projection["today_focus"]["title"] == "今日焦点：地下室防水工程施工"
    rendered = json.dumps(projection, ensure_ascii=False)
    assert "这题" not in rendered
    assert projection["today_focus"]["intent"]["topic_source"] == "taxonomy_code"
    assert projection["recommended_prompts"][0]["text"] == "用 3 道题训练地下室防水工程施工"
    assert projection["recommended_prompts"][1]["text"] == "复盘地下室防水工程施工里的M01"


def test_learning_signal_projection_drops_generic_only_focus() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": "construction_exam_1",
            "next_training_signal": {"focus": "这题"},
            "concept": {"label": "这题"},
            "error": {"label": "这题"},
            "event_id": "evt-home-generic-only",
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert projection is None


def test_learning_signal_projection_requires_learnable_focus_topic() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": "construction_exam_1",
            "error": {"label": "M01"},
            "error_codes": ["M01"],
            "event_id": "evt-home-error-only",
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert projection is None


def test_learning_signal_projection_uses_llm_inferred_topic_when_taxonomy_misses() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": "construction_exam_1",
            "question_stem": "雨季施工时，混凝土浇筑后的养护措施选择错误。",
            "simple_explanation": "应结合雨季施工和混凝土养护要求判断。",
            "event_id": "evt-home-llm-topic",
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
        llm_topic_inferer=lambda payload, candidates: "雨季混凝土养护",
    )

    assert projection is not None
    assert projection["today_focus"]["title"] == "今日焦点：雨季混凝土养护"
    assert projection["today_focus"]["intent"]["topic_source"] == "llm_inferred"
    assert projection["today_focus"]["intent"]["topic_confidence"] == "low"


def test_learning_signal_projection_generates_six_actionable_prompt_types() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": "construction_exam_1",
            "concept": {"label": "项目质量计划管理"},
            "error": {"label": "质量计划和质量保证混淆"},
            "event_id": "evt-quality-plan",
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert projection is not None
    prompt_types = [item["prompt_type"] for item in projection["recommended_prompts"]]
    assert prompt_types == [
        "practice_prompt",
        "mistake_review",
        "concept_explain",
        "exam_transfer",
        "knowledge_map",
        "quick_check",
    ]
    assert [item["text"] for item in projection["recommended_prompts"]] == [
        "用 3 道题训练项目质量计划管理",
        "复盘项目质量计划管理里的质量计划和质量保证混淆",
        "讲清楚项目质量计划管理的关键判断",
        "用一道真题场景理解项目质量计划管理",
        "梳理项目质量计划管理的高频考点",
        "用 1 个小问题验证项目质量计划管理是否真会了",
    ]


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


def test_fresh_projection_with_deictic_focus_recovers_from_learning_evidence() -> None:
    generated_at = datetime(2026, 5, 21, 9, 0, tzinfo=_TZ).isoformat()
    bad_projection = {
        "generated_at": generated_at,
        "source_status": {"fallback_used": False, "learning_report": "projection"},
        "today_focus": {
            "title": "今日焦点：这题",
            "meta": "来自 learner_state.home_personalization",
            "intent": {"source": "learner_state.home_personalization", "concept_label": "这题"},
        },
        "recommended_prompts": [
            {
                "prompt_type": "practice_prompt",
                "text": "用 3 道题训练这题",
                "intent": {"source": "learner_state.home_personalization", "concept_label": "这题"},
            }
        ],
    }
    latest_event = SimpleNamespace(
        event_id="evt_recover_deictic",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
        payload_json={
            "event_type": "learning_evidence",
            "assessment_type": "topic_diagnostic",
            "knowledge_points": ["防水工程"],
            "error_codes": ["M01"],
            "attempt_ref": "attempt-ref-recover",
        },
    )

    dashboard = build_home_dashboard_learning_projection(
        projection=bad_projection,
        conversation_events=[latest_event],
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert dashboard["today_focus"]["title"] == "今日焦点：防水工程"
    assert dashboard["recommended_prompts"][0]["text"] == "用 3 道题训练防水工程"
    assert "这题" not in json.dumps(dashboard, ensure_ascii=False)
    assert dashboard["source_status"]["recovered_from"] == "learner_memory_events.learning_evidence"


def test_missing_projection_recovers_from_assessment_learning_evidence() -> None:
    older_event = SimpleNamespace(
        event_id="evt_assessment_old",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
        payload_json={
            "event_type": "learning_evidence",
            "assessment_type": "topic_diagnostic",
            "question_id": "q0",
            "knowledge_points": ["旧摸底"],
            "error_codes": ["M00"],
            "attempt_ref": "attempt-ref-old",
        },
    )
    latest_event = SimpleNamespace(
        event_id="evt_assessment_1",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
        payload_json={
            "event_type": "learning_evidence",
            "assessment_type": "topic_diagnostic",
            "question_id": "q1",
            "knowledge_points": ["防水工程"],
            "error_codes": ["M01"],
            "attempt_ref": "attempt-ref-1",
        },
    )

    dashboard = build_home_dashboard_learning_projection(
        projection=None,
        conversation_events=[older_event, latest_event],
        subject_id="construction_exam_1",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert dashboard["today_focus"]["title"] == "今日焦点：防水工程"
    assert dashboard["today_focus"]["meta"] == "来自 learner_state.home_personalization"
    assert dashboard["recommended_prompts"][0]["text"] == "用 3 道题训练防水工程"
    assert dashboard["recommended_prompts"][0]["intent"]["evidence_refs"] == [
        "evt_assessment_1",
        "attempt-ref-1",
    ]
    assert dashboard["source_status"]["fallback_used"] is False
    assert dashboard["source_status"]["recovered_from"] == "learner_memory_events.learning_evidence"


def test_training_completion_projection_recommends_topic_retest() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "event_type": "learning_evidence",
            "learning_signal_type": "training_completed",
            "subject_id": "construction_exam",
            "concept": {"label": "地下防水"},
            "error": {"label": "M01"},
            "learning_state_ref": "knowledge:1A413053",
            "attempt_ref": "attempt_signed",
            "evidence_refs": ["attempt_signed"],
        },
        generated_at=datetime(2026, 5, 21, 10, 0, tzinfo=_TZ),
    )

    assert projection is not None
    first_prompt = projection["recommended_prompts"][0]
    assert first_prompt["prompt_type"] == "assessment"
    assert first_prompt["text"] == "再测一次地下室防水工程施工"
    assert first_prompt["intent"]["learning_signal_type"] == "assessment"
    assert first_prompt["intent"]["concept_label"] == "地下室防水工程施工"
    assert first_prompt["intent"]["taxonomy_code"] == "1A413053"
    assert first_prompt["intent"]["evidence_refs"] == ["attempt_signed"]


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


def test_dashboard_recovers_projection_from_assessment_learning_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME_PERSONALIZATION_ENABLED", "true")
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("assessment_projection_user")

    event = SimpleNamespace(
        event_id="evt_assessment_1",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
        payload_json={
            "event_type": "learning_evidence",
            "assessment_type": "topic_diagnostic",
            "question_id": "q1",
            "knowledge_points": ["防水工程"],
            "error_codes": ["M01"],
        },
    )

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "assessment_projection_user"
            return SimpleNamespace(
                profile={},
                progress={},
                summary="",
                memory_events=[event],
            )

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, limit: int = 3):
            return []

    service._get_learner_state_service = lambda: _FakeLearnerStateService()  # type: ignore[method-assign]

    dashboard = service.get_home_dashboard("assessment_projection_user")

    assert dashboard["today_focus"]["title"] == "今日焦点：防水工程"
    assert dashboard["recommended_prompts"][0]["text"] == "用 3 道题训练防水工程"
    assert dashboard["recommended_prompts"][0]["prompt_type"] == "practice_prompt"
    assert dashboard["home_projection"]["source_status"]["recovered_from"] == "learner_memory_events.learning_evidence"


def test_home_dashboard_reads_canonical_learner_state_for_merged_member(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME_PERSONALIZATION_ENABLED", "true")
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            service._build_default_member(canonical_user_id),
            {
                **service._build_default_member("user_2008"),
                "user_id": "user_2008",
                "display_name": "chenyh2008",
                "external_auth_user_id": canonical_user_id,
                "merged_into": canonical_user_id,
            },
        ]

    service._mutate(_seed)
    event = SimpleNamespace(
        event_id="evt_canonical_assessment_1",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
            payload_json={
                "event_type": "learning_evidence",
                "assessment_type": "topic_diagnostic",
                "knowledge_points": ["1A432000"],
                "error_codes": [],
            },
    )
    requested_snapshot_users: list[str] = []
    requested_heartbeat_users: list[str] = []

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            requested_snapshot_users.append(user_id)
            return SimpleNamespace(
                profile={},
                progress={},
                summary="",
                memory_events=[event],
            )

        def list_heartbeat_jobs(self, user_id: str):
            requested_heartbeat_users.append(user_id)
            return []

        def list_heartbeat_history(self, user_id: str, limit: int = 3):
            requested_heartbeat_users.append(user_id)
            return []

    service._get_learner_state_service = lambda: _FakeLearnerStateService()  # type: ignore[method-assign]

    dashboard = service.get_home_dashboard("user_2008")

    assert requested_snapshot_users == [canonical_user_id]
    assert requested_heartbeat_users == [canonical_user_id, canonical_user_id]
    assert dashboard["today_focus"]["title"] == "今日焦点：工程招标投标与合同管理"
    assert dashboard["recommended_prompts"][0]["text"] == "用 3 道题训练工程招标投标与合同管理"


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


def test_member_console_today_focus_skips_deictic_topics() -> None:
    service = MemberConsoleService()
    snapshot = SimpleNamespace(
        profile={"focus_topic": "这题"},
        progress={"knowledge_map": {"weak_points": ["防水工程"]}},
        summary="当前聚焦：这题",
    )

    focus = service._build_home_today_focus(
        {"focus_topic": "这题"},
        weak_nodes=[{"name": "地下防水"}],
        review={},
        snapshot=snapshot,
        study_plan={"focus_topic": "这题"},
    )

    assert focus["topic"] == "防水工程"
    assert focus["title"] == "推进防水工程下一步学习"
    assert "这题" not in json.dumps(focus, ensure_ascii=False)
