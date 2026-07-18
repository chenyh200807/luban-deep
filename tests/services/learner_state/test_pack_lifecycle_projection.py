"""§1 生命周期投影：5 态派生、蓝环/掌握双轨、未归位诚实桶、
revalidation_queue 对未学/exposed 态零 probe（M0）。"""

from __future__ import annotations

from deeptutor.services.learner_state.evidence_lifecycle import (
    committed_retest_completion_ids,
)
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


def _signed_terminal(
    *,
    status: str = "verified",
    score_ratio: float = 1.0,
    source_feature: str = "assessment_testset",
    assessment_type: str = "luban_review_completion",
    target_pack_id: str = "N01",
) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id="terminal_adversarial",
        user_id="student_demo",
        source_feature=source_feature,
        source_id="adversarial:terminal",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key="terminal_adversarial",
        created_at="2026-07-04T09:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "assessment_testset",
            "assessment_type": assessment_type,
            "retest_completion_id": "adversarial",
            "completion_terminal": True,
            "request_hash": "a" * 64,
            "practice_mode": "review",
            "pack_id": "N01",
            "target_pack_id": target_pack_id,
            "score_ratio": score_ratio,
            "score_awarded": score_ratio,
            "max_score": 1.0,
            "item_event_refs": ["item_adversarial"],
            "claim_promotion_allowed": True,
            "prescription_result": {"status": status, "score_ratio": score_ratio},
            "quality": {
                "authority": "signed_variant_server_rescore",
                "writeback_eligible": True,
                "measurement_confidence": "high",
                "evidence_level": "L2_real_retest",
            },
        },
    )


def _completion_events(terminal: LearnerStateEvent) -> list[LearnerStateEvent]:
    payload = terminal.payload_json
    completion_id = str(payload["retest_completion_id"])
    item_id = str(payload["item_event_refs"][0])
    item = LearnerStateEvent(
        event_id=item_id,
        user_id=terminal.user_id,
        source_feature="assessment_testset",
        source_id=f"{completion_id}:q1",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key=item_id,
        created_at=terminal.created_at,
        payload_json={
            "event_type": "learning_evidence",
            "retest_completion_id": completion_id,
            "request_hash": payload["request_hash"],
            **(
                {
                    "request_hash_version": payload.get("request_hash_version"),
                    "probe_id": payload.get("probe_id", ""),
                    "cycle_anchor": payload.get("cycle_anchor", ""),
                }
                if payload.get("request_hash_version") is not None
                else {}
            ),
            "practice_mode": payload["practice_mode"],
            "pack_id": payload["pack_id"],
            "target_pack_id": payload["target_pack_id"],
            "question_id": "q1",
            "is_correct": bool(payload["score_awarded"]),
            "score_awarded": payload["score_awarded"],
            "max_score": 1.0,
        },
    )
    return [item, terminal]


def _compiled_forward_terminal() -> LearnerStateEvent:
    terminal = _signed_terminal(
        status="not_verified",
        assessment_type="luban_forward_completion",
        target_pack_id="N01",
    )
    terminal.payload_json.update(
        {
            "practice_mode": "forward",
            "claim_promotion_allowed": False,
        }
    )
    terminal.payload_json["quality"].update(
        {
            "authority": "compiled_html_server_rescore",
            "measurement_confidence": "medium",
            "evidence_level": "L0_observed",
        }
    )
    return terminal


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


def test_weak_point_claim_never_promotes_to_mastered() -> None:
    # 病G(语义反转地雷):mastered 地板曾 key 在**弱点 claim** 的
    # evidence_level rank 上——复测「确认弱点」(L2_real_retest)反而翻成
    # 「已掌握」。弱点证据强度只说明弱点可信,绝不是正向掌握信号。
    weak_claim = {
        "concept_id": "1A433000-B041",
        "evidence_level": "L2_real_retest",
        "decay_state": "active",
    }
    projection = project_pack_lifecycle(events=[], claims=[weak_claim], pack_ids=_PACK_IDS)
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_PRACTICED


def test_verified_concepts_are_the_only_mastered_signal() -> None:
    # mastered 只认显式正向信号:prescription_outcome verified 的 concept
    # codes(verified_concepts 入参)∩ pack refs 非空。
    projection = project_pack_lifecycle(
        events=[],
        claims=[],
        pack_ids=_PACK_IDS,
        verified_concepts={"1A433000-B041"},
    )
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_MASTERED
    assert projection["packs"]["A01"]["lifecycle_state"] == LIFECYCLE_UNLEARNED


def test_dormant_requires_verified_plus_stale_and_improving_stays_mastered() -> None:
    # dormant = 真懂过 + 记忆衰减(stale)。improving = 弱点仍在改善,
    # 不是「该休眠」——从 dormant 判定移除(病G 裁决)。
    stale_claim = {
        "concept_id": "1A433000-B041",
        "evidence_level": "L1_repeated",
        "decay_state": "stale",
    }
    projection = project_pack_lifecycle(
        events=[], claims=[stale_claim], pack_ids=_PACK_IDS, verified_concepts={"1A433000-B041"}
    )
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_DORMANT

    improving_claim = {**stale_claim, "decay_state": "improving"}
    projection = project_pack_lifecycle(
        events=[],
        claims=[improving_claim],
        pack_ids=_PACK_IDS,
        verified_concepts={"1A433000-B041"},
    )
    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_MASTERED


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
    assert len(projection["packs"]) == 41  # 40+D14(2026-07-04)——manifest 全集,加站时有意识 bump


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


def test_terminal_review_projects_cycle_facts_without_coarse_pack_mastery() -> None:
    terminal = LearnerStateEvent(
        event_id="terminal_r1",
        user_id="student_demo",
        source_feature="assessment_testset",
        source_id="r1:terminal",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key="terminal_r1",
        created_at="2026-07-04T09:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "assessment_testset",
            "assessment_type": "luban_review_completion",
            "retest_completion_id": "r1",
            "completion_terminal": True,
            "request_hash": "b" * 64,
            "practice_mode": "review",
            "pack_id": "N01",
            "target_pack_id": "N01",
            "score_ratio": 1.0,
            "score_awarded": 1.0,
            "max_score": 1.0,
            "item_event_refs": ["item_r1"],
            "claim_promotion_allowed": True,
            "prescription_result": {"status": "verified", "score_ratio": 1.0},
            "quality": {
                "authority": "signed_variant_server_rescore",
                "writeback_eligible": True,
                "measurement_confidence": "high",
                "evidence_level": "L2_real_retest",
            },
        },
    )
    projection = project_pack_lifecycle(
        events=_completion_events(terminal),
        claims=[],
        pack_ids=_PACK_IDS,
    )
    n01 = projection["packs"]["N01"]
    assert n01["lifecycle_state"] == LIFECYCLE_PRACTICED
    assert n01["last_review_status"] == "verified"
    assert n01["successful_review_streak"] == 1
    assert n01["review_cycle_anchor"] == "terminal_r1"


def test_compiled_forward_terminal_is_canonical_for_lifecycle_only() -> None:
    terminal = _compiled_forward_terminal()
    projection = project_pack_lifecycle(
        events=_completion_events(terminal),
        claims=[],
        pack_ids=_PACK_IDS,
    )

    n01 = projection["packs"]["N01"]
    assert n01["lifecycle_state"] == LIFECYCLE_PRACTICED
    assert n01["last_completion_at"] == terminal.created_at
    assert n01["terminal_evidence_refs"] == [terminal.event_id]
    assert projection["unassigned_practice"] == []


def test_immediate_confirm_terminal_does_not_restart_forward_review_cycle() -> None:
    forward = _compiled_forward_terminal()
    forward.event_id = "terminal_forward"
    forward.source_id = "forward:terminal"
    forward.created_at = "2026-07-04T09:00:00+08:00"
    forward.payload_json["retest_completion_id"] = "forward"
    forward.payload_json["item_event_refs"] = ["item_forward"]
    forward.payload_json.update(
        {"score_awarded": 0.0, "score_ratio": 0.0, "request_hash_version": 3}
    )
    forward.payload_json["prescription_result"].update(
        {"status": "not_verified", "score_ratio": 0.0}
    )

    confirm = _compiled_forward_terminal()
    confirm.event_id = "terminal_confirm"
    confirm.source_id = "confirm:terminal"
    confirm.created_at = "2026-07-04T09:05:00+08:00"
    confirm.payload_json["retest_completion_id"] = "confirm"
    confirm.payload_json["item_event_refs"] = ["item_confirm"]
    confirm.payload_json["request_hash_version"] = 3
    confirm.payload_json["cycle_anchor"] = "terminal_forward"

    forward_events = _completion_events(forward)
    forward_events[0].payload_json.update(
        {"fact_id": "fact-n01", "probe_role": "anchor"}
    )
    confirm_events = _completion_events(confirm)
    confirm_events[0].payload_json.update(
        {"probe_role": "immediate_confirm", "fact_id": "fact-n01"}
    )

    projection = project_pack_lifecycle(
        events=[*forward_events, *confirm_events], claims=[], pack_ids=_PACK_IDS
    )

    n01 = projection["packs"]["N01"]
    assert n01["last_completion_at"] == forward.created_at
    assert n01["review_cycle_anchor"] == forward.event_id
    assert n01["immediate_confirm_at"] == confirm.created_at


def test_wrong_review_cycle_anchor_cannot_move_pack_clock() -> None:
    forward = _compiled_forward_terminal()
    forward.event_id = "terminal_forward"
    forward.source_id = "forward:terminal"
    forward.payload_json.update(
        {
            "retest_completion_id": "forward",
            "item_event_refs": ["item_forward"],
            "request_hash_version": 3,
        }
    )
    review = _signed_terminal()
    review.event_id = "terminal_review"
    review.source_id = "review:terminal"
    review.payload_json.update(
        {
            "retest_completion_id": "review",
            "item_event_refs": ["item_review"],
            "request_hash_version": 3,
            "probe_id": "probe-review",
            "cycle_anchor": "terminal-from-another-cycle",
        }
    )
    projection = project_pack_lifecycle(
        events=[*_completion_events(forward), *_completion_events(review)],
        claims=[],
        pack_ids=_PACK_IDS,
    )
    n01 = projection["packs"]["N01"]
    assert n01["review_cycle_anchor"] == "terminal_forward"
    assert n01["last_review_at"] == ""
    assert n01["successful_review_streak"] == 0


def test_compiled_authority_cannot_impersonate_review_terminal() -> None:
    terminal = _compiled_forward_terminal()
    terminal.payload_json.update(
        {
            "assessment_type": "luban_review_completion",
            "practice_mode": "review",
            "claim_promotion_allowed": True,
        }
    )
    terminal.payload_json["quality"].update(
        {
            "measurement_confidence": "high",
            "evidence_level": "L2_real_retest",
        }
    )
    projection = project_pack_lifecycle(events=[terminal], claims=[], pack_ids=_PACK_IDS)

    assert projection["packs"]["N01"]["lifecycle_state"] == LIFECYCLE_UNLEARNED
    assert projection["packs"]["N01"]["last_completion_at"] == ""


def test_forged_terminal_cannot_commit_item_promotion() -> None:
    terminal = _compiled_forward_terminal()
    events = _completion_events(terminal)
    assert committed_retest_completion_ids(events) == {"adversarial"}

    terminal.payload_json["quality"]["authority"] = "client_claimed_complete"
    assert committed_retest_completion_ids(events) == set()


def test_item_without_terminal_never_advances_pack_review_cycle() -> None:
    item = _practice_event("1A433000-B041", question_id="variant_partial")
    item.payload_json.update({
        "assessment_type": "luban_review_variant",
        "retest_completion_id": "partial",
        "practice_mode": "review",
        "score_ratio": 1.0,
        "claim_promotion_allowed": True,
    })
    projection = project_pack_lifecycle(events=[item], claims=[], pack_ids=_PACK_IDS)
    n01 = projection["packs"]["N01"]
    assert n01["lifecycle_state"] == LIFECYCLE_UNLEARNED
    assert n01["successful_review_streak"] == 0
    assert n01["last_review_status"] == ""
    assert projection["unassigned_practice"][0]["reason"] == "completion_terminal_ref_missing"


def test_terminal_prescription_status_wins_over_conflicting_score_ratio() -> None:
    projection = project_pack_lifecycle(
        events=_completion_events(
            _signed_terminal(status="not_verified", score_ratio=1.0)
        ),
        claims=[],
        pack_ids=_PACK_IDS,
    )
    n01 = projection["packs"]["N01"]
    assert n01["last_review_status"] == "not_verified"
    assert n01["successful_review_streak"] == 0


def test_foreign_or_internally_inconsistent_terminal_cannot_move_pack_clock() -> None:
    events = [
        _signed_terminal(source_feature="construction_grading"),
        _signed_terminal(assessment_type="luban_forward_completion"),
        _signed_terminal(target_pack_id="F16"),
    ]
    projection = project_pack_lifecycle(events=events, claims=[], pack_ids=_PACK_IDS)
    n01 = projection["packs"]["N01"]
    assert n01["last_completion_at"] == ""
    assert n01["successful_review_streak"] == 0


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

    # 文件缺失 → 空索引(降级 ok=False),但不落缓存
    (index, cross_year), ok = plp._question_to_packs()
    assert index == {} and cross_year == frozenset() and ok is False

    artifact.write_text(
        '{"reverse_index": {"2015:EXAM_XW2015_MU_30": ["N01"]}}', encoding="utf-8"
    )
    (index, _), ok = plp._question_to_packs()
    # 同进程恢复:qualified 精确键 + 裸键都可查
    assert ok is True
    assert index["2015:EXAM_XW2015_MU_30"] == ("N01",)
    assert index["EXAM_XW2015_MU_30"] == ("N01",)

    # 产物热更新(内容变) → 缓存按 stat 键失效重读
    artifact.write_text(
        '{"reverse_index": {"2016:EXAM_XW2016_SI_01": ["A01"]}}', encoding="utf-8"
    )
    (index, _), ok = plp._question_to_packs()
    assert "EXAM_XW2016_SI_01" in index and "EXAM_XW2015_MU_30" not in index
    plp._ARTIFACT_CACHE.clear()


def test_missing_artifacts_mark_projection_degraded_and_recover(tmp_path, monkeypatch) -> None:
    # 病A:容器里缺编译产物时曾静默降级成"什么都没练过"且看起来健康。
    # 契约:加载失败 → degraded=True + warning 可观测;修好文件后同进程恢复
    # (失败不落缓存),degraded 回 False。
    import deeptutor.services.learner_state.pack_lifecycle_projection as plp

    map_path = tmp_path / "map.json"
    registry_path = tmp_path / "registry.json"
    monkeypatch.setattr(plp, "_QUESTION_PACK_MAP_PATH", map_path)
    monkeypatch.setattr(plp, "_PACK_TAXONOMY_REGISTRY_PATH", registry_path)
    plp._ARTIFACT_CACHE.clear()

    # 不挂真 loguru sink:同 shard 的 tutorbot 测试会在 sys.modules 顶层塞假 loguru
    # (无 .add),直接替换模块级 logger 才不吃隔离污染。
    warnings: list[str] = []

    class _CaptureLogger:
        def warning(self, message: str, *args: object, **kwargs: object) -> None:
            warnings.append(str(message).format(*args, **kwargs) if args or kwargs else str(message))

        def __getattr__(self, _name: str):
            return lambda *args, **kwargs: None

    monkeypatch.setattr(plp, "logger", _CaptureLogger())
    projection = project_pack_lifecycle(events=[], claims=[], pack_ids=_PACK_IDS)
    assert projection["degraded"] is True
    assert any("pack lifecycle artifact" in text for text in warnings)

    map_path.write_text('{"reverse_index": {}}', encoding="utf-8")
    registry_path.write_text('{"packs": {}}', encoding="utf-8")
    projection = project_pack_lifecycle(events=[], claims=[], pack_ids=_PACK_IDS)
    assert projection["degraded"] is False
    plp._ARTIFACT_CACHE.clear()


def test_healthy_repo_artifacts_are_not_degraded() -> None:
    projection = project_pack_lifecycle(events=[], claims=[], pack_ids=_PACK_IDS)
    assert projection["degraded"] is False


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
    # 裸键跨年 fan-out 不同 → fail-closed,专用 reason 可观测(病H-1)
    pack, reason = plp._resolve_pack_for_practice({"question_id": "EXAM_1A411001_P0001_01"})
    assert pack == "" and reason == "cross_year_ambiguous"
    plp._ARTIFACT_CACHE.clear()


def test_same_year_multi_pack_stays_question_ambiguous(tmp_path, monkeypatch) -> None:
    # 对照臂:同年一题多 pack 不是跨年碰撞,保留原 question_ambiguous。
    import deeptutor.services.learner_state.pack_lifecycle_projection as plp

    artifact = tmp_path / "map.json"
    artifact.write_text(
        '{"reverse_index": {"2022:EXAM_MULTI_01": ["A01", "N01"]}}', encoding="utf-8"
    )
    monkeypatch.setattr(plp, "_QUESTION_PACK_MAP_PATH", artifact)
    plp._ARTIFACT_CACHE.clear()
    pack, reason = plp._resolve_pack_for_practice({"question_id": "EXAM_MULTI_01"})
    assert pack == "" and reason == "question_ambiguous"
    plp._ARTIFACT_CACHE.clear()


def test_repo_artifact_cross_year_collision_audit_is_fail_closed() -> None:
    """病H-1 数据锚定审计:真实编译产物中「裸 chunk_id 跨年碰撞且 pack
    fan-out 不同」实测 >0(2026-07-04 审计 = 14 个)——按规格走运行时
    fail-closed 分支:每个碰撞裸 id 必须落 unassigned,
    reason="cross_year_ambiguous",禁硬塞任何一个 pack。"""
    from collections import defaultdict
    import json as _json

    import deeptutor.services.learner_state.pack_lifecycle_projection as plp

    compiled = _json.loads(plp._QUESTION_PACK_MAP_PATH.read_text(encoding="utf-8"))
    year_sets: dict[str, dict[str, frozenset]] = defaultdict(dict)
    for qualified, packs in (compiled.get("reverse_index") or {}).items():
        year, _, bare = qualified.partition(":")
        year_sets[bare][year] = frozenset(packs)
    collisions = sorted(
        bare
        for bare, by_year in year_sets.items()
        if len(by_year) > 1 and len(set(by_year.values())) > 1
    )
    assert collisions, "审计前提失效:产物已无跨年 fan-out 碰撞,应改走编译期 guard 分支"
    plp._ARTIFACT_CACHE.clear()
    for bare in collisions:
        pack, reason = plp._resolve_pack_for_practice({"question_id": bare})
        assert (pack, reason) == ("", "cross_year_ambiguous"), bare
