from __future__ import annotations


def _pack(units: list[dict], version: str) -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": version,
        "runtime_token_pack_units": units,
    }


def _ab(rows: list[dict]) -> dict:
    return {
        "schema": "luban_rich_leaf_v23_near_live_shadow_ab.v1",
        "verdict": "PASS_V23_NEAR_LIVE_SHADOW_AB",
        "verdict_ceiling": "NEAR_LIVE_PROXY_ONLY",
        "quality_claim_allowed": False,
        "rows": rows,
    }


def test_remap_rewrites_rich_leaf_rows_to_target_axis_and_keeps_other_arms() -> None:
    from scripts.run_luban_rich_leaf_frozen_axis_near_live_ab_remap import (
        build_frozen_axis_near_live_ab_remap,
    )

    source = _pack(
        [{"unit_id": "u1", "leaf_id": "A"}, {"unit_id": "u2", "leaf_id": "B"}],
        "v2.3",
    )
    target = _pack(
        [{"unit_id": "u2", "leaf_id": "Y"}, {"unit_id": "u1", "leaf_id": "X"}],
        "v2.6.2",
    )
    rows = [
        {"arm": "current_rag_proxy", "case_id": "c1", "leaf_id": "A"},
        {"arm": "rich_leaf_v23_context", "case_id": "c1", "leaf_id": "A"},
        {"arm": "rich_leaf_v23_context", "case_id": "c2", "leaf_id": "B"},
    ]

    report = build_frozen_axis_near_live_ab_remap(
        near_live_ab=_ab(rows), source_pack=source, target_pack=target
    )

    assert report["verdict"] == "PASS_V23_NEAR_LIVE_SHADOW_AB"
    rich = [row for row in report["rows"] if row["arm"] == "rich_leaf_v23_context"]
    assert [(row["case_id"], row["leaf_id"]) for row in rich] == [("c2", "Y"), ("c1", "X")]
    assert all(row["remapped_from_leaf_id"] in {"A", "B"} for row in rich)
    other = [row for row in report["rows"] if row["arm"] != "rich_leaf_v23_context"]
    assert other == [{"arm": "current_rag_proxy", "case_id": "c1", "leaf_id": "A"}]
    assert report["remap_lineage"]["outcomes_inherited_from_v23_proxy"] is True
    assert "frozen_axis_near_live_rerun_with_recompiled_context" in report["not_exercised"]


def test_remap_fails_when_unit_id_sets_differ() -> None:
    from scripts.run_luban_rich_leaf_frozen_axis_near_live_ab_remap import (
        build_frozen_axis_near_live_ab_remap,
    )

    source = _pack([{"unit_id": "u1", "leaf_id": "A"}], "v2.3")
    target = _pack([{"unit_id": "uX", "leaf_id": "X"}], "v2.6.2")
    rows = [{"arm": "rich_leaf_v23_context", "case_id": "c1", "leaf_id": "A"}]

    report = build_frozen_axis_near_live_ab_remap(
        near_live_ab=_ab(rows), source_pack=source, target_pack=target
    )

    assert report["verdict"] == "FAIL_FROZEN_AXIS_REMAP"
    assert "unit_id_sets_differ_between_packs" in report["blockers"]
