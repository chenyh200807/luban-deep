"""Provider-neutral helpers for official billing reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any


def _as_str(value: Any) -> str:
    return str(value or "").strip()


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


__all__ = [
    "BillingScope",
    "CostBasis",
    "ProviderAccountScope",
    "fingerprint_secret",
]
