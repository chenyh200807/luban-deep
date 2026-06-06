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
            "relative_path": "nested/amount.csv",
            "headers": ["model", "amount", "currency"],
            "source_file_name": "usage.zip",
            "source_file_sha256": payload["files"][0]["source_file_sha256"],
            "schema_hash": payload["files"][0]["schema_hash"],
        }
    ]
    assert not (tmp_path / "nested").exists()


def test_audit_export_reads_nested_directory_csv_headers(tmp_path) -> None:
    export = tmp_path / "deepseek-export"
    nested = export / "nested"
    nested.mkdir(parents=True)
    (nested / "amount.csv").write_text(
        "model,api_key_id,amount,currency\n"
        "deepseek-v4-flash,real-key,123.45,USD\n",
        encoding="utf-8",
    )

    payload = audit_export(export, max_bytes=2048)

    assert payload["files"][0]["name"] == "amount.csv"
    assert payload["files"][0]["relative_path"] == "nested/amount.csv"
    assert payload["files"][0]["headers"] == ["model", "api_key_id", "amount", "currency"]
    assert "deepseek-v4-flash" not in str(payload)
    assert "real-key" not in str(payload)


def test_audit_export_rejects_oversized_zip_csv_entry(tmp_path) -> None:
    export = tmp_path / "usage.zip"
    with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("amount.csv", "model,amount\n" + ("x,1\n" * 4096))

    assert export.stat().st_size < 1024
    with pytest.raises(ValueError, match="entry exceeds"):
        audit_export(export, max_bytes=1024)


def test_audit_export_rejects_oversized_file(tmp_path) -> None:
    export = tmp_path / "usage.csv"
    export.write_text("model,amount\nx,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds"):
        audit_export(export, max_bytes=4)


def test_audit_export_rejects_missing_path(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        audit_export(tmp_path / "missing.zip", max_bytes=1024)


def test_audit_export_rejects_symlink_without_root(tmp_path) -> None:
    real_export = tmp_path / "usage.csv"
    real_export.write_text("model,amount\nx,1\n", encoding="utf-8")
    symlink = tmp_path / "linked.csv"
    symlink.symlink_to(real_export)

    with pytest.raises(ValueError, match="symlinked billing export"):
        audit_export(symlink, max_bytes=1024)


def test_audit_export_rejects_directory_csv_symlink_outside_root(tmp_path) -> None:
    root = tmp_path / "billing-root"
    root.mkdir()
    export_dir = root / "deepseek-export"
    export_dir.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("model,amount\nx,1\n", encoding="utf-8")
    (export_dir / "amount.csv").symlink_to(outside)

    with pytest.raises(ValueError, match="outside root"):
        audit_export(export_dir, max_bytes=1024, billing_export_root=root)
