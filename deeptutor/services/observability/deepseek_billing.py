"""DeepSeek official billing helpers.

Only the balance endpoint is network-backed here. Usage export parsing is kept
deterministic and schema-gated until a real DeepSeek export has been audited.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
from pathlib import Path
import os
from typing import Any
import zipfile

import httpx

from deeptutor.services.observability.official_billing_imports import (
    OfficialBillingImportStore,
)


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _export_max_bytes() -> int:
    raw = _as_str(os.getenv("DEEPSEEK_BILLING_EXPORT_MAX_BYTES"))
    if not raw:
        return 10 * 1024 * 1024
    try:
        return max(1, int(raw))
    except ValueError:
        return 10 * 1024 * 1024


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _schema_hash(headers: list[str]) -> str:
    return _sha256_bytes(json.dumps(headers, ensure_ascii=False).encode("utf-8"))


def _headers_from_payload(payload: bytes) -> list[str]:
    with io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return [str(value or "").strip() for value in next(reader, [])]


def _manifest_entry(
    *,
    name: str,
    relative_path: str,
    source_file_name: str,
    source_file_sha256: str,
    headers: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "relative_path": relative_path,
        "headers": headers,
        "source_file_name": source_file_name,
        "source_file_sha256": source_file_sha256,
        "schema_hash": _schema_hash(headers),
    }


def _assert_payload_size(size: int, max_bytes: int) -> None:
    if int(size or 0) > max_bytes:
        raise ValueError("export_too_large")


def _iter_export_header_entries(path: Path, *, max_bytes: int) -> list[dict[str, Any]]:
    if path.is_dir():
        rows: list[dict[str, Any]] = []
        for file in sorted(path.rglob("*.csv")):
            relative_path = file.relative_to(path).as_posix()
            if file.is_symlink():
                raise ValueError("unsafe_export_path")
            _assert_payload_size(file.stat().st_size, max_bytes)
            payload = file.read_bytes()
            rows.append(
                _manifest_entry(
                    name=file.name,
                    relative_path=relative_path,
                    source_file_name=file.name,
                    source_file_sha256=_sha256_bytes(payload),
                    headers=_headers_from_payload(payload),
                )
            )
        return rows

    _assert_payload_size(path.stat().st_size, max_bytes)
    payload = path.read_bytes()
    source_sha = _sha256_bytes(payload)
    if path.suffix.lower() == ".zip":
        rows = []
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                name = info.filename
                if not name.lower().endswith(".csv"):
                    continue
                _assert_payload_size(info.file_size, max_bytes)
                with archive.open(name) as raw:
                    headers = _headers_from_payload(raw.read())
                rows.append(
                    _manifest_entry(
                        name=Path(name).name,
                        relative_path=name,
                        source_file_name=path.name,
                        source_file_sha256=source_sha,
                        headers=headers,
                    )
                )
        return rows

    return [
        _manifest_entry(
            name=path.name,
            relative_path=path.name,
            source_file_name=path.name,
            source_file_sha256=source_sha,
            headers=_headers_from_payload(payload),
        )
    ]


@dataclass(slots=True)
class DeepSeekBillingConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    usage_export_dir: str = ""
    timeout_s: float = 15.0

    @classmethod
    def from_env(cls) -> "DeepSeekBillingConfig":
        return cls(
            api_key=_as_str(
                os.getenv("DEEPSEEK_BILLING_API_KEY")
                or os.getenv("DEEPSEEK_API_KEY")
                or ""
            ),
            base_url=_as_str(os.getenv("DEEPSEEK_BILLING_BASE_URL"))
            or "https://api.deepseek.com",
            usage_export_dir=_as_str(os.getenv("DEEPSEEK_BILLING_USAGE_EXPORT_DIR")),
        )


@dataclass(slots=True)
class DeepSeekBalanceTotals:
    status: str = "unconfigured"
    is_available: bool = False
    currency_balances: dict[str, dict[str, float]] = field(default_factory=dict)
    provider_name: str = "deepseek"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeepSeekBalanceTotals":
        balances: dict[str, dict[str, float]] = {}
        for item in payload.get("balance_infos") or []:
            if not isinstance(item, dict):
                continue
            currency = _as_str(item.get("currency")).upper()
            if not currency:
                continue
            balances[currency] = {
                "total_balance": _safe_float(item.get("total_balance")),
                "granted_balance": _safe_float(item.get("granted_balance")),
                "topped_up_balance": _safe_float(item.get("topped_up_balance")),
            }
        return cls(
            status="ok",
            is_available=bool(payload.get("is_available")),
            currency_balances=balances,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_name": self.provider_name,
            "is_available": bool(self.is_available),
            "currency_balances": {
                currency: dict(values)
                for currency, values in self.currency_balances.items()
            },
        }


@dataclass(slots=True)
class DeepSeekUsageExportTotals:
    status: str = "unconfigured"
    total_amount: float = 0.0
    currency: str = "USD"
    currency_amounts: dict[str, float] = field(default_factory=dict)
    cost_basis: str = "net_charge_cost"
    models: dict[str, dict[str, float]] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_official_usage_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_name": "deepseek",
            "cost_basis": self.cost_basis,
            "total_amount": round(float(self.total_amount or 0.0), 8),
            "currency": self.currency,
            "currency_amounts": dict(self.currency_amounts),
            "models": {model: dict(values) for model, values in self.models.items()},
            "files": list(self.files),
            "manifest": dict(self.manifest),
        }


def parse_deepseek_usage_export(path: Path) -> DeepSeekUsageExportTotals:
    export_path = Path(path).expanduser()
    if not export_path.exists():
        return DeepSeekUsageExportTotals(status="missing_export")
    if export_path.is_symlink():
        return DeepSeekUsageExportTotals(status="unsafe_export_path")
    try:
        files = _iter_export_header_entries(export_path, max_bytes=_export_max_bytes())
    except ValueError as exc:
        if str(exc) == "unsafe_export_path":
            return DeepSeekUsageExportTotals(status="unsafe_export_path")
        if str(exc) == "export_too_large":
            return DeepSeekUsageExportTotals(status="export_too_large")
        raise
    except zipfile.BadZipFile:
        return DeepSeekUsageExportTotals(status="invalid_export")
    if not files:
        return DeepSeekUsageExportTotals(status="empty_export")
    return DeepSeekUsageExportTotals(
        status="unsupported_export_schema",
        files=[str(item.get("name") or "") for item in files if str(item.get("name") or "")],
        manifest={"files": files},
    )


def _has_import_manifest(manifest: dict[str, Any]) -> bool:
    return all(
        _as_str(manifest.get(field))
        for field in ("source_file_sha256", "schema_hash", "source_file_name")
    )


class DeepSeekBillingClient:
    def __init__(
        self,
        config: DeepSeekBillingConfig | None = None,
        *,
        http_client: Any | None = None,
        import_store: OfficialBillingImportStore | None = None,
    ) -> None:
        self._config = config or DeepSeekBillingConfig.from_env()
        self._http_client = http_client
        self._import_store = import_store

    def is_configured(self) -> bool:
        return bool(self._config.api_key or self._config.usage_export_dir)

    async def get_balance(self) -> DeepSeekBalanceTotals:
        if not self._config.api_key:
            return DeepSeekBalanceTotals(status="unconfigured")
        return await self._fetch_balance()

    async def _fetch_balance(self) -> DeepSeekBalanceTotals:
        base_url = self._config.base_url.rstrip("/") or "https://api.deepseek.com"
        client = self._http_client
        close_client = False
        if client is None:
            client = httpx.AsyncClient()
            close_client = True
        try:
            response = await client.get(
                f"{base_url}/user/balance",
                headers={"Authorization": f"Bearer {self._config.api_key}"},
                timeout=float(self._config.timeout_s),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return DeepSeekBalanceTotals(status="invalid_response")
            return DeepSeekBalanceTotals.from_payload(payload)
        finally:
            if close_client:
                await client.aclose()

    @staticmethod
    def parse_usage_export(path: Path) -> DeepSeekUsageExportTotals:
        return parse_deepseek_usage_export(path)

    async def get_usage_export_totals(
        self,
        *,
        billing_cycle: str | None = None,
        model: str | None = None,
    ) -> DeepSeekUsageExportTotals:
        if not self._config.usage_export_dir:
            return DeepSeekUsageExportTotals(status="unconfigured")
        totals = self.parse_usage_export(Path(self._config.usage_export_dir))
        if model and totals.models:
            selected = totals.models.get(model, {})
            totals.models = {model: dict(selected)} if selected else {}
        if totals.status in {"ok", "empty"}:
            if not _has_import_manifest(totals.manifest):
                totals.status = "invalid_export_manifest"
                return totals
            import_store = self._import_store or OfficialBillingImportStore()
            import_store.record_import(
                provider_name="deepseek",
                billing_cycle=_as_str(totals.manifest.get("billing_cycle") or billing_cycle),
                source_file_sha256=_as_str(totals.manifest["source_file_sha256"]),
                schema_hash=_as_str(totals.manifest.get("schema_hash")),
                source_file_name=_as_str(totals.manifest.get("source_file_name")),
                manifest=totals.manifest,
            )
        return totals


__all__ = [
    "DeepSeekBalanceTotals",
    "DeepSeekBillingClient",
    "DeepSeekBillingConfig",
    "DeepSeekUsageExportTotals",
    "parse_deepseek_usage_export",
]
