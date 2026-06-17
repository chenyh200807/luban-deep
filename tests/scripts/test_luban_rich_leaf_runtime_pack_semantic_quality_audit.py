from __future__ import annotations

from scripts.run_luban_rich_leaf_runtime_pack_semantic_quality_audit import (
    build_runtime_pack_semantic_quality_audit,
)


def _classification() -> dict:
    return {
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
        "release_truth_claimed": False,
    }


def _safety() -> dict:
    return {
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "installed_runtime_supply": False,
        "production_write_count": 0,
        "release_truth_claimed": False,
    }


def _pack(units: list[dict]) -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": "vtest",
        "classification": _classification(),
        "safety": _safety(),
        "runtime_token_pack_units": units,
    }


def _taxonomy() -> dict:
    return {
        "children": [
            {
                "code": "L-STONE",
                "name": "石材的性能与应用",
                "keywords": ["天然石材", "抗压强度", "耐久性", "勒脚"],
            },
            {"code": "L-DUP", "name": "叶子甲", "keywords": ["甲"]},
            {"code": "L-DUP", "name": "叶子乙", "keywords": ["乙"]},
            {"code": "L-NOKW", "name": "无关键词叶子"},
        ]
    }


def _good_unit() -> dict:
    return {
        "unit_id": "u_good",
        "leaf_id": "L-STONE",
        "leaf_name_path": "材料 > 石材的性能与应用",
        "compiled_context": {
            "concepts": ["天然石材抗压强度高，耐久性好，多用于基础、勒脚部位。"],
            "rules": ['{"description": "石材勒脚规则", "source_refs": ["chunk_1"]}'],
        },
        "source_ref": {
            "record_id": "book.json#chunk:chunk_1",
            "source_path": "book.json",
            "source_lane": "textbook",
            "span_hash": "abc",
            "file_sha256": "def",
        },
    }


def _polluted_unit() -> dict:
    return {
        "unit_id": "u_polluted",
        "leaf_id": "L-STONE",
        "leaf_name_path": "材料 > 石材的性能与应用",
        "compiled_context": {"concepts": ["地基基础应满足承载力要求，沉降不得影响上部结构。"]},
        "source_ref": {"record_id": "gb.json", "source_path": "gb.json", "source_lane": "textbook", "span_hash": "x"},
    }


def test_audit_tiers_good_and_polluted_units() -> None:
    report = build_runtime_pack_semantic_quality_audit(
        runtime_token_pack=_pack([_good_unit(), _polluted_unit()]),
        taxonomy=_taxonomy(),
        check_source_files=False,
    )
    rows = {row["unit_id"]: row for row in report["rows"]}
    assert rows["u_good"]["semantic_tier"] == "ok"
    assert rows["u_good"]["keyword_overlap"] >= 0.5
    assert rows["u_polluted"]["semantic_tier"] == "pollution_suspect"
    assert rows["u_polluted"]["keyword_overlap"] == 0.0
    assert report["summary"]["unit_count"] == 2
    assert report["summary"]["pollution_suspect_count"] == 1
    assert report["verdict"] == "AUDIT_COMPLETED_WITH_FINDINGS"


def test_audit_flags_missing_provenance_and_duplicate_codes() -> None:
    unit = _good_unit()
    unit["unit_id"] = "u_noprov"
    unit["source_ref"] = {"record_id": "book.json"}
    dup_unit = {
        "unit_id": "u_dup",
        "leaf_id": "L-DUP",
        "leaf_name_path": "x > 叶子乙",
        "compiled_context": {"concepts": ["乙的内容"]},
        "source_ref": _good_unit()["source_ref"],
    }
    report = build_runtime_pack_semantic_quality_audit(
        runtime_token_pack=_pack([unit, dup_unit]),
        taxonomy=_taxonomy(),
        check_source_files=False,
    )
    rows = {row["unit_id"]: row for row in report["rows"]}
    assert "span_hash" in rows["u_noprov"]["provenance_missing_fields"]
    assert "file_sha256" in rows["u_noprov"]["provenance_missing_fields"]
    assert rows["u_dup"]["taxonomy_duplicate_code"] is True
    assert report["summary"]["provenance_incomplete_count"] >= 1
    assert report["summary"]["taxonomy_duplicate_code_unit_count"] == 1


def test_audit_low_signal_when_leaf_has_no_keywords() -> None:
    unit = _good_unit()
    unit["unit_id"] = "u_nokw"
    unit["leaf_id"] = "L-NOKW"
    unit["leaf_name_path"] = "x > 无关键词叶子"
    report = build_runtime_pack_semantic_quality_audit(
        runtime_token_pack=_pack([unit]),
        taxonomy=_taxonomy(),
        check_source_files=False,
    )
    assert report["rows"][0]["semantic_tier"] == "low_signal_needs_review"


def test_audit_field_source_ref_coverage_and_thinness() -> None:
    thin = {
        "unit_id": "u_thin",
        "leaf_id": "L-STONE",
        "leaf_name_path": "材料 > 石材的性能与应用",
        "compiled_context": {"concepts": ["天然石材勒脚。"]},
        "source_ref": _good_unit()["source_ref"],
    }
    report = build_runtime_pack_semantic_quality_audit(
        runtime_token_pack=_pack([_good_unit(), thin]),
        taxonomy=_taxonomy(),
        check_source_files=False,
    )
    rows = {row["unit_id"]: row for row in report["rows"]}
    assert rows["u_good"]["field_source_ref_coverage"] == 1.0
    assert rows["u_thin"]["thin_context"] is True
    assert report["summary"]["thin_context_count"] == 1


def test_audit_preserves_safety_invariants() -> None:
    report = build_runtime_pack_semantic_quality_audit(
        runtime_token_pack=_pack([_good_unit()]),
        taxonomy=_taxonomy(),
        check_source_files=False,
    )
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["review_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert "production_rag_runtime" in report["not_exercised"]
