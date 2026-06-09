from __future__ import annotations

from deeptutor.api.routers import learning_brain as lb


def test_wechat_harness_has_point_level_teacher_review_controls():
    html = lb.render_learning_brain_harness_html()

    for token in (
        "teacherReviewPanel",
        "teacherReviewedCheckbox",
        "teacherFinalScorePreview",
        "writebackNow",
        "nextSuggestionPreview",
        "data-review-action",
        "data-teacher-hit",
        "data-teacher-score",
        "data-teacher-note",
        "evidence-span",
        "model-votes",
        "review-pending",
    ):
        assert token in html


def test_wechat_harness_reuses_existing_teacher_review_writeback_route():
    html = lb.render_learning_brain_harness_html()

    assert "/api/v1/learning-brain/harness-case-grading-review" in html
    assert "trusted_adjudication confirmed" in html
    assert "legacy alias" in html
    assert "dry_run:true" in html
    assert "writeback:false" in html
    assert "dry_run:false" in html
    assert "writeback:true" in html
    assert "不替代正式评分 authority" in html


def test_wechat_harness_exports_manual_review_audit_metadata():
    html = lb.render_learning_brain_harness_html()

    for token in (
        "reviewerId",
        "reviewStartedAt",
        "reviewer_id",
        "reviewed_at",
        "review_duration_seconds",
        "review_ui_version",
        "writebackUserId",
        "qa_luban_teacher_review_manual_v0",
        "manual_qa_teacher",
        "teacher_review_ux_v0",
    ):
        assert token in html


def test_wechat_harness_review_source_is_explicit_selector_not_hardcoded():
    """Provenance discipline: review_source must be an explicit 3-way selector,
    default operator_smoke (local QA never silently impersonates a human teacher)."""
    html = lb.render_learning_brain_harness_html()

    assert 'id="reviewSource"' in html
    for value in ("operator_smoke", "model_jury_teacher_review", "manual_qa_teacher"):
        assert f'value="{value}"' in html
    assert 'value="operator_smoke" selected' in html
    assert 'review_source:"manual_qa_teacher"' not in html  # old hardcoded default gone
    for token in ("reviewer_type", "authority_label", "trusted_adjudication",
                  "operator_smoke_final", "trusted_adjudication_jury_v1", "llm_jury"):
        assert token in html


def test_review_audit_carries_authority_label_and_jury_provenance():
    """Writeback audit must carry authority_label + (for jury) reviewer_type/jury_models."""
    from deeptutor.services.construction_grading.teacher_review_writeback import (
        build_teacher_review_writeback,
    )

    base = {
        "case_id": "Q17-1A433000", "student_id": "qa_prov", "engine": "best_quality_4model",
        "teacher_reviewed": True,
        "point_reviews": [{"point_id": "P1", "policy_type": "list_rule", "max_score": 2,
                           "ai_hit": "hit", "ai_score": 2, "review_action": "confirm",
                           "teacher_hit": "hit", "teacher_score": 2}],
    }
    op = build_teacher_review_writeback(
        {**base, "review_source": "operator_smoke", "reviewer_type": "operator",
         "authority_label": "operator_smoke_final"}, dry_run=True)
    op_audit = op["learning_evidence_payload"]["next_training_signal"]["teacher_review_audit"]
    assert op_audit["review_source"] == "operator_smoke"
    assert op_audit["authority_label"] == "operator_smoke_final"
    assert op_audit["reviewer_type"] == "operator"

    jury = build_teacher_review_writeback(
        {**base, "review_source": "model_jury_teacher_review", "reviewer_type": "llm_jury",
         "authority_label": "trusted_adjudication",
         "jury_models": ["gpt55", "opus48", "deepseek_v4", "qwen37"],
         "adjudication_protocol": "trusted_adjudication_jury_v1"}, dry_run=True)
    jury_audit = jury["learning_evidence_payload"]["next_training_signal"]["teacher_review_audit"]
    assert jury_audit["reviewer_type"] == "llm_jury"
    assert jury_audit["jury_models"] == ["gpt55", "opus48", "deepseek_v4", "qwen37"]
    assert jury_audit["adjudication_protocol"] == "trusted_adjudication_jury_v1"
    assert jury_audit["authority_label"] == "trusted_adjudication"
