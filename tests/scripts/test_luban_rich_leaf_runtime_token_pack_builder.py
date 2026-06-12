from __future__ import annotations

import json
from pathlib import Path


def _runtime_supply_payload() -> dict:
    long_span = "前置说明。" + "防水卷材应符合设计和规范要求，施工前应检查基层质量。" * 30
    return {
        "schema": "luban_rich_leaf_runtime_supply_candidate_bundle.v1",
        "version": "v_test",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_supply_candidate": True,
            "regression_required": True,
            "install_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
        },
        "summary": {"supply_unit_count": 1},
        "supply_units": [
            {
                "unit_id": "unit_1",
                "leaf_id": "leaf_1",
                "artifact_id": "artifact_1",
                "missing_lane": "textbook",
                "source_ref": {
                    "source_lane": "textbook",
                    "source_path": "教材.json",
                    "record_id": "rec_1",
                    "span": long_span,
                    "span_hash": "hash_1",
                    "support_candidate": True,
                },
                "provenance": {
                    "candidate_id": "candidate_1",
                    "audit_item_id": "audit_1",
                    "review_decision": "accept_source_ref_candidate",
                    "reviewer_role": "codex_semantic_shadow_reviewer",
                },
                "candidate_only": True,
                "review_only": True,
                "install_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
            }
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_runtime_token_pack_builder_derives_thin_pack_without_runtime_install() -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_builder import build_runtime_token_pack

    report = build_runtime_token_pack(runtime_supply_candidate=_runtime_supply_payload(), max_excerpt_chars=120)

    assert report["schema"] == "luban_rich_leaf_runtime_token_pack.v1"
    assert report["classification"]["runtime_token_pack"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["production_default"] is False
    assert report["summary"]["input_supply_unit_count"] == 1
    assert report["summary"]["token_pack_unit_count"] == 1
    assert report["summary"]["blocker_count"] == 0
    unit = report["runtime_token_pack_units"][0]
    assert unit["source_ref"]["span_hash"] == "hash_1"
    assert unit["source_ref"]["full_span_omitted"] is True
    assert len(unit["source_ref"]["excerpt"]) <= 120
    assert "span" not in unit["source_ref"]
    assert unit["authority_pointer"]["full_artifact_required_for_release"] is True
    assert unit["runtime_install_allowed"] is False
    assert unit["production_default"] is False


def test_runtime_token_pack_builder_fails_on_runtime_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_builder import build_runtime_token_pack

    payload = _runtime_supply_payload()
    payload["classification"]["runtime_install_allowed"] = True

    report = build_runtime_token_pack(runtime_supply_candidate=payload, max_excerpt_chars=120)

    assert report["summary"]["token_pack_unit_count"] == 0
    assert report["summary"]["blocker_count"] == 1
    assert "input_runtime_install_allowed" in report["blockers"]


def test_runtime_token_pack_builder_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_builder import main

    runtime_supply = tmp_path / "runtime_supply.json"
    output = tmp_path / "runtime_token_pack.json"
    runtime_supply.write_text(json.dumps(_runtime_supply_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--runtime-supply-candidate",
            str(runtime_supply),
            "--max-excerpt-chars",
            "120",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["token_pack_unit_count"] == 1
    assert payload["safety"]["production_write_count"] == 0
