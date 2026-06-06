# DeepSeek Usage Export Schema Audit

Date: 2026-06-03

Status: blocked pending a real DeepSeek Usage export ZIP or extracted directory.

Current local evidence on 2026-06-03: no real DeepSeek official Usage export was found under Downloads, Desktop, Documents, or Developer. Search results only included repo scripts/tests/fixtures/docs and unrelated personal bill files, so this document must remain blocked.

## Files And Headers

Run locally after downloading the official export:

```bash
python scripts/audit_deepseek_usage_export.py "$DEEPSEEK_USAGE_EXPORT_PATH" --json > /tmp/deepseek_usage_export_headers.json
```

Paste the JSON output here only after confirming it contains headers and hashes, not row values.

Expected audit JSON fields per CSV entry:

- `name`
- `relative_path`
- `headers`
- `source_file_name`
- `source_file_sha256`
- `schema_hash`

Do not paste raw rows, API keys, prompts, completions, user identifiers, or provider request bodies into this document.

## Parser Decision

- The amount CSV is the monthly monetary authority.
- A redacted fixture must preserve real header names and use synthetic row values.
- If the export does not expose model, API key, amount, and currency semantics, implementation stops and the BI response reports `official_usage.status = "unsupported_export_schema"`.
