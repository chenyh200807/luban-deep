from __future__ import annotations

import json
from pathlib import Path

PACK_CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "runtime_install_allowed": False,
    "production_default": False,
    "release_truth_claimed": False,
}
PACK_SAFETY = {
    "canonical_truth_written": False,
    "official_score_allowed": False,
    "installed_runtime_supply": False,
    "production_write_count": 0,
    "release_truth_claimed": False,
}


def _unit(index: int) -> dict:
    return {
        "unit_id": f"rtpf1_{index:016x}",
        "leaf_id": f"L{index}",
        "leaf_name_path": f"root > 叶{index}",
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
        "compiled_context": {"concepts": [f"概念 {index}。"], "rules": [f"规则 {index}"]},
        "source_ref": {
            "source_lane": "textbook",
            "source_path": "2026教材/a.json",
            "record_id": f"2026教材/a.json#chunk:C{index}",
            "chunk_id": f"C{index}",
            "page_num": index,
            "file_sha256": "sha",
            "span_hash": f"span-{index}",
        },
    }


def _runtime_token_pack(unit_count: int = 3) -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "version": "v3.0_frozen_v1_full_compile",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "runtime_token_pack_units": [_unit(i) for i in range(1, unit_count + 1)],
        "classification": dict(PACK_CLASSIFICATION),
        "safety": dict(PACK_SAFETY),
    }


def _fake_provider(model: str, messages: list[dict], *, timeout_s: float) -> dict:
    del timeout_s
    payload = json.loads(messages[-1]["content"])
    context = payload["context"]
    answerable = bool(
        context.get("retrieved_evidence") or context.get("keywords") or context.get("compiled_context")
    )
    return {
        "model": model,
        "content": json.dumps(
            {"answerable": answerable, "evidence_cited": answerable, "fail_open": False, "answer": "ok"},
            ensure_ascii=False,
        ),
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "latency_ms": 10,
    }


def test_frozen_v1_live_ab_runs_four_arms_with_expected_answerable_true() -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_ab import build_frozen_v1_live_ab

    report = build_frozen_v1_live_ab(
        runtime_token_pack=_runtime_token_pack(unit_count=3),
        sample_size=2,
        seed=7,
        provider_call=_fake_provider,
        model="deepseek-chat",
        max_workers=2,
    )

    assert report["schema"] == "luban_rich_leaf_frozen_v1_live_ab.v1"
    assert report["verdict"] == "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB"
    assert report["verdict_ceiling"] == "PROJECTED_LIVE_PROVIDER_ONLY"
    assert report["runtime_exercised"] is True
    assert report["provider_call_count"] == 8
    assert report["total_tokens"] == 960
    assert report["quality_claim_allowed"] is False
    assert all(row["expected_answerable"] is True for row in report["rows"])
    by_arm = {arm["arm"]: arm for arm in report["arms"]}
    assert set(by_arm) == {
        "current_rag_projection_live",
        "legacy_keyword_projection_live",
        "rich_leaf_context_live",
        "artifact_first_guard_live",
    }
    assert by_arm["rich_leaf_context_live"]["accuracy_rate"] == 1.0
    assert by_arm["artifact_first_guard_live"]["fail_open_rate"] == 0.0
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert "production_rag_runtime" in report["not_exercised"]


def test_frozen_v1_live_ab_sampling_is_seed_deterministic() -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_ab import _sample_units

    pack = _runtime_token_pack(unit_count=10)
    first = [u["unit_id"] for u in _sample_units(pack, sample_size=4, seed=20260613)]
    second = [u["unit_id"] for u in _sample_units(pack, sample_size=4, seed=20260613)]
    assert first == second
    assert len(first) == 4


def test_frozen_v1_live_ab_fails_closed_without_provider() -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_ab import build_frozen_v1_live_ab

    report = build_frozen_v1_live_ab(
        runtime_token_pack=_runtime_token_pack(),
        sample_size=2,
        seed=7,
        provider_call=None,
        model="deepseek-chat",
    )

    assert report["runtime_exercised"] is False
    assert report["provider_call_count"] == 0
    assert "provider_call_not_configured" in report["blockers"]
    assert report["safety"]["release_truth_claimed"] is False


def test_frozen_v1_live_ab_blocks_on_wrong_pack_version() -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_ab import build_frozen_v1_live_ab

    pack = _runtime_token_pack()
    pack["version"] = "v2.6.2"
    report = build_frozen_v1_live_ab(
        runtime_token_pack=pack,
        sample_size=1,
        seed=7,
        provider_call=_fake_provider,
        model="deepseek-chat",
    )

    assert report["verdict"] == "BLOCKED_OR_FAILED"
    assert any(b.startswith("runtime_token_pack_version_mismatch") for b in report["blockers"])


def test_frozen_v1_live_ab_cli_writes_blocked_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_ab import main

    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = main(
        [
            "--runtime-token-pack",
            str(pack_path),
            "--output",
            str(output),
            "--sample-size",
            "1",
            "--no-provider-call",
        ]
    )

    assert exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_frozen_v1_live_ab.v1"
    assert payload["verdict"] == "BLOCKED_OR_FAILED"
