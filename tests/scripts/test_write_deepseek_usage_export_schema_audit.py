from __future__ import annotations

from pathlib import Path

import scripts.write_deepseek_usage_export_schema_audit as schema_audit_writer
from scripts.write_deepseek_usage_export_schema_audit import (
    build_schema_audit_markdown,
    write_schema_audit,
)


def test_schema_audit_markdown_contains_headers_and_hashes_without_row_values(tmp_path) -> None:
    export = tmp_path / "amount.csv"
    export.write_text(
        "model,api_key_id,amount,currency\n"
        "deepseek-v4-flash,key-real-should-not-leak,123.45,USD\n",
        encoding="utf-8",
    )

    markdown = build_schema_audit_markdown(
        export,
        date="2026-06-03",
        max_bytes=1024,
    )

    assert "# DeepSeek Usage Export Schema Audit" in markdown
    assert "Date: 2026-06-03" in markdown
    assert '"headers": [' in markdown
    assert '"model"' in markdown
    assert '"source_file_sha256"' in markdown
    assert '"schema_hash"' in markdown
    assert "deepseek-v4-flash" not in markdown
    assert "key-real-should-not-leak" not in markdown
    assert "123.45" not in markdown


def test_write_schema_audit_writes_markdown_file(tmp_path) -> None:
    export = tmp_path / "amount.csv"
    export.write_text("model,amount,currency\nsynthetic,0.01,USD\n", encoding="utf-8")
    output = tmp_path / "schema-audit.md"

    write_schema_audit(
        export,
        output_path=output,
        date="2026-06-03",
        max_bytes=1024,
    )

    assert output.exists()
    assert "amount.csv" in output.read_text(encoding="utf-8")


def test_schema_audit_markdown_rejects_export_without_csv_files(tmp_path) -> None:
    export = tmp_path / "empty-export"
    export.mkdir()

    try:
        build_schema_audit_markdown(
            export,
            date="2026-06-03",
            max_bytes=1024,
        )
    except ValueError as exc:
        assert "no CSV files" in str(exc)
    else:
        raise AssertionError("schema audit must reject exports without CSV files")


def test_schema_audit_markdown_rejects_files_without_hash_manifest(tmp_path, monkeypatch) -> None:
    export = tmp_path / "amount.csv"
    export.write_text("model,amount,currency\nsynthetic,0.01,USD\n", encoding="utf-8")

    def fake_audit_export(*_args, **_kwargs):
        return {
            "files": [
                {
                    "name": "amount.csv",
                    "headers": ["model", "amount", "currency"],
                }
            ]
        }

    monkeypatch.setattr(schema_audit_writer, "audit_export", fake_audit_export)

    try:
        build_schema_audit_markdown(
            export,
            date="2026-06-03",
            max_bytes=1024,
        )
    except ValueError as exc:
        assert "hash manifest" in str(exc)
    else:
        raise AssertionError("schema audit must reject files without source/schema hashes")
