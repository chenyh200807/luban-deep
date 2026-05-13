#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.construction_grading.audit import evaluate_grading_supabase_audit


QUESTION_FIELDS = (
    "correct_answer",
    "analysis",
    "grading_rubric",
    "grading_keywords",
    "option_reasoning",
    "trap_type",
    "testing_focus",
    "source_meta",
    "structured_rules",
    "node_code",
    "options",
    "source_type",
    "exam_year",
    "difficulty",
    "stem",
    "question_stem",
    "original_id",
    "source_chunk_id",
)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _db_url(env_file: Path) -> str:
    values = _read_env(env_file)
    return os.getenv("DB_URL") or os.getenv("DATABASE_URL") or values.get("DB_URL") or values.get("DATABASE_URL") or ""


def _meaningful_expr(column: str) -> str:
    return (
        f"({column} is not null and nullif({column}::text,'') is not null "
        f"and {column}::text not in ('[]','{{}}','null','\"\"'))"
    )


def _fill_counts(cur: Any, table: str, fields: tuple[str, ...], where: str = "true") -> dict[str, Any]:
    selects = [f"count(*) filter (where {_meaningful_expr(field)}) as {field}__filled" for field in fields]
    cur.execute(f"select count(*) as total, {', '.join(selects)} from {table} where {where}")
    return dict(zip(["total", *[f"{field}__filled" for field in fields]], cur.fetchone()))


def _table_exists(cur: Any, table: str) -> bool:
    cur.execute(
        "select exists(select 1 from information_schema.tables where table_schema='public' and table_name=%s)",
        (table,),
    )
    return bool(cur.fetchone()[0])


def _table_count(cur: Any, table: str) -> int:
    cur.execute(f"select count(*) from {table}")
    return int(cur.fetchone()[0])


def build_report(env_file: Path) -> dict[str, Any]:
    try:
        import psycopg2
    except Exception as exc:  # pragma: no cover - environment guard
        raise RuntimeError("psycopg2 is required for direct read-only DB audit") from exc

    url = _db_url(env_file)
    if not url:
        raise RuntimeError("DB_URL or DATABASE_URL is required")

    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SET application_name='deeptutor_construction_grading_audit'")
    try:
        report: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "audit_mode": "read_only_meaningful_fill_empty_json_excluded",
            "questions_bank": {},
            "online_evidence_tables": {},
        }
        if not _table_exists(cur, "questions_bank"):
            raise RuntimeError("public.questions_bank is missing")

        report["questions_bank"] = {
            "exists": True,
            "count_total": _table_count(cur, "questions_bank"),
            "field_fill_all": _fill_counts(cur, "questions_bank", QUESTION_FIELDS),
            "field_fill_mcq": _fill_counts(
                cur,
                "questions_bank",
                QUESTION_FIELDS,
                "question_type in ('single_choice','multi_choice','multiple_choice','judgment','true_false')",
            ),
            "field_fill_case": _fill_counts(cur, "questions_bank", QUESTION_FIELDS, "question_type='case_study'"),
        }
        cur.execute("select question_type, count(*) as n from questions_bank group by question_type order by n desc")
        report["questions_bank"]["count_by_type"] = [
            {"question_type": row[0], "n": int(row[1])} for row in cur.fetchall()
        ]

        for table in (
            "kb_chunks",
            "standard_articles",
            "standard_chunks",
            "syllabus_tree",
            "question_intelligence",
            "question_summaries",
            "teaching_cards",
            "knowledge_graph_edges",
            "knowledge_cards",
        ):
            exists = _table_exists(cur, table)
            payload: dict[str, Any] = {"exists": exists}
            if exists:
                payload["count_total"] = _table_count(cur, table)
            report["online_evidence_tables"][table] = payload

        if report["online_evidence_tables"]["kb_chunks"]["exists"]:
            cur.execute("select source_type, count(*) as n from kb_chunks group by source_type order by n desc")
            report["online_evidence_tables"]["kb_chunks"]["source_types"] = [
                {"source_type": row[0], "n": int(row[1])} for row in cur.fetchall()
            ]
            metadata_fill: dict[str, int] = {}
            for key in ("exam_matrix", "structured_rules", "logic_chains", "key_parameters", "pitfalls", "source_meta", "taxonomy"):
                cur.execute("select count(*) from kb_chunks where metadata ? %s", (key,))
                metadata_fill[key] = int(cur.fetchone()[0])
            report["online_evidence_tables"]["kb_chunks"]["metadata_key_fill"] = metadata_fill

        if report["online_evidence_tables"]["standard_articles"]["exists"]:
            report["online_evidence_tables"]["standard_articles"]["field_fill"] = _fill_counts(
                cur,
                "standard_articles",
                (
                    "content",
                    "logic_constraints",
                    "common_violations",
                    "synthetic_qa",
                    "standard_code",
                    "article_code",
                    "key_parameters",
                    "taxonomy_node_codes",
                ),
            )

        if report["online_evidence_tables"]["syllabus_tree"]["exists"]:
            report["online_evidence_tables"]["syllabus_tree"]["field_fill"] = _fill_counts(
                cur,
                "syllabus_tree",
                ("node_code", "keywords", "level", "parent_code", "cognitive_type", "category"),
            )
        report["evaluation"] = evaluate_grading_supabase_audit(report)
        return report
    finally:
        cur.close()
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Supabase fields for construction grading skills.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output", default="tmp/supabase_grading_skill_field_audit.json")
    args = parser.parse_args(argv)

    report = build_report(Path(args.env_file))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["evaluation"], ensure_ascii=False, indent=2))
    return 0 if report["evaluation"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
