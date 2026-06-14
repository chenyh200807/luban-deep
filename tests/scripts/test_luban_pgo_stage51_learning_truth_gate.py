"""Stage 5.1 PGO mnemonic quality + stable learner-truth gate tests."""

from __future__ import annotations

from pathlib import Path


def _turn(
    *,
    sample_id: str,
    awarded: float,
    maximum: float = 5.0,
    include_mnemonic_action: bool = True,
) -> dict:
    secondary = [
        {"slug": "show_mnemonic", "label": "看记忆口诀", "role": "secondary"},
        {"slug": "practice_more_3", "label": "再练3题", "role": "secondary"},
    ] if include_mnemonic_action else [
        {"slug": "practice_more_3", "label": "再练3题", "role": "secondary"},
    ]
    return {
        "sample_id": sample_id,
        "result_event": {
            "type": "result",
            "metadata": {
                "response": (
                    "【得分】2 / 5 分\n【逐采分点点评】\n"
                    "- ❌ 漏写本采分点：施工准备工作计划。\n"
                    "【薄弱点】施工部署计划容易漏项。\n"
                    "【说明】非正式成绩，仅作学习诊断。"
                ),
                "progressive_disclosure": {
                    "primary_next_action": {
                        "slug": "explain_thoroughly",
                        "label": "讲透这个点",
                        "role": "primary",
                    },
                    "secondary_actions": secondary,
                },
                "luban_case_rubric_v1": {
                    "grading_event": {
                        "event_type": "case_grading_completed",
                        "question_id": "2015::EXAM_XW2015_CASE_1::E0",
                        "rubric_bank_slot": "pgo",
                        "grading_source": "rubric_scored_pgo",
                        "score_authority": "official_total_x_verdict_coverage",
                        "awarded_score": awarded,
                        "max_score": maximum,
                        "official_score_allowed": False,
                        "high_risk_review": False,
                    },
                },
            },
        },
    }


def test_stage51_gate_passes_with_mnemonic_content_and_stable_readback(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage51_learning_truth_gate import run_stage51_gate

    result = run_stage51_gate(
        live_ws_events={
            "qa": [_turn(sample_id="partial", awarded=2.0)],
            "operator": [_turn(sample_id="partial", awarded=2.0)],
        },
        mnemonic_samples=[
            {
                "sample_id": "deployment_plan_four_items",
                "text": "总进度、分期开竣工、资源平衡、施工准备，部署计划四项别漏。",
                "required_terms": ["总进度", "分期", "资源", "施工准备"],
            }
        ],
        out_dir=tmp_path,
    )

    assert result["go_no_go"]["status"] == "STAGE51_GO"
    assert result["go_no_go"]["blockers"] == []
    assert result["mnemonic_quality"]["content_status"] == "PASS"
    assert result["mnemonic_quality"]["live_action_status"] == "PASS"
    assert result["stable_truth_promotion"]["persisted_readback_status"] == "PASS"
    assert result["stable_truth_promotion"]["weak_point_evidence_level"] == "L1_repeated"
    assert (tmp_path / "stage51_learning_truth_gate.json").exists()


def test_stage51_gate_blocks_missing_mnemonic_action(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage51_learning_truth_gate import run_stage51_gate

    result = run_stage51_gate(
        live_ws_events={"qa": [_turn(sample_id="partial", awarded=2.0, include_mnemonic_action=False)]},
        mnemonic_samples=[
            {
                "sample_id": "deployment_plan_four_items",
                "text": "总进度、分期开竣工、资源平衡、施工准备，部署计划四项别漏。",
                "required_terms": ["总进度", "分期", "资源", "施工准备"],
            }
        ],
        out_dir=tmp_path,
    )

    assert result["go_no_go"]["status"] == "STAGE51_BLOCKED"
    assert "mnemonic_action_missing_for_non_full_pgo" in result["go_no_go"]["blockers"]


def test_stage51_gate_blocks_bad_mnemonic_content(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage51_learning_truth_gate import run_stage51_gate

    result = run_stage51_gate(
        live_ws_events={"qa": [_turn(sample_id="partial", awarded=2.0)]},
        mnemonic_samples=[
            {
                "sample_id": "bad",
                "text": "背一下就行，官方肯定给满分。",
                "required_terms": ["总进度", "分期", "资源", "施工准备"],
            }
        ],
        out_dir=tmp_path,
    )

    assert result["go_no_go"]["status"] == "STAGE51_BLOCKED"
    assert "mnemonic_content_quality_failed" in result["go_no_go"]["blockers"]


def test_stage51_gate_can_use_supplied_core_store_service(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage51_learning_truth_gate import run_stage51_gate

    class _Event:
        def __init__(self, event_id: str) -> None:
            self.event_id = event_id

    class _Service:
        def __init__(self) -> None:
            self.append_count = 0

        def append_memory_event(self, *_args, **_kwargs):
            self.append_count += 1
            return _Event(f"evt-{self.append_count}")

        def synthesize_learning_truth(self, *_args, **_kwargs):
            return {"projection": {"synthesis_run": {"output_projection_hash": "sha256:core"}}}

        def read_compiled_learning_truth(self, *_args, **_kwargs):
            return {
                "synthesis_run": {"output_projection_hash": "sha256:core"},
                "weak_points": [
                    {
                        "concept_id": "1A413050",
                        "error_code": "E02",
                        "evidence_level": "L1_repeated",
                    }
                ],
            }

    service = _Service()
    result = run_stage51_gate(
        live_ws_events={"qa": [_turn(sample_id="partial", awarded=2.0)]},
        mnemonic_samples=[
            {
                "sample_id": "deployment_plan_four_items",
                "text": "总进度、分期开竣工、资源平衡、施工准备，部署计划四项别漏。",
                "required_terms": ["总进度", "分期", "资源", "施工准备"],
            }
        ],
        out_dir=tmp_path,
        learner_state_service_factory=lambda _runtime_root: service,
    )

    assert service.append_count == 2
    assert result["go_no_go"]["status"] == "STAGE51_GO"
    assert result["stable_truth_promotion"]["output_projection_hash"] == "sha256:core"
