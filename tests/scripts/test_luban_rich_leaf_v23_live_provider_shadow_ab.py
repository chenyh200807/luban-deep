from __future__ import annotations

import json
from pathlib import Path


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "runtime_token_pack_units": [
            {
                "unit_id": "rtp23_1",
                "leaf_id": "L1",
                "leaf_name_path": "root > L1",
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "compiled_context": {
                    "concepts": ["概念 A"],
                    "definitions": ["定义 A"],
                    "rules": ["规则 A"],
                },
                "source_ref": {
                    "source_lane": "textbook",
                    "source_path": "2026教材/a.json",
                    "record_id": "2026教材/a.json",
                    "span_hash": "span-a",
                },
            },
            {
                "unit_id": "rtp23_2",
                "leaf_id": "L2",
                "leaf_name_path": "root > L2",
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "compiled_context": {
                    "concepts": ["概念 B"],
                    "definitions": ["定义 B"],
                    "rules": ["规则 B"],
                },
                "source_ref": {
                    "source_lane": "lecture",
                    "source_path": "讲义/b.json",
                    "record_id": "讲义/b.json",
                    "span_hash": "span-b",
                },
            },
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _near_live_ab() -> dict:
    rows = []
    for index, leaf_id in enumerate(("L1", "L2"), 1):
        case_id = f"case_{index}"
        current_answerable = index == 2
        for arm, answerable in (
            ("current_rag_proxy", current_answerable),
            ("legacy_keyword_projection", True),
            ("rich_leaf_v23_context", True),
            ("artifact_first_guard_proxy", True),
        ):
            rows.append(
                {
                    "arm": arm,
                    "case_id": case_id,
                    "leaf_id": leaf_id,
                    "answerable": answerable,
                    "matches_expected": answerable,
                    "evidence_cited": answerable,
                    "fail_open": False,
                }
            )
    return {
        "schema": "luban_rich_leaf_v23_near_live_shadow_ab.v1",
        "verdict": "PASS_V23_NEAR_LIVE_SHADOW_AB",
        "quality_claim_allowed": False,
        "summary": {"case_count": 2, "provider_call_count": 0, "live_runtime_executed": False},
        "rows": rows,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _fake_provider(model: str, messages: list[dict], *, timeout_s: float) -> dict:
    del timeout_s
    payload = json.loads(messages[-1]["content"])
    context = payload["context"]
    answerable = bool(
        context.get("retrieved_evidence")
        or context.get("keywords")
        or context.get("compiled_context")
    )
    content = json.dumps(
        {
            "answerable": answerable,
            "evidence_cited": answerable,
            "fail_open": False,
            "answer": "ok" if answerable else "",
        },
        ensure_ascii=False,
    )
    return {
        "model": model,
        "content": content,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "latency_ms": 10,
    }


def test_v23_live_provider_shadow_ab_builds_projected_four_arm_trace() -> None:
    from scripts.run_luban_rich_leaf_v23_live_provider_shadow_ab import build_v23_live_provider_shadow_ab

    report = build_v23_live_provider_shadow_ab(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        sample_limit=2,
        provider_call=_fake_provider,
        model="deepseek-chat",
    )

    assert report["schema"] == "luban_rich_leaf_v23_live_provider_shadow_ab.v1"
    assert report["verdict"] == "PASS_V23_PROJECTED_LIVE_PROVIDER_SHADOW_AB"
    assert report["verdict_ceiling"] == "PROJECTED_LIVE_PROVIDER_ONLY"
    assert report["runtime_exercised"] is True
    assert report["provider_call_count"] == 8
    assert report["total_tokens"] == 960
    assert report["quality_claim_allowed"] is False
    by_arm = {arm["arm"]: arm for arm in report["arms"]}
    assert set(by_arm) == {
        "current_rag_projection_live",
        "legacy_keyword_projection_live",
        "rich_leaf_v23_context_live",
        "artifact_first_guard_live",
    }
    assert by_arm["rich_leaf_v23_context_live"]["accuracy_rate"] == 1.0
    assert by_arm["artifact_first_guard_live"]["fail_open_rate"] == 0.0
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert "production_rag_runtime" in report["not_exercised"]


def test_v23_live_provider_shadow_ab_fails_closed_without_provider() -> None:
    from scripts.run_luban_rich_leaf_v23_live_provider_shadow_ab import build_v23_live_provider_shadow_ab

    report = build_v23_live_provider_shadow_ab(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        sample_limit=1,
        provider_call=None,
        model="deepseek-chat",
    )

    assert report["runtime_exercised"] is False
    assert report["provider_call_count"] == 0
    assert "provider_call_not_configured" in report["blockers"]
    assert report["safety"]["release_truth_claimed"] is False


def test_v23_live_provider_shadow_ab_cli_writes_blocked_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_v23_live_provider_shadow_ab import main

    runtime = tmp_path / "runtime.json"
    near_live = tmp_path / "near_live.json"
    output = tmp_path / "report.json"
    runtime.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")
    near_live.write_text(json.dumps(_near_live_ab(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--runtime-token-pack",
            str(runtime),
            "--near-live-ab",
            str(near_live),
            "--output",
            str(output),
            "--sample-limit",
            "1",
            "--no-provider-call",
        ]
    )

    assert exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_v23_live_provider_shadow_ab.v1"
    assert payload["verdict"] == "BLOCKED_OR_FAILED"
    assert payload["summary"]["sample_count"] == 1
