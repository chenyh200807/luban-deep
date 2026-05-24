#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.source_compiler.psql import PsqlRunner, assert_target_database_is_main


TOPIC_KEYWORDS = {
    "waterproof": ("防水",),
    "waterproof_decoration_mep": ("防水", "装饰", "机电"),
}

SUPPORTED_TOPIC_TYPES = {
    "single_choice",
    "multi_choice",
    "multiple_choice",
    "case_study",
    "calculation",
    "structured_judgment",
}

MOBILE_SAFE_STEM_MAX_CHARS = 520
MAX_CANDIDATE_ROWS = 5000

FIGURE_REF_RE = re.compile(r"(<img\b|!\[[^\]]*\]\(|如图|见图|图\s*\d|图片|figure)", re.IGNORECASE)
TABLE_REF_RE = re.compile(r"(如下表|见表|表\s*\d|\|[^\n]+\|)")
WHITESPACE_RE = re.compile(r"\s+")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _db_url(env_file: Path | None) -> str:
    file_values = _read_env_file(env_file) if env_file else {}
    return (
        os.getenv("DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or file_values.get("DB_URL")
        or file_values.get("DATABASE_URL")
        or file_values.get("SUPABASE_DB_URL")
        or ""
    )


def _ensure_artifact_root(path: Path, run_id: str) -> Path:
    resolved = path.resolve()
    allowed_root = (_repo_root() / "artifacts" / "assessment_testset" / "p0a").resolve()
    if not str(resolved).startswith(str(allowed_root) + os.sep) and resolved != allowed_root:
        raise SystemExit(f"Output path must stay under {allowed_root}")
    if resolved.name != run_id:
        resolved = resolved / run_id
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _fetch_columns(runner: PsqlRunner) -> set[str]:
    rows = runner.run_csv(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'questions_bank'
        ORDER BY ordinal_position
        """
    )
    return {row.get("column_name", "") for row in rows if row.get("column_name")}


def _selectable_columns(columns: set[str]) -> list[str]:
    wanted = [
        "id",
        "question_stem",
        "stem",
        "question_type",
        "source_type",
        "source_chunk_id",
        "node_code",
        "taxonomy_node_code",
        "taxonomy_node_codes",
        "source_meta",
        "options",
        "correct_answer",
        "difficulty",
        "tags",
        "analysis",
        "explanation",
        "option_reasoning",
        "grading_keywords",
        "grading_key",
        "semantic_signature",
    ]
    return [item for item in wanted if item in columns]


def _topic_filter_clause(columns: set[str], topic: str) -> str:
    searchable = [
        column
        for column in (
            "question_stem",
            "stem",
            "node_code",
            "taxonomy_node_code",
            "taxonomy_node_codes",
            "source_meta",
            "tags",
            "analysis",
            "explanation",
        )
        if column in columns
    ]
    if not searchable:
        return "TRUE"
    text_expr = " || ' ' || ".join(f"COALESCE({_quote_ident(column)}::text, '')" for column in searchable)
    predicates = []
    for keyword in TOPIC_KEYWORDS[topic]:
        escaped = keyword.replace("'", "''")
        predicates.append(f"({text_expr}) ILIKE '%{escaped}%'")
    return "(" + " OR ".join(predicates) + ")"


def _fetch_candidates(runner: PsqlRunner, topic: str) -> tuple[set[str], list[dict[str, str]]]:
    columns = _fetch_columns(runner)
    selected = _selectable_columns(columns)
    if "id" not in selected:
        raise RuntimeError("questions_bank.id is required for P0A coverage audit")
    sql = f"""
        SELECT {", ".join(_quote_ident(column) for column in selected)}
        FROM public.questions_bank
        WHERE {_topic_filter_clause(columns, topic)}
        ORDER BY id::text ASC
        LIMIT {MAX_CANDIDATE_ROWS}
    """
    return columns, runner.run_csv(sql)


def _json_value(value: str) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _normalize_text(value: Any) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").strip())


def _stem(row: dict[str, str]) -> str:
    return _normalize_text(row.get("question_stem") or row.get("stem") or "")


def _parse_options(value: str) -> list[tuple[str, str]]:
    parsed = _json_value(value)
    if isinstance(parsed, dict):
        return [(str(key).strip(), _normalize_text(text)) for key, text in sorted(parsed.items()) if str(key).strip()]
    if isinstance(parsed, list):
        options: list[tuple[str, str]] = []
        for index, item in enumerate(parsed):
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("label") or item.get("option") or chr(ord("A") + index)).strip()
                text = _normalize_text(item.get("text") or item.get("value") or item.get("content") or "")
            else:
                key = chr(ord("A") + index)
                text = _normalize_text(item)
            if key and text:
                options.append((key, text))
        return options
    return []


def _has_simple_explanation(row: dict[str, str]) -> bool:
    for column in ("analysis", "explanation", "option_reasoning", "grading_keywords", "grading_key"):
        if _normalize_text(row.get(column)):
            return True
    source_meta = _json_value(row.get("source_meta") or "")
    if isinstance(source_meta, dict):
        for key in ("analysis", "explanation", "rationale", "simple_explanation"):
            if _normalize_text(source_meta.get(key)):
                return True
    return False


def _has_knowledge_node(row: dict[str, str]) -> bool:
    for column in ("node_code", "taxonomy_node_code", "taxonomy_node_codes"):
        if _normalize_text(row.get(column)):
            return True
    source_meta = _json_value(row.get("source_meta") or "")
    if isinstance(source_meta, dict):
        for key in ("node_code", "taxonomy_node_code", "taxonomy_node_codes", "predicted_node"):
            if _normalize_text(source_meta.get(key)):
                return True
    return False


def _semantic_signature(row: dict[str, str], options: list[tuple[str, str]]) -> str:
    existing = _normalize_text(row.get("semantic_signature"))
    if existing:
        return existing
    normalized = json.dumps(
        {
            "stem": _stem(row),
            "options": [(key.upper(), text) for key, text in options],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "derived_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _candidate_record(row: dict[str, str]) -> dict[str, Any]:
    stem = _stem(row)
    options = _parse_options(row.get("options") or "")
    question_type = _normalize_text(row.get("question_type") or "single_choice")
    answer_present = bool(_normalize_text(row.get("correct_answer")))
    option_present = len(options) >= 2
    knowledge_node_present = _has_knowledge_node(row)
    has_figure_ref = bool(FIGURE_REF_RE.search(stem))
    has_table_ref = bool(TABLE_REF_RE.search(stem))
    long_stem = len(stem) > MOBILE_SAFE_STEM_MAX_CHARS
    supported_type = question_type in SUPPORTED_TOPIC_TYPES
    duplicate_key = str(row.get("id") or "").strip()
    exclusion_reasons: list[str] = []
    if not duplicate_key:
        exclusion_reasons.append("missing_source_question_id")
    if not stem:
        exclusion_reasons.append("missing_stem")
    if not option_present:
        exclusion_reasons.append("missing_options")
    if not answer_present:
        exclusion_reasons.append("missing_answer_key")
    if not supported_type:
        exclusion_reasons.append("unsupported_question_type")
    if has_figure_ref:
        exclusion_reasons.append("figure_ref_requires_mobile_renderer_review")
    if has_table_ref:
        exclusion_reasons.append("table_ref_requires_mobile_renderer_review")
    if long_stem:
        exclusion_reasons.append("long_stem_mobile_risk")
    return {
        "source_question_id": duplicate_key,
        "question_type": question_type,
        "source_type": _normalize_text(row.get("source_type")),
        "node_code": _normalize_text(row.get("node_code") or row.get("taxonomy_node_code")),
        "stem_chars": len(stem),
        "stem_preview": stem[:96],
        "answer_key_present": answer_present,
        "option_count": len(options),
        "option_coverage": option_present,
        "knowledge_node_present": knowledge_node_present,
        "simple_explanation_present": _has_simple_explanation(row),
        "has_figure_ref": has_figure_ref,
        "has_table_ref": has_table_ref,
        "long_stem": long_stem,
        "semantic_signature": _semantic_signature(row, options),
        "eligible_before_dedupe": not exclusion_reasons,
        "exclusion_reasons": exclusion_reasons,
    }


def _analyze(topic: str, columns: set[str], rows: list[dict[str, str]], *, emit_form_preview: bool) -> dict[str, Any]:
    records = [_candidate_record(row) for row in rows]
    by_source_id: dict[str, dict[str, Any]] = {}
    source_duplicates = 0
    for record in records:
        source_id = record["source_question_id"]
        if source_id in by_source_id:
            source_duplicates += 1
            continue
        by_source_id[source_id] = record

    semantic_seen: set[str] = set()
    semantic_duplicates = 0
    eligible: list[dict[str, Any]] = []
    for record in by_source_id.values():
        if not record["eligible_before_dedupe"]:
            continue
        signature = record["semantic_signature"]
        if signature in semantic_seen:
            semantic_duplicates += 1
            record["exclusion_reasons"] = ["duplicate_semantic_signature"]
            continue
        semantic_seen.add(signature)
        eligible.append(record)

    source_type_distribution = Counter(record["source_type"] or "unknown" for record in records)
    question_type_distribution = Counter(record["question_type"] or "unknown" for record in records)
    exclusion_counts: Counter[str] = Counter()
    for record in records:
        for reason in record["exclusion_reasons"]:
            exclusion_counts[reason] += 1

    delivered_recommendation: int | str
    if len(eligible) >= 24:
        delivered_recommendation = 12
    elif len(eligible) >= 20:
        delivered_recommendation = 10
    elif len(eligible) >= 16:
        delivered_recommendation = 8
    else:
        delivered_recommendation = "blocked"

    form_preview = []
    if emit_form_preview and isinstance(delivered_recommendation, int):
        form_preview = [
            {
                "source_question_id": item["source_question_id"],
                "question_type": item["question_type"],
                "source_type": item["source_type"],
                "node_code": item["node_code"],
                "stem_chars": item["stem_chars"],
            }
            for item in eligible[:delivered_recommendation]
        ]

    return {
        "topic": topic,
        "keywords": list(TOPIC_KEYWORDS[topic]),
        "columns_seen": sorted(columns),
        "filter_description": "OR keyword match over stem/node/tags/source_meta/analysis text; read-only SQL",
        "candidate_count": len(records),
        "unique_source_question_count": len(by_source_id),
        "eligible_candidate_count": len(eligible),
        "source_question_duplicate_count": source_duplicates,
        "semantic_duplicate_count": semantic_duplicates,
        "answer_key_coverage_count": sum(1 for item in records if item["answer_key_present"]),
        "option_coverage_count": sum(1 for item in records if item["option_coverage"]),
        "knowledge_node_coverage_count": sum(1 for item in records if item["knowledge_node_present"]),
        "simple_explanation_available_count": sum(1 for item in records if item["simple_explanation_present"]),
        "long_stem_exclusion_count": exclusion_counts["long_stem_mobile_risk"],
        "figure_ref_count": exclusion_counts["figure_ref_requires_mobile_renderer_review"],
        "table_ref_count": exclusion_counts["table_ref_requires_mobile_renderer_review"],
        "source_type_distribution": dict(sorted(source_type_distribution.items())),
        "question_type_distribution": dict(sorted(question_type_distribution.items())),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "delivered_recommendation": delivered_recommendation,
        "candidate_ids_for_manual_review": [item["source_question_id"] for item in eligible[:48]],
        "candidate_review": records,
        "form_preview": form_preview,
    }


def _load_existing_coverage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "assessment_p0a_coverage_v1", "topics": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": "assessment_p0a_coverage_v1", "topics": {}}


def _write_outputs(out_dir: Path, topic: str, report: dict[str, Any]) -> None:
    topic_json = out_dir / f"coverage_{topic}.json"
    topic_md = out_dir / f"coverage_{topic}.md"
    topic_csv = out_dir / f"candidate_review_{topic}.csv"
    topic_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    topic_md.write_text(_render_markdown(report), encoding="utf-8")
    _write_candidate_csv(topic_csv, report["candidate_review"])

    aggregate_path = out_dir / "coverage.json"
    aggregate = _load_existing_coverage(aggregate_path)
    slim_report = {key: value for key, value in report.items() if key != "candidate_review"}
    aggregate.setdefault("topics", {})[topic] = slim_report
    aggregate_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "coverage.md").write_text(_render_aggregate_markdown(aggregate), encoding="utf-8")
    _write_combined_csv(out_dir / "candidate_review.csv", aggregate, out_dir)


def _write_candidate_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "source_question_id",
        "question_type",
        "source_type",
        "node_code",
        "stem_chars",
        "answer_key_present",
        "option_count",
        "knowledge_node_present",
        "simple_explanation_present",
        "has_figure_ref",
        "has_table_ref",
        "long_stem",
        "eligible_before_dedupe",
        "exclusion_reasons",
        "semantic_signature",
        "stem_preview",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field, "") for field in fields}
            row["exclusion_reasons"] = "|".join(record.get("exclusion_reasons") or [])
            writer.writerow(row)


def _write_combined_csv(path: Path, aggregate: dict[str, Any], out_dir: Path) -> None:
    topic_files = [out_dir / f"candidate_review_{topic}.csv" for topic in sorted(aggregate.get("topics", {}))]
    wrote_header = False
    with path.open("w", encoding="utf-8", newline="") as combined:
        for topic_file in topic_files:
            if not topic_file.exists():
                continue
            rows = topic_file.read_text(encoding="utf-8").splitlines()
            if not rows:
                continue
            if not wrote_header:
                combined.write(rows[0] + "\n")
                wrote_header = True
            for row in rows[1:]:
                combined.write(row + "\n")


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Assessment TestSet P0A Coverage: {report['topic']}",
        "",
        f"- Keywords: {', '.join(report['keywords'])}",
        f"- Candidate count: {report['candidate_count']}",
        f"- Eligible candidate count: {report['eligible_candidate_count']}",
        f"- Delivered recommendation: {report['delivered_recommendation']}",
        f"- Answer-key coverage: {report['answer_key_coverage_count']}",
        f"- Option coverage: {report['option_coverage_count']}",
        f"- Knowledge-node coverage: {report['knowledge_node_coverage_count']}",
        f"- Simple-explanation availability: {report['simple_explanation_available_count']}",
        f"- Long-stem exclusions: {report['long_stem_exclusion_count']}",
        f"- Figure refs: {report['figure_ref_count']}",
        f"- Table refs: {report['table_ref_count']}",
        f"- Source-question duplicates: {report['source_question_duplicate_count']}",
        f"- Semantic duplicates: {report['semantic_duplicate_count']}",
        "",
        "## Source Type Distribution",
        "",
    ]
    for key, count in report["source_type_distribution"].items():
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## Exclusion Counts", ""])
    if report["exclusion_counts"]:
        for key, count in report["exclusion_counts"].items():
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Candidate IDs For Manual Review", ""])
    for source_id in report["candidate_ids_for_manual_review"]:
        lines.append(f"- {source_id}")
    if report["form_preview"]:
        lines.extend(["", "## Deterministic Form Preview", ""])
        for item in report["form_preview"]:
            lines.append(
                f"- {item['source_question_id']} | {item['question_type']} | "
                f"{item['source_type']} | {item['node_code']} | stem_chars={item['stem_chars']}"
            )
    return "\n".join(lines).strip() + "\n"


def _render_aggregate_markdown(aggregate: dict[str, Any]) -> str:
    lines = ["# Assessment TestSet P0A Coverage Aggregate", ""]
    for topic, report in sorted(aggregate.get("topics", {}).items()):
        lines.extend(
            [
                f"## {topic}",
                "",
                f"- Candidate count: {report['candidate_count']}",
                f"- Eligible candidate count: {report['eligible_candidate_count']}",
                f"- Delivered recommendation: {report['delivered_recommendation']}",
                f"- Answer-key coverage: {report['answer_key_coverage_count']}",
                f"- Option coverage: {report['option_coverage_count']}",
                f"- Knowledge-node coverage: {report['knowledge_node_coverage_count']}",
                f"- Simple-explanation availability: {report['simple_explanation_available_count']}",
                f"- Long-stem exclusions: {report['long_stem_exclusion_count']}",
                f"- Figure refs: {report['figure_ref_count']}",
                f"- Table refs: {report['table_ref_count']}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only P0A assessment coverage audit.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--topic", required=True, choices=sorted(TOPIC_KEYWORDS))
    parser.add_argument("--out", default="")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--read-only", action="store_true", help="Required safety acknowledgment.")
    parser.add_argument("--emit-form-preview", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    if not args.read_only:
        raise SystemExit("--read-only is required; this audit must never write Supabase")
    root = _repo_root()
    out_base = Path(args.out) if args.out else root / "artifacts" / "assessment_testset" / "p0a" / args.run_id
    out_dir = _ensure_artifact_root(out_base if out_base.is_absolute() else root / out_base, args.run_id)
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = root / env_file
    db_url = _db_url(env_file)
    if not db_url:
        raise SystemExit("DB_URL, DATABASE_URL, or SUPABASE_DB_URL is required for read-only coverage audit")

    runner = PsqlRunner(db_url, timeout=30)
    assert_target_database_is_main(runner)
    columns, rows = _fetch_candidates(runner, args.topic)
    report = _analyze(args.topic, columns, rows, emit_form_preview=bool(args.emit_form_preview))
    _write_outputs(out_dir, args.topic, report)
    print(
        "topic={topic} candidates={candidates} eligible={eligible} recommendation={recommendation} out={out}".format(
            topic=args.topic,
            candidates=report["candidate_count"],
            eligible=report["eligible_candidate_count"],
            recommendation=report["delivered_recommendation"],
            out=out_dir,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
