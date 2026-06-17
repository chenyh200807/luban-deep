import pytest

from deeptutor.services.bi_metrics import BI_METRICS, metric_by_id


def test_bi_metric_dictionary_has_unique_ids() -> None:
    ids = [metric.metric_id for metric in BI_METRICS]

    assert len(ids) == len(set(ids))


def test_bi_metric_dictionary_covers_top_tier_sections() -> None:
    groups = {metric.group for metric in BI_METRICS}

    assert {
        "north_star",
        "growth",
        "member_ops",
        "member_health",
        "teaching_effect",
        "ai_quality",
        "unit_economics",
        "data_trust",
    }.issubset(groups)


def test_bi_metric_dictionary_requires_trust_owner_and_drilldown() -> None:
    allowed_trust_levels = {"A", "B", "C", "D"}

    for metric in BI_METRICS:
        assert metric.trust_level in allowed_trust_levels
        assert metric.owner
        assert metric.drilldown


def test_metric_by_id_returns_definition() -> None:
    metric = metric_by_id("effective_learning_members")

    assert metric.label == "有效学习成功会员数"
    assert metric.authority == "bi_service"
    assert metric.trust_level == "B"
    assert metric.owner == "boss"
    assert "真实手机号会员" in metric.definition


def test_metric_by_id_rejects_unknown_metric() -> None:
    with pytest.raises(KeyError):
        metric_by_id("unknown_metric")


def test_bi_metric_dictionary_includes_product_behavior_metrics() -> None:
    ids = {metric.metric_id for metric in BI_METRICS}

    assert {
        "behavior.module.open_count",
        "behavior.learning_report.section_view_count",
        "behavior.funnel.report_to_training",
        "behavior.member_ops.report_high_no_action",
    }.issubset(ids)


def test_product_behavior_metrics_drill_into_member_ops() -> None:
    for metric_id in [
        "behavior.module.open_count",
        "behavior.learning_report.section_view_count",
        "behavior.funnel.report_to_training",
        "behavior.member_ops.report_high_no_action",
    ]:
        metric = metric_by_id(metric_id)
        assert metric.group == "product_behavior"
        assert metric.drilldown == "member_ops"
        assert metric.owner in {"product", "ops"}
        assert metric.trust_level in {"A", "B"}


def test_metric_registry_ts_in_sync() -> None:
    """Round 3 D drift guard: the generated TS mirror must match BI_METRICS.

    If this fails, regenerate via:
        python -m scripts.gen_bi_metrics_ts

    Editing web/lib/bi-v2-metric-registry.generated.ts by hand is forbidden;
    the file header says so and this test is the enforcement gate.
    """
    from scripts.gen_bi_metrics_ts import OUTPUT_PATH, render_module

    expected = render_module()
    actual = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
    assert actual == expected, (
        "bi-v2-metric-registry.generated.ts is out of sync with BI_METRICS. "
        "Run: python -m scripts.gen_bi_metrics_ts"
    )


def test_metric_registry_fields_complete() -> None:
    """Plan §3.6 requires every KPI to surface refresh cadence + degraded note
    in hover. Guard that BI_METRICS never reintroduces an empty cadence."""
    for metric in BI_METRICS:
        assert metric.refresh_cadence.strip() != "", (
            f"{metric.metric_id} missing refresh_cadence (plan §3.6)"
        )
        # degraded_note may be empty for A-tier metrics with no known degradation
        # path; only C/D tier must declare it.
        if metric.trust_level in ("C", "D"):
            assert metric.degraded_note.strip() != "", (
                f"{metric.metric_id} is trust {metric.trust_level} but has no degraded_note (plan §3.6)"
            )
