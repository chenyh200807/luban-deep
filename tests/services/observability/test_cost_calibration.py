from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deeptutor.services.observability.cost_calibration import (
    CALIBRATION_SNAPSHOT_VERSION,
    apply_calibration,
    compute_calibration,
    evaluate_calibration,
    factor_map,
    load_calibration,
    save_calibration,
)


def test_compute_factor_per_model_from_official_billing():
    """真实单价由官方账单金额 / 内账token反推；校准系数 = 真实 / 内账估算。"""
    official = {"deepseek-v4-flash": 18.18, "qwen-plus": 5.50}
    internal = {
        "deepseek-v4-flash": {"total_tokens": 16_000_000, "internal_cost": 2.40},
        "qwen-plus": {"total_tokens": 2_000_000, "internal_cost": 0.50},
    }
    result = compute_calibration(official, internal)
    flash = result["models"]["deepseek-v4-flash"]
    assert abs(flash["real_unit_price_per_1m"] - (18.18 / 16.0)) < 1e-6
    assert abs(flash["calibration_factor"] - (18.18 / 2.40)) < 1e-6
    # 全局健康度：校准后总额应等于官方总额
    assert abs(result["global"]["calibrated_total"] - (18.18 + 5.50)) < 1e-6
    assert abs(result["global"]["official_total"] - (18.18 + 5.50)) < 1e-6
    assert abs(result["global"]["calibration_health"] - 1.0) < 1e-6


def test_uncovered_model_keeps_internal_estimate():
    """官方账单没有的 model（如 DeepSeek 直连）保留内账估算，factor=1。"""
    official = {"deepseek-v4-flash": 18.18}
    internal = {
        "deepseek-v4-flash": {"total_tokens": 16_000_000, "internal_cost": 2.40},
        "deepseek-direct": {"total_tokens": 1_000_000, "internal_cost": 0.02},
    }
    result = compute_calibration(official, internal)
    direct = result["models"]["deepseek-direct"]
    assert direct["calibration_factor"] == 1.0
    assert direct["covered_by_official"] is False


def test_token_coverage_ratio_flags_missing_tokens():
    """官方 token > 内账 token 时记录覆盖率，提示漏记。"""
    official = {"deepseek-v4-flash": 18.18}
    internal = {"deepseek-v4-flash": {"total_tokens": 16_000_000, "internal_cost": 2.40}}
    result = compute_calibration(official, internal, official_total_tokens=26_000_000)
    assert abs(result["global"]["token_coverage_ratio"] - (16_000_000 / 26_000_000)) < 1e-6


def test_zero_internal_tokens_does_not_divide_by_zero():
    official = {"ghost-model": 5.0}
    internal = {"ghost-model": {"total_tokens": 0, "internal_cost": 0.0}}
    result = compute_calibration(official, internal)
    g = result["models"]["ghost-model"]
    assert g["real_unit_price_per_1m"] is None
    assert g["calibration_factor"] == 1.0


def test_apply_calibration_scales_internal_cost():
    factors = {"deepseek-v4-flash": 7.5}
    assert apply_calibration("deepseek-v4-flash", 2.40, factors) == 2.40 * 7.5
    # 无系数的 model 原样返回
    assert apply_calibration("unknown", 1.0, factors) == 1.0


def test_persist_and_load_roundtrip(tmp_path):
    payload = {"models": {"deepseek-v4-flash": {"calibration_factor": 7.5}}, "global": {}}
    p = tmp_path / "cost_calibration.json"
    save_calibration(p, payload)
    loaded = load_calibration(p)
    assert loaded["models"]["deepseek-v4-flash"]["calibration_factor"] == 7.5


def test_load_missing_file_returns_empty(tmp_path):
    loaded = load_calibration(tmp_path / "nope.json")
    assert loaded == {"models": {}, "global": {}}


def _applicable_snapshot(now: datetime) -> dict:
    return {
        "snapshot_version": CALIBRATION_SNAPSHOT_VERSION,
        "refreshed_at": now.isoformat(),
        "billing_cycle": "2026-06",
        "models": {
            "deepseek-v4-flash": {
                "calibration_factor": 7.5,
                "currency": "CNY",
            }
        },
        "global": {
            "token_coverage_status": "ok",
            "token_coverage_ratio": 1.0,
        },
        "scope": {
            "status": "matched",
            "provider_name": "dashscope",
            "billing_cycle": "2026-06",
            "apikey_id": "api-key-scope",
            "currency": "CNY",
            "currency_status": "single_currency",
            "official_token_scope_status": "exact",
        },
    }


def test_factor_map_only_applies_fresh_exact_scope_snapshot():
    now = datetime.now(timezone.utc)
    snapshot = _applicable_snapshot(now)
    assert evaluate_calibration(snapshot, now=now)["applicable"] is True
    assert factor_map(snapshot) == {"deepseek-v4-flash": 7.5}


def test_legacy_or_stale_snapshot_does_not_apply():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    legacy = {"models": {"deepseek-v4-flash": {"calibration_factor": 7.5}}}
    assert factor_map(legacy) == {}

    stale = _applicable_snapshot(now - timedelta(days=46))
    evaluation = evaluate_calibration(stale, now=now)
    assert evaluation["applicable"] is False
    assert "stale_calibration" in evaluation["reasons"]


def test_low_coverage_or_ambiguous_currency_does_not_apply():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    low_coverage = _applicable_snapshot(now)
    low_coverage["global"]["token_coverage_ratio"] = 0.625
    assert evaluate_calibration(low_coverage, now=now)["applicable"] is False

    mixed = _applicable_snapshot(now)
    mixed["scope"]["currency_status"] = "mixed_currency"
    assert evaluate_calibration(mixed, now=now)["applicable"] is False
    assert factor_map(mixed) == {}


def test_non_exact_token_window_does_not_apply():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    snapshot = _applicable_snapshot(now)
    snapshot["scope"]["official_token_scope_status"] = "insufficient_evidence"
    snapshot["global"]["token_coverage_status"] = "insufficient_evidence"
    snapshot["global"].pop("token_coverage_ratio")
    evaluation = evaluate_calibration(snapshot, now=now)
    assert evaluation["applicable"] is False
    assert "official_token_scope_not_exact" in evaluation["reasons"]
