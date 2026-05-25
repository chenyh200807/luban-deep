#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from deeptutor.services.assessment import AssessmentBlueprintService, AssessmentBlueprintUnavailable
from deeptutor.services.assessment.blueprint_service import SupabaseAssessmentQuestionProvider
from deeptutor.services.assessment.topic_catalog import (
    build_topic_assessment_blueprint,
    classify_topic_form_count,
    get_topic_testset_catalog,
    get_topic_testset_spec,
)
from deeptutor.services.source_compiler.psql import PsqlRunner, assert_target_database_is_main


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(_repo_root() / ".env")


def _db_url() -> str:
    return os.getenv("DB_URL") or os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or ""


def _assert_target_database() -> None:
    db_url = _db_url()
    if not db_url:
        raise SystemExit("Missing DB_URL or DATABASE_URL for assessment_forms write guard")
    runner = PsqlRunner(db_url, timeout=30)
    assert_target_database_is_main(runner)


def _topic_ids(selected: list[str]) -> list[str]:
    if selected:
        return [get_topic_testset_spec(topic_id).topic_id for topic_id in selected]
    return [spec.topic_id for spec in get_topic_testset_catalog()]


def _prewarm_topic(topic_id: str, *, persist: bool) -> dict[str, Any]:
    blueprint = build_topic_assessment_blueprint(topic_id)
    service = AssessmentBlueprintService(
        blueprint=blueprint,
        provider=SupabaseAssessmentQuestionProvider(),
    )
    result = service.generate_and_persist_forms() if persist else service.prewarm_forms()
    status = classify_topic_form_count(int(result.get("form_count") or 0))
    return {
        "topic_id": topic_id,
        "blueprint_version": result.get("blueprint_version"),
        "status": status,
        "form_count": int(result.get("form_count") or 0),
        "form_ids": result.get("form_ids") or [],
        "form_source": result.get("form_source") or "",
        "fallback_used": bool(result.get("fallback_used")),
        "question_bank_size": int(result.get("question_bank_size") or 0),
        "persisted": bool(result.get("persisted")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and optionally persist P0A+ topic TestSet forms.")
    parser.add_argument("--topic-id", action="append", default=[], help="Topic id to process. Repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Build/read forms without writing assessment_forms.")
    parser.add_argument("--persist", action="store_true", help="Persist active forms into assessment_forms.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--out-json", default="", help="Write audit payload JSON to this path.")
    parser.add_argument("--out-md", default="", help="Write audit summary Markdown to this path.")
    parser.add_argument("--reviewed-json", default="", help="Reviewed dry-run JSON required before --persist.")
    parser.add_argument("--require-target-main", action="store_true", help="Require DeepTutor main DB guard before --persist.")
    parser.add_argument("--idempotency-key", default="", help="Required operator idempotency key for --persist.")
    args = parser.parse_args()

    if args.dry_run and args.persist:
        raise SystemExit("--dry-run and --persist are mutually exclusive")
    if not args.dry_run and not args.persist:
        args.dry_run = True
    if args.persist:
        if not args.reviewed_json:
            raise SystemExit("reviewed_json_required_for_persist")
        if not args.require_target_main:
            raise SystemExit("target_database_guard_required")
        if not args.idempotency_key:
            raise SystemExit("idempotency_key_required_for_persist")

    _load_env()
    if args.persist:
        _assert_target_database()

    rows: list[dict[str, Any]] = []
    for topic_id in _topic_ids(args.topic_id):
        try:
            row = _prewarm_topic(topic_id, persist=bool(args.persist))
        except AssessmentBlueprintUnavailable as exc:
            row = {
                "topic_id": topic_id,
                "blueprint_version": f"topic_{topic_id}_v1",
                "status": "authoring_needed",
                "form_count": 0,
                "form_ids": [],
                "form_source": "",
                "fallback_used": False,
                "question_bank_size": 0,
                "persisted": False,
                "error": str(exc),
            }
        except Exception as exc:
            row = {
                "topic_id": topic_id,
                "blueprint_version": f"topic_{topic_id}_v1",
                "status": "authoring_needed",
                "form_count": 0,
                "form_ids": [],
                "form_source": "",
                "fallback_used": False,
                "question_bank_size": 0,
                "persisted": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
        if not args.json:
            _print_row(row)

    payload = {"persist": bool(args.persist), "topics": rows}
    if args.out_json:
        _write_json(Path(args.out_json), payload)
    if args.out_md:
        _write_md(Path(args.out_md), payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    return 0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Assessment Topic Catalog Form Bank Audit",
        "",
        "| topic_id | status | form_count | persisted | source |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in payload.get("topics") or []:
        lines.append(
            "| {topic_id} | {status} | {form_count} | {persisted} | {form_source} |".format(
                topic_id=row.get("topic_id", ""),
                status=row.get("status", ""),
                form_count=row.get("form_count", 0),
                persisted=row.get("persisted", False),
                form_source=row.get("form_source", ""),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_row(row: dict[str, Any]) -> None:
    suffix = f" error={row['error']}" if row.get("error") else ""
    print(
        "topic={topic_id} status={status} forms={form_count} persisted={persisted} "
        "source={form_source}{suffix}".format(**row, suffix=suffix),
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
