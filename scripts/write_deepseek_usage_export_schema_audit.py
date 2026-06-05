from __future__ import annotations

import argparse
from datetime import date as date_type
import json
from pathlib import Path

from scripts.audit_deepseek_usage_export import audit_export


DEFAULT_OUTPUT_PATH = Path("docs/qa/2026-06-03-deepseek-usage-export-schema-audit.md")


def _validate_audit_payload(payload: dict) -> None:
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("DeepSeek usage export audit found no CSV files")
    missing_headers = [
        str(item.get("name") or "<unknown>")
        for item in files
        if not isinstance(item, dict) or not item.get("headers")
    ]
    if missing_headers:
        raise ValueError(
            "DeepSeek usage export audit found CSV files without headers: "
            + ", ".join(missing_headers)
        )
    required_manifest_fields = ("source_file_name", "source_file_sha256", "schema_hash")
    missing_manifest = [
        str(item.get("name") or "<unknown>")
        for item in files
        if not isinstance(item, dict)
        or any(not item.get(field) for field in required_manifest_fields)
    ]
    if missing_manifest:
        raise ValueError(
            "DeepSeek usage export audit found CSV files without hash manifest: "
            + ", ".join(missing_manifest)
        )


def build_schema_audit_markdown(
    export_path: Path,
    *,
    date: str | None = None,
    max_bytes: int | None = None,
    billing_export_root: Path | None = None,
) -> str:
    payload = audit_export(
        export_path,
        max_bytes=max_bytes,
        billing_export_root=billing_export_root,
    )
    _validate_audit_payload(payload)
    audit_date = date or date_type.today().isoformat()
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return "\n".join(
        [
            "# DeepSeek Usage Export Schema Audit",
            "",
            f"Date: {audit_date}",
            "",
            "Input: official DeepSeek Usage export ZIP or extracted directory, not committed.",
            "",
            "## Files And Headers",
            "",
            "```json",
            payload_json,
            "```",
            "",
            "## Parser Decision",
            "",
            "- The amount CSV is the monthly monetary authority.",
            "- A redacted fixture must preserve real header names and use synthetic row values.",
            '- If the export does not expose model, API key, amount, and currency semantics, implementation stops and the BI response reports `official_usage.status = "unsupported_export_schema"`.',
            "",
        ]
    )


def write_schema_audit(
    export_path: Path,
    *,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    date: str | None = None,
    max_bytes: int | None = None,
    billing_export_root: Path | None = None,
) -> None:
    markdown = build_schema_audit_markdown(
        export_path,
        date=date,
        max_bytes=max_bytes,
        billing_export_root=billing_export_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("export_path", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--date", default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--max-bytes", type=int, default=None)
    args = parser.parse_args()

    write_schema_audit(
        args.export_path,
        output_path=args.output,
        date=args.date,
        max_bytes=args.max_bytes,
        billing_export_root=args.root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
