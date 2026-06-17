from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_luban_deepseek_typed_policy_shadow import build_deepseek_shadow_packet


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    agentic_packet = {
        "slice_id": "slice-x",
        "status": "awaiting_model_predictions",
        "grading_guideline": "踩字给分。",
        "tasks": [
            {
                "case_id": "Q1",
                "student_id": "S1",
                "task_id": "Q1::S1",
                "student_answer": "学生写出见证人员。",
                "scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出见证人员",
                        "max_score": 2,
                    }
                ],
            }
        ],
    }
    typed_policy = {
        "summary": {"version_id": "typed-policy-fixture"},
        "policies": [
            {
                "case_id": "Q1",
                "point_id": "P1",
                "policy_type": "exact_required",
                "policy_readiness": "ready_for_llm_adjudication",
                "required_terms": ["见证人员"],
                "list_spec": None,
                "numeric_spec": None,
                "penalty_spec": None,
                "figure_spec": None,
                "safety_notes": ["not_runtime_guardrail"],
            }
        ],
    }
    packet_path = tmp_path / "agentic_packet.json"
    policy_path = tmp_path / "typed_policy.json"
    packet_path.write_text(json.dumps(agentic_packet, ensure_ascii=False), encoding="utf-8")
    policy_path.write_text(json.dumps(typed_policy, ensure_ascii=False), encoding="utf-8")
    return packet_path, policy_path


def test_build_deepseek_shadow_packet_injects_policy_without_human_labels(tmp_path: Path) -> None:
    packet_path, policy_path = _write_inputs(tmp_path)

    paths = build_deepseek_shadow_packet(
        agentic_packet_path=packet_path,
        typed_policy_path=policy_path,
        output_dir=tmp_path / "out",
    )

    packet = json.loads(paths["packet"].read_text(encoding="utf-8"))
    serialized = json.dumps(packet, ensure_ascii=False)
    point = packet["tasks"][0]["scoring_points"][0]
    assert packet["typed_policy_version_id"] == "typed-policy-fixture"
    assert point["typed_policy"]["policy_type"] == "exact_required"
    assert point["typed_policy"]["required_terms"] == ["见证人员"]
    assert "human_hit" not in serialized
    assert "human_score" not in serialized
    assert "ledger" not in serialized


def test_deepseek_template_has_three_roles_and_no_fake_predictions(tmp_path: Path) -> None:
    packet_path, policy_path = _write_inputs(tmp_path)

    paths = build_deepseek_shadow_packet(
        agentic_packet_path=packet_path,
        typed_policy_path=policy_path,
        output_dir=tmp_path / "out",
    )

    template = json.loads(paths["template"].read_text(encoding="utf-8"))
    arms = {row["arm"]: row["predictions"] for row in template["prediction_sets"]}
    assert set(arms) == {
        "deepseek_v4_flash_primary",
        "deepseek_v4_flash_strict_reviewer",
        "deepseek_v4_flash_dual_adjudicated",
    }
    assert all(predictions == [] for predictions in arms.values())


def test_prompt_warns_against_global_required_term_hard_gate(tmp_path: Path) -> None:
    packet_path, policy_path = _write_inputs(tmp_path)

    paths = build_deepseek_shadow_packet(
        agentic_packet_path=packet_path,
        typed_policy_path=policy_path,
        output_dir=tmp_path / "out",
    )

    prompt = paths["dual_prompt"].read_text(encoding="utf-8")
    assert "不要把 required_terms 当作全局 substring 硬门" in prompt
    assert "policy_type" in prompt
    assert "unsupported" in prompt


def test_deepseek_shadow_cli_builds_packet(tmp_path: Path) -> None:
    packet_path, policy_path = _write_inputs(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_luban_deepseek_typed_policy_shadow.py",
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
    assert (tmp_path / "out" / "deepseek_typed_policy_packet.json").exists()
    assert (tmp_path / "out" / "FINDING_deepseek_typed_policy_shadow_20260603.md").exists()
