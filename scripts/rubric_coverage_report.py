#!/usr/bin/env python
"""Read-only rubric coverage audit for Phase -1.A.1 of the Luban learning-state plan.

Queries `public.questions_bank`, `public.rubrics`, `public.question_intelligence` and
`public.knowledge_question_links` to measure:

- raw_rubric_coverage: share of items with non-empty grading_rubric
- legacy_signal_coverage: share with non-empty grading_keywords / structured_rules / correct_answer
- map_eligible_coverage: share whose normalized projection yields >= 2 distinct scoring points
- node_code distribution and authoring backlog

Writes a markdown report to docs/qa/<date>-rubric-coverage-baseline.md.

Usage:
    python scripts/rubric_coverage_report.py \
        --env /Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env \
        --out docs/qa/2026-05-22-rubric-coverage-baseline.md

The script performs no writes against Supabase.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _psql(db_url: str, sql: str) -> list[list[str]]:
    cmd = ["psql", db_url, "-tAc", sql, "-F", "\t"]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr.strip()}\nSQL: {sql[:160]}")
    rows: list[list[str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("\t"))
    return rows


def _scalar(db_url: str, sql: str) -> str:
    rows = _psql(db_url, sql)
    if not rows:
        return ""
    return rows[0][0] if rows[0] else ""


def collect(db_url: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}

    facts["totals"] = _psql(
        db_url,
        """
        SELECT
          COUNT(*),
          COUNT(*) FILTER (WHERE grading_rubric IS NOT NULL
                          AND grading_rubric::text NOT IN ('null','{}','[]')),
          COUNT(*) FILTER (WHERE source_type='REAL_EXAM')
        FROM public.questions_bank;
        """,
    )[0]

    facts["by_question_type"] = _psql(
        db_url,
        """
        SELECT
          COALESCE(question_type,'<null>') AS qt,
          COUNT(*) AS n,
          COUNT(*) FILTER (WHERE grading_rubric IS NOT NULL
                          AND grading_rubric::text NOT IN ('null','{}','[]')) AS raw_rubric,
          COUNT(*) FILTER (WHERE jsonb_typeof(grading_keywords)='array'
                          AND jsonb_array_length(grading_keywords) > 0) AS gk_nonempty,
          COUNT(*) FILTER (WHERE jsonb_typeof(structured_rules)='array'
                          AND jsonb_array_length(structured_rules) > 0) AS sr_nonempty,
          COUNT(*) FILTER (WHERE analysis IS NOT NULL AND LENGTH(TRIM(analysis)) > 0) AS analysis_nonempty,
          COUNT(*) FILTER (WHERE correct_answer IS NOT NULL
                          AND correct_answer::text NOT IN ('null','{}','[]','""')) AS correct_answer_nonempty,
          COUNT(*) FILTER (WHERE node_code IS NOT NULL AND TRIM(node_code) <> '') AS node_code_present,
          COUNT(*) FILTER (WHERE cited_standard_codes IS NOT NULL
                          AND array_length(cited_standard_codes, 1) > 0) AS cited_codes_present
        FROM public.questions_bank
        GROUP BY question_type
        ORDER BY n DESC;
        """,
    )

    facts["map_eligible_case"] = _psql(
        db_url,
        """
        WITH case_rows AS (
          SELECT
            id,
            question_type,
            jsonb_typeof(grading_keywords)='array' AS gk_arr,
            (CASE WHEN jsonb_typeof(grading_keywords)='array'
                  THEN jsonb_array_length(grading_keywords) ELSE 0 END) AS gk_n,
            (CASE WHEN jsonb_typeof(structured_rules)='array'
                  THEN jsonb_array_length(structured_rules) ELSE 0 END) AS sr_n
          FROM public.questions_bank
          WHERE question_type='case_study'
        )
        SELECT
          COUNT(*) AS case_total,
          COUNT(*) FILTER (WHERE sr_n >= 2) AS structured_rules_ge2,
          COUNT(*) FILTER (WHERE gk_n >= 2) AS grading_keywords_ge2,
          COUNT(*) FILTER (WHERE sr_n >= 2 OR gk_n >= 2) AS map_eligible_any,
          COUNT(*) FILTER (WHERE sr_n >= 2 AND gk_n >= 2) AS both_signals
        FROM case_rows;
        """,
    )[0]

    facts["map_eligible_by_year"] = _psql(
        db_url,
        """
        WITH case_rows AS (
          SELECT
            id,
            exam_year,
            source_type,
            (CASE WHEN jsonb_typeof(grading_keywords)='array'
                  THEN jsonb_array_length(grading_keywords) ELSE 0 END) AS gk_n,
            (CASE WHEN jsonb_typeof(structured_rules)='array'
                  THEN jsonb_array_length(structured_rules) ELSE 0 END) AS sr_n
          FROM public.questions_bank
          WHERE question_type='case_study'
        )
        SELECT
          COALESCE(exam_year::text, '<null>') AS yr,
          COUNT(*) AS n,
          COUNT(*) FILTER (WHERE sr_n >= 2 OR gk_n >= 2) AS map_eligible
        FROM case_rows
        GROUP BY exam_year
        ORDER BY exam_year DESC NULLS LAST;
        """,
    )

    facts["map_eligible_by_node_prefix"] = _psql(
        db_url,
        """
        WITH case_rows AS (
          SELECT
            id,
            SUBSTRING(node_code FROM 1 FOR 7) AS prefix,
            (CASE WHEN jsonb_typeof(grading_keywords)='array'
                  THEN jsonb_array_length(grading_keywords) ELSE 0 END) AS gk_n,
            (CASE WHEN jsonb_typeof(structured_rules)='array'
                  THEN jsonb_array_length(structured_rules) ELSE 0 END) AS sr_n
          FROM public.questions_bank
          WHERE question_type='case_study' AND node_code IS NOT NULL
        )
        SELECT
          prefix,
          COUNT(*) AS n,
          COUNT(*) FILTER (WHERE sr_n >= 2 OR gk_n >= 2) AS map_eligible
        FROM case_rows
        GROUP BY prefix
        ORDER BY n DESC
        LIMIT 20;
        """,
    )

    facts["structured_rule_types"] = _psql(
        db_url,
        """
        SELECT rule->>'type' AS rule_type, COUNT(*) AS n
        FROM public.questions_bank,
             LATERAL jsonb_array_elements(structured_rules) AS rule
        WHERE jsonb_typeof(structured_rules)='array'
        GROUP BY rule_type
        ORDER BY n DESC
        LIMIT 15;
        """,
    )

    facts["adjacent_tables"] = {
        "rubrics_rows": _scalar(db_url, "SELECT COUNT(*) FROM public.rubrics;"),
        "rubrics_distinct_questions": _scalar(
            db_url, "SELECT COUNT(DISTINCT question_id) FROM public.rubrics;"
        ),
        "question_intelligence_rows": _scalar(
            db_url, "SELECT COUNT(*) FROM public.question_intelligence;"
        ),
        "question_intelligence_success": _scalar(
            db_url,
            "SELECT COUNT(*) FROM public.question_intelligence WHERE compile_status='success';",
        ),
        "knowledge_question_links_rows": _scalar(
            db_url, "SELECT COUNT(*) FROM public.knowledge_question_links;"
        ),
        "knowledge_question_links_questions": _scalar(
            db_url,
            "SELECT COUNT(DISTINCT question_id) FROM public.knowledge_question_links;",
        ),
    }

    facts["authoring_backlog_top"] = _psql(
        db_url,
        """
        SELECT
          id, node_code, exam_year, source_type,
          ROUND(COALESCE(error_rate, 0)::numeric, 3) AS error_rate,
          REGEXP_REPLACE(LEFT(COALESCE(question_stem, stem, ''), 80), E'[\\n\\r\\t]+', ' ', 'g') AS stem_preview
        FROM public.questions_bank
        WHERE question_type='case_study'
          AND (
            grading_keywords IS NULL
            OR jsonb_typeof(grading_keywords)<>'array'
            OR jsonb_array_length(grading_keywords) < 2
          )
          AND (
            structured_rules IS NULL
            OR jsonb_typeof(structured_rules)<>'array'
            OR jsonb_array_length(structured_rules) < 2
          )
        ORDER BY
          -- Audit insight (2026-05-22): REAL_EXAM 2015-2021 are 0% map-eligible.
          -- 2017-2021 already have node_code and need rubric authoring only.
          -- 2015-2016 need classification/content recovery first, so keep them as
          -- a separate queue after the faster 2017-2021 authoring lane.
          (CASE WHEN source_type='REAL_EXAM' THEN 0 ELSE 1 END),
          (CASE WHEN source_type='REAL_EXAM' AND exam_year BETWEEN 2017 AND 2021 THEN 0 ELSE 1 END),
          exam_year DESC NULLS LAST,
          COALESCE(error_rate, 0) DESC
        LIMIT 30;
        """,
    )

    facts["normalization_preview"] = _psql(
        db_url,
        """
        SELECT
          id,
          node_code,
          jsonb_array_length(grading_keywords) AS gk_n,
          jsonb_array_length(structured_rules) AS sr_n,
          REGEXP_REPLACE(LEFT(COALESCE(question_stem, stem, ''), 70), E'[\\n\\r\\t]+', ' ', 'g') AS stem_preview
        FROM public.questions_bank
        WHERE question_type='case_study'
          AND jsonb_typeof(grading_keywords)='array'
          AND jsonb_array_length(grading_keywords) >= 3
          AND jsonb_typeof(structured_rules)='array'
          AND jsonb_array_length(structured_rules) >= 2
        ORDER BY id
        LIMIT 20;
        """,
    )

    return facts


def _pct(num: str | int, denom: str | int) -> str:
    try:
        n = int(num)
        d = int(denom)
    except (TypeError, ValueError):
        return "—"
    if d == 0:
        return "—"
    return f"{(n / d) * 100:.1f}%"


def render(facts: dict[str, Any], host: str) -> str:
    today = _dt.date.today().isoformat()
    total_rows, raw_rubric, real_exam = facts["totals"]
    case_total, sr_ge2, gk_ge2, map_any, both = facts["map_eligible_case"]

    lines: list[str] = []
    lines.append("# Rubric Coverage Baseline")
    lines.append("")
    lines.append(f"Generated: {today}")
    lines.append(f"Source: Supabase host `{host}`, table `public.questions_bank`.")
    lines.append("Audit is read-only; no writes performed.")
    lines.append("")
    lines.append("## Top-level totals")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Total questions_bank rows | {total_rows} |")
    lines.append(f"| Rows with non-empty grading_rubric | {raw_rubric} ({_pct(raw_rubric, total_rows)}) |")
    lines.append(f"| Rows with source_type=REAL_EXAM | {real_exam} ({_pct(real_exam, total_rows)}) |")
    lines.append("")

    lines.append("## Coverage by question_type")
    lines.append("")
    lines.append(
        "| question_type | n | grading_rubric | grading_keywords nonempty | "
        "structured_rules nonempty | analysis nonempty | correct_answer nonempty | "
        "node_code present | cited_standard_codes present |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in facts["by_question_type"]:
        qt, n, raw_r, gk_ne, sr_ne, an_ne, ca_ne, nc, cc = row
        lines.append(
            f"| {qt} | {n} | {raw_r} ({_pct(raw_r, n)}) | {gk_ne} ({_pct(gk_ne, n)}) | "
            f"{sr_ne} ({_pct(sr_ne, n)}) | {an_ne} ({_pct(an_ne, n)}) | {ca_ne} ({_pct(ca_ne, n)}) | "
            f"{nc} ({_pct(nc, n)}) | {cc} ({_pct(cc, n)}) |"
        )
    lines.append("")

    lines.append("## Map-eligibility on case_study items")
    lines.append("")
    lines.append("Map-eligible = normalized projection yields >= 2 distinct scoring points.")
    lines.append("Today we use the union of `structured_rules` >= 2 entries OR `grading_keywords` >= 2 entries.")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| case_study total | {case_total} |")
    lines.append(f"| structured_rules >= 2 | {sr_ge2} ({_pct(sr_ge2, case_total)}) |")
    lines.append(f"| grading_keywords >= 2 | {gk_ge2} ({_pct(gk_ge2, case_total)}) |")
    lines.append(f"| **map_eligible (union)** | **{map_any} ({_pct(map_any, case_total)})** |")
    lines.append(f"| both signals (intersect) | {both} ({_pct(both, case_total)}) |")
    lines.append("")

    lines.append("### Map-eligibility by exam_year (case_study)")
    lines.append("")
    lines.append("| exam_year | n | map_eligible | share |")
    lines.append("| --- | --- | --- | --- |")
    for yr, n, me in facts["map_eligible_by_year"]:
        lines.append(f"| {yr} | {n} | {me} | {_pct(me, n)} |")
    lines.append("")

    lines.append("### Map-eligibility by node_code prefix (top 20, case_study)")
    lines.append("")
    lines.append("| node_code prefix | n | map_eligible | share |")
    lines.append("| --- | --- | --- | --- |")
    for prefix, n, me in facts["map_eligible_by_node_prefix"]:
        lines.append(f"| {prefix} | {n} | {me} | {_pct(me, n)} |")
    lines.append("")

    lines.append("## structured_rules.type distribution")
    lines.append("")
    lines.append("These rule types inform the ability_dimension mapping in the normalization spec.")
    lines.append("")
    lines.append("| rule type | count |")
    lines.append("| --- | --- |")
    for rule_type, n in facts["structured_rule_types"]:
        lines.append(f"| {rule_type or '<null>'} | {n} |")
    lines.append("")

    adj = facts["adjacent_tables"]
    lines.append("## Adjacent tables")
    lines.append("")
    lines.append("| Table | Rows | Distinct keys |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| public.rubrics | {adj['rubrics_rows']} | {adj['rubrics_distinct_questions']} distinct questions |"
    )
    lines.append(
        f"| public.question_intelligence | {adj['question_intelligence_rows']} | "
        f"{adj['question_intelligence_success']} compile_status=success |"
    )
    lines.append(
        f"| public.knowledge_question_links | {adj['knowledge_question_links_rows']} | "
        f"{adj['knowledge_question_links_questions']} distinct questions linked |"
    )
    lines.append("")

    lines.append("## Authoring backlog — top 30 case_study items needing rubric")
    lines.append("")
    lines.append(
        "Priority: REAL_EXAM 2017-2021 first (node_code present; rubric authoring only), "
        "then 2015-2016 classification/content recovery, then high error_rate."
    )
    lines.append("")
    lines.append("| id | node_code | exam_year | source_type | error_rate | stem preview |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in facts["authoring_backlog_top"]:
        id_, nc, yr, st, er, stem = row
        lines.append(f"| {id_} | {nc} | {yr} | {st} | {er} | {stem.replace('|', '/')} |")
    lines.append("")

    preview_count = len(facts["normalization_preview"])
    lines.append(f"## Normalization preview — {preview_count} high-signal case items")
    lines.append("")
    lines.append("These items already have >= 3 keywords AND >= 2 structured rules; they are the")
    lines.append("available high-signal candidates for the教研 sign-off review described in Phase -1.A.1.")
    lines.append("A second preview must cover keyword-only items because they dominate the current map-eligible set.")
    lines.append("")
    lines.append("| id | node_code | grading_keywords | structured_rules | stem preview |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in facts["normalization_preview"]:
        id_, nc, gk_n, sr_n, stem = row
        lines.append(f"| {id_} | {nc} | {gk_n} | {sr_n} | {stem.replace('|', '/')} |")
    lines.append("")

    lines.append("## Phase -1.A gate readout")
    lines.append("")
    map_share = (int(map_any) / int(case_total)) if int(case_total) else 0.0
    gate_status = "PASS (>= 0.70)" if map_share >= 0.70 else "FAIL — promote scoring_point_map UI only with rubric_pending empty state"
    lines.append(f"- Measured map_eligible_coverage on case_study: **{map_share*100:.1f}%**")
    lines.append(f"- Promotion gate (>= 70%): **{gate_status}**")
    lines.append("- LLM grounding discipline: not measured in this report; see Phase -1.A.3 grader_disagreement audit.")
    lines.append("")
    lines.append("---")
    lines.append("Generated by `scripts/rubric_coverage_report.py` (read-only).")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        default="/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env",
        help="Path to .env file containing DB_URL or KBV5_DB_URL",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Postgres connection string (overrides --env)",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "qa" / f"{_dt.date.today().isoformat()}-rubric-coverage-baseline.md"),
        help="Markdown output path",
    )
    args = parser.parse_args()

    db_url = args.db_url
    if not db_url:
        env_path = Path(args.env)
        env = _read_env(env_path)
        # DB_URL first because the production questions_bank lives in the legacy
        # Supabase project; KBV5_DB_URL points at the V5 project which currently
        # has no questions_bank table.
        db_url = env.get("DB_URL") or env.get("KBV5_DB_URL") or env.get("DATABASE_URL", "")
    if not db_url:
        print("error: no DB_URL resolved", file=sys.stderr)
        return 2

    host = "<unknown>"
    if "@" in db_url:
        try:
            host = db_url.split("@", 1)[1].split("/", 1)[0]
        except Exception:
            host = "<parse_error>"

    print(f"Connecting to {host}...", file=sys.stderr)
    facts = collect(db_url)
    report = render(facts, host=host)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
