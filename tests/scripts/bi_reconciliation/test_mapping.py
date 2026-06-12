from __future__ import annotations

import pytest

from deeptutor.services.bi_metrics import BI_METRICS
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS, mapping_by_id


def test_mapping_covers_every_registered_metric():
    """指标宇宙 = BI_METRICS；每个注册指标必须有映射声明（哪怕声明为 unmapped）。"""
    mapped_ids = {m.metric_id for m in METRIC_MAPPINGS}
    registry_ids = {m.metric_id for m in BI_METRICS}
    assert mapped_ids == registry_ids


def test_mapping_declares_at_least_bi_source_or_explicit_gap():
    """每个映射要么声明 bi_api 取数路径，要么显式 gap_note——不许沉默缺源。"""
    for m in METRIC_MAPPINGS:
        assert m.bi_api_path or m.gap_note, m.metric_id


def test_mapping_by_id_raises_on_unknown():
    with pytest.raises(KeyError):
        mapping_by_id("nonexistent_metric")
