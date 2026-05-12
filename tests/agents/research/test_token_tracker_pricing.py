from __future__ import annotations

from deeptutor.agents.research.utils.token_tracker import get_model_pricing


def test_deepseek_v4_pro_pricing_is_available() -> None:
    assert get_model_pricing("deepseek-v4-pro") == {"input": 0.000435, "output": 0.00087}
