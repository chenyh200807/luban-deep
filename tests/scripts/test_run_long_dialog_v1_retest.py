from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "run_long_dialog_v1_retest.py"
    spec = importlib.util.spec_from_file_location("run_long_dialog_v1_retest_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_ws_turn_config_does_not_bind_eval_user() -> None:
    module = _load_module()

    runtime_config = module._build_turn_config(
        query="测试问题",
        teaching_mode="smart",
        include_eval_user=True,
    )
    live_ws_config = module._build_turn_config(
        query="测试问题",
        teaching_mode="smart",
        include_eval_user=False,
    )

    assert runtime_config["billing_context"]["user_id"] == "ld_eval_user"
    assert "user_id" not in live_ws_config["billing_context"]
    assert live_ws_config["billing_context"]["source"] == "wx_miniprogram"
    assert runtime_config["interaction_profile"] == "tutorbot"
    assert runtime_config["interaction_hints"]["profile"] == "tutorbot"
