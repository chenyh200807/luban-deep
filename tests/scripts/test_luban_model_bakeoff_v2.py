from __future__ import annotations

import json
from pathlib import Path

from scripts.summarize_luban_model_bakeoff_v2 import summarize_bakeoff


def _write_metrics(path: Path, *, arm: str, agreement: float, delta: float, unsupported: int) -> None:
    payload = {
        "slice_id": "slice-1",
        "human_vs_artifact_first": {
            "target": "artifact_first",
            "sample_count": 24,
            "point_count": 131,
            "point_hit_agreement": 0.5267,
            "mean_abs_score_delta": 4.6091,
            "disagreements": [{}] * 71,
        },
        "human_vs_ledger": {
            "target": "human_vs_ledger",
            "sample_count": 24,
            "point_count": 131,
            "point_hit_agreement": 0.9618,
            "mean_abs_score_delta": 0.4292,
            "disagreements": [{}] * 15,
        },
        "agentic_arms": {
            arm: {
                "target": arm,
                "sample_count": 24,
                "point_count": 131,
                "point_hit_agreement": agreement,
                "mean_abs_score_delta": delta,
                "unsupported_judgment_count": unsupported,
                "unsupported_judgment_rate": round(unsupported / 131, 4),
                "disagreements": [{}] * 11,
            }
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_model_bakeoff_v2_extracts_arms_and_marks_gate(tmp_path: Path) -> None:
    qwen_metrics = tmp_path / "qwen" / "metrics.json"
    ds_metrics = tmp_path / "deepseek" / "metrics.json"
    _write_metrics(qwen_metrics, arm="qwen_primary", agreement=0.9389, delta=0.4131, unsupported=0)
    _write_metrics(ds_metrics, arm="deepseek_dual", agreement=0.9466, delta=0.4999, unsupported=0)

    result = summarize_bakeoff(
        output_dir=tmp_path / "out",
        arm_specs=[
            {
                "id": "qwen37_primary",
                "label": "Qwen3.7 primary",
                "metrics_path": str(qwen_metrics),
                "metrics_key": "agentic_arms.qwen_primary",
                "protocol": "agentic_packet",
            },
            {
                "id": "deepseek_typed_span_guard",
                "label": "DeepSeek typed span guarded",
                "metrics_path": str(ds_metrics),
                "metrics_key": "agentic_arms.deepseek_dual",
                "protocol": "typed_policy_span_guard",
            },
        ],
    )

    arms = {row["id"]: row for row in result["arms"]}
    assert arms["qwen37_primary"]["gate"] == "pass"
    assert arms["deepseek_typed_span_guard"]["gate"] == "pass"
    assert result["slice_consistency"]["slice_id"] == "slice-1"
    assert result["protocol_consistency"]["same_protocol"] is False
    assert result["best_candidate"]["id"] == "qwen37_primary"
    assert (tmp_path / "out" / "model_bakeoff_v2_summary.json").exists()
    assert (tmp_path / "out" / "FINDING_model_bakeoff_v2.md").exists()


def test_model_bakeoff_v2_fails_unsupported_even_when_accuracy_is_high(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics, arm="model_primary", agreement=0.99, delta=0.1, unsupported=1)

    result = summarize_bakeoff(
        output_dir=tmp_path / "out",
        arm_specs=[
            {
                "id": "model_primary",
                "label": "Model primary",
                "metrics_path": str(metrics),
                "metrics_key": "agentic_arms.model_primary",
                "protocol": "agentic_packet",
            }
        ],
    )

    arm = result["arms"][0]
    assert arm["gate"] == "fail"
    assert "unsupported_judgment_count=1" in arm["gate_reasons"]


def test_default_bakeoff_uses_non_empty_gpt_opus_reference(tmp_path: Path) -> None:
    result = summarize_bakeoff(output_dir=tmp_path / "out")

    arms = {row["id"]: row for row in result["arms"]}
    gpt_opus = arms["gpt55_opus48_dual"]
    assert gpt_opus["sample_count"] == 24
    assert gpt_opus["point_count"] == 131
    assert gpt_opus["point_hit_agreement"] == 0.9389
