from __future__ import annotations

import json


def test_terminal_leaf_completion_drops_minted_leaf_ids() -> None:
    from scripts.run_luban_rich_leaf_terminal_leaf_completion_runner import run_terminal_leaf_completion

    work_orders = {
        "schema": "luban_rich_leaf_terminal_leaf_completion_work_orders.v1",
        "verdict": "READY_FOR_TERMINAL_LEAF_COMPLETION_SHADOW",
        "classification": {"runtime_install_allowed": False},
        "safety": {"production_write_count": 0},
        "work_orders": [
            {
                "work_order_id": "wo_1",
                "reason": "needs_terminal_leaf_split",
                "unit": {
                    "unit_id": "unit_1",
                    "relative_path": "教材/防水卷材.json",
                    "source_lane": "source_truth",
                    "compiled_context": {"concepts": ["防水卷材"]},
                    "source_ref": {"span_hash": "hash_1", "source_path": "教材.json"},
                },
                "taxonomy_link": {
                    "candidate_leaf_links": [
                        {"leaf_id": "1A412012-01-a", "name_path": "防水材料 > 防水卷材", "score": 5}
                    ]
                },
            }
        ],
    }
    taxonomy_index = {
        "manifest": {"schema_version": "luban_canonical_taxonomy_index.v1"},
        "leaves": [{"code": "1A412012-01-a", "name_path": "防水材料 > 防水卷材", "keywords": ["防水卷材"]}],
    }

    def fake_provider(model: str, messages: list[dict[str, str]], timeout_s: float) -> dict:
        return {
            "model": model,
            "content": json.dumps(
                {
                    "terminal_leaf_units": [
                        {
                            "leaf_id": "MINTED",
                            "confidence": "high",
                            "support_rationale": "bad",
                            "selected_context_fields": {"concepts": ["防水卷材"]},
                        }
                    ],
                    "unresolved_reason": None,
                }
            ),
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "latency_ms": 1.0,
        }

    report = run_terminal_leaf_completion(
        work_orders=work_orders,
        taxonomy_index=taxonomy_index,
        provider_call=fake_provider,
        model="fake",
        start_index=0,
        max_work_orders=None,
        max_workers=1,
        progress_every=0,
        timeout_s=1,
        top_k=3,
    )

    assert report["verdict"] == "PASS_TERMINAL_LEAF_COMPLETION_SHADOW"
    assert report["summary"]["terminal_leaf_unit_count"] == 0
    assert report["summary"]["unresolved_work_order_count"] == 1
    assert report["safety"]["production_write_count"] == 0
