from __future__ import annotations

from pathlib import Path

from scripts.verify_runtime_assets import validate_runtime_assets


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_assets_remain_self_consistent() -> None:
    errors = validate_runtime_assets(PROJECT_ROOT)
    assert errors == []
