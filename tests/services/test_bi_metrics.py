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
