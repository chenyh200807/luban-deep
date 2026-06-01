from __future__ import annotations

from deeptutor.tutorbot.providers.registry import find_gateway


def test_find_gateway_detects_volcengine_coding_plan_base_url() -> None:
    spec = find_gateway(api_base="https://ark.cn-beijing.volces.com/api/coding/v3")

    assert spec is not None
    assert spec.name == "volcengine_coding_plan"
    assert spec.strip_model_prefix is True


def test_find_gateway_detects_byteplus_coding_plan_base_url() -> None:
    spec = find_gateway(api_base="https://ark.ap-southeast.bytepluses.com/api/coding/v3")

    assert spec is not None
    assert spec.name == "byteplus_coding_plan"
    assert spec.strip_model_prefix is True
