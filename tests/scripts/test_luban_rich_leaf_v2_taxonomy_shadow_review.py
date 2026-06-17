from __future__ import annotations

import json


def test_taxonomy_shadow_review_rejects_minted_leaf_ids() -> None:
    from scripts.run_luban_rich_leaf_v2_taxonomy_shadow_review import run_taxonomy_shadow_review

    runtime_token_pack = {
        "schema": "luban_rich_leaf_runtime_token_pack.v2",
        "classification": {"runtime_install_allowed": False, "production_default": False},
        "safety": {"production_write_count": 0, "release_truth_claimed": False},
        "runtime_token_pack_units": [
            {
                "unit_id": "unit_1",
                "candidate_id": "candidate_1",
                "relative_path": "教材/防水卷材.json",
                "source_lane": "source_truth",
                "compiled_context": {"concepts": ["防水卷材"]},
                "source_ref": {"excerpt": "SBS 卷材适用于较低气温环境的建筑防水。"},
            }
        ],
    }
    taxonomy_linking = {
        "schema": "luban_rich_leaf_v2_taxonomy_leaf_linking.v1",
        "verdict": "PASS_TAXONOMY_LEAF_LINKING_SHADOW_CANDIDATES",
        "classification": {"runtime_install_allowed": False, "production_default": False},
        "safety": {"production_write_count": 0, "release_truth_claimed": False},
        "taxonomy_leaf_links": [
            {
                "link_id": "link_1",
                "unit_id": "unit_1",
                "status": "weak_link_candidate",
                "candidate_leaf_links": [
                    {"leaf_id": "1A412012-01-a", "name_path": "防水材料 > 防水卷材", "score": 5}
                ],
            }
        ],
    }

    def fake_provider(model: str, messages: list[dict[str, str]], timeout_s: float) -> dict:
        return {
            "model": model,
            "content": json.dumps(
                {
                    "decision": "accept_shadow_leaf_link",
                    "accepted_leaf_id": "MINTED-LEAF",
                    "confidence": "high",
                    "rationale": "bad",
                    "risk_codes": ["none"],
                }
            ),
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "latency_ms": 1.0,
        }

    report = run_taxonomy_shadow_review(
        runtime_token_pack=runtime_token_pack,
        taxonomy_linking=taxonomy_linking,
        provider_call=fake_provider,
        model="fake",
        start_index=0,
        max_links=None,
        max_workers=1,
        progress_every=0,
        timeout_s=1,
    )

    assert report["verdict"] == "PASS_TAXONOMY_SHADOW_REVIEW"
    assert report["decisions"][0]["decision"] == "needs_terminal_leaf_split"
    assert report["decisions"][0]["accepted_leaf_id"] is None
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
