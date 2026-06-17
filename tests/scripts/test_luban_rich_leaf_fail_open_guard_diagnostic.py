from __future__ import annotations

import json
from pathlib import Path

from tests.scripts.test_luban_rich_leaf_context_pack_smoke import _promotion_review_payload


def _context_pack_smoke_payload(review_candidate_field_count: int = 1) -> dict:
    return {
        "schema": "luban_rich_leaf_context_pack_smoke.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "context_pack_smoke": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "input_promoted_artifact_count": 3,
            "task_pack_count": 5,
            "blocker_count": 0,
            "knowledge_task_question_lane_source_ref_count": 0,
            "review_candidate_field_count": review_candidate_field_count,
        },
        "compiled_context_packs": [
            {
                "task": "review",
                "review_candidate_field_ids": ["neg_1"] if review_candidate_field_count else [],
                "review_candidate_field_count": review_candidate_field_count,
            }
        ],
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_fail_open_guard_diagnostic_surfaces_candidate_negative_evidence() -> None:
    from scripts.run_luban_rich_leaf_fail_open_guard_diagnostic import run_fail_open_guard_diagnostic

    report = run_fail_open_guard_diagnostic(
        field_promotion_review=_promotion_review_payload(),
        context_pack_smoke=_context_pack_smoke_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_fail_open_guard_diagnostic.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["summary"]["negative_evidence_candidate_count"] == 1
    assert report["summary"]["top_leaf_count"] == 1
    assert report["summary"]["review_candidate_field_count"] == 1
    assert report["leaf_diagnostics"][0]["leaf_id"] == "L3"
    assert report["leaf_diagnostics"][0]["negative_evidence_count"] == 1
    assert report["leaf_diagnostics"][0]["source_lanes"] == ["textbook"]
    assert report["leaf_diagnostics"][0]["guard_suggestion"] == "block_positive_context_until_source_ref_reviewed"
    assert report["not_exercised"] == [
        "runtime_fail_open_reduction",
        "production_runtime_enforcement",
        "learner_memory_writeback",
    ]


def test_fail_open_guard_diagnostic_fails_if_review_pack_hides_candidate_evidence() -> None:
    from scripts.run_luban_rich_leaf_fail_open_guard_diagnostic import run_fail_open_guard_diagnostic

    report = run_fail_open_guard_diagnostic(
        field_promotion_review=_promotion_review_payload(),
        context_pack_smoke=_context_pack_smoke_payload(review_candidate_field_count=0),
    )

    assert report["verdict"] == "FAIL"
    assert "negative_evidence_not_visible_in_review_pack" in report["blockers"]


def test_fail_open_guard_diagnostic_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_fail_open_guard_diagnostic import main

    promotion_review = tmp_path / "field_promotion_review.json"
    smoke = tmp_path / "context_pack_smoke.json"
    output = tmp_path / "fail_open_guard_diagnostic.json"
    promotion_review.write_text(json.dumps(_promotion_review_payload(), ensure_ascii=False), encoding="utf-8")
    smoke.write_text(json.dumps(_context_pack_smoke_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--field-promotion-review",
            str(promotion_review),
            "--context-pack-smoke",
            str(smoke),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_fail_open_guard_diagnostic.v1"
    assert payload["summary"]["negative_evidence_candidate_count"] == 1
