"""成本自校准：用官方账单 model 级金额反推真实单价，校准内账估算。

理念（用户 2026-06-12）：官方账单为锚（权威）+ 实时 token 统计保留（快速反馈）
+ 自己的算法不断和官方校准。

- 实时统计：UsageLedger 按 model 累加 token（快，但定价表单价可能偏）。
- 官方账单：阿里云 BssOpenApi 拉 model 级真实金额（CNY，权威）。
- 自校准：每个 model 的校准系数 = 官方金额 / 内账估算成本；校准后内账 ≈ 官方真值。
- 漏 token：校准系数会自动吸收（真实单价被推高补偿），同时独立记录 token_coverage_ratio 提示漏记。

货币：用户明确忽略换算，全部按 CNY 同口径比较。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_EMPTY: dict[str, Any] = {"models": {}, "global": {}}


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


def factor_map(calibration: dict[str, Any]) -> dict[str, float]:
    """从 compute_calibration 结果提取 {model: factor}，供 apply_calibration 用。"""
    return {
        model: float(payload.get("calibration_factor") or 1.0)
        for model, payload in (calibration.get("models") or {}).items()
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
