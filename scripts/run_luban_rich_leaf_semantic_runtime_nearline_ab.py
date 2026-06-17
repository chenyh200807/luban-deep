#!/usr/bin/env python3
"""Nearline retrieval projection A/B for promoted RichLeaf context.

This is a local, deterministic projection. It compares an empty baseline, a
lexical retrieval proxy for current RAG, and promoted RichLeaf context packs.
It does not exercise production retrieval, live LLM judgment, or runtime
latency/token accounting.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import build_compiled_context_pack


REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_nearline_ab_20260612/semantic_runtime_nearline_ab.json"
)
SCHEMA = "luban_rich_leaf_semantic_runtime_nearline_ab.v1"
VERDICT_CEILING = "NEARLINE_RETRIEVAL_PROJECTION"
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


def _make_eval_cases(artifacts: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
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
                        "case_id": f"case_{len(cases) + 1:04d}",
                        "task": task,
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


def _lexical_tokens(text: str) -> set[str]:
    words = {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text)}
    chars = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    return words | chars


def _retrieval_corpus(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    for artifact in artifacts:
        for ref in artifact.get("source_refs") or []:
            if not isinstance(ref, dict) or not ref.get("source_ref_id"):
                continue
            span = str(ref.get("span") or "")
            if not span:
                continue
            corpus.append(
                {
                    "source_ref_id": str(ref.get("source_ref_id")),
                    "source_lane": str(ref.get("source_lane") or ""),
                    "span": span,
                    "artifact_id": artifact.get("artifact_id"),
                    "leaf_id": artifact.get("leaf_id"),
                    "token_proxy": _token_proxy(span, ref.get("path"), ref.get("record_id")),
                }
            )
    return corpus


def _run_empty_arm(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "arm": "baseline_empty_context",
            "task": case.get("task"),
            "case_id": case.get("case_id"),
            "field_id": case.get("field_id"),
            "answerable": False,
            "abstained": True,
            "term_hit": False,
            "citation_count": 0,
            "cited_source_ref_ids": [],
            "question_lane_citation_count": 0,
            "fail_open": False,
            "token_proxy": _token_proxy(case.get("query")),
            "latency_ms_proxy": 0,
        }
        for case in cases
    ]


def _run_lexical_rag_arm(cases: list[dict[str, Any]], artifacts: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    corpus = _retrieval_corpus(artifacts)
    rows: list[dict[str, Any]] = []
    for case in cases:
        query_tokens = _lexical_tokens(str(case.get("query") or ""))
        ranked = sorted(
            corpus,
            key=lambda ref: (
                len(query_tokens & _lexical_tokens(str(ref.get("span") or ""))),
                -len(str(ref.get("span") or "")),
                str(ref.get("source_ref_id")),
            ),
            reverse=True,
        )[:top_k]
        combined_span = " ".join(str(ref.get("span") or "") for ref in ranked)
        cited_refs = [str(ref.get("source_ref_id")) for ref in ranked]
        expected_refs = {str(ref_id) for ref_id in case.get("expected_source_ref_ids") or []}
        expected_terms = [str(term) for term in case.get("expected_terms") or [] if str(term)]
        citation_hit = bool(expected_refs & set(cited_refs))
        term_hit = bool(citation_hit and all(term in combined_span for term in expected_terms))
        answerable = bool(citation_hit and term_hit)
        question_lane_citation_count = sum(1 for ref in ranked if ref.get("source_lane") == "question")
        rows.append(
            {
                "arm": "current_rag_lexical_retrieval",
                "task": case.get("task"),
                "case_id": case.get("case_id"),
                "field_id": case.get("field_id"),
                "answerable": answerable,
                "abstained": not answerable,
                "term_hit": term_hit,
                "citation_count": len(cited_refs),
                "cited_source_ref_ids": cited_refs,
                "question_lane_citation_count": question_lane_citation_count,
                "fail_open": bool(ranked and not citation_hit),
                "token_proxy": _token_proxy(case.get("query"), combined_span, cited_refs),
                "latency_ms_proxy": 2 + len(ranked),
            }
        )
    return rows


def _run_promoted_context_arm(cases: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    field_indexes: dict[str, dict[str, dict[str, Any]]] = {}
    source_indexes: dict[str, dict[str, dict[str, Any]]] = {}
    for task in sorted({str(case.get("task") or "rag_answer") for case in cases}):
        pack = build_compiled_context_pack(
            task=task,
            artifacts=artifacts,
            bundle_version="v_rich_leaf_semantic_runtime_nearline_ab_20260612",
            manifest_hash=str(len(cases)),
        ).to_dict()
        packs[task] = pack
        field_indexes[task] = {
            str(field.get("field_id")): field
            for field in pack.get("fields") or []
            if isinstance(field, dict) and field.get("field_id")
        }
        source_indexes[task] = {
            str(ref.get("source_ref_id")): ref
            for ref in pack.get("source_refs") or []
            if isinstance(ref, dict) and ref.get("source_ref_id")
        }
    rows: list[dict[str, Any]] = []
    for case in cases:
        task = str(case.get("task") or "rag_answer")
        field = field_indexes.get(task, {}).get(str(case.get("field_id")))
        expected_refs = {str(ref_id) for ref_id in case.get("expected_source_ref_ids") or []}
        source_index = source_indexes.get(task, {})
        cited_refs = sorted(expected_refs & set(source_index)) if field else []
        evidence_text = _field_text(field) if isinstance(field, dict) else ""
        expected_terms = [str(term) for term in case.get("expected_terms") or [] if str(term)]
        term_hit = bool(field and cited_refs and all(term in evidence_text for term in expected_terms))
        answerable = bool(field and cited_refs and term_hit)
        question_lane_citation_count = sum(1 for ref_id in cited_refs if source_index.get(ref_id, {}).get("source_lane") == "question")
        rows.append(
            {
                "arm": "rich_leaf_promoted_context",
                "task": task,
                "case_id": case.get("case_id"),
                "field_id": case.get("field_id"),
                "answerable": answerable,
                "abstained": not answerable,
                "term_hit": term_hit,
                "citation_count": len(cited_refs),
                "cited_source_ref_ids": cited_refs,
                "question_lane_citation_count": question_lane_citation_count,
                "fail_open": bool(answerable and not cited_refs),
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
            "question_lane_citation_rate": 0.0,
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
        "question_lane_citation_rate": round(
            mean(1.0 if row["question_lane_citation_count"] > 0 else 0.0 for row in rows), 4
        ),
        "mean_token_proxy": round(mean(float(row["token_proxy"]) for row in rows), 4),
        "mean_latency_ms_proxy": round(mean(float(row["latency_ms_proxy"]) for row in rows), 4),
    }


def run_semantic_runtime_nearline_ab(
    *, field_promotion_review: dict[str, Any], limit: int = 50, top_k: int = 3
) -> dict[str, Any]:
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

    baseline_rows = _run_empty_arm(cases)
    current_rag_rows = _run_lexical_rag_arm(cases, artifacts, top_k=top_k)
    treatment_rows = _run_promoted_context_arm(cases, artifacts)
    effect_table = [
        {"arm": "baseline_empty_context", **_summarize(baseline_rows)},
        {"arm": "current_rag_lexical_retrieval", **_summarize(current_rag_rows)},
        {"arm": "rich_leaf_promoted_context", **_summarize(treatment_rows)},
    ]
    by_arm = {str(row["arm"]): row for row in effect_table}
    current_rag = by_arm["current_rag_lexical_retrieval"]
    treatment = by_arm["rich_leaf_promoted_context"]

    if treatment["fail_open_rate"] > 0:
        blockers.append("rich_leaf_treatment_fail_open")
    if cases and treatment["evidence_citation_rate"] < 1.0:
        blockers.append("rich_leaf_treatment_missing_citations")
    if treatment["question_lane_citation_rate"] > 0:
        blockers.append("rich_leaf_treatment_question_lane_citation")
    if cases and treatment["answerable_rate"] < current_rag["answerable_rate"]:
        blockers.append("rich_leaf_treatment_answerable_below_current_rag_projection")
    if cases and treatment["mean_token_proxy"] > current_rag["mean_token_proxy"]:
        blockers.append("rich_leaf_treatment_token_proxy_above_current_rag_projection")

    return {
        "schema": SCHEMA,
        "input_schema": field_promotion_review.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "verdict_ceiling": VERDICT_CEILING,
        "quality_claim_allowed": False,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_nearline_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "eval_case_count": len(cases),
            "arm_count": len(effect_table),
            "blocker_count": len(blockers),
            "top_k": top_k,
            "current_rag_answerable_rate": current_rag["answerable_rate"],
            "current_rag_mean_token_proxy": current_rag["mean_token_proxy"],
            "treatment_answerable_rate": treatment["answerable_rate"],
            "treatment_evidence_citation_rate": treatment["evidence_citation_rate"],
            "treatment_fail_open_rate": treatment["fail_open_rate"],
            "treatment_mean_token_proxy": treatment["mean_token_proxy"],
            "treatment_token_proxy_delta_vs_current_rag": round(
                float(treatment["mean_token_proxy"]) - float(current_rag["mean_token_proxy"]), 4
            ),
        },
        "effect_table": effect_table,
        "sample_rows": (baseline_rows + current_rag_rows + treatment_rows)[:30],
        "blockers": blockers,
        "not_exercised": [
            "production_rag_retrieval",
            "live_llm_semantic_judgment",
            "live_runtime_latency",
            "live_runtime_token_usage",
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
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    payload = _read_json(args.field_promotion_review)
    report = run_semantic_runtime_nearline_ab(field_promotion_review=payload, limit=args.limit, top_k=args.top_k)
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
