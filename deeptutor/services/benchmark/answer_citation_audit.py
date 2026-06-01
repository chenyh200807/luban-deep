"""Offline citation accuracy audit for paper-style answer fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


MARKER_RE = re.compile(r"〔\d+〕")
FOOTER_RE = re.compile(r"\n{1,2}依据\n", re.MULTILINE)


def _markers(text: str) -> set[str]:
    return set(MARKER_RE.findall(text or ""))


def _split_answer_footer(answer: str) -> tuple[str, str]:
    match = FOOTER_RE.search(answer)
    if not match:
        return answer, ""
    return answer[: match.start()], answer[match.start() :]


def _span_matches(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, dict):
        return True
    if not isinstance(actual, dict):
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _hidden_leaks(case: dict[str, Any]) -> list[dict[str, str]]:
    answer = str(case.get("answer") or "")
    bundle_text = _json_text(case.get("citation_bundle") or {})
    leaks: list[dict[str, str]] = []
    for term in case.get("forbidden_terms") or []:
        term_text = str(term or "").strip()
        if not term_text:
            continue
        if term_text in answer:
            leaks.append({"term": term_text, "location": "answer"})
        if term_text in bundle_text:
            leaks.append({"term": term_text, "location": "citation_bundle"})
    return leaks


def _footer_supported(answer: str) -> tuple[bool, list[str]]:
    body, footer = _split_answer_footer(answer)
    failures: list[str] = []
    if not footer:
        failures.append("missing_footer")
        return False, failures

    body_markers = _markers(body)
    footer_markers = _markers(footer)

    missing_footer_rows = sorted(marker for marker in body_markers if marker not in footer_markers)
    unknown_footer_rows = sorted(marker for marker in footer_markers if marker not in body_markers)
    if missing_footer_rows:
        failures.append(f"missing_footer_rows:{','.join(missing_footer_rows)}")
    if unknown_footer_rows:
        failures.append(f"unknown_footer_rows:{','.join(unknown_footer_rows)}")
    return not failures, failures


def _citation_supported(case: dict[str, Any], refs: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for expected in case.get("expected_claim_refs") or []:
        source_ids = {str(source_id) for source_id in expected.get("expected_source_ids") or []}
        expected_span = expected.get("expected_source_span") or {}
        matched = any(
            str(ref.get("source_id") or "") in source_ids
            and _span_matches(ref.get("source_span"), expected_span)
            for ref in refs
        )
        if not matched:
            claim = str(expected.get("claim_text") or "<unknown>")
            failures.append(f"unsupported_expected_claim_ref:{claim}")
    return not failures, failures


def audit_answer_citation_cases(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    results: list[dict[str, Any]] = []
    citation_supported_count = 0
    footer_supported_count = 0
    hidden_leak_count = 0

    for case in cases:
        bundle = case.get("citation_bundle") or {}
        refs = [ref for ref in bundle.get("refs") or [] if isinstance(ref, dict)]
        answer = str(case.get("answer") or "")

        footer_supported, footer_failures = _footer_supported(answer)
        citation_supported, citation_failures = _citation_supported(case, refs)
        leaks = _hidden_leaks(case)
        failures = [*footer_failures, *citation_failures]
        if leaks:
            failures.append("hidden_forbidden_terms")

        if footer_supported:
            footer_supported_count += 1
        if citation_supported:
            citation_supported_count += 1
        hidden_leak_count += len(leaks)

        results.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "citation_supported": citation_supported,
                "footer_supported": footer_supported,
                "hidden_leaks": leaks,
                "failures": failures,
            }
        )

    total = len(cases)
    return {
        "suite": payload.get("suite"),
        "citation_accuracy": citation_supported_count / total if total else 0.0,
        "footer_coverage": footer_supported_count / total if total else 0.0,
        "hidden_leak_count": hidden_leak_count,
        "results": results,
    }
