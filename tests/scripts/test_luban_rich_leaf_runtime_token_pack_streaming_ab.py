from __future__ import annotations

import json
from pathlib import Path


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v1",
        "version": "v_test_pack",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_token_pack": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {"token_pack_unit_count": 1},
        "runtime_token_pack_units": [
            {
                "unit_id": "unit_1",
                "leaf_id": "leaf_1",
                "artifact_id": "artifact_1",
                "missing_lane": "textbook",
                "source_ref": {
                    "source_lane": "textbook",
                    "source_path": "教材.json",
                    "record_id": "rec_1",
                    "span_hash": "hash_1",
                    "excerpt": "防水卷材应符合设计和规范要求。",
                    "excerpt_char_count": 16,
                    "full_span_omitted": True,
                    "support_candidate": True,
                },
                "provenance": {"audit_item_id": "audit_1"},
                "authority_pointer": {
                    "source_span_hash": "hash_1",
                    "runtime_supply_unit_id": "unit_1",
                    "full_artifact_required_for_release": True,
                },
                "candidate_only": True,
                "review_only": True,
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


def _runtime_supply() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_supply_candidate_bundle.v1",
        "version": "v_test_supply",
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
                    "span": "防水卷材应符合设计和规范要求。" * 80,
                    "span_hash": "hash_1",
                    "support_candidate": True,
                },
                "provenance": {"audit_item_id": "audit_1"},
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


def _runtime_token_pack_v2() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2",
        "version": "v_test_pack_v2",
        "status": "candidate_ready_for_shadow_ab",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_token_pack_v2": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {"token_pack_unit_count": 1},
        "runtime_token_pack_units": [
            {
                "unit_id": "rtp2_unit_1",
                "candidate_id": "candidate_1",
                "source_lane": "source_truth",
                "relative_path": "教材.json",
                "compiled_context": {
                    "concepts": ["防水卷材"],
                    "definitions": ["柔性防水材料"],
                    "rules": ["卷材性能应符合设计和规范要求"],
                    "procedures": [],
                    "numeric_constraints": [],
                    "common_mistakes": [],
                    "exam_patterns": ["材料特性判断"],
                    "teaching_cards": ["防水材料分类"],
                    "grading_relevance": ["只按原文证据判定"],
                },
                "source_ref": {
                    "source_lane": "textbook",
                    "source_path": "教材.json",
                    "record_id": "rec_1",
                    "span_hash": "hash_1",
                    "excerpt": "防水卷材应符合设计和规范要求。",
                },
                "candidate_only": True,
                "review_only": True,
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


def _runtime_token_pack_v21() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.1",
        "version": "v_test_pack_v21",
        "status": "candidate_ready_for_leaf_scoped_shadow_ab",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_token_pack_v21": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {"token_pack_unit_count": 1},
        "runtime_token_pack_units": [
            {
                "unit_id": "rtp21_unit_1",
                "parent_unit_id": "rtp2_unit_1",
                "leaf_id": "1A412012-01-a",
                "leaf_name_path": "建筑材料 > 防水材料 > 防水卷材",
                "source_lane": "source_truth",
                "compiled_context": {
                    "concepts": ["防水卷材"],
                    "rules": ["SBS 卷材适用于较低气温环境的建筑防水"],
                },
                "source_ref": {
                    "source_lane": "textbook",
                    "source_path": "教材.json",
                    "record_id": "rec_1",
                    "span_hash": "hash_1",
                },
                "candidate_only": True,
                "review_only": True,
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


def test_runtime_token_pack_streaming_ab_records_ttft_and_context_size() -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_streaming_ab import (
        build_runtime_token_pack_streaming_ab,
    )

    def fake_stream_call(model: str, messages: list[dict[str, str]], timeout_s: float) -> dict:
        context_chars = len(messages[-1]["content"])
        return {
            "model": model,
            "content": "ok",
            "first_byte_ms": 10.0,
            "ttft_ms": 15.0,
            "full_latency_ms": 20.0 + context_chars / 1000,
            "prompt_char_count": context_chars,
            "completion_char_count": 2,
        }

    report = build_runtime_token_pack_streaming_ab(
        runtime_token_pack=_runtime_token_pack(),
        runtime_supply_candidate=_runtime_supply(),
        sample_limit=1,
        provider_call=fake_stream_call,
        model="fake-model",
    )

    assert report["schema"] == "luban_rich_leaf_runtime_token_pack_streaming_ab.v1"
    assert report["runtime_exercised"] is True
    assert report["summary"]["provider_call_count"] == 2
    assert report["summary"]["blocker_count"] == 0
    arms = {arm["arm"]: arm for arm in report["arms"]}
    assert arms["runtime_token_pack_thin"]["sample_count"] == 1
    assert arms["runtime_supply_full_span"]["sample_count"] == 1
    assert arms["runtime_token_pack_thin"]["mean_context_char_count"] < arms["runtime_supply_full_span"]["mean_context_char_count"]
    assert arms["runtime_token_pack_thin"]["mean_ttft_ms"] == 15.0
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_runtime_token_pack_streaming_ab_supports_v21_leaf_scoped_pack() -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_streaming_ab import (
        build_runtime_token_pack_streaming_ab,
    )

    def fake_stream_call(model: str, messages: list[dict[str, str]], timeout_s: float) -> dict:
        context_chars = len(messages[-1]["content"])
        return {
            "model": model,
            "content": "ok",
            "first_byte_ms": 8.0,
            "ttft_ms": 10.0,
            "full_latency_ms": 18.0,
            "prompt_char_count": context_chars,
            "completion_char_count": 2,
        }

    report = build_runtime_token_pack_streaming_ab(
        runtime_token_pack=_runtime_token_pack_v21(),
        runtime_supply_candidate={"schema": "unused_for_v21"},
        sample_limit=1,
        provider_call=fake_stream_call,
        model="fake-model",
    )

    assert report["runtime_exercised"] is True
    assert report["input_schema"] == "luban_rich_leaf_runtime_token_pack.v2.1"
    assert {arm["arm"] for arm in report["arms"]} == {"leaf_scoped_context_v21", "source_pointer_only_v21"}
    assert report["classification"]["runtime_token_pack_v21"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_runtime_token_pack_streaming_ab_supports_v2_without_supply_join() -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_streaming_ab import (
        build_runtime_token_pack_streaming_ab,
    )

    def fake_stream_call(model: str, messages: list[dict[str, str]], timeout_s: float) -> dict:
        context_chars = len(messages[-1]["content"])
        return {
            "model": model,
            "content": "ok",
            "first_byte_ms": 10.0,
            "ttft_ms": 12.0,
            "full_latency_ms": 20.0,
            "prompt_char_count": context_chars,
            "completion_char_count": 2,
        }

    report = build_runtime_token_pack_streaming_ab(
        runtime_token_pack=_runtime_token_pack_v2(),
        runtime_supply_candidate={"schema": "unused_for_v2"},
        sample_limit=1,
        provider_call=fake_stream_call,
        model="fake-model",
    )

    assert report["runtime_exercised"] is True
    assert report["input_schema"] == "luban_rich_leaf_runtime_token_pack.v2"
    assert report["summary"]["provider_call_count"] == 2
    assert report["summary"]["blocker_count"] == 0
    assert {arm["arm"] for arm in report["arms"]} == {"rich_leaf_promoted_context_v2", "source_excerpt_only_v2"}
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_runtime_token_pack_streaming_ab_blocks_without_provider() -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_streaming_ab import (
        build_runtime_token_pack_streaming_ab,
    )

    report = build_runtime_token_pack_streaming_ab(
        runtime_token_pack=_runtime_token_pack(),
        runtime_supply_candidate=_runtime_supply(),
        sample_limit=1,
        provider_call=None,
        model="fake-model",
    )

    assert report["runtime_exercised"] is False
    assert "provider_call_not_configured" in report["blockers"]


def test_runtime_token_pack_streaming_ab_cli_no_provider_writes_blocked_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_runtime_token_pack_streaming_ab import main

    token_pack = tmp_path / "runtime_token_pack.json"
    runtime_supply = tmp_path / "runtime_supply.json"
    output = tmp_path / "streaming_ab.json"
    token_pack.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")
    runtime_supply.write_text(json.dumps(_runtime_supply(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--runtime-token-pack",
            str(token_pack),
            "--runtime-supply-candidate",
            str(runtime_supply),
            "--output",
            str(output),
            "--sample-limit",
            "1",
            "--no-provider-call",
        ]
    )

    assert exit_code == 1
    payload = json.loads(output.read_text("utf-8"))
    assert "provider_call_not_configured" in payload["blockers"]
