"""成本自校准：用官方账单 model 级金额反推真实单价，校准内账估算。

理念（用户 2026-06-12）：官方账单为锚（权威）+ 实时 token 统计保留（快速反馈）
+ 自己的算法不断和官方校准。

- 实时统计：UsageLedger 按 model 累加 token（快，但定价表单价可能偏）。
- 官方账单：阿里云 BssOpenApi 拉 model 级真实金额（CNY，权威）。
- 自校准：每个 model 的校准系数 = 官方金额 / 内账估算成本；校准后内账 ≈ 官方真值。
- 漏 token：校准系数会自动吸收（真实单价被推高补偿），同时独立记录 token_coverage_ratio 提示漏记。

货币：官方账单与内账必须显式处于同一币种；混币或缺币种时禁止应用校准。
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import threading
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_EMPTY: dict[str, Any] = {"models": {}, "global": {}}
CALIBRATION_SNAPSHOT_VERSION = 2
DEFAULT_MAX_AGE_DAYS = 45
MIN_TOKEN_COVERAGE_RATIO = 0.9
MAX_TOKEN_COVERAGE_RATIO = 1.1


def compute_calibration(
    official_model_amounts: dict[str, float],
    internal_by_model: dict[str, dict[str, Any]],
    *,
    official_total_tokens: float | None = None,
) -> dict[str, Any]:
    """反推真实单价与校准系数。

    official_model_amounts: {model: 官方账单金额}
    internal_by_model: {model: {"total_tokens": int, "internal_cost": float}}
    """
    models: dict[str, Any] = {}
    calibrated_total = 0.0
    internal_total_tokens = 0.0

    for model, internal in internal_by_model.items():
        tokens = float(internal.get("total_tokens") or 0)
        internal_cost = float(internal.get("internal_cost") or 0)
        internal_total_tokens += tokens
        official_amount = official_model_amounts.get(model)
        covered = official_amount is not None

        if covered and internal_cost > 0:
            factor = float(official_amount) / internal_cost
        else:
            factor = 1.0

        if covered and tokens > 0:
            real_unit_price_per_1m: float | None = float(official_amount) / (tokens / 1_000_000)
        else:
            real_unit_price_per_1m = None

        calibrated_cost = internal_cost * factor
        calibrated_total += calibrated_cost
        models[model] = {
            "total_tokens": tokens,
            "internal_cost": round(internal_cost, 8),
            "official_amount": round(float(official_amount), 8) if covered else None,
            "covered_by_official": covered,
            "real_unit_price_per_1m": (
                round(real_unit_price_per_1m, 8) if real_unit_price_per_1m is not None else None
            ),
            "calibration_factor": round(factor, 8),
            "calibrated_cost": round(calibrated_cost, 8),
        }

    official_total = sum(float(v or 0) for v in official_model_amounts.values())
    global_payload: dict[str, Any] = {
        "calibrated_total": round(calibrated_total, 8),
        "official_total": round(official_total, 8),
        "calibration_health": (
            round(calibrated_total / official_total, 6) if official_total > 0 else None
        ),
        "internal_total_tokens": internal_total_tokens,
    }
    if official_total_tokens:
        global_payload["official_total_tokens"] = float(official_total_tokens)
        global_payload["token_coverage_ratio"] = round(
            internal_total_tokens / float(official_total_tokens), 6
        )
    return {"models": models, "global": global_payload}


def apply_calibration(model: str, internal_cost: float, factors: dict[str, float]) -> float:
    """把校准系数应用到实时内账成本；无系数的 model 原样返回。"""
    factor = factors.get(model)
    if factor is None:
        return internal_cost
    return internal_cost * float(factor)


def evaluate_calibration(
    calibration: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """判断快照能否参与成本计算；证据不足时一律 fail closed。"""
    reasons: list[str] = []
    try:
        snapshot_version = int(calibration.get("snapshot_version") or 0)
    except (TypeError, ValueError):
        snapshot_version = 0
    if snapshot_version != CALIBRATION_SNAPSHOT_VERSION:
        reasons.append("unsupported_snapshot_version")
    models = calibration.get("models")
    if not isinstance(models, dict) or not models:
        reasons.append("missing_model_calibration")
    else:
        for payload in models.values():
            try:
                factor = float(payload.get("calibration_factor"))
            except (AttributeError, TypeError, ValueError):
                reasons.append("invalid_model_calibration")
                break
            if not math.isfinite(factor) or factor <= 0 or not payload.get("currency"):
                reasons.append("invalid_model_calibration")
                break

    refreshed_at = str(calibration.get("refreshed_at") or "").strip()
    try:
        refreshed = datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
        if refreshed.tzinfo is None:
            refreshed = refreshed.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        age_seconds = (reference - refreshed).total_seconds()
        if age_seconds < 0 or age_seconds > max_age_days * 86400:
            reasons.append("stale_calibration")
    except ValueError:
        reasons.append("missing_or_invalid_refreshed_at")

    scope = calibration.get("scope") or {}
    if not isinstance(scope, dict) or scope.get("status") != "matched":
        reasons.append("scope_not_matched")
    else:
        if scope.get("provider_name") != "dashscope":
            reasons.append("provider_scope_mismatch")
        if not scope.get("billing_cycle") or not scope.get("apikey_id"):
            reasons.append("incomplete_account_scope")
        if scope.get("currency_status") != "single_currency" or not scope.get("currency"):
            reasons.append("ambiguous_currency_scope")
        if scope.get("official_token_scope_status") != "exact":
            reasons.append("official_token_scope_not_exact")

    global_payload = calibration.get("global") or {}
    ratio = global_payload.get("token_coverage_ratio")
    if global_payload.get("token_coverage_status") != "ok" or ratio is None:
        reasons.append("insufficient_token_coverage_evidence")
    else:
        try:
            numeric_ratio = float(ratio)
        except (TypeError, ValueError):
            reasons.append("invalid_token_coverage_ratio")
        else:
            if not MIN_TOKEN_COVERAGE_RATIO <= numeric_ratio <= MAX_TOKEN_COVERAGE_RATIO:
                reasons.append("token_coverage_out_of_range")

    return {
        "applicable": not reasons,
        "status": "applicable" if not reasons else "insufficient_evidence",
        "reasons": reasons,
    }


def factor_map(calibration: dict[str, Any]) -> dict[str, float]:
    """仅从适用、同币种、同范围快照提取 {model: factor}。"""
    if not evaluate_calibration(calibration).get("applicable"):
        return {}
    scope_currency = str((calibration.get("scope") or {}).get("currency") or "").upper()
    return {
        model: float(payload.get("calibration_factor") or 1.0)
        for model, payload in (calibration.get("models") or {}).items()
        if str(payload.get("currency") or "").upper() == scope_currency
    }


def save_calibration(path: Path, payload: dict[str, Any]) -> None:
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def load_calibration(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"models": {}, "global": {}}
    except (json.JSONDecodeError, OSError):
        logger.warning("cost_calibration.json unreadable, treating as empty: %s", path)
        return {"models": {}, "global": {}}
    if not isinstance(raw, dict):
        return {"models": {}, "global": {}}
    raw.setdefault("models", {})
    raw.setdefault("global", {})
    return raw
