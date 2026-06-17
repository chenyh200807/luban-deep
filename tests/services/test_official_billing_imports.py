from __future__ import annotations

from deeptutor.services.observability.official_billing_imports import (
    OfficialBillingImportStore,
)


def test_official_billing_import_store_is_idempotent_by_provider_cycle_and_hash(
    tmp_path,
) -> None:
    store = OfficialBillingImportStore(db_path=tmp_path / "official_billing_imports.db")

    first = store.record_import(
        provider_name="deepseek",
        billing_cycle="2026-06",
        source_file_sha256="abc123",
        schema_hash="schema123",
        source_file_name="usage.zip",
        manifest={"files": ["amount.csv"]},
    )
    second = store.record_import(
        provider_name="deepseek",
        billing_cycle="2026-06",
        source_file_sha256="abc123",
        schema_hash="schema123",
        source_file_name="usage.zip",
        manifest={"files": ["amount.csv"]},
    )

    assert first.inserted is True
    assert second.inserted is False
    assert second.import_id == first.import_id
    assert (
        store.list_imports(provider_name="deepseek", billing_cycle="2026-06")[
            0
        ].source_file_sha256
        == "abc123"
    )


def test_official_billing_import_store_requires_schema_hash(tmp_path) -> None:
    store = OfficialBillingImportStore(db_path=tmp_path / "official_billing_imports.db")

    try:
        store.record_import(
            provider_name="deepseek",
            billing_cycle="2026-06",
            source_file_sha256="abc123",
            schema_hash="",
            source_file_name="usage.zip",
            manifest={"files": ["amount.csv"]},
        )
    except ValueError as exc:
        assert "schema_hash" in str(exc)
    else:
        raise AssertionError("official billing imports must require schema_hash")


def test_official_billing_import_store_requires_source_file_name(tmp_path) -> None:
    store = OfficialBillingImportStore(db_path=tmp_path / "official_billing_imports.db")

    try:
        store.record_import(
            provider_name="deepseek",
            billing_cycle="2026-06",
            source_file_sha256="abc123",
            schema_hash="schema123",
            source_file_name="",
            manifest={"files": ["amount.csv"]},
        )
    except ValueError as exc:
        assert "source_file_name" in str(exc)
    else:
        raise AssertionError("official billing imports must require source_file_name")


def test_official_billing_import_store_does_not_persist_raw_export_rows(tmp_path) -> None:
    store = OfficialBillingImportStore(db_path=tmp_path / "official_billing_imports.db")

    record = store.record_import(
        provider_name="deepseek",
        billing_cycle="2026-06",
        source_file_sha256="abc123",
        schema_hash="schema123",
        source_file_name="usage.zip",
        manifest={
            "files": [
                {
                    "name": "amount.csv",
                    "headers": ["model", "api_key_id"],
                    "rows": [{"api_key_id": "nested-real-key-should-not-persist"}],
                }
            ],
            "rows": [{"api_key_id": "real-key-should-not-persist"}],
        },
    )

    stored = store.list_imports(provider_name="deepseek", billing_cycle="2026-06")[0]
    assert record.inserted is True
    assert "rows" not in stored.manifest
    assert "real-key-should-not-persist" not in str(stored.manifest)
    assert "nested-real-key-should-not-persist" not in str(stored.manifest)
