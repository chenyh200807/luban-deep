from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_canonical_promotion_arm_release_gate_m33 import run_m33


def _j(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_write_go_reads_back_from_single_learner_truth(tmp_path: Path) -> None:
    result = run_m33(out_dir=tmp_path, learner_root=tmp_path / "learner_runtime")

    gate = _j(tmp_path / "go_no_go_m33.json")
    proof = _j(tmp_path / "canonical_truth_readback_m33.json")

    assert result["canonical_write"] == "GO"
    assert gate["canonical_write"] == "GO"
    assert gate["canonical_truth_written"] is True
    assert gate["canonical_truth_authority"] == "LearnerStateService.write_compiled_learning_truth"
    assert proof["canonical_source_ids"] == [
        "m33_teacher_final_canonical",
        "m33_real_retest_canonical",
    ]
    assert proof["teacher_final"]["source"] == "LearnerStateService.MEMORY_EVENTS"
    assert proof["real_retest"]["source"] == "LearnerStateService.MEMORY_EVENTS"
    assert proof["learning_brain_readback"]["source"] == "LearnerStateService.COMPILED_TRUTH"
    assert proof["report_readback"]["learning_brain_source"] == "compiled_learning_truth"
    assert proof["next_action_readback"]["source"] == "PersonalizationContextPack"
    assert proof["same_projection_hash"] is True
    assert proof["shadow_ledger_used"] is False
    assert proof["mirror_state_used"] is False
    assert proof["tmp_json_used_as_canonical"] is False
    assert proof["learning_brain_readback"]["improvement_signal_count"] >= 1
    assert proof["report_readback"]["grading_loop_status"] in {"improving", "complete", "ready"}
    assert proof["next_action_readback"]["action_type"]


def test_production_default_flip_go_is_limited_reversible_and_safe(tmp_path: Path) -> None:
    run_m33(out_dir=tmp_path, learner_root=tmp_path / "learner_runtime")

    gate = _j(tmp_path / "go_no_go_m33.json")
    default = _j(tmp_path / "production_default_flip_gate_m33.json")

    assert gate["production_default_flip_now"] == "GO"
    assert gate["production_v1_overall"] == "GO"
    assert default["default_mode"] == "one_percent_qa_operator_default"
    assert default["allowed_default_cohorts"] == ["qa_", "operator_"]
    assert default["blocked_cohorts"] == ["real_student_", "guest_"]
    assert default["kill_switch"]["env"] == "LUBAN_V1_BETA_SHADOW_ENABLED"
    assert default["kill_switch"]["verified"] is True
    assert default["rollback"]["verified"] is True
    assert default["rollback"]["paths"] == [
        "request_flag_off",
        "env_kill_switch",
        "registry_unavailable_failclosed",
    ]
    assert default["safety"]["false_positive"] == 0
    assert default["safety"]["source_laundering"] == 0
    assert default["safety"]["high_risk_fallback_ok"] is True
    assert default["safety"]["non_cohort_blocked"] is True


def test_formal_registry_go_names_canonical_authority_and_promotion_arm(tmp_path: Path) -> None:
    run_m33(out_dir=tmp_path, learner_root=tmp_path / "learner_runtime")

    gate = _j(tmp_path / "go_no_go_m33.json")
    registry = _j(tmp_path / "formal_registry_candidate_m33.json")

    assert gate["formal_registry"] == "GO"
    assert registry["registry_status"] == "formal_candidate"
    assert registry["formal_registry_emitted"] is True
    assert registry["promotion_arm"] == "v1_canonical_teacher_final_real_retest"
    assert registry["single_authority"]["writer"] == "LearnerStateService.append_memory_event"
    assert registry["single_authority"]["canonical_store"] == "LearnerStateService.COMPILED_TRUTH"
    assert registry["single_authority"]["reader"] == "LearnerStateService.read_compiled_learning_truth"
    assert registry["writes_where"] == ["MEMORY_EVENTS.jsonl", "COMPILED_TRUTH.json"]
    assert registry["reads_where"] == [
        "Learning Brain read model",
        "learning report read model",
        "PersonalizationContextPack next action",
    ]
    assert registry["rollback"]["strategy"] == "disable_default_and_restore_previous_compiled_truth"
    assert registry["allowed_traffic"] == {
        "default": ["qa_", "operator_"],
        "canonical_write": ["qa_", "operator_"],
        "blocked": ["real_student_", "guest_"],
    }
