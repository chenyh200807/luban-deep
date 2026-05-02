#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import error, parse, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.assessment.blueprint import AssessmentSection, get_assessment_blueprint
from deeptutor.services.assessment.coverage import evaluate_blueprint_coverage


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'").strip('"')
        values[key.strip()] = value
    return values


def _env_value(env_file: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = os.getenv(name) or env_file.get(name)
        if value:
            return value
    return ""


def _supabase_config(env_file_path: Path) -> tuple[str, str]:
    env_file = _read_env_file(env_file_path)
    url = _env_value(
        env_file,
        ("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL", "PUBLIC_SUPABASE_URL"),
    ).rstrip("/")
    key = _env_value(
        env_file,
        (
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_SERVICE_KEY",
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        ),
    )
    if not url or not key:
        raise RuntimeError(
            "Missing Supabase config. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, "
            "or pass --fixture for offline audit."
        )
    return url, key


def _postgrest_count(base_url: str, api_key: str, filters: dict[str, str]) -> int:
    query = {"select": "id", **filters}
    encoded = parse.urlencode(query)
    req = request.Request(
        f"{base_url}/rest/v1/questions_bank?{encoded}",
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Prefer": "count=exact",
            "Range": "0-0",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            content_range = response.headers.get("Content-Range", "")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase count query failed: HTTP {exc.code} {body}") from exc

    try:
        return int(content_range.rsplit("/", 1)[1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Supabase count query returned invalid Content-Range: {content_range!r}") from exc


def _in_filter(values: tuple[str, ...]) -> str:
    unique_values = tuple(dict.fromkeys(value for value in values if value))
    return f"in.({','.join(unique_values)})"


def _section_filters(section: AssessmentSection) -> dict[str, str]:
    filters: dict[str, str] = {}
    question_types = section.question_types + section.fallback_question_types
    if question_types:
        filters["question_type"] = _in_filter(question_types)
    if section.source_types and section.source_types != ("PROFILE_PROBE",):
        filters["source_type"] = _in_filter(section.source_types)
    return filters


def _profile_section_row(section: AssessmentSection) -> dict[str, Any]:
    required_candidates = section.count * section.minimum_multiplier
    return {
        "section_id": section.id,
        "candidate_count": required_candidates,
        "with_question_id": required_candidates,
        "with_source_chunk_id": required_candidates,
        "renderable_count": required_candidates,
        "calculation_count": 0,
        "structured_judgment_count": required_candidates,
    }


def _fetch_supabase_rows(version: str, env_file_path: Path) -> list[dict[str, Any]]:
    blueprint = get_assessment_blueprint(version)
    base_url, api_key = _supabase_config(env_file_path)
    rows: list[dict[str, Any]] = []

    for section in blueprint.sections:
        if not section.scored:
            rows.append(_profile_section_row(section))
            continue

        filters = _section_filters(section)
        candidate_count = _postgrest_count(base_url, api_key, filters)
        with_source_chunk_id = _postgrest_count(
            base_url,
            api_key,
            {**filters, "source_chunk_id": "not.is.null"},
        )
        calculation_count = _postgrest_count(
            base_url,
            api_key,
            {**{key: value for key, value in filters.items() if key != "question_type"}, "question_type": "eq.calculation"},
        )
        structured_judgment_count = _postgrest_count(
            base_url,
            api_key,
            {**{key: value for key, value in filters.items() if key != "question_type"}, "question_type": "in.(structured_judgment,case_study)"},
        )
        rows.append(
            {
                "section_id": section.id,
                "candidate_count": candidate_count,
                "with_question_id": candidate_count,
                "with_source_chunk_id": with_source_chunk_id,
                "renderable_count": candidate_count,
                "calculation_count": calculation_count,
                "structured_judgment_count": structured_judgment_count,
            }
        )

    return rows


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("rows")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise RuntimeError("Fixture must be a JSON list or an object with a 'rows' list.")
    return rows


def _write_report(report: dict[str, Any], output_path: Path | None) -> None:
    content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        sys.stdout.write(content)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit assessment blueprint coverage.")
    parser.add_argument("--blueprint", default="diagnostic_v1")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--fixture", help="Offline fixture JSON with normalized section rows.")
    parser.add_argument("--output", help="Path to write JSON report. Prints to stdout when omitted.")
    args = parser.parse_args(argv)

    blueprint = get_assessment_blueprint(args.blueprint)
    rows = _load_fixture(Path(args.fixture)) if args.fixture else _fetch_supabase_rows(args.blueprint, Path(args.env_file))
    report = evaluate_blueprint_coverage(blueprint, rows)
    _write_report(report, Path(args.output) if args.output else None)
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
