#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from deeptutor.services.source_compiler.psql import PsqlRunner, assert_target_database_is_main


class ConfigError(RuntimeError):
    pass


def _run_dir(run_id: str) -> Path:
    path = Path("artifacts") / "knowledge_compiler" / "2026" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_env_file(path: str) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        raise ConfigError(f"env file not found: {env_path}")
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _db_url(env_file: str = "") -> str:
    values = _read_env_file(env_file) if env_file else os.environ
    value = values.get("DB_URL") or values.get("DATABASE_URL")
    if not value:
        raise ConfigError("Missing DB_URL or DATABASE_URL. DB_URL or DATABASE_URL is required for Supabase coverage dry-run.")
    return value


def _metrics(runner: PsqlRunner) -> list[dict[str, str]]:
    queries = {
        "questions_bank.rows": "SELECT count(*) FROM public.questions_bank",
        "questions_bank.grading_rubric_present": "SELECT count(*) FROM public.questions_bank WHERE grading_rubric IS NOT NULL",
        "questions_bank.option_reasoning_present": "SELECT count(*) FROM public.questions_bank WHERE option_reasoning IS NOT NULL AND option_reasoning <> '{}'::jsonb",
        "questions_bank.cited_standard_codes_present": "SELECT count(*) FROM public.questions_bank WHERE cited_standard_codes IS NOT NULL",
        "standard_articles.rows": "SELECT count(*) FROM public.standard_articles",
        "standard_articles.taxonomy_node_code_present": "SELECT count(*) FROM public.standard_articles WHERE taxonomy_node_code IS NOT NULL",
        "standard_articles.taxonomy_node_codes_present": "SELECT count(*) FROM public.standard_articles WHERE taxonomy_node_codes IS NOT NULL",
        "questions_bank.source_chunk_id_valid_join": "SELECT count(*) FROM public.questions_bank q JOIN public.kb_chunks k ON q.source_chunk_id = k.chunk_id",
    }
    rows = [{"metric": name, "count": runner.scalar(sql)} for name, sql in queries.items()]
    edge_relation_column = "relation_type"
    edge_columns = {
        row["column_name"]
        for row in runner.run_csv(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'knowledge_graph_edges'
            """
        )
    }
    if "relation" in edge_columns:
        edge_relation_column = "relation"
    edge_rows = runner.run_csv(
        f"""
        SELECT source_type || '->' || target_type || ':' || {edge_relation_column} AS metric, count(*)::text AS count
        FROM public.knowledge_graph_edges
        GROUP BY source_type, target_type, {edge_relation_column}
        ORDER BY count(*) DESC
        """
    )
    rows.extend({"metric": f"knowledge_graph_edges.{row['metric']}", "count": row["count"]} for row in edge_rows)
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "count"])
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    lines = ["# 2026 Source Compiler Supabase Coverage", "", "| Metric | Count |", "| --- | ---: |"]
    lines.extend(f"| `{row['metric']}` | {row['count']} |" for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--env", default="", help="Optional env file containing DB_URL or DATABASE_URL")
    args = parser.parse_args()

    try:
        runner = PsqlRunner(_db_url(args.env))
        assert_target_database_is_main(runner)
        rows = _metrics(runner)
        run_dir = _run_dir(args.run_id)
        _write_csv(run_dir / "supabase_coverage.csv", rows)
        _write_markdown(run_dir / "supabase_coverage.md", rows)
        print(f"coverage_metrics={len(rows)} questions_bank={runner.scalar('SELECT count(*) FROM public.questions_bank')}")
        return 0
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI should fail closed with a clear message.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
