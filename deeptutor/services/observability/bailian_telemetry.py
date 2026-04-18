"""Bailian model telemetry client backed by Aliyun Prometheus HTTP API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from typing import Any

import httpx

from deeptutor.services.observability.langfuse_adapter import (
    estimate_model_cost,
    get_model_pricing_metadata,
)


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class BailianTelemetryConfig:
    base_url: str = ""
    access_key_id: str = ""
    access_key_secret: str = ""
    workspace_id: str = ""
    apikey_id: str = ""
    timeout_s: float = 15.0
    verify_ssl: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.access_key_id and self.access_key_secret)


@dataclass(slots=True)
class BailianUsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    models: dict[str, int] = field(default_factory=dict)
    model_details: dict[str, dict[str, Any]] = field(default_factory=dict)
    estimated_total_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "total_tokens": int(self.total_tokens),
            "models": dict(self.models),
            "model_details": dict(self.model_details),
            "estimated_total_cost_usd": round(float(self.estimated_total_cost_usd or 0.0), 8),
        }


class BailianTelemetryClient:
    def __init__(self, config: BailianTelemetryConfig | None = None) -> None:
        self._config = config or self._load_config_from_env()

    @property
    def config(self) -> BailianTelemetryConfig:
        return self._config

    def is_configured(self) -> bool:
        return self._config.is_configured

    @staticmethod
    def _load_config_from_env() -> BailianTelemetryConfig:
        return BailianTelemetryConfig(
            base_url=_as_str(os.getenv("BAILIAN_TELEMETRY_BASE_URL")),
            access_key_id=_as_str(
                os.getenv("BAILIAN_TELEMETRY_ACCESS_KEY_ID")
                or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
                or os.getenv("ALICLOUD_ACCESS_KEY_ID")
            ),
            access_key_secret=_as_str(
                os.getenv("BAILIAN_TELEMETRY_ACCESS_KEY_SECRET")
                or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
                or os.getenv("ALICLOUD_ACCESS_KEY_SECRET")
            ),
            workspace_id=_as_str(os.getenv("BAILIAN_TELEMETRY_WORKSPACE_ID")),
            apikey_id=_as_str(os.getenv("BAILIAN_TELEMETRY_APIKEY_ID")),
            timeout_s=_safe_float(os.getenv("BAILIAN_TELEMETRY_TIMEOUT_S"), 15.0) or 15.0,
            verify_ssl=_as_str(os.getenv("BAILIAN_TELEMETRY_VERIFY_SSL")).lower() not in {"0", "false", "no"},
        )

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        return base_url.rstrip("/")

    @staticmethod
    def _prometheus_ts(timestamp_s: float) -> str:
        return datetime.fromtimestamp(timestamp_s, tz=timezone.utc).isoformat()

    @staticmethod
    def _parse_vector_value(item: dict[str, Any]) -> int:
        value = item.get("value")
        if not isinstance(value, list) or len(value) < 2:
            return 0
        return int(round(_safe_float(value[1], 0.0)))

    @classmethod
    def _parse_model_vector(cls, rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            _as_str((item.get("metric") or {}).get("model")): cls._parse_vector_value(item)
            for item in rows
            if _as_str((item.get("metric") or {}).get("model")) and cls._parse_vector_value(item) > 0
        }

    @staticmethod
    def _build_label_matchers(
        *,
        usage_type: str | None = None,
        workspace_id: str | None = None,
        apikey_id: str | None = None,
        model: str | None = None,
    ) -> str:
        labels: list[str] = []
        if usage_type:
            labels.append(f'usage_type="{_as_str(usage_type)}"')
        if workspace_id:
            labels.append(f'workspace_id="{_as_str(workspace_id)}"')
        if apikey_id:
            labels.append(f'apikey_id="{_as_str(apikey_id)}"')
        if model:
            labels.append(f'model="{_as_str(model)}"')
        return "{" + ",".join(labels) + "}" if labels else ""

    async def _query(self, *, query: str, time_s: float | None = None) -> list[dict[str, Any]]:
        if not self.is_configured():
            raise RuntimeError("Bailian telemetry is not configured")

        params = {"query": query}
        if time_s is not None:
            params["time"] = self._prometheus_ts(time_s)

        async with httpx.AsyncClient(
            auth=(self._config.access_key_id, self._config.access_key_secret),
            timeout=self._config.timeout_s,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.get(
                f"{self._normalize_base_url(self._config.base_url)}/api/v1/query",
                params=params,
            )
            response.raise_for_status()

        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"Bailian telemetry query failed: {payload}")

        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        result = data.get("result")
        return result if isinstance(result, list) else []

    async def get_usage_totals(
        self,
        *,
        start_ts: float,
        end_ts: float,
        workspace_id: str | None = None,
        apikey_id: str | None = None,
        model: str | None = None,
    ) -> BailianUsageTotals:
        if not self.is_configured():
            return BailianUsageTotals()

        effective_workspace_id = _as_str(workspace_id) or self._config.workspace_id
        effective_apikey_id = _as_str(apikey_id) or self._config.apikey_id
        window_s = max(int(round(float(end_ts) - float(start_ts))), 60)

        async def _model_totals(usage_type: str) -> dict[str, int]:
            matchers = self._build_label_matchers(
                usage_type=usage_type,
                workspace_id=effective_workspace_id,
                apikey_id=effective_apikey_id,
                model=model,
            )
            query = f"sum by (model) (increase(model_usage{matchers}[{window_s}s]))"
            result = await self._query(query=query, time_s=end_ts)
            return self._parse_model_vector(result)

        input_by_model = await _model_totals("input_tokens")
        output_by_model = await _model_totals("output_tokens")
        total_by_model = await _model_totals("total_tokens")
        model_names = sorted(set(input_by_model) | set(output_by_model) | set(total_by_model))

        model_details: dict[str, dict[str, Any]] = {}
        estimated_total_cost = 0.0
        for model_name in model_names:
            usage_details = {
                "input": float(input_by_model.get(model_name, 0)),
                "output": float(output_by_model.get(model_name, 0)),
                "total": float(total_by_model.get(model_name, 0)),
            }
            detail: dict[str, Any] = {
                "input_tokens": int(input_by_model.get(model_name, 0)),
                "output_tokens": int(output_by_model.get(model_name, 0)),
                "total_tokens": int(total_by_model.get(model_name, 0)),
            }
            estimated_cost = estimate_model_cost(model=model_name, usage_details=usage_details)
            pricing_metadata = get_model_pricing_metadata(model_name)
            if estimated_cost:
                detail["estimated_cost_usd"] = round(float(estimated_cost.get("total") or 0.0), 8)
                estimated_total_cost += float(estimated_cost.get("total") or 0.0)
            if pricing_metadata:
                detail.update(pricing_metadata)
            model_details[model_name] = detail

        input_tokens = sum(input_by_model.values())
        output_tokens = sum(output_by_model.values())
        total_tokens = sum(total_by_model.values())

        return BailianUsageTotals(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            models=dict(sorted(total_by_model.items(), key=lambda item: item[0])),
            model_details=model_details,
            estimated_total_cost_usd=round(estimated_total_cost, 8),
        )


_client: BailianTelemetryClient | None = None


def get_bailian_telemetry_client() -> BailianTelemetryClient:
    global _client
    if _client is None:
        _client = BailianTelemetryClient()
    return _client


__all__ = [
    "BailianTelemetryClient",
    "BailianTelemetryConfig",
    "BailianUsageTotals",
    "get_bailian_telemetry_client",
]
