"""Rich-leaf runtime supply: publish builder, fail-open loader, flag gate, and the
resolve_general_knowledge_context injection seam (flag off -> byte-identical behavior)."""
from __future__ import annotations

import json
from pathlib import Path
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


# --------------------------- injection seam (general knowledge confluence) ---------------------------


def test_flag_off_resolve_general_knowledge_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge as gk

    monkeypatch.delenv(rlr.ENV_FLAG, raising=False)
    out = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert out is not None
    assert "rich_leaf_context" not in out  # flag off -> no new key, legacy pack shape exactly


def test_flag_on_attaches_rich_leaf_context_and_grounding_renders_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge as gk

    monkeypatch.delenv(rlr.ENV_FLAG, raising=False)
    baseline = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert baseline is not None
    leaf = baseline["classified_leaf"]

    _install_supply(tmp_path, monkeypatch, _pack([_unit(leaf, "u1")], quarantined=[]))
    monkeypatch.setenv(rlr.ENV_FLAG, "true")
    out = gk.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert out is not None
    rich = out.get("rich_leaf_context")
    assert isinstance(rich, dict) and rich["leaf_id"] == leaf
    assert rich["official_score_allowed"] is False
    # rich context renders into the grounding, before the four-source items
    grounding = gk.format_general_knowledge_grounding(out)
    assert "富叶编译上下文" in grounding
    assert grounding.index("富叶编译上下文") < grounding.index("- [教材")
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
