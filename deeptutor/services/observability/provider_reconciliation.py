"""Provider-neutral helpers for official billing reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _amounts(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        _as_str(currency).upper(): round(_safe_float(amount), 8)
        for currency, amount in value.items()
        if _as_str(currency) and _safe_float(amount) != 0.0
    }


def fingerprint_secret(value: str) -> str:
    """Return a stable non-secret fingerprint for provider keys."""
    secret = _as_str(value)
    if not secret:
        return ""
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


@dataclass(slots=True)
class BillingScope:
    provider_name: str
    charged_account_fingerprint: str
    runtime_environment: str
    cost_center: str
    billing_cycle: str
    raw_model: str = ""
    normalized_model: str = ""
    pricing_model: str = ""
    billable_unit: str = "non_billable"
    billable_turn_id: str = ""

    @property
    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if not _as_str(self.charged_account_fingerprint):
            warnings.append("missing_account_scope")
        if _as_str(self.runtime_environment).lower() in {"", "unknown"} or _as_str(
            self.cost_center
        ).lower() in {"", "unknown"}:
            warnings.append("unknown_scope")
        if _as_str(self.billable_unit) == "conversation_turn" and not _as_str(
            self.billable_turn_id
        ):
            warnings.append("missing_billable_turn_id")
        return warnings

    @property
    def margin_confidence(self) -> str:
        return "untrusted" if self.warnings else "trusted"


@dataclass(frozen=True, slots=True)
class CostBasis:
    primary: str
    supporting: tuple[str, ...] = ()

    @classmethod
    def for_margin(cls) -> "CostBasis":
        return cls(
            primary="list_price_cost",
            supporting=("net_charge_cost", "cash_paid_cost"),
        )


@dataclass(slots=True)
class ProviderAccountScope:
    provider_name: str
    api_key_fingerprint: str = ""
    official_key_id: str = ""
    official_key_label: str = ""
    official_masked_key: str = ""

    def matches_official_key(self, official_row: dict[str, Any]) -> bool:
        candidates = {
            _as_str(official_row.get("key_id")),
            _as_str(official_row.get("key_label")),
            _as_str(official_row.get("masked_key")),
            _as_str(official_row.get("api_key_fingerprint")),
        }
        expected = {
            _as_str(self.official_key_id),
            _as_str(self.official_key_label),
            _as_str(self.official_masked_key),
            _as_str(self.api_key_fingerprint),
        }
        return bool({value for value in expected if value} & {value for value in candidates if value})


def build_reconciliation_delta(
    *,
    provider_name: str,
    cost_basis: str,
    internal: dict[str, Any],
    official: dict[str, Any],
    warn_ratio: float = 0.05,
) -> dict[str, Any]:
    internal_tokens = _safe_int((internal or {}).get("total_tokens"))
    official_tokens = _safe_int((official or {}).get("total_tokens"))
    token_delta = internal_tokens - official_tokens
    token_denominator = max(abs(official_tokens), 1)
    token_delta_ratio = round(float(token_delta) / float(token_denominator), 6)

    warnings: list[str] = []
    status = "ok"
    official_status = _as_str((official or {}).get("status"))
    if internal_tokens > 0 and official_status in {"unconfigured", "empty"}:
        status = "waiting_for_official_export"
        warnings.append("waiting_for_official_export")

    internal_amounts = _amounts((internal or {}).get("currency_amounts"))
    official_amounts = _amounts((official or {}).get("currency_amounts"))
    shared_currencies = sorted(set(internal_amounts) & set(official_amounts))
    amount_delta_by_currency: dict[str, float] = {}
    if internal_amounts and official_amounts and not shared_currencies:
        warnings.append("currency_mismatch")
        if status == "ok":
            status = "warning"
    for currency in shared_currencies:
        delta = round(internal_amounts.get(currency, 0.0) - official_amounts.get(currency, 0.0), 8)
        amount_delta_by_currency[currency] = delta
        denominator = max(abs(official_amounts.get(currency, 0.0)), 1e-12)
        if abs(delta) / denominator > warn_ratio and status == "ok":
            status = "warning"

    if abs(token_delta_ratio) > warn_ratio and status == "ok":
        status = "warning"

    provider_calls = _safe_int((internal or {}).get("provider_calls"))
    unattributed_calls = _safe_int((internal or {}).get("unattributed_provider_calls"))
    if provider_calls > 0 and unattributed_calls / provider_calls > 0.05:
        status = "untrusted"
        warnings.append("unattributed_provider_calls")

    internal_scope = _as_str((internal or {}).get("account_scope") or (internal or {}).get("api_key_fingerprint"))
    official_scope = _as_str((official or {}).get("account_scope") or (official or {}).get("api_key_fingerprint"))
    if internal_scope and official_scope and internal_scope != official_scope:
        warnings.append("scope_mismatch")
        if status == "ok":
            status = "warning"

    billable_turns = _safe_int((internal or {}).get("billable_turns"))
    cost_per_billable_turn: dict[str, float] = {}
    if billable_turns > 0:
        cost_per_billable_turn = {
            currency: round(amount / float(billable_turns), 8)
            for currency, amount in internal_amounts.items()
        }

    confidence = "trusted" if status == "ok" else status
    return {
        "provider_name": _as_str(provider_name),
        "status": status,
        "token_delta": token_delta,
        "token_delta_ratio": token_delta_ratio,
        "cost_basis": _as_str(cost_basis) or "list_price_cost",
        "cost_per_billable_turn": cost_per_billable_turn,
        "amount_delta_by_currency": amount_delta_by_currency,
        "warnings": sorted(set(warnings)),
        "confidence": confidence,
    }


__all__ = [
    "BillingScope",
    "CostBasis",
    "ProviderAccountScope",
    "build_reconciliation_delta",
    "fingerprint_secret",
]
