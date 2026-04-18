"""Official Bailian billing reconciliation via Aliyun BssOpenApi."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
from typing import Any


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_bailian_instance_id(instance_id: str | None) -> dict[str, str]:
    parts = str(instance_id or "").split(";")
    return {
        "apikey_id": str(parts[0]).strip() if len(parts) > 0 else "",
        "workspace_id": str(parts[1]).strip() if len(parts) > 1 else "",
        "model": str(parts[2]).strip() if len(parts) > 2 else "",
        "usage_kind": str(parts[3]).strip() if len(parts) > 3 else "",
    }


@dataclass(slots=True)
class BailianBillingConfig:
    access_key_id: str = ""
    access_key_secret: str = ""
    endpoint: str = "business.aliyuncs.com"
    region_id: str = "cn-hangzhou"
    product_code: str = "sfm"
    product_type: str = "sfm_inference_public_cn"
    workspace_id: str = ""
    apikey_id: str = ""
    max_results: int = 100

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret)


@dataclass(slots=True)
class BailianBillingTotals:
    billing_cycles: list[dict[str, Any]] = field(default_factory=list)
    pretax_amount: float = 0.0
    after_discount_amount: float = 0.0
    items_count: int = 0
    currency: str = "CNY"
    model_amounts: dict[str, float] = field(default_factory=dict)
    usage_kind_amounts: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "billing_cycles": list(self.billing_cycles),
            "pretax_amount": round(float(self.pretax_amount or 0.0), 8),
            "after_discount_amount": round(float(self.after_discount_amount or 0.0), 8),
            "items_count": int(self.items_count),
            "currency": self.currency,
            "model_amounts": {
                key: round(float(value or 0.0), 8)
                for key, value in sorted(self.model_amounts.items(), key=lambda item: item[0])
            },
            "usage_kind_amounts": {
                key: round(float(value or 0.0), 8)
                for key, value in sorted(self.usage_kind_amounts.items(), key=lambda item: item[0])
            },
        }


class BailianBillingClient:
    def __init__(self, config: BailianBillingConfig | None = None) -> None:
        self._config = config or self._load_config_from_env()

    @property
    def config(self) -> BailianBillingConfig:
        return self._config

    def is_configured(self) -> bool:
        return self._config.is_configured

    @staticmethod
    def _load_config_from_env() -> BailianBillingConfig:
        return BailianBillingConfig(
            access_key_id=_as_str(
                os.getenv("BAILIAN_BILLING_ACCESS_KEY_ID")
                or os.getenv("BAILIAN_TELEMETRY_ACCESS_KEY_ID")
                or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
                or os.getenv("ALICLOUD_ACCESS_KEY_ID")
            ),
            access_key_secret=_as_str(
                os.getenv("BAILIAN_BILLING_ACCESS_KEY_SECRET")
                or os.getenv("BAILIAN_TELEMETRY_ACCESS_KEY_SECRET")
                or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
                or os.getenv("ALICLOUD_ACCESS_KEY_SECRET")
            ),
            endpoint=_as_str(os.getenv("BAILIAN_BILLING_ENDPOINT")) or "business.aliyuncs.com",
            region_id=_as_str(os.getenv("BAILIAN_BILLING_REGION_ID")) or "cn-hangzhou",
            product_code=_as_str(os.getenv("BAILIAN_BILLING_PRODUCT_CODE")) or "sfm",
            product_type=_as_str(os.getenv("BAILIAN_BILLING_PRODUCT_TYPE")) or "sfm_inference_public_cn",
            workspace_id=_as_str(os.getenv("BAILIAN_BILLING_WORKSPACE_ID"))
            or _as_str(os.getenv("BAILIAN_TELEMETRY_WORKSPACE_ID")),
            apikey_id=_as_str(os.getenv("BAILIAN_BILLING_APIKEY_ID"))
            or _as_str(os.getenv("BAILIAN_TELEMETRY_APIKEY_ID")),
            max_results=max(1, min(int(os.getenv("BAILIAN_BILLING_MAX_RESULTS", "100") or "100"), 300)),
        )

    @staticmethod
    def _load_sdk() -> tuple[Any, Any, Any]:
        try:
            from alibabacloud_bssopenapi20171214.client import Client
            from alibabacloud_bssopenapi20171214 import models
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:  # pragma: no cover - exercised through fallback behavior
            raise RuntimeError(
                "Bailian billing SDK is not installed. Install alibabacloud_bssopenapi20171214."
            ) from exc
        return Client, models, open_api_models

    def _build_client(self) -> tuple[Any, Any]:
        Client, models, open_api_models = self._load_sdk()
        config = open_api_models.Config(
            access_key_id=self._config.access_key_id,
            access_key_secret=self._config.access_key_secret,
            endpoint=self._config.endpoint,
            region_id=self._config.region_id,
        )
        return Client(config), models

    @staticmethod
    def _matches_filters(
        *,
        parsed_instance: dict[str, str],
        workspace_id: str,
        apikey_id: str,
        model: str,
    ) -> bool:
        if workspace_id and parsed_instance.get("workspace_id") != workspace_id:
            return False
        if apikey_id and parsed_instance.get("apikey_id") != apikey_id:
            return False
        if model and parsed_instance.get("model") != model:
            return False
        return True

    def _query_cycle_sync(
        self,
        *,
        billing_cycle: str,
        workspace_id: str,
        apikey_id: str,
        model: str,
    ) -> dict[str, Any]:
        client, models = self._build_client()
        next_token: str | None = None
        items: list[dict[str, Any]] = []
        currency = "CNY"

        while True:
            request = models.DescribeInstanceBillRequest(
                billing_cycle=billing_cycle,
                product_code=self._config.product_code,
                product_type=self._config.product_type,
                max_results=self._config.max_results,
                next_token=next_token,
            )
            response = client.describe_instance_bill(request)
            body = response.body.to_map() if hasattr(response.body, "to_map") else {}
            data = body.get("Data") if isinstance(body, dict) else {}
            page_items = data.get("Items") if isinstance(data, dict) else []
            for item in page_items or []:
                parsed_instance = _parse_bailian_instance_id(item.get("InstanceID"))
                if not self._matches_filters(
                    parsed_instance=parsed_instance,
                    workspace_id=workspace_id,
                    apikey_id=apikey_id,
                    model=model,
                ):
                    continue
                normalized = dict(item)
                normalized["_parsed_instance"] = parsed_instance
                items.append(normalized)
                currency = _as_str(item.get("Currency")) or currency

            next_token = _as_str((data or {}).get("NextToken"))
            if not next_token:
                break

        pretax_amount = 0.0
        after_discount_amount = 0.0
        model_amounts: dict[str, float] = {}
        usage_kind_amounts: dict[str, float] = {}
        for item in items:
            parsed_instance = item.get("_parsed_instance") or {}
            amount = _safe_float(item.get("PretaxAmount"))
            after_discount = _safe_float(item.get("AfterDiscountAmount"), amount)
            pretax_amount += amount
            after_discount_amount += after_discount

            model_name = _as_str(parsed_instance.get("model")) or "unknown"
            usage_kind = _as_str(parsed_instance.get("usage_kind")) or "unknown"
            model_amounts[model_name] = float(model_amounts.get(model_name) or 0.0) + amount
            usage_kind_amounts[usage_kind] = float(usage_kind_amounts.get(usage_kind) or 0.0) + amount

        return {
            "billing_cycle": billing_cycle,
            "pretax_amount": round(pretax_amount, 8),
            "after_discount_amount": round(after_discount_amount, 8),
            "items_count": len(items),
            "currency": currency,
            "model_amounts": {key: round(value, 8) for key, value in model_amounts.items()},
            "usage_kind_amounts": {key: round(value, 8) for key, value in usage_kind_amounts.items()},
            "filters": {
                "workspace_id": workspace_id,
                "apikey_id": apikey_id,
                "model": model,
                "product_code": self._config.product_code,
                "product_type": self._config.product_type,
            },
        }

    async def get_totals(
        self,
        *,
        billing_cycles: list[str],
        workspace_id: str | None = None,
        apikey_id: str | None = None,
        model: str | None = None,
    ) -> BailianBillingTotals:
        if not self.is_configured():
            return BailianBillingTotals()

        effective_workspace_id = _as_str(workspace_id) or self._config.workspace_id
        effective_apikey_id = _as_str(apikey_id) or self._config.apikey_id
        effective_model = _as_str(model)

        cycle_payloads: list[dict[str, Any]] = []
        total_pretax = 0.0
        total_after_discount = 0.0
        total_items = 0
        currency = "CNY"
        model_amounts: dict[str, float] = {}
        usage_kind_amounts: dict[str, float] = {}

        for billing_cycle in [cycle for cycle in billing_cycles if _as_str(cycle)]:
            payload = await asyncio.to_thread(
                self._query_cycle_sync,
                billing_cycle=_as_str(billing_cycle),
                workspace_id=effective_workspace_id,
                apikey_id=effective_apikey_id,
                model=effective_model,
            )
            cycle_payloads.append(payload)
            total_pretax += _safe_float(payload.get("pretax_amount"))
            total_after_discount += _safe_float(payload.get("after_discount_amount"))
            total_items += int(payload.get("items_count") or 0)
            currency = _as_str(payload.get("currency")) or currency

            for key, value in (payload.get("model_amounts") or {}).items():
                model_amounts[str(key)] = float(model_amounts.get(str(key)) or 0.0) + _safe_float(value)
            for key, value in (payload.get("usage_kind_amounts") or {}).items():
                usage_kind_amounts[str(key)] = float(usage_kind_amounts.get(str(key)) or 0.0) + _safe_float(value)

        return BailianBillingTotals(
            billing_cycles=cycle_payloads,
            pretax_amount=round(total_pretax, 8),
            after_discount_amount=round(total_after_discount, 8),
            items_count=total_items,
            currency=currency,
            model_amounts=model_amounts,
            usage_kind_amounts=usage_kind_amounts,
        )


_client: BailianBillingClient | None = None


def get_bailian_billing_client() -> BailianBillingClient:
    global _client
    if _client is None:
        _client = BailianBillingClient()
    return _client


__all__ = [
    "BailianBillingClient",
    "BailianBillingConfig",
    "BailianBillingTotals",
    "get_bailian_billing_client",
]
