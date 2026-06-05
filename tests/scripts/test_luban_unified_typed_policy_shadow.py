from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_luban_unified_typed_policy_shadow import build_unified_typed_policy_shadow


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    packet = {
        "slice_id": "slice-heldout",
        "tasks": [
            {
                "case_id": "Q1-NA",
                "student_id": "S1",
                "task_id": "Q1-NA::S1",
                "student_answer": "写出施工总进度计划表(图)。",
                "scoring_points": [
                    {"point_id": "P1", "label": "列出施工总进度计划表(图)", "max_score": 5}
                ],
            }
        ],
    }
    policies = {
        "summary": {"schema_version": "policy.v1", "version_id": "policy-version"},
        "policies": [
            {
                "case_id": "Q1-NA",
                "point_id": "P1",
                "policy_type": "list_rule",
                "base_policy": None,
                "policy_readiness": "ready_for_llm_adjudication",
                "required_terms": ["施工总进度计划表(图)"],
                "list_spec": {"denominator": 1},
                "numeric_spec": None,
                "figure_spec": None,
                "penalty_spec": None,
                "evidence_policy": {"span_required": True},
                "residual_signals": [],
                "safety_notes": ["fixture"],
            }
        ],
    }
    packet_path = tmp_path / "packet.json"
    policy_path = tmp_path / "policy.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    policy_path.write_text(json.dumps(policies, ensure_ascii=False), encoding="utf-8")
    return packet_path, policy_path


def test_unified_typed_policy_shadow_injects_policy_and_prompts(tmp_path: Path) -> None:
    packet_path, policy_path = _write_inputs(tmp_path)

    paths = build_unified_typed_policy_shadow(
        agentic_packet_path=packet_path,
        typed_policy_path=policy_path,
        output_dir=tmp_path / "out",
    )

    packet = json.loads(paths["packet"].read_text(encoding="utf-8"))
    template = json.loads(paths["template"].read_text(encoding="utf-8"))
    point = packet["tasks"][0]["scoring_points"][0]
    assert packet["typed_policy_version_id"] == "policy-version"
    assert point["typed_policy"]["policy_type"] == "list_rule"
    assert point["typed_policy"]["required_terms"] == ["施工总进度计划表(图)"]
    assert {row["arm"] for row in template["prediction_sets"]} == {
        "qwen37_plus_thinking_primary",
        "deepseek_v4_flash_typed_policy_primary",
    }
    assert "不要把 required_terms 当作全局 substring 硬门" in paths["qwen_prompt"].read_text(encoding="utf-8")
    assert paths["finding"].exists()


def test_unified_typed_policy_shadow_cli_builds_packet(tmp_path: Path) -> None:
    packet_path, policy_path = _write_inputs(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_luban_unified_typed_policy_shadow.py",
            "--agentic-packet",
            str(packet_path),
            "--typed-policy",
            str(policy_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "out" / "unified_typed_policy_packet.json").exists()
    assert (tmp_path / "out" / "qwen37_plus_thinking_primary_prompt.md").exists()
