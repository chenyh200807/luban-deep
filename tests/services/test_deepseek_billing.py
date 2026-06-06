from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from deeptutor.services.observability.deepseek_billing import (
    DeepSeekBalanceTotals,
    DeepSeekBillingClient,
    DeepSeekBillingConfig,
    DeepSeekUsageExportTotals,
    parse_deepseek_usage_export,
)


def test_deepseek_balance_totals_parse_official_payload() -> None:
    payload = {
        "is_available": True,
        "balance_infos": [
            {
                "currency": "CNY",
                "total_balance": "110.00",
                "granted_balance": "10.00",
                "topped_up_balance": "100.00",
            }
        ],
    }

    totals = DeepSeekBalanceTotals.from_payload(payload)

    assert totals.is_available is True
    assert totals.currency_balances["CNY"]["total_balance"] == 110.0
    assert totals.currency_balances["CNY"]["granted_balance"] == 10.0
    assert totals.currency_balances["CNY"]["topped_up_balance"] == 100.0


@pytest.mark.asyncio
async def test_deepseek_balance_returns_unconfigured_without_api_key() -> None:
    class FailingHttpClient:
        async def get(self, *_args, **_kwargs):
            raise AssertionError("HTTP should not be called without an API key")

    client = DeepSeekBillingClient(
        DeepSeekBillingConfig(api_key=""),
        http_client=FailingHttpClient(),
    )

    totals = await client.get_balance()

    assert totals.status == "unconfigured"
    assert totals.is_available is False


@pytest.mark.asyncio
async def test_deepseek_balance_client_fetches_official_balance_endpoint() -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "USD",
                        "total_balance": "1.25",
                        "granted_balance": "0",
                        "topped_up_balance": "1.25",
                    }
                ],
            }

    class FakeHttpClient:
        async def get(self, url: str, *, headers: dict[str, str], timeout: float):
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["timeout"] = timeout
            return FakeResponse()

    client = DeepSeekBillingClient(
        DeepSeekBillingConfig(api_key="sk-test", base_url="https://api.deepseek.com"),
        http_client=FakeHttpClient(),
    )

    totals = await client.get_balance()

    assert captured["url"] == "https://api.deepseek.com/user/balance"
    assert captured["headers"] == {"Authorization": "Bearer sk-test"}
    assert totals.status == "ok"
    assert totals.currency_balances["USD"]["total_balance"] == 1.25


def test_deepseek_usage_export_reports_missing_path_without_guessing(tmp_path) -> None:
    totals = parse_deepseek_usage_export(tmp_path / "missing-export.zip")

    assert totals.status == "missing_export"
    assert totals.files == []


def test_deepseek_usage_export_rejects_symlinked_path(tmp_path) -> None:
    real_export = tmp_path / "amount.csv"
    real_export.write_text("model,amount,currency\nsynthetic,0.01,USD\n", encoding="utf-8")
    symlink = tmp_path / "linked.csv"
    symlink.symlink_to(real_export)

    totals = parse_deepseek_usage_export(symlink)

    assert totals.status == "unsafe_export_path"
    assert totals.files == []


def test_deepseek_usage_export_rejects_oversized_zip_csv_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_BILLING_EXPORT_MAX_BYTES", "1024")
    export = tmp_path / "usage.zip"
    with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("amount.csv", "model,amount\n" + ("x,1\n" * 4096))

    totals = parse_deepseek_usage_export(export)

    assert totals.status == "export_too_large"
    assert totals.files == []


def test_deepseek_usage_export_reports_invalid_zip_without_raising(tmp_path) -> None:
    export = tmp_path / "broken.zip"
    export.write_text("not a zip", encoding="utf-8")

    totals = parse_deepseek_usage_export(export)

    assert totals.status == "invalid_export"
    assert totals.files == []


def test_deepseek_usage_export_reports_empty_directory_without_guessing(tmp_path) -> None:
    export = tmp_path / "empty-export"
    export.mkdir()

    totals = parse_deepseek_usage_export(export)

    assert totals.status == "empty_export"
    assert totals.files == []


def test_deepseek_usage_export_reports_zip_without_csv_without_guessing(tmp_path) -> None:
    export = tmp_path / "usage.zip"
    with zipfile.ZipFile(export, "w") as archive:
        archive.writestr("readme.txt", "not usage data")

    totals = parse_deepseek_usage_export(export)

    assert totals.status == "empty_export"
    assert totals.files == []


@pytest.mark.asyncio
async def test_deepseek_usage_export_totals_rejects_usable_export_without_complete_manifest(
    tmp_path,
) -> None:
    class FailingImportStore:
        def record_import(self, **_kwargs):
            raise AssertionError("incomplete manifest must not be persisted")

    client = DeepSeekBillingClient(
        DeepSeekBillingConfig(usage_export_dir=str(tmp_path / "usage.zip")),
        import_store=FailingImportStore(),
    )
    client.parse_usage_export = lambda _path: DeepSeekUsageExportTotals(
        status="ok",
        manifest={"source_file_sha256": "abc123"},
    )

    totals = await client.get_usage_export_totals(billing_cycle="2026-06")

    assert totals.status == "invalid_export_manifest"
    assert totals.manifest["source_file_sha256"] == "abc123"


def test_deepseek_usage_export_keeps_header_manifest_for_unsupported_schema(tmp_path) -> None:
    export = tmp_path / "deepseek-export"
    export.mkdir()
    amount_file = export / "amount.csv"
    amount_file.write_text(
        "unknown_model_column,unknown_amount_column,currency\n"
        "real-row-value-should-not-leak,123.45,USD\n",
        encoding="utf-8",
    )

    totals = parse_deepseek_usage_export(export)

    assert totals.status == "unsupported_export_schema"
    assert totals.files == ["amount.csv"]
    assert totals.manifest["files"][0]["name"] == "amount.csv"
    assert totals.manifest["files"][0]["headers"] == [
        "unknown_model_column",
        "unknown_amount_column",
        "currency",
    ]
    assert totals.manifest["files"][0]["schema_hash"]
    assert "real-row-value-should-not-leak" not in str(totals.manifest)


def test_deepseek_usage_export_reads_nested_directory_csv_headers(tmp_path) -> None:
    export = tmp_path / "deepseek-export"
    nested = export / "nested"
    nested.mkdir(parents=True)
    amount_file = nested / "amount.csv"
    amount_file.write_text(
        "unknown_model_column,unknown_amount_column,currency\n"
        "real-row-value-should-not-leak,123.45,USD\n",
        encoding="utf-8",
    )

    totals = parse_deepseek_usage_export(export)

    assert totals.status == "unsupported_export_schema"
    assert totals.files == ["amount.csv"]
    assert totals.manifest["files"][0]["name"] == "amount.csv"
    assert totals.manifest["files"][0]["relative_path"] == "nested/amount.csv"
    assert totals.manifest["files"][0]["headers"] == [
        "unknown_model_column",
        "unknown_amount_column",
        "currency",
    ]
    assert "real-row-value-should-not-leak" not in str(totals.manifest)
