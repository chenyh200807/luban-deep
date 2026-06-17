from __future__ import annotations

from scripts.run_luban_rich_leaf_batch_relink_live_spot_check import (
    build_batch_relink_live_spot_check,
)


def _relink_report() -> dict:
    return {
        "schema": "luban_rich_leaf_batch_relink_candidates.v1",
        "relinked": [
            {"unit_id": "u1", "leaf_id": "L1"},
            {"unit_id": "u2", "leaf_id": "L2"},
        ],
    }


def _pack() -> dict:
    unit = {
        "leaf_name_path": "x > 叶子",
        "compiled_context": {"concepts": ["内容"]},
        "source_ref": {"record_id": "r", "source_path": "p", "source_lane": "textbook", "span_hash": "h"},
    }
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "runtime_token_pack_units": [
            {**unit, "unit_id": "u1", "leaf_id": "L1"},
            {**unit, "unit_id": "u2", "leaf_id": "L2"},
        ],
    }


def _fake_provider(answerable: bool = True):
    def call(model: str, messages: list, timeout_s: float = 45.0) -> dict:
        return {
            "content": (
                '{"answerable": %s, "evidence_cited": true, "fail_open": false, "answer": "好"}'
                % ("true" if answerable else "false")
            ),
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "latency_ms": 50.0,
        }

    return call


def test_spot_check_passes_when_all_sampled_units_answerable() -> None:
    report = build_batch_relink_live_spot_check(
        relink_report=_relink_report(),
        runtime_token_pack=_pack(),
        sample_size=2,
        seed=1,
        provider_call=_fake_provider(True),
        model="fake-model",
    )
    assert report["verdict"] == "PASS_BATCH_RELINK_LIVE_SPOT_CHECK"
    assert report["verdict_ceiling"] == "PROJECTED_LIVE_PROVIDER_ONLY"
    assert report["summary"]["provider_call_count"] == 4
    assert report["summary"]["accuracy_rate"] == 1.0
    assert report["summary"]["fail_open_rate"] == 0.0
    assert report["summary"]["total_tokens"] == 480


def test_spot_check_records_unanswerable_as_mismatch() -> None:
    report = build_batch_relink_live_spot_check(
        relink_report=_relink_report(),
        runtime_token_pack=_pack(),
        sample_size=1,
        seed=1,
        provider_call=_fake_provider(False),
        model="fake-model",
    )
    assert report["summary"]["accuracy_rate"] == 0.0
    assert all(r["matches_expected"] is False for r in report["rows"])


def test_spot_check_blocked_without_provider() -> None:
    report = build_batch_relink_live_spot_check(
        relink_report=_relink_report(),
        runtime_token_pack=_pack(),
        sample_size=2,
        seed=1,
        provider_call=None,
        model="fake-model",
    )
    assert report["verdict"] == "BLOCKED_OR_FAILED"
    assert "provider_call_not_configured" in report["blockers"]


def test_spot_check_safety_invariants() -> None:
    report = build_batch_relink_live_spot_check(
        relink_report=_relink_report(),
        runtime_token_pack=_pack(),
        sample_size=2,
        seed=1,
        provider_call=_fake_provider(True),
        model="fake-model",
    )
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert "production_rag_runtime" in report["not_exercised"]
