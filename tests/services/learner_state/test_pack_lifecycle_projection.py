"""§1 生命周期投影：5 态派生、蓝环/掌握双轨、未归位诚实桶、
revalidation_queue 对未学/exposed 态零 probe（M0）。"""

from __future__ import annotations

from deeptutor.services.learner_state.pack_lifecycle_projection import (
    LIFECYCLE_DORMANT,
    LIFECYCLE_EXPOSED,
    LIFECYCLE_MASTERED,
    LIFECYCLE_PRACTICED,
    LIFECYCLE_UNLEARNED,
    project_pack_lifecycle,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

_PACK_IDS = ["A01", "N01", "S05"]


def _lesson_event(pack_id: str = "N01") -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=f"lesson_{pack_id}",
        user_id="student_demo",
        source_feature="luban_lesson",
        source_id=f"lesson_viewed:{pack_id}:lesson",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key=f"lesson_viewed:student_demo:{pack_id}:lesson:2026-07-03",
        created_at="2026-07-03T10:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "learning_signal_type": "lesson_viewed",
            "pack_id": pack_id,
            "watched_stage": "lesson",
            "evidence_level": "exposed",
            "quality": {"progress_countable": False},
        },
    )


def _practice_event(taxonomy_code: str = "1A433000-B041", question_id: str = "q_free_1") -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=f"practice_{question_id}",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id=f"turn:{question_id}",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key=f"practice_{question_id}",
        created_at="2026-07-03T11:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "question_id": question_id,
            "score_awarded": 0.0,
            "max_score": 1.0,
            "canonical_topic": {"taxonomy_code": taxonomy_code},
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )


def test_unlearned_is_derived_as_full_set_minus_evidence() -> None:
    projection = project_pack_lifecycle(events=[], claims=[], pack_ids=_PACK_IDS)
    assert set(projection["packs"]) == set(_PACK_IDS)
    for pack_id in _PACK_IDS:
        entry = projection["packs"][pack_id]
        assert entry["lifecycle_state"] == LIFECYCLE_UNLEARNED
        assert entry["blue_ring"] == "empty"


def test_lesson_view_moves_pack_to_exposed_only() -> None:
    projection = project_pack_lifecycle(events=[_lesson_event("N01")], claims=[], pack_ids=_PACK_IDS)
    n01 = projection["packs"]["N01"]
    assert n01["lifecycle_state"] == LIFECYCLE_EXPOSED
    assert n01["blue_ring"] == "exposed"
    # M0：接触绝不进掌握轨——其余 pack 仍未学。
    assert projection["packs"]["A01"]["lifecycle_state"] == LIFECYCLE_UNLEARNED


def test_practice_evidence_promotes_to_practiced_via_taxonomy_join() -> None:
    # 1A433000-B041 是 N01 的 primary_taxonomy_ref（60-slot registry slot 8）。
    projection = project_pack_lifecycle(
        events=[_lesson_event("N01"), _practice_event("1A433000-B041")],
        claims=[],
        pack_ids=_PACK_IDS,
    )
    n01 = projection["packs"]["N01"]
    assert n01["lifecycle_state"] == LIFECYCLE_PRACTICED
    assert n01["blue_ring"] == "exposed"  # 蓝环独立于掌握轨保留
    assert n01["practice_event_count"] == 1


def test_real_retest_claim_promotes_to_mastered_and_stale_to_dormant() -> None:
    mastered_claim = {
        "concept_id": "1A433000-B041",
        "evidence_level": "L2_real_retest",
        "decay_state": "active",
    }
    projection = project_pack_lifecycle(events=[], claims=[mastered_claim], pack_ids=_PACK_IDS)
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_MASTERED

    dormant_claim = {**mastered_claim, "decay_state": "stale"}
    projection = project_pack_lifecycle(events=[], claims=[dormant_claim], pack_ids=_PACK_IDS)
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_DORMANT


def test_confirmed_without_retest_stays_practiced_m0() -> None:
    # M0：掌握只由客观复测升——L2_confirmed（人工确认）不给真懂。
    claim = {
        "concept_id": "1A433000-B041",
        "evidence_level": "L2_confirmed",
        "decay_state": "active",
    }
    projection = project_pack_lifecycle(events=[], claims=[claim], pack_ids=_PACK_IDS)
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_PRACTICED


def test_unmappable_practice_falls_into_unassigned_bucket() -> None:
    event = _practice_event("1A999999-Z999", question_id="q_unknown")
    projection = project_pack_lifecycle(events=[event], claims=[], pack_ids=_PACK_IDS)
    assert all(
        entry["lifecycle_state"] == LIFECYCLE_UNLEARNED for entry in projection["packs"].values()
    )
    assert len(projection["unassigned_practice"]) == 1
    assert projection["unassigned_practice"][0]["question_id"] == "q_unknown"


def test_full_40_pack_set_is_the_default_universe() -> None:
    projection = project_pack_lifecycle(events=[], claims=[])
    assert len(projection["packs"]) == 40


def test_revalidation_queue_emits_zero_probe_for_unlearned_and_exposed() -> None:
    # §1.2：revalidation_queue 的 state 白名单 {weak,unstable,needs_revalidation}
    # 天然忽略未学/已学·待验证——钉死零 probe。
    from deeptutor.services.learner_state.revalidation_queue import (
        build_revalidation_queue_projection,
    )

    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        events=[_lesson_event("N01")],
        learning_state={
            "knowledge_state": [
                {"state": "unlearned", "concept_id": "1A433000-B041"},
                {"state": "exposed", "concept_id": "1A433000-G03"},
            ]
        },
    )
    assert queue["items"] == []
    assert queue["source_status"]["candidate_count"] == 0

    # 对照臂（防恒真断言）：weak 态必须真的产出 probe。
    weak_queue = build_revalidation_queue_projection(
        user_id="student_demo",
        events=[],
        learning_state={
            "knowledge_state": [{"state": "weak", "concept_id": "1A433000-B041", "error_code": "E02"}]
        },
    )
    assert len(weak_queue["items"]) == 1


def test_report_read_model_exposes_pack_lifecycle_composer() -> None:
    from deeptutor.services.learner_state.learning_report_read_model import (
        _build_pack_lifecycle_from,
    )

    payload = _build_pack_lifecycle_from(events=[_lesson_event("N01")], weak_points=[])
    assert payload["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_EXPOSED
    assert payload["authority"] == "pack_lifecycle_projection.read_model"


def test_artifact_loader_never_caches_failure(tmp_path, monkeypatch) -> None:
    # Codex #3:lru_cache 曾把首次读失败(空 dict)缓存到进程死;
    # 修好文件后同进程必须能恢复,失败必打 warning。
    import deeptutor.services.learner_state.pack_lifecycle_projection as plp

    artifact = tmp_path / "map.json"
    monkeypatch.setattr(plp, "_QUESTION_PACK_MAP_PATH", artifact)
    plp._ARTIFACT_CACHE.clear()

    # 文件缺失 → 空索引(降级),但不落缓存
    assert plp._question_to_packs() == {}

    artifact.write_text(
        '{"reverse_index": {"2015:EXAM_XW2015_MU_30": ["N01"]}}', encoding="utf-8"
    )
    index = plp._question_to_packs()
    # 同进程恢复:qualified 精确键 + 裸键都可查
    assert index["2015:EXAM_XW2015_MU_30"] == ("N01",)
    assert index["EXAM_XW2015_MU_30"] == ("N01",)

    # 产物热更新(内容变) → 缓存按 stat 键失效重读
    artifact.write_text(
        '{"reverse_index": {"2016:EXAM_XW2016_SI_01": ["A01"]}}', encoding="utf-8"
    )
    index = plp._question_to_packs()
    assert "EXAM_XW2016_SI_01" in index and "EXAM_XW2015_MU_30" not in index
    plp._ARTIFACT_CACHE.clear()


def test_question_index_serves_qualified_and_unique_bare_keys(tmp_path, monkeypatch) -> None:
    # Codex #2 修复:qualified 键保留精确契约;裸键跨年合并后不同 pack = 歧义,
    # resolver 不硬塞(fail-closed 语义不变)。
    import deeptutor.services.learner_state.pack_lifecycle_projection as plp

    artifact = tmp_path / "map.json"
    artifact.write_text(
        '{"reverse_index": {"2022:EXAM_1A411001_P0001_01": ["A01"], "2023:EXAM_1A411001_P0001_01": ["N01"]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(plp, "_QUESTION_PACK_MAP_PATH", artifact)
    plp._ARTIFACT_CACHE.clear()

    # qualified 精确键各归各的 pack(年份限定契约在 runtime 不再被剥)
    assert plp._resolve_pack_for_practice({"question_id": "2022:EXAM_1A411001_P0001_01"}) == (
        "A01",
        "question_map",
    )
    assert plp._resolve_pack_for_practice({"question_id": "2023:EXAM_1A411001_P0001_01"}) == (
        "N01",
        "question_map",
    )
    # 裸键跨年属不同 pack → 歧义,禁硬塞
    pack, reason = plp._resolve_pack_for_practice({"question_id": "EXAM_1A411001_P0001_01"})
    assert pack == "" and reason == "question_ambiguous"
    plp._ARTIFACT_CACHE.clear()
