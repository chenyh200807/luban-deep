from __future__ import annotations

from pathlib import Path

from scripts.build_deepseek_usage_export_redacted_fixture import (
    build_redacted_fixture,
)


def test_build_redacted_fixture_preserves_headers_without_real_values(tmp_path) -> None:
    audit = tmp_path / "schema-audit.md"
    audit.write_text(
        """
# DeepSeek Usage Export Schema Audit

## Files And Headers

```json
{
  "files": [
    {
      "name": "amount.csv",
      "headers": [
        "model",
        "api_key_id",
        "amount",
        "currency",
        "input_cache_hit_tokens",
        "input_cache_miss_tokens",
        "output_tokens"
      ],
      "source_file_name": "real-export.zip",
      "source_file_sha256": "real-sha",
      "schema_hash": "schema-sha"
    }
  ]
}
```
""",
        encoding="utf-8",
    )
    output = tmp_path / "amount_redacted.csv"

    build_redacted_fixture(audit, output_path=output)

    content = output.read_text(encoding="utf-8")
    assert content.splitlines()[0] == (
        "model,api_key_id,amount,currency,input_cache_hit_tokens,"
        "input_cache_miss_tokens,output_tokens"
    )
    assert "real-export" not in content
    assert "real-sha" not in content
    assert "deepseek-v4-flash" not in content
    assert "sk-" not in content
    assert "synthetic" in content


def test_build_redacted_fixture_selects_amount_file_over_other_csvs(tmp_path) -> None:
    audit = tmp_path / "schema-audit.md"
    audit.write_text(
        """
```json
{
  "files": [
    {"name": "summary.csv", "headers": ["summary_only"]},
    {"name": "amount_details.csv", "headers": ["model", "api_key_id", "amount", "currency"]}
  ]
}
```
""",
        encoding="utf-8",
    )
    output = tmp_path / "amount_redacted.csv"

    build_redacted_fixture(audit, output_path=output)

    assert output.read_text(encoding="utf-8").splitlines()[0] == "model,api_key_id,amount,currency"


def test_build_redacted_fixture_selects_semantic_amount_file_when_name_is_generic(tmp_path) -> None:
    audit = tmp_path / "schema-audit.md"
    audit.write_text(
        """
```json
{
  "files": [
    {"name": "a_summary.csv", "headers": ["summary_only"]},
    {"name": "usage.csv", "headers": ["model_name", "api_key_fingerprint", "total_cost", "currency"]}
  ]
}
```
""",
        encoding="utf-8",
    )
    output = tmp_path / "amount_redacted.csv"

    build_redacted_fixture(audit, output_path=output)

    assert (
        output.read_text(encoding="utf-8").splitlines()[0]
        == "model_name,api_key_fingerprint,total_cost,currency"
    )


def test_build_redacted_fixture_rejects_schema_without_required_semantics(tmp_path) -> None:
    audit = tmp_path / "schema-audit.md"
    audit.write_text(
        """
```json
{
  "files": [
    {"name": "amount.csv", "headers": ["model", "amount", "currency"]}
  ]
}
```
""",
        encoding="utf-8",
    )

    try:
        build_redacted_fixture(audit, output_path=tmp_path / "amount_redacted.csv")
    except ValueError as exc:
        assert "api_key" in str(exc)
    else:
        raise AssertionError("schema without API-key semantics must be rejected")
