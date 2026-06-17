#!/usr/bin/env python3
"""Near-live local adapter smoke for promoted RichLeaf context packs.

This runner exercises a runtime-facing local adapter over CompiledContextPack.
It does not call production RAG, live LLMs, remote services, DBs, or registries.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import build_compiled_context_pack


REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_LIVE_AB_PREFLIGHT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_preflight_20260612/live_ab_preflight.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_smoke_20260612/near_live_smoke.json"
)
SCHEMA = "luban_rich_leaf_semantic_runtime_near_live_smoke.v1"
VERDICT_CEILING = "NEAR_LIVE_LOCAL_ADAPTER_ONLY"
KNOWLEDGE_LANES = {"textbook", "standard", "lecture"}
FAMILY_TASK = {
    "definitions": "rag_answer",
    "rules": "rag_answer",
    "procedures": "rag_answer",
    "numeric_constraints": "grading",
    "teaching_cards": "tutoring",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _field_text(field: dict[str, Any]) -> str:
    for key in ("definition", "statement", "rule_text", "procedure_text", "card", "source_excerpt"):
        value = field.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    steps = field.get("steps")
    if isinstance(steps, list):
        joined = "；".join(str(step).strip() for step in steps if str(step).strip())
        if joined:
            return joined
    items = field.get("items")
    if isinstance(items, list):
        joined = "；".join(
            str(item.get("context") or item.get("value") or "").strip()
            for item in items
            if isinstance(item, dict)
        )
        if joined:
            return joined
    return ""


def _source_ref_index(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(ref.get("source_ref_id")): ref
        for ref in artifact.get("source_refs") or []
        if isinstance(ref, dict) and ref.get("source_ref_id")
    }


def _make_smoke_cases(artifacts: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    cases: list[dict[str, Any]] = []
    for artifact in artifacts:
        refs = _source_ref_index(artifact)
        for family, task in FAMILY_TASK.items():
            for field in artifact.get(family) or []:
                if not isinstance(field, dict) or field.get("claim_status") != "source_backed":
                    continue
                ref_ids = [str(ref_id) for ref_id in field.get("source_ref_ids") or []]
                lanes = {str(refs[ref_id].get("source_lane")) for ref_id in ref_ids if ref_id in refs}
                if "question" in lanes:
                    blockers.append(
                        f"question_lane_source_backed_knowledge_field:{artifact.get('artifact_id')}:{family}:{field.get('field_id')}"
                    )
                    continue
                if not lanes or not lanes <= KNOWLEDGE_LANES:
                    blockers.append(
                        f"unsupported_source_lane_for_knowledge_field:{artifact.get('artifact_id')}:{family}:{field.get('field_id')}:{sorted(lanes)}"
                    )
                    continue
                text = _field_text(field)
                if not text:
                    continue
                cases.append(
                    {
                        "case_id": f"near_live_{len(cases) + 1:04d}",
                        "task": task,
                        "artifact_id": artifact.get("artifact_id"),
                        "leaf_id": artifact.get("leaf_id"),
                        "field_id": field.get("field_id"),
                        "family": family,
                        "query": f"请基于编译知识回答：{text[:32]}",
                        "expected_terms": [text[: min(len(text), 12)]],
                        "expected_source_ref_ids": ref_ids,
                    }
                )
                if len(cases) >= limit:
                    return cases, blockers
    return cases, blockers


def _adapter_indexes(artifacts: list[dict[str, Any]], tasks: set[str], case_count: int) -> dict[str, dict[str, Any]]:
    indexes: dict[str, dict[str, Any]] = {}
    for task in sorted(tasks):
        pack = build_compiled_context_pack(
            task=task,
            artifacts=artifacts,
            bundle_version="v_rich_leaf_semantic_runtime_near_live_smoke_20260612",
            manifest_hash=str(case_count),
        ).to_dict()
        indexes[task] = {
            "pack": pack,
            "fields": {
                str(field.get("field_id")): field
                for field in pack.get("fields") or []
                if isinstance(field, dict) and field.get("field_id")
            },
            "source_refs": {
                str(ref.get("source_ref_id")): ref
                for ref in pack.get("source_refs") or []
                if isinstance(ref, dict) and ref.get("source_ref_id")
            },
        }
    return indexes


def _run_local_adapter(cases: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexes = _adapter_indexes(artifacts, {str(case["task"]) for case in cases}, len(cases))
    rows: list[dict[str, Any]] = []
    for case in cases:
        task = str(case["task"])
        index = indexes.get(task) or {}
        field = (index.get("fields") or {}).get(str(case["field_id"]))
        source_refs = index.get("source_refs") or {}
        expected_refs = [str(ref_id) for ref_id in case.get("expected_source_ref_ids") or []]
        cited = [ref_id for ref_id in expected_refs if ref_id in source_refs]
        answer_text = _field_text(field) if isinstance(field, dict) else ""
        expected_terms = [str(term) for term in case.get("expected_terms") or [] if str(term)]
        answerable = bool(answer_text and cited and all(term in answer_text for term in expected_terms))
        question_lane_citation_count = sum(1 for ref_id in cited if source_refs.get(ref_id, {}).get("source_lane") == "question")
        rows.append(
            {
                "case_id": case["case_id"],
                "task": task,
                "field_id": case["field_id"],
                "runtime_answer": {
                    "answer_text": answer_text,
                    "cited_source_ref_ids": cited,
                    "abstained": not answerable,
                },
                "answerable": answerable,
                "term_hit": bool(answerable),
                "citation_count": len(cited),
                "question_lane_citation_count": question_lane_citation_count,
                "fail_open": bool(answerable and not cited),
                "latency_ms_local_adapter_proxy": 1,
            }
        )
    return rows


def _rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(mean(1.0 if row.get(key) else 0.0 for row in rows), 4)


def _classification_blocks(prefix: str, payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{prefix}_{key}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(key) is not False:
            blockers.append(f"{prefix}_safety_{key}")
    if safety.get("production_write_count") not in (0, False):
        blockers.append(f"{prefix}_safety_production_write_count_nonzero")


def run_near_live_smoke(
    *, field_promotion_review: dict[str, Any], live_ab_preflight: dict[str, Any], limit: int = 10
) -> dict[str, Any]:
    blockers: list[str] = []
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"field_promotion_schema_mismatch:{field_promotion_review.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"field_promotion_not_pass:{field_promotion_review.get('verdict')}")
    _classification_blocks("field_promotion", field_promotion_review, blockers)
    if live_ab_preflight.get("schema") != "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1":
        blockers.append(f"live_ab_preflight_schema_mismatch:{live_ab_preflight.get('schema')}")
    if live_ab_preflight.get("verdict") != "READY_FOR_LIVE_RUNTIME_AB":
        blockers.append(f"live_ab_preflight_not_ready:{live_ab_preflight.get('verdict')}")
    if live_ab_preflight.get("quality_claim_allowed") is not False:
        blockers.append("live_ab_preflight_quality_claim_allowed")
    _classification_blocks("live_ab_preflight", live_ab_preflight, blockers)

    artifacts = [
        artifact
        for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    cases, case_blockers = _make_smoke_cases(artifacts, limit=limit)
    blockers.extend(case_blockers)
    if not cases:
        blockers.append("no_near_live_smoke_cases")
    rows = _run_local_adapter(cases, artifacts) if cases else []
    if rows and _rate(rows, "answerable") <= 0.0:
        blockers.append("near_live_smoke_no_answerable_cases")
    if rows and _rate(rows, "fail_open") != 0.0:
        blockers.append("near_live_smoke_fail_open")
    question_lane_rate = round(mean(1.0 if row["question_lane_citation_count"] > 0 else 0.0 for row in rows), 4) if rows else 0.0
    if question_lane_rate != 0.0:
        blockers.append("near_live_smoke_question_lane_citation")

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "field_promotion_review": field_promotion_review.get("schema"),
            "live_ab_preflight": live_ab_preflight.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "verdict_ceiling": VERDICT_CEILING,
        "quality_claim_allowed": False,
        "execution_mode": "near_live_runtime",
        "cohort_scope": "local_fixture",
        "auth_mode": "none",
        "runtime_entry": {
            "entrypoint": "local_compiled_context_adapter",
            "runtime_exercised": bool(rows),
            "runtime_trace_ids": [row["case_id"] for row in rows],
        },
        "provider_call_policy": {
            "provider_calls_allowed": False,
            "provider_call_count": 0,
            "models": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_recorded": False,
        },
        "summary": {
            "blocker_count": len(blockers),
            "smoke_case_count": len(cases),
            "answerable_rate": _rate(rows, "answerable"),
            "evidence_citation_rate": round(mean(1.0 if row["citation_count"] > 0 else 0.0 for row in rows), 4) if rows else 0.0,
            "term_hit_rate": _rate(rows, "term_hit"),
            "fail_open_rate": _rate(rows, "fail_open"),
            "question_lane_citation_rate": question_lane_rate,
            "live_runtime_executed": False,
            "provider_call_count": 0,
        },
        "evidence_validation": {
            "citation_rate": round(mean(1.0 if row["citation_count"] > 0 else 0.0 for row in rows), 4) if rows else 0.0,
            "fail_open_rate": _rate(rows, "fail_open"),
            "question_lane_citation_rate": question_lane_rate,
            "span_hash_validation_exercised": False,
        },
        "smoke_rows": rows,
        "blockers": blockers,
        "not_exercised_by_layer": {
            "review_not_exercised": [],
            "runtime_not_exercised": [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
            ],
            "release_not_exercised": ["production_default_decision", "release_truth_governance"],
        },
        "not_exercised": [
            "production_rag_retrieval",
            "legacy_runtime_live_path",
            "live_llm_semantic_judgment",
            "live_runtime_latency",
            "live_runtime_token_usage",
            "learner_outcome_gain",
            "production_default_decision",
            "release_truth_governance",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_near_live_smoke": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--live-ab-preflight", type=Path, default=DEFAULT_LIVE_AB_PREFLIGHT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    report = run_near_live_smoke(
        field_promotion_review=_read_json(args.field_promotion_review),
        live_ab_preflight=_read_json(args.live_ab_preflight),
        limit=args.limit,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
