"""Rich-leaf runtime supply: publish builder, fail-open loader, flag gate, and the
resolve_general_knowledge_context injection seam (flag off -> byte-identical behavior)."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

from deeptutor.services.construction_grading import compiled_registry_resolver as crr
from deeptutor.services.construction_grading import rich_leaf_runtime as rlr

REPO = Path(__file__).resolve().parents[3]
REAL_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613"
    / "runtime_token_pack_v301_quarantine_annotated.json"
)


def _unit(leaf_id: str, unit_id: str) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "leaf_id": leaf_id,
        "leaf_name_path": f"路径 > {leaf_id}",
        "compiled_context": {
            "concepts": [f"### {leaf_id}\n\n概念正文。"],
            "rules": [json.dumps({"id": "R1", "description": f"{leaf_id} 规则。", "severity": "informative"})],
            "exam_patterns": [json.dumps({"id": "EP1", "description": "考点？", "grading_keywords": ["甲", "乙"]})],
            "teaching_cards": [json.dumps({"id": "TC1", "title": "卡片", "content": "卡片内容。"})],
        },
        "confidence": "high",
        "source_lane": "source_truth",
        "source_ref": {"record_id": "r", "chunk_id": "c"},
        "relative_path": "2026教材/x.json",
        # pack-internal lifecycle flags must NOT leak into runtime records
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
    }


def _pack(units: list[dict[str, Any]], quarantined: list[str]) -> dict[str, Any]:
    return {
        "schema": rlr.PACK_SCHEMA,
        "version": "v3.0.1_test",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "safety": {
            "official_score_allowed": False,
            "canonical_truth_written": False,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
        },
        "quarantine": {"quarantine_candidate_unit_ids": quarantined},
        "runtime_token_pack_units": units,
    }


@pytest.fixture(autouse=True)
def _fresh_loader_cache():
    rlr._load_index.cache_clear()
    yield
    rlr._load_index.cache_clear()


def _install_supply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pack: dict[str, Any]) -> dict[str, Any]:
    bundle, pointer = rlr.build_runtime_supply_bundle(pack)
    supply = tmp_path / "v_rich_leaf_context"
    supply.mkdir(parents=True, exist_ok=True)
    (supply / "rich_leaf_context_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    (supply / "canonical_pointer.json").write_text(json.dumps(pointer, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rlr, "_SUPPLY_DIR", supply)
    rlr._load_index.cache_clear()
    return pointer


# --------------------------- publish builder ---------------------------


def test_build_filters_quarantine_units_and_strips_lifecycle_flags() -> None:
    pack = _pack([_unit("L1", "u1"), _unit("L2", "u2"), _unit("L3", "uq")], quarantined=["uq"])
    bundle, pointer = rlr.build_runtime_supply_bundle(pack)
    records = bundle["records"]
    assert [r["leaf_id"] for r in records] == ["L1", "L2"]
    assert bundle["manifest"]["quarantine_excluded_count"] == 1
    assert pointer["quarantine_excluded_count"] == 1
    assert all("runtime_install_allowed" not in r and "candidate_only" not in r for r in records)
    # default lifecycle: release_candidate, NOT published (publish-to-default is an owner action)
    assert bundle["manifest"]["status"] == "release_candidate"
    assert bundle["manifest"]["published"] is False
    assert pointer["published"] is False
    assert bundle["manifest"]["official_score_allowed"] is False
    ok, reason = crr.verify_bundle(bundle, pointer, namespace="rich_leaf_context")
    assert ok, reason


def test_build_rejects_wrong_schema_and_safety_violation() -> None:
    pack = _pack([_unit("L1", "u1")], quarantined=[])
    with pytest.raises(ValueError, match="schema"):
        rlr.build_runtime_supply_bundle({**pack, "schema": "other.v9"})
    bad_safety = {**pack, "safety": {**pack["safety"], "official_score_allowed": True}}
    with pytest.raises(ValueError, match="official_score_allowed"):
        rlr.build_runtime_supply_bundle(bad_safety)


@pytest.mark.skipif(not REAL_PACK.exists(), reason="frozen v3.0.1 pack artifact not present")
def test_build_real_pack_excludes_exactly_the_17_quarantine_candidates() -> None:
    pack = json.loads(REAL_PACK.read_text(encoding="utf-8"))
    bundle, pointer = rlr.build_runtime_supply_bundle(pack)
    assert bundle["manifest"]["source_pack_unit_count"] == 1534
    assert bundle["manifest"]["quarantine_excluded_count"] == 17
    assert bundle["manifest"]["record_count"] == 1517
    quarantined = set(pack["quarantine"]["quarantine_candidate_unit_ids"])
    assert not any(r["unit_id"] in quarantined for r in bundle["records"])
    ok, reason = crr.verify_bundle(bundle, pointer, namespace="rich_leaf_context")
    assert ok, reason


# --------------------------- loader ---------------------------


def test_loader_hit_returns_teaching_tier_context_and_miss_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_supply(tmp_path, monkeypatch, _pack([_unit("L1", "u1")], quarantined=[]))
    hit = rlr.get_rich_leaf_context("L1")
    assert hit is not None
    assert hit["authority"] == rlr.AUTHORITY
    assert hit["official_score_allowed"] is False
    assert hit["llm_may_decide_correctness"] is False
    assert hit["tier"] == "teaching_context_not_answer_key"
    assert hit["compiled_context"]["concepts"]
    assert rlr.get_rich_leaf_context("NOPE") is None
    assert rlr.get_rich_leaf_context("") is None


def test_loader_hash_mismatch_fails_open_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pointer = _install_supply(tmp_path, monkeypatch, _pack([_unit("L1", "u1")], quarantined=[]))
    tampered = {**pointer, "expected_content_hash": "0" * 64}
    (rlr._SUPPLY_DIR / "canonical_pointer.json").write_text(json.dumps(tampered), encoding="utf-8")
    rlr._load_index.cache_clear()
    with caplog.at_level("WARNING"):
        assert rlr.get_rich_leaf_context("L1") is None
    assert any("rich leaf runtime supply rejected" in r.message for r in caplog.records)


def test_loader_missing_supply_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rlr, "_SUPPLY_DIR", tmp_path / "absent")
    rlr._load_index.cache_clear()
    assert rlr.get_rich_leaf_context("L1") is None


# --------------------------- multi-leaf selection ---------------------------


def _kw_unit(leaf_id: str, unit_id: str, *, name_path: str, keywords: list[str]) -> dict[str, Any]:
    unit = _unit(leaf_id, unit_id)
    unit["leaf_name_path"] = name_path
    unit["compiled_context"]["exam_patterns"] = [
        json.dumps({"id": "EP1", "description": "考点？", "grading_keywords": keywords}, ensure_ascii=False)
    ]
    return unit


def _multi_supply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_supply(
        tmp_path,
        monkeypatch,
        _pack(
            [
                _kw_unit("L-PRIMARY", "u1", name_path="技术 > 防水", keywords=["屋面防水"]),
                _kw_unit("L-RARE", "u2", name_path="技术 > 脚手架", keywords=["连墙件"]),
                _kw_unit("L-COMMON-A", "u3", name_path="管理 > 质量甲", keywords=["质量验收"]),
                _kw_unit("L-COMMON-B", "u4", name_path="管理 > 质量乙", keywords=["质量验收"]),
                _kw_unit("L-NOHIT", "u5", name_path="法规 > 其他", keywords=["招标投标"]),
            ],
            quarantined=[],
        ),
    )


def test_multi_leaf_primary_first_and_idf_prefers_rare_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    terms = ["连墙件", "质量验收"]
    out = rlr.get_rich_leaf_contexts(terms, ["L-PRIMARY"], top_k=3)
    ids = [c["leaf_id"] for c in out]
    # primary first; the rare keyword (df=1) outweighs the common one (df=2)
    assert ids[0] == "L-PRIMARY"
    assert ids[1] == "L-RARE"
    assert len(ids) == 3 and ids[2] in ("L-COMMON-A", "L-COMMON-B")
    # tie between common leaves breaks deterministically by leaf_id
    assert ids[2] == "L-COMMON-A"
    # deterministic across calls
    assert [c["leaf_id"] for c in rlr.get_rich_leaf_contexts(terms, ["L-PRIMARY"], top_k=3)] == ids
    # every context keeps the teaching-tier shape
    assert all(c["official_score_allowed"] is False for c in out)


def test_multi_leaf_top_k_truncates_and_no_hit_leaves_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    out = rlr.get_rich_leaf_contexts(["连墙件", "质量验收"], ["L-PRIMARY"], top_k=2)
    assert [c["leaf_id"] for c in out] == ["L-PRIMARY", "L-RARE"]
    # zero-score leaves never selected even with budget left
    out_wide = rlr.get_rich_leaf_contexts(["连墙件"], ["L-PRIMARY"], top_k=5)
    assert [c["leaf_id"] for c in out_wide] == ["L-PRIMARY", "L-RARE"]


def test_multi_leaf_primary_miss_and_empty_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    # primary not in bundle -> supplements still selected by terms
    out = rlr.get_rich_leaf_contexts(["连墙件"], ["ZZ-NOPE"], top_k=3)
    assert [c["leaf_id"] for c in out] == ["L-RARE"]
    # no primary hit + no term hit -> empty (caller attaches nothing)
    assert rlr.get_rich_leaf_contexts(["不存在词"], ["ZZ-NOPE"], top_k=3) == []
    assert rlr.get_rich_leaf_contexts([], [], top_k=3) == []


def test_multi_leaf_single_leaf_backward_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    single = rlr.get_rich_leaf_context("L-PRIMARY")
    assert rlr.get_rich_leaf_contexts([], ["L-PRIMARY"], top_k=1) == [single]
    assert rlr.get_rich_leaf_contexts(["连墙件"], ["L-PRIMARY"], top_k=1) == [single]


def test_multi_leaf_missing_supply_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rlr, "_SUPPLY_DIR", tmp_path / "absent")
    rlr._load_index.cache_clear()
    assert rlr.get_rich_leaf_contexts(["连墙件"], ["L-PRIMARY"]) == []


# --------------------------- two-layer (focus / background) selection ---------------------------


def test_focus_terms_hit_outranks_background_only_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    # Background terms alone would rank L-RARE first (rare keyword); a focus hit on the
    # common keyword must outrank any background-only hit (focus layer dominates).
    out = rlr.get_rich_leaf_contexts(["连墙件"], [], focus_terms=["质量验收"], top_k=2)
    ids = [c["leaf_id"] for c in out]
    # both focus hits (common keyword, df=2) outrank the background-only hit (rare keyword,
    # higher IDF but 0.3x background weight and zero focus score)
    assert ids == ["L-COMMON-A", "L-COMMON-B"]


def test_focus_terms_only_caller_single_text_compat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    # caller with only one text passes it as focus and leaves the background layer empty;
    # ranking equals the legacy single-layer call with the same terms
    legacy = [c["leaf_id"] for c in rlr.get_rich_leaf_contexts(["连墙件", "质量验收"], ["L-PRIMARY"], top_k=3)]
    focused = [c["leaf_id"] for c in rlr.get_rich_leaf_contexts([], ["L-PRIMARY"], focus_terms=["连墙件", "质量验收"], top_k=3)]
    assert focused == legacy


def test_background_terms_alone_keep_legacy_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    # no focus terms -> background layer behaves exactly like the legacy single-layer query
    out = rlr.get_rich_leaf_contexts(["连墙件", "质量验收"], ["L-PRIMARY"], focus_terms=None, top_k=3)
    assert [c["leaf_id"] for c in out] == ["L-PRIMARY", "L-RARE", "L-COMMON-A"]


# --------------------------- citable block labels ---------------------------


def test_format_pack_grounding_lines_multi_blocks_carry_citable_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    riches = rlr.get_rich_leaf_contexts(["连墙件", "质量验收"], ["L-PRIMARY"], top_k=3)
    text = "\n".join(rlr.format_rich_leaf_pack_grounding_lines({"rich_leaf_contexts": riches}))
    assert "【教材要点 L1】(L-PRIMARY)" in text
    assert "【教材要点 L2】(L-RARE)" in text
    assert "【教材要点 L3】(L-COMMON-A)" in text
    assert text.index("【教材要点 L1】") < text.index("【教材要点 L2】") < text.index("【教材要点 L3】")


def test_format_pack_grounding_lines_single_legacy_key_has_no_label() -> None:
    hit = {
        "leaf_id": "L1",
        "leaf_name_path": "路径 > L1",
        "compiled_context": _unit("L1", "u1")["compiled_context"],
    }
    text = "\n".join(rlr.format_rich_leaf_pack_grounding_lines({"rich_leaf_context": hit}))
    assert "教材要点" not in text  # legacy single-key rendering stays byte-identical


# --------------------------- multi-block grounding renderer ---------------------------


def test_format_pack_grounding_lines_multi_blocks_primary_always_and_cap_drops_supplements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _multi_supply(tmp_path, monkeypatch)
    riches = rlr.get_rich_leaf_contexts(["连墙件", "质量验收"], ["L-PRIMARY"], top_k=3)
    pack = {"rich_leaf_contexts": riches}
    lines = rlr.format_rich_leaf_pack_grounding_lines(pack)
    text = "\n".join(lines)
    assert text.count("富叶编译上下文") == 3
    assert text.index("L-PRIMARY") < text.index("L-RARE") < text.index("L-COMMON-A")
    # a tight cap keeps the primary block whole and drops supplement blocks
    primary_only = rlr.format_rich_leaf_pack_grounding_lines(pack, max_chars=1)
    assert "\n".join(primary_only).count("富叶编译上下文") == 1
    assert "L-PRIMARY" in "\n".join(primary_only)
    # env override is honored
    monkeypatch.setenv(rlr.GROUNDING_MAX_CHARS_ENV, "1")
    assert "\n".join(rlr.format_rich_leaf_pack_grounding_lines(pack)).count("富叶编译上下文") == 1


def test_format_pack_grounding_lines_single_key_backward_compatible() -> None:
    hit = {
        "leaf_id": "L1",
        "leaf_name_path": "路径 > L1",
        "compiled_context": _unit("L1", "u1")["compiled_context"],
    }
    # legacy single rich_leaf_context key renders identically to the single-block renderer
    assert rlr.format_rich_leaf_pack_grounding_lines({"rich_leaf_context": hit}) == (
        rlr.format_rich_leaf_grounding_lines(hit)
    )
    # neither key -> [] (flag-off packs render byte-identically to legacy)
    assert rlr.format_rich_leaf_pack_grounding_lines({}) == []
    assert rlr.format_rich_leaf_pack_grounding_lines(None) == []
    assert rlr.format_rich_leaf_pack_grounding_lines({"rich_leaf_contexts": ["garbage", 42]}) == []


# --------------------------- env flag ---------------------------


def test_runtime_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(rlr.ENV_FLAG, raising=False)
    assert rlr.rich_leaf_runtime_enabled() is False
    monkeypatch.setenv(rlr.ENV_FLAG, "false")
    assert rlr.rich_leaf_runtime_enabled() is False
    monkeypatch.setenv(rlr.ENV_FLAG, "true")
    assert rlr.rich_leaf_runtime_enabled() is True


# --------------------------- grounding lines ---------------------------


def test_format_rich_leaf_grounding_lines_renders_marker_and_fails_open() -> None:
    hit = {
        "leaf_id": "L1",
        "leaf_name_path": "路径 > L1",
        "compiled_context": _unit("L1", "u1")["compiled_context"],
    }
    lines = rlr.format_rich_leaf_grounding_lines(hit)
    text = "\n".join(lines)
    assert "不得作为官方判分依据" in text
    assert "L1" in text and "概念正文" in text and "关键词" in text
    assert rlr.format_rich_leaf_grounding_lines(None) == []
    assert rlr.format_rich_leaf_grounding_lines({"compiled_context": "garbage"}) == []
    assert rlr.format_rich_leaf_grounding_lines({"compiled_context": {}}) == []


# --------------------------- scoring_points grading-mode rendering ---------------------------


def _scoring_point_unit_context() -> dict[str, Any]:
    compiled = dict(_unit("L1", "u1")["compiled_context"])
    compiled["scoring_points"] = [
        {
            "point_id": "m35:Q2-1A436000-罚则:P1",
            "source": "m35_artifact",
            "statement": "必须写出规范术语原文。",
            "max_score": 5,
            "policy_type": "list_rule",
            "required_terms": ["施工总进度计划表(图)", "资源需要量及供应平衡表"],
            "provenance": {
                "source_authority": "textbook",
                "chunk_id": "1A433000_059_0089",
                "quote": "施工总进度计划表（图",
            },
        },
        {
            "point_id": "ca:1A433000_059_0089",
            "source": "chunk_assessment",
            "statement": "施工总进度计划应包含哪些内容？",
            "required_terms": ["编制说明"],
            "provenance": {"source_authority": "textbook", "chunk_id": "1A433000_059_0089", "quote": "编制说明…"},
        },
    ]
    return {"leaf_id": "L1", "leaf_name_path": "路径 > L1", "compiled_context": compiled}


def test_grading_mode_renders_scoring_points_first_with_terms_and_source() -> None:
    rich = _scoring_point_unit_context()
    lines = rlr.format_rich_leaf_grounding_lines(rich, grading=True)
    text = "\n".join(lines)
    # scoring points render before the teaching body (concepts/rules/...)
    sp_idx = next(i for i, ln in enumerate(lines) if ln.startswith("- [采分点]"))
    concept_idx = next(i for i, ln in enumerate(lines) if ln.startswith("- [概念]"))
    assert sp_idx < concept_idx
    assert "必含术语：施工总进度计划表(图)、资源需要量及供应平衡表" in text
    assert "〔源:1A433000_059_0089〕" in text
    # teaching-tier authority marker is unchanged
    assert "不得作为官方判分依据" in text


def test_default_mode_ignores_scoring_points_byte_identical() -> None:
    rich = _scoring_point_unit_context()
    plain = {
        "leaf_id": "L1",
        "leaf_name_path": "路径 > L1",
        "compiled_context": _unit("L1", "u1")["compiled_context"],
    }
    # normal (non-grading) rendering never shows scoring_points and stays byte-identical
    assert rlr.format_rich_leaf_grounding_lines(rich) == rlr.format_rich_leaf_grounding_lines(plain)
    assert "采分点" not in "\n".join(rlr.format_rich_leaf_grounding_lines(rich))


def test_grading_mode_without_scoring_points_matches_default() -> None:
    plain = {
        "leaf_id": "L1",
        "leaf_name_path": "路径 > L1",
        "compiled_context": _unit("L1", "u1")["compiled_context"],
    }
    assert rlr.format_rich_leaf_grounding_lines(plain, grading=True) == rlr.format_rich_leaf_grounding_lines(plain)


def test_grading_mode_malformed_scoring_points_degrade_silently() -> None:
    compiled = dict(_unit("L1", "u1")["compiled_context"])
    compiled["scoring_points"] = ["garbage", 42, {"source": "x"}, {"statement": "  "}]
    rich = {"leaf_id": "L1", "leaf_name_path": "路径 > L1", "compiled_context": compiled}
    lines = rlr.format_rich_leaf_grounding_lines(rich, grading=True)
    assert all(not ln.startswith("- [采分点]") for ln in lines)
    assert "概念正文" in "\n".join(lines)


def test_pack_grounding_lines_grading_passthrough() -> None:
    rich = _scoring_point_unit_context()
    pack = {"rich_leaf_contexts": [rich]}
    graded = "\n".join(rlr.format_rich_leaf_pack_grounding_lines(pack, grading=True))
    normal = "\n".join(rlr.format_rich_leaf_pack_grounding_lines(pack))
    assert "- [采分点]" in graded
    assert "- [采分点]" not in normal
    # legacy single-key path also honors grading
    single = "\n".join(rlr.format_rich_leaf_pack_grounding_lines({"rich_leaf_context": rich}, grading=True))
    assert "- [采分点]" in single


# --------------------------- injection seam (general knowledge confluence) ---------------------------


def test_flag_off_resolve_general_knowledge_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge as gk

    monkeypatch.delenv(rlr.ENV_FLAG, raising=False)
    out = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert out is not None
    assert "rich_leaf_context" not in out  # flag off -> no new key, legacy pack shape exactly
    assert "rich_leaf_contexts" not in out


def test_flag_on_attaches_rich_leaf_context_and_grounding_renders_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge as gk

    monkeypatch.delenv(rlr.ENV_FLAG, raising=False)
    baseline = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert baseline is not None
    leaf = baseline["classified_leaf"]

    supplement = _kw_unit("L-SUPP", "u2", name_path="技术 > 高层住宅补充", keywords=["高层住宅"])
    _install_supply(tmp_path, monkeypatch, _pack([_unit(leaf, "u1"), supplement], quarantined=[]))
    monkeypatch.setenv(rlr.ENV_FLAG, "true")
    out = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert out is not None
    riches = out.get("rich_leaf_contexts")
    assert isinstance(riches, list) and riches
    assert riches[0]["leaf_id"] == leaf  # primary (classified leaf) first
    assert [r["leaf_id"] for r in riches[1:]] == ["L-SUPP"]  # query-term supplement follows
    assert all(r["official_score_allowed"] is False for r in riches)
    # rich context renders into the grounding, before the four-source items
    grounding = gk.format_general_knowledge_grounding(out)
    assert "富叶编译上下文" in grounding
    # rich context renders before the first four-source lane item; the lane of that first
    # item is axis content (taxonomy-frozen revisions may legitimately change it), so pin
    # the ordering MECHANISM against any four-source lane marker, not a specific lane.
    first_lane = re.search(r"- \[(教材|规范|真题|讲义)", grounding)
    assert first_lane is not None
    assert grounding.index("富叶编译上下文") < first_lane.start()
    assert "L-SUPP" in grounding
    # legacy pack fields are untouched (additive key only)
    for key in ("classified_leaf", "sources", "confidence", "official_score_allowed"):
        assert out[key] == baseline[key]


def test_flag_on_miss_fails_open_to_legacy_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge as gk

    # supply contains only an unrelated leaf -> miss -> pack identical to legacy shape
    _install_supply(tmp_path, monkeypatch, _pack([_unit("ZZ-NOPE", "u1")], quarantined=[]))
    monkeypatch.setenv(rlr.ENV_FLAG, "true")
    out = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert out is not None
    assert "rich_leaf_context" not in out
    assert "rich_leaf_contexts" not in out


# ----------- G2 runtime authority invariant: official_answer > textbook_cited -----------
# A grading authority-resolution sink can call these to get a STRUCTURAL guarantee that a
# rich-leaf point (50x the volume of the official key) can never enter the official
# correctness channel — today that is held only by the accident that no caller wires
# grading=True / merges rich-leaf points into rubric_points. The invariant makes it
# deterministic: rich-leaf is structurally supporting (textbook_cited), official always wins.


def test_rich_leaf_grading_authority_is_canonical_textbook_cited() -> None:
    # the structural tier of every rich-leaf point reuses the canonical vocabulary, never a new name
    from deeptutor.services.construction_grading import unified_grading_object as ugo

    assert rlr.RICH_LEAF_GRADING_AUTHORITY == ugo.AUTH_TEXTBOOK_CITED
    assert rlr.RICH_LEAF_GRADING_AUTHORITY != ugo.AUTH_OFFICIAL_ANSWER


def test_assert_supporting_only_passes_for_real_loader_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_supply(tmp_path, monkeypatch, _pack([_unit("L1", "u1")], quarantined=[]))
    record = rlr.get_rich_leaf_context("L1")
    assert record is not None
    # the loader's own output is structurally supporting — the invariant accepts it unchanged
    assert rlr.assert_supporting_only(record) is record


def test_assert_supporting_only_rejects_official_self_claim() -> None:
    # a rich-leaf record that tries to claim official correctness authority is a contract breach
    for forged in (
        {"leaf_id": "L1", "official_score_allowed": True},
        {"leaf_id": "L1", "llm_may_decide_correctness": True},
        {"leaf_id": "L1", "authority_source": "official_answer"},
        {"leaf_id": "L1", "tier": "answer_key"},
    ):
        with pytest.raises(ValueError, match="rich_leaf"):
            rlr.assert_supporting_only(forged)


def test_resolve_grading_point_authority_official_always_wins() -> None:
    # official present: rich-leaf points are demoted to supporting and NEVER decide correctness
    resolved = rlr.resolve_grading_point_authority(
        official_present=True,
        rich_leaf_points=[{"point_id": "rl1", "statement": "教材补充点"}],
    )
    assert resolved["official_decides_correctness"] is True
    assert resolved["rich_leaf_role"] == "supporting_citation_only"
    assert all(p["authority_source"] == rlr.RICH_LEAF_GRADING_AUTHORITY for p in resolved["supporting_points"])
    assert all(p["official_score_allowed"] is False for p in resolved["supporting_points"])
    # rich-leaf points are NEVER returned as official scoring points
    assert "scoring_points" not in resolved


def test_resolve_grading_point_authority_official_absent_never_promotes_rich_leaf() -> None:
    # official ABSENT: rich-leaf must NOT impersonate the official key — it stays supporting,
    # correctness falls to the open-world official path (RAG-grounded reference), not the 5705 points
    resolved = rlr.resolve_grading_point_authority(
        official_present=False,
        rich_leaf_points=[{"point_id": "rl1", "statement": "教材补充点"}],
    )
    assert resolved["official_decides_correctness"] is False
    assert resolved["rich_leaf_role"] == "supporting_citation_only"
    # crucially: rich-leaf points are still supporting-only; they do not become scoring points
    assert "scoring_points" not in resolved
    assert all(p["authority_source"] == rlr.RICH_LEAF_GRADING_AUTHORITY for p in resolved["supporting_points"])


def test_resolve_grading_point_authority_empty_rich_leaf_is_byte_identical_noop() -> None:
    # no rich-leaf points -> the resolver adds nothing the legacy path didn't have
    resolved = rlr.resolve_grading_point_authority(official_present=True, rich_leaf_points=[])
    assert resolved["supporting_points"] == []
    assert resolved["rich_leaf_role"] == "supporting_citation_only"
