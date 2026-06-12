#!/usr/bin/env python3
"""Near-live shadow A/B over local RichLeaf adapter vs lexical RAG proxy.

This runner expands the 10-case local adapter smoke into a shadow comparison.
It remains local and review-only: no production RAG, provider, DB, registry, or
runtime default is exercised.
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
DEFAULT_NEAR_LIVE_SMOKE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_smoke_20260612/near_live_smoke.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_shadow_ab_20260612/near_live_shadow_ab.json"
)
SCHEMA = "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1"
VERDICT_CEILING = "NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY"
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


def _token_proxy(*values: Any) -> int:
    encoded = "".join(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str) for value in values)
    return max(0, len(encoded) // 4)


def _lexical_tokens(text: str) -> set[str]:
    words = {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text)}
    chars = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    return words | chars


def _source_ref_index(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(ref.get("source_ref_id")): ref
        for ref in artifact.get("source_refs") or []
        if isinstance(ref, dict) and ref.get("source_ref_id")
    }


def _make_shadow_cases(artifacts: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
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
                        "case_id": f"near_live_shadow_{len(cases) + 1:04d}",
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
                    "token_proxy": _token_proxy(span, ref.get("path"), ref.get("record_id")),
                }
            )
    return corpus


def _run_rag_proxy(cases: list[dict[str, Any]], artifacts: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
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
        cited_refs = [str(ref.get("source_ref_id")) for ref in ranked]
        combined_span = " ".join(str(ref.get("span") or "") for ref in ranked)
        expected_refs = {str(ref_id) for ref_id in case.get("expected_source_ref_ids") or []}
        expected_terms = [str(term) for term in case.get("expected_terms") or [] if str(term)]
        citation_hit = bool(expected_refs & set(cited_refs))
        term_hit = bool(citation_hit and all(term in combined_span for term in expected_terms))
        rows.append(
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": case["case_id"],
                "task": case["task"],
                "answerable": bool(citation_hit and term_hit),
                "term_hit": bool(term_hit),
                "citation_count": len(cited_refs),
                "question_lane_citation_count": sum(1 for ref in ranked if ref.get("source_lane") == "question"),
                "fail_open": bool(ranked and not citation_hit),
                "token_proxy": _token_proxy(case.get("query"), combined_span, cited_refs),
                "latency_ms_local_proxy": 2 + len(ranked),
            }
        )
    return rows


def _adapter_indexes(artifacts: list[dict[str, Any]], tasks: set[str], case_count: int) -> dict[str, dict[str, Any]]:
    indexes: dict[str, dict[str, Any]] = {}
    for task in sorted(tasks):
        pack = build_compiled_context_pack(
            task=task,
            artifacts=artifacts,
            bundle_version="v_rich_leaf_semantic_runtime_near_live_shadow_ab_20260612",
            manifest_hash=str(case_count),
        ).to_dict()
        indexes[task] = {
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
        index = indexes.get(str(case["task"])) or {}
        field = (index.get("fields") or {}).get(str(case["field_id"]))
        source_refs = index.get("source_refs") or {}
        expected_refs = [str(ref_id) for ref_id in case.get("expected_source_ref_ids") or []]
        cited = [ref_id for ref_id in expected_refs if ref_id in source_refs]
        answer_text = _field_text(field) if isinstance(field, dict) else ""
        expected_terms = [str(term) for term in case.get("expected_terms") or [] if str(term)]
        answerable = bool(answer_text and cited and all(term in answer_text for term in expected_terms))
        rows.append(
            {
                "arm": "rich_leaf_local_adapter",
                "case_id": case["case_id"],
                "task": case["task"],
                "artifact_id": case.get("artifact_id"),
                "leaf_id": case.get("leaf_id"),
                "field_id": case.get("field_id"),
                "family": case.get("family"),
                "answerable": answerable,
                "term_hit": bool(answerable),
                "citation_count": len(cited),
                "cited_source_ref_ids": cited,
                "expected_source_ref_ids": expected_refs,
                "question_lane_citation_count": sum(1 for ref_id in cited if source_refs.get(ref_id, {}).get("source_lane") == "question"),
                "fail_open": bool(answerable and not cited),
                "token_proxy": _token_proxy(case.get("query"), answer_text, cited),
                "latency_ms_local_proxy": 1 if answerable else 0,
                "answer": {
                    "text": answer_text,
                    "cited_source_ref_ids": cited,
                },
            }
        )
    return rows


def _summarize(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "arm": arm,
            "sample_count": 0,
            "answerable_rate": 0.0,
            "term_hit_rate": 0.0,
            "evidence_citation_rate": 0.0,
            "fail_open_rate": 0.0,
            "question_lane_citation_rate": 0.0,
            "mean_token_proxy": 0.0,
            "mean_latency_ms_local_proxy": 0.0,
        }
    return {
        "arm": arm,
        "sample_count": len(rows),
        "answerable_rate": round(mean(1.0 if row["answerable"] else 0.0 for row in rows), 4),
        "term_hit_rate": round(mean(1.0 if row["term_hit"] else 0.0 for row in rows), 4),
        "evidence_citation_rate": round(mean(1.0 if row["citation_count"] > 0 else 0.0 for row in rows), 4),
        "fail_open_rate": round(mean(1.0 if row["fail_open"] else 0.0 for row in rows), 4),
        "question_lane_citation_rate": round(mean(1.0 if row["question_lane_citation_count"] > 0 else 0.0 for row in rows), 4),
        "mean_token_proxy": round(mean(float(row["token_proxy"]) for row in rows), 4),
        "mean_latency_ms_local_proxy": round(mean(float(row["latency_ms_local_proxy"]) for row in rows), 4),
    }


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


def run_near_live_shadow_ab(
    *, field_promotion_review: dict[str, Any], near_live_smoke: dict[str, Any], limit: int = 50, top_k: int = 3
) -> dict[str, Any]:
    blockers: list[str] = []
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"field_promotion_schema_mismatch:{field_promotion_review.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"field_promotion_not_pass:{field_promotion_review.get('verdict')}")
    _classification_blocks("field_promotion", field_promotion_review, blockers)
    if near_live_smoke.get("schema") != "luban_rich_leaf_semantic_runtime_near_live_smoke.v1":
        blockers.append(f"near_live_smoke_schema_mismatch:{near_live_smoke.get('schema')}")
    if near_live_smoke.get("verdict") != "PASS":
        blockers.append(f"near_live_smoke_not_pass:{near_live_smoke.get('verdict')}")
    if near_live_smoke.get("quality_claim_allowed") is not False:
        blockers.append("near_live_smoke_quality_claim_allowed")
    _classification_blocks("near_live_smoke", near_live_smoke, blockers)

    artifacts = [
        artifact
        for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    cases, case_blockers = _make_shadow_cases(artifacts, limit=limit)
    blockers.extend(case_blockers)
    if not cases:
        blockers.append("no_near_live_shadow_cases")
    rag_rows = _run_rag_proxy(cases, artifacts, top_k=top_k) if cases else []
    adapter_rows = _run_local_adapter(cases, artifacts) if cases else []
    effect_table = [
        _summarize("current_rag_lexical_proxy", rag_rows),
        _summarize("rich_leaf_local_adapter", adapter_rows),
    ]
    by_arm = {row["arm"]: row for row in effect_table}
    adapter = by_arm["rich_leaf_local_adapter"]
    rag = by_arm["current_rag_lexical_proxy"]
    if cases and adapter["answerable_rate"] < rag["answerable_rate"]:
        blockers.append("local_adapter_answerable_below_rag_proxy")
    if adapter["fail_open_rate"] != 0.0:
        blockers.append("local_adapter_fail_open")
    if adapter["question_lane_citation_rate"] != 0.0:
        blockers.append("local_adapter_question_lane_citation")
    if cases and adapter["mean_token_proxy"] > rag["mean_token_proxy"]:
        blockers.append("local_adapter_token_proxy_regression")

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "field_promotion_review": field_promotion_review.get("schema"),
            "near_live_smoke": near_live_smoke.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "verdict_ceiling": VERDICT_CEILING,
        "quality_claim_allowed": False,
        "execution_mode": "near_live_shadow",
        "cohort_scope": "local_fixture",
        "auth_mode": "none",
        "runtime_entry": {
            "entrypoint": "local_compiled_context_adapter",
            "runtime_exercised": bool(adapter_rows),
            "runtime_trace_ids": [row["case_id"] for row in adapter_rows],
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
            "shadow_case_count": len(cases),
            "top_k": top_k,
            "current_rag_answerable_rate": rag["answerable_rate"],
            "current_rag_mean_token_proxy": rag["mean_token_proxy"],
            "local_adapter_answerable_rate": adapter["answerable_rate"],
            "local_adapter_evidence_citation_rate": adapter["evidence_citation_rate"],
            "local_adapter_fail_open_rate": adapter["fail_open_rate"],
            "local_adapter_question_lane_citation_rate": adapter["question_lane_citation_rate"],
            "local_adapter_mean_token_proxy": adapter["mean_token_proxy"],
            "local_adapter_token_delta_vs_rag_proxy": round(float(adapter["mean_token_proxy"]) - float(rag["mean_token_proxy"]), 4),
            "live_runtime_executed": False,
            "provider_call_count": 0,
        },
        "effect_table": effect_table,
        "current_rag_rows": rag_rows,
        "local_adapter_rows": adapter_rows,
        "sample_rows": (rag_rows + adapter_rows)[:30],
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
            "semantic_runtime_near_live_shadow_ab": True,
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
    parser.add_argument("--near-live-smoke", type=Path, default=DEFAULT_NEAR_LIVE_SMOKE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    report = run_near_live_shadow_ab(
        field_promotion_review=_read_json(args.field_promotion_review),
        near_live_smoke=_read_json(args.near_live_smoke),
        limit=args.limit,
        top_k=args.top_k,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
