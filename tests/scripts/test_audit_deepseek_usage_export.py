from __future__ import annotations

import zipfile

import pytest

from scripts.audit_deepseek_usage_export import audit_export


def test_audit_export_reports_headers_and_hash_without_row_values(tmp_path) -> None:
    export = tmp_path / "usage.csv"
    export.write_text(
        "model,api_key_id,amount,currency\n"
        "deepseek-v4-flash,key-real,123.45,USD\n",
        encoding="utf-8",
    )

    payload = audit_export(export, max_bytes=1024)

    assert payload["files"][0]["name"] == "usage.csv"
    assert payload["files"][0]["headers"] == ["model", "api_key_id", "amount", "currency"]
    assert payload["files"][0]["source_file_sha256"]
    assert payload["files"][0]["schema_hash"]
    assert "deepseek-v4-flash" not in str(payload)
    assert "123.45" not in str(payload)


def test_audit_export_reads_zip_csv_headers_without_extracting(tmp_path) -> None:
    export = tmp_path / "usage.zip"
    with zipfile.ZipFile(export, "w") as archive:
        archive.writestr("nested/amount.csv", "model,amount,currency\nsynthetic,0.01,USD\n")

    payload = audit_export(export, max_bytes=2048)

    assert payload["files"] == [
        {
            "name": "amount.csv",
            "headers": ["model", "amount", "currency"],
            "source_file_name": "usage.zip",
            "source_file_sha256": payload["files"][0]["source_file_sha256"],
            "schema_hash": payload["files"][0]["schema_hash"],
        }
    ]
    assert not (tmp_path / "nested").exists()


def test_audit_export_rejects_oversized_file(tmp_path) -> None:
    export = tmp_path / "usage.csv"
    export.write_text("model,amount\nx,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds"):
        audit_export(export, max_bytes=4)
