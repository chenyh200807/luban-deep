#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.mcq import grade_mcq_submission
from deeptutor.services.construction_grading.normalization import normalize_choice_letters, normalize_options


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


def _dictfetchone(cur: Any) -> dict[str, Any]:
    names = [desc.name for desc in cur.description]
    row = cur.fetchone()
    return dict(zip(names, row)) if row else {}


def _sample_wrong_answer(row: dict[str, Any]) -> str:
    correct = normalize_choice_letters(row.get("correct_answer"))
    options = normalize_options(row.get("options"))
    option_keys = sorted(options) or list("ABCDE")
    extra = next((key for key in option_keys if key not in set(correct)), "")
    if correct and extra:
        return correct[0] + extra
    if len(correct) > 1:
        return correct[:-1]
    return "A" if correct != "A" else "B"


def _fetch_evidence_rows(cur: Any, node_code: str) -> list[dict[str, Any]]:
    if not node_code:
        return []
    cur.execute(
        """
        select 'kb_chunks' as source, 'metadata' as field, rag_content as text
        from kb_chunks
        where node_code = %s
        order by case source_type when 'exam' then 0 when 'textbook' then 1 when 'standard' then 2 else 3 end
        limit 3
        """,
        (node_code,),
    )
    names = [desc.name for desc in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def run_smoke(env_file: Path) -> dict[str, Any]:
    try:
        import psycopg2
        import psycopg2.extras
    except Exception as exc:  # pragma: no cover - environment guard
        raise RuntimeError("psycopg2 is required for direct read-only DB smoke") from exc

    url = _db_url(env_file)
    if not url:
        raise RuntimeError("DB_URL or DATABASE_URL is required")

    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SET application_name='deeptutor_construction_grading_smoke'")
    try:
        cur.execute(
            """
            select id, original_id, question_type, question_stem, stem, options, correct_answer,
                   analysis, option_reasoning, trap_type, testing_focus, grading_keywords,
                   source_meta, node_code
            from questions_bank
            where question_type in ('single_choice','multi_choice','multiple_choice','judgment')
              and correct_answer is not null
              and options is not null and options::text not in ('[]','{}','null','""')
              and option_reasoning is not null and option_reasoning::text not in ('[]','{}','null','""')
            limit 1
            """
        )
        mcq_row = dict(_dictfetchone(cur))
        if not mcq_row:
            raise RuntimeError("No MCQ row with option_reasoning found")
        mcq_user_answer = _sample_wrong_answer(mcq_row)
        mcq_result = grade_mcq_submission(mcq_row, mcq_user_answer)
        if not any(ref.field == "option_reasoning" for ref in mcq_result.evidence_refs):
            raise RuntimeError("MCQ grading did not use option_reasoning evidence")
        if not mcq_result.error_events:
            raise RuntimeError("MCQ grading did not emit error events")

        cur.execute(
            """
            select id, original_id, question_type, question_stem, stem, correct_answer, analysis,
                   grading_keywords, grading_rubric, structured_rules, source_meta, node_code, testing_focus
            from questions_bank
            where question_type = 'case_study'
              and correct_answer is not null and correct_answer::text not in ('[]','{}','null','""')
              and grading_keywords is not null and grading_keywords::text not in ('[]','{}','null','""')
            order by case when structured_rules is not null and structured_rules::text not in ('[]','{}','null','""') then 0 else 1 end
            limit 1
            """
        )
        case_row = dict(_dictfetchone(cur))
        if not case_row:
            raise RuntimeError("No case row with grading_keywords found")
        evidence_rows = _fetch_evidence_rows(cur, str(case_row.get("node_code") or ""))
        case_result = CaseGradingSkillKernel().grade(
            question_row=case_row,
            user_answer="应加强管理，严格检查。",
            evidence_rows=evidence_rows,
        )
        if case_result.grading_mode not in {"projected_rubric", "curated_rubric"}:
            raise RuntimeError(f"Unexpected case grading mode: {case_result.grading_mode}")
        if not any(ref.source == "questions_bank" and ref.field == "grading_keywords" for ref in case_result.evidence_refs):
            raise RuntimeError("Case grading did not use questions_bank.grading_keywords")
        if evidence_rows and not any(ref.source == "kb_chunks" for ref in case_result.evidence_refs):
            raise RuntimeError("Case grading did not attach kb_chunks evidence")
        if not case_result.error_events:
            raise RuntimeError("Case grading did not emit error events")

        return {
            "status": "pass",
            "mcq": {
                "question_id": mcq_result.question_id,
                "user_answer": mcq_result.user_answer,
                "correct_answer": mcq_result.correct_answer,
                "evidence_fields": [ref.field for ref in mcq_result.evidence_refs],
                "error_codes": [event.error_code for event in mcq_result.error_events],
            },
            "case": {
                "question_id": case_result.question_id,
                "grading_mode": case_result.grading_mode,
                "score_awarded": case_result.score_awarded,
                "max_score": case_result.max_score,
                "evidence_sources": sorted({ref.source for ref in case_result.evidence_refs}),
                "evidence_fields": [ref.field for ref in case_result.evidence_refs],
                "error_codes": [event.error_code for event in case_result.error_events],
            },
        }
    finally:
        cur.close()
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only live grading smoke against Supabase.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    report = run_smoke(Path(args.env_file))
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    print(content)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
