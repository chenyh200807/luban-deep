from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_AUDIT_PATH = Path("docs/qa/2026-06-03-deepseek-usage-export-schema-audit.md")
DEFAULT_OUTPUT_PATH = Path("tests/fixtures/deepseek_usage_export/amount_redacted.csv")


def _extract_json_payload(markdown: str) -> dict[str, Any]:
    match = re.search(r"```json\s*(\{.*?\})\s*```", markdown, flags=re.DOTALL)
    if not match:
        raise ValueError("schema audit markdown does not contain a json code block")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise ValueError("schema audit json block must be an object")
    return payload


def _has_semantic(headers: list[str], *needles: str) -> bool:
    normalized = [header.strip().lower() for header in headers]
    return any(all(needle in header for needle in needles) for header in normalized)


def _required_semantics(headers: list[str]) -> dict[str, bool]:
    return {
        "model": _has_semantic(headers, "model"),
        "api_key": _has_semantic(headers, "key"),
        "amount": _has_semantic(headers, "amount") or _has_semantic(headers, "cost"),
        "currency": _has_semantic(headers, "currency"),
    }


def _select_amount_headers(payload: dict[str, Any]) -> list[str]:
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("schema audit json block must contain files")
    candidates: list[tuple[int, str, list[str]]] = []
    first_named_amount_headers: list[str] | None = None
    for item in files:
        if not isinstance(item, dict):
            continue
        raw_headers = item.get("headers")
        if not isinstance(raw_headers, list) or not raw_headers:
            continue
        headers = [str(header or "").strip() for header in raw_headers]
        file_name = str(item.get("name") or "")
        if first_named_amount_headers is None and "amount" in file_name.lower():
            first_named_amount_headers = headers
        if all(_required_semantics(headers).values()):
            candidates.append((0 if "amount" in file_name.lower() else 1, file_name, headers))
    if candidates:
        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
        return candidates[0][2]
    if first_named_amount_headers is not None:
        _validate_required_semantics(first_named_amount_headers)
    raise ValueError("schema audit files do not contain headers with required amount semantics")


def _validate_required_semantics(headers: list[str]) -> None:
    required = _required_semantics(headers)
    missing = [name for name, present in required.items() if not present]
    if missing:
        raise ValueError(f"schema audit amount file missing required semantics: {', '.join(missing)}")


def _synthetic_value(header: str) -> str:
    normalized = header.strip().lower()
    if "currency" in normalized:
        return "USD"
    if "model" in normalized:
        return "synthetic_model"
    if "key" in normalized:
        return "synthetic_key"
    if "token" in normalized or "count" in normalized:
        return "1"
    if "amount" in normalized or "cost" in normalized or "price" in normalized:
        return "0.0001"
    if "time" in normalized or "date" in normalized:
        return "2026-06-03T00:00:00Z"
    return "synthetic"


def build_redacted_fixture(
    audit_path: Path = DEFAULT_AUDIT_PATH,
    *,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> None:
    payload = _extract_json_payload(audit_path.read_text(encoding="utf-8"))
    headers = _select_amount_headers(payload)
    _validate_required_semantics(headers)
    row = [_synthetic_value(header) for header in headers]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerow(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(buffer.getvalue(), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    build_redacted_fixture(args.audit, output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
