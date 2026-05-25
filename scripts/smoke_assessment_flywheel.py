#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


FORBIDDEN_PAYLOAD_KEYS = {
    "answer",
    "answer_key",
    "correct_answer",
    "grading_key",
    "scoring_points",
    "minimal_rationale",
    "option_reasoning",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a production-like Assessment TestSet flywheel smoke through /api/v1/assessment/*."
    )
    parser.add_argument("--base-url", required=True, help="API origin, for example https://test2.yousenjiaoyu.com")
    parser.add_argument("--token", default="", help="Bearer token for an existing learner account.")
    parser.add_argument("--topic-id", default="waterproof", help="Topic TestSet id to smoke.")
    parser.add_argument(
        "--assessment-type",
        default="topic_diagnostic",
        choices=("topic_diagnostic", "real_exam_simulation"),
        help="Assessment TestSet type to smoke.",
    )
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds.")
    args = parser.parse_args()

    token = str(args.token or "").strip()
    if not token:
        print("assessment_flywheel_smoke_requires_token", file=sys.stderr)
        return 2

    api_base_url = _normalize_api_base_url(str(args.base_url or ""))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        topics = _request_json("GET", f"{api_base_url}/assessment/topics", headers=headers, timeout=args.timeout)
        _assert_json(topics, "topics")

        assessment_type = str(args.assessment_type or "topic_diagnostic").strip()
        expected_count = 20 if assessment_type == "real_exam_simulation" else 12
        create_body: dict[str, Any] = {
            "assessment_type": assessment_type,
            "subject_id": "construction_exam",
            "count": expected_count,
        }
        if assessment_type == "topic_diagnostic":
            create_body["topic_ids"] = [str(args.topic_id or "").strip() or "waterproof"]
        created = _request_json(
            "POST",
            f"{api_base_url}/assessment/create",
            headers=headers,
            timeout=args.timeout,
            body=create_body,
        )
        quiz_id = str(created.get("quiz_id") or "").strip()
        questions = list(created.get("questions") or [])
        if not quiz_id or not questions:
            raise RuntimeError("assessment_create_missing_quiz_or_questions")
        if len(questions) != expected_count:
            raise RuntimeError(f"assessment_create_unexpected_question_count:{len(questions)}")
        if assessment_type == "real_exam_simulation":
            if str(created.get("assessment_type") or "") != "real_exam_simulation":
                raise RuntimeError(f"assessment_create_wrong_type:{created.get('assessment_type')}")
            if str(created.get("blueprint_version") or "") != "real_exam_simulation_mini_v1":
                raise RuntimeError(f"assessment_create_wrong_blueprint:{created.get('blueprint_version')}")
        leaked = sorted(_find_forbidden_keys(created))
        if leaked:
            raise RuntimeError(f"assessment_create_payload_leaked_hidden_keys: {', '.join(leaked)}")

        answers = {
            str(question.get("question_id") or ""): _first_option_key(question)
            for question in questions
            if str(question.get("question_id") or "").strip()
        }
        submitted = _request_json(
            "POST",
            f"{api_base_url}/assessment/{quiz_id}/submit",
            headers=headers,
            timeout=args.timeout,
            body={"answers": answers, "time_spent_seconds": 60},
        )
        if "score_summary" not in submitted and "score" not in submitted:
            raise RuntimeError("assessment_submit_missing_score")

        report = _request_json("GET", f"{api_base_url}/assessment/{quiz_id}/report", headers=headers, timeout=args.timeout)
        if str(report.get("quiz_id") or "") != quiz_id:
            raise RuntimeError("assessment_report_quiz_mismatch")

        first_question_id = str(questions[0].get("question_id") or "").strip()
        explanation = _request_json(
            "POST",
            f"{api_base_url}/assessment/{quiz_id}/items/{first_question_id}/explain",
            headers=headers,
            timeout=args.timeout,
        )
        if explanation.get("explanation", {}).get("score_mutation_allowed") is not False:
            raise RuntimeError("assessment_explanation_score_mutation_not_forbidden")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "quiz_id": quiz_id,
                "question_count": len(questions),
                "assessment_type": assessment_type,
                "blueprint_version": created.get("blueprint_version"),
                "report_ready": True,
                "deep_explanation_ready": True,
                "pre_submit_redaction": "passed",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _normalize_api_base_url(base_url: str) -> str:
    normalized = str(base_url or "").rstrip("/")
    if normalized.endswith("/api/v1"):
        return normalized
    return f"{normalized}/api/v1"


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read(500).decode("utf-8", "ignore")
        raise RuntimeError(f"http_{exc.code}: {text}") from exc


def _assert_json(payload: dict[str, Any], key: str) -> None:
    if key not in payload:
        raise RuntimeError(f"assessment_smoke_missing_{key}")


def _first_option_key(question: dict[str, Any]) -> str:
    options = question.get("options")
    if isinstance(options, list) and options:
        return str(options[0].get("key") or options[0].get("value") or "A")
    return "A"


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key)
            if normalized_key in FORBIDDEN_PAYLOAD_KEYS:
                found.add(normalized_key)
            found.update(_find_forbidden_keys(child))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found


if __name__ == "__main__":
    raise SystemExit(main())
