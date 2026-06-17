#!/usr/bin/env python3
"""Review-only offline semantic runtime A/B for promoted RichLeaf context.

This adapter is deterministic and does not call an LLM. It checks whether
promoted RichLeaf context can supply cited evidence for source-backed knowledge
cases while baseline empty context abstains fail-closed. It is not a live
accuracy/latency/token benchmark.
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
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_offline_ab_20260612/semantic_runtime_offline_ab.json"
)
SCHEMA = "luban_rich_leaf_semantic_runtime_offline_ab.v1"
KNOWLEDGE_LANES = {"textbook", "standard", "lecture"}
EVAL_TASK = "rag_answer"
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
        joined = "；".join(str(item.get("context") or item.get("value") or "").strip() for item in items if isinstance(item, dict))
        if joined:
            return joined
    return ""


def _source_ref_index(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(ref.get("source_ref_id")): ref
        for ref in artifact.get("source_refs") or []
        if isinstance(ref, dict) and ref.get("source_ref_id")
    }


def _make_eval_cases(artifacts: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    cases: list[dict[str, Any]] = []
    for artifact in artifacts:
        refs = _source_ref_index(artifact)
        for family in ("definitions", "rules", "procedures", "numeric_constraints", "teaching_cards"):
            for field in artifact.get(family) or []:
                if not isinstance(field, dict) or field.get("claim_status") != "source_backed":
                    continue
                ref_ids = [str(ref_id) for ref_id in field.get("source_ref_ids") or []]
                lanes = {str(refs[ref_id].get("source_lane")) for ref_id in ref_ids if ref_id in refs}
                if "question" in lanes:
                    blockers.append(f"question_lane_source_backed_knowledge_field:{artifact.get('artifact_id')}:{family}:{field.get('field_id')}")
                    continue
                if not lanes or not lanes <= KNOWLEDGE_LANES:
                    blockers.append(f"unsupported_source_lane_for_knowledge_field:{artifact.get('artifact_id')}:{family}:{field.get('field_id')}:{sorted(lanes)}")
                    continue
                text = _field_text(field)
                if not text:
                    continue
                cases.append(
                    {
                        "case_id": f"case_{len(cases) + 1:04d}",
                        "task": FAMILY_TASK[family],
                        "leaf_id": artifact.get("leaf_id"),
                        "artifact_id": artifact.get("artifact_id"),
                        "field_id": field.get("field_id"),
                        "family": family,
                        "query": f"请说明：{text[:32]}",
                        "expected_terms": [text[: min(len(text), 12)]],
                        "expected_source_ref_ids": ref_ids,
                    }
                )
                if len(cases) >= limit:
                    return cases, blockers
    return cases, blockers


def _token_proxy(*values: Any) -> int:
    encoded = "".join(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str) for value in values)
    return max(0, len(encoded) // 4)


def _run_arm(*, arm: str, cases: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    field_indexes: dict[str, dict[str, dict[str, Any]]] = {}
    source_indexes: dict[str, set[str]] = {}
    for task in sorted({str(case.get("task") or EVAL_TASK) for case in cases}):
        pack = build_compiled_context_pack(
            task=task,
            artifacts=artifacts,
            bundle_version=f"v_rich_leaf_semantic_runtime_offline_ab_{arm}_20260612",
            manifest_hash=str(len(cases)),
        ).to_dict()
        packs[task] = pack
        field_indexes[task] = {
            str(field.get("field_id")): field
            for field in pack.get("fields") or []
            if isinstance(field, dict) and field.get("field_id")
        }
        source_indexes[task] = {
            str(ref.get("source_ref_id")) for ref in pack.get("source_refs") or [] if isinstance(ref, dict)
        }
    rows: list[dict[str, Any]] = []
    for case in cases:
        task = str(case.get("task") or EVAL_TASK)
        field = field_indexes.get(task, {}).get(str(case.get("field_id")))
        expected_refs = set(case.get("expected_source_ref_ids") or [])
        cited_refs = sorted(expected_refs & source_indexes.get(task, set())) if field else []
        evidence_text = _field_text(field) if isinstance(field, dict) else ""
        answerable = bool(field and cited_refs and evidence_text)
        abstained = not answerable
        expected_terms = [str(term) for term in case.get("expected_terms") or [] if str(term)]
        term_hit = bool(answerable and all(term in evidence_text for term in expected_terms))
        fail_open = bool(answerable and not cited_refs)
        rows.append(
            {
                "arm": arm,
                "task": task,
                "case_id": case.get("case_id"),
                "field_id": case.get("field_id"),
                "answerable": answerable,
                "abstained": abstained,
                "term_hit": term_hit,
                "citation_count": len(cited_refs),
                "cited_source_ref_ids": cited_refs,
                "fail_open": fail_open,
                "token_proxy": _token_proxy(case.get("query"), evidence_text, cited_refs),
                "latency_ms_proxy": 1 if answerable else 0,
            }
        )
    return rows


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "answerable_rate": 0.0,
            "abstention_rate": 0.0,
            "term_hit_rate": 0.0,
            "evidence_citation_rate": 0.0,
            "fail_open_rate": 0.0,
            "mean_token_proxy": 0.0,
            "mean_latency_ms_proxy": 0.0,
        }
    return {
        "sample_count": len(rows),
        "answerable_rate": round(mean(1.0 if row["answerable"] else 0.0 for row in rows), 4),
        "abstention_rate": round(mean(1.0 if row["abstained"] else 0.0 for row in rows), 4),
        "term_hit_rate": round(mean(1.0 if row["term_hit"] else 0.0 for row in rows), 4),
        "evidence_citation_rate": round(mean(1.0 if row["citation_count"] > 0 else 0.0 for row in rows), 4),
        "fail_open_rate": round(mean(1.0 if row["fail_open"] else 0.0 for row in rows), 4),
        "mean_token_proxy": round(mean(float(row["token_proxy"]) for row in rows), 4),
        "mean_latency_ms_proxy": round(mean(float(row["latency_ms_proxy"]) for row in rows), 4),
    }


def run_semantic_runtime_offline_ab(*, field_promotion_review: dict[str, Any], limit: int = 50) -> dict[str, Any]:
    blockers: list[str] = []
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"input_schema_mismatch:{field_promotion_review.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"input_field_promotion_review_failed:{field_promotion_review.get('verdict')}")
    classification = field_promotion_review.get("classification") if isinstance(field_promotion_review.get("classification"), dict) else {}
    if classification.get("runtime_install_allowed") is not False or classification.get("release_truth_claimed") is not False:
        blockers.append("input_field_promotion_review_runtime_or_release_allowed")
    artifacts = [
        artifact
        for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    cases, case_blockers = _make_eval_cases(artifacts, limit=limit)
    blockers.extend(case_blockers)
    if not cases:
        blockers.append("no_source_backed_eval_cases")

    baseline_rows = _run_arm(arm="baseline_empty_context", cases=cases, artifacts=[])
    treatment_rows = _run_arm(arm="rich_leaf_promoted_context", cases=cases, artifacts=artifacts)
    effect_table = [
        {"arm": "baseline_empty_context", **_summarize(baseline_rows)},
        {"arm": "rich_leaf_promoted_context", **_summarize(treatment_rows)},
    ]
    treatment = effect_table[1]
    if treatment["fail_open_rate"] > 0:
        blockers.append("rich_leaf_treatment_fail_open")
    if cases and treatment["evidence_citation_rate"] < 1.0:
        blockers.append("rich_leaf_treatment_missing_citations")

    return {
        "schema": SCHEMA,
        "input_schema": field_promotion_review.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "verdict_ceiling": "OFFLINE_ADAPTER_ONLY",
        "quality_claim_allowed": False,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_offline_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "eval_case_count": len(cases),
            "arm_count": len(effect_table),
            "blocker_count": len(blockers),
            "treatment_answerable_rate": treatment["answerable_rate"],
            "treatment_evidence_citation_rate": treatment["evidence_citation_rate"],
            "treatment_fail_open_rate": treatment["fail_open_rate"],
        },
        "effect_table": effect_table,
        "sample_rows": (baseline_rows + treatment_rows)[:20],
        "blockers": blockers,
        "not_exercised": [
            "live_llm_semantic_judgment",
            "live_runtime_latency",
            "live_runtime_token_usage",
            "production_rag_retrieval",
            "learner_outcome_gain",
            "production_default_decision",
        ],
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)

    report = run_semantic_runtime_offline_ab(
        field_promotion_review=_read_json(args.field_promotion_review),
        limit=max(1, args.limit),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
