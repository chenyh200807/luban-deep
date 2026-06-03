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
