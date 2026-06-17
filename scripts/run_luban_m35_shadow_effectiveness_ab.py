#!/usr/bin/env python3
"""Shadow effectiveness A/B for M35/M36 live-council candidate gold.

This runner is deliberately NOT a release gate. It answers a narrower product
question: does the compiled/artifact-first scoring path beat a weak legacy
keyword projection against the same shadow candidate gold, and what remains
not-exercised because no offline adapter exists.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any


DEFAULT_GOLD_DIR = Path(
    "artifacts/luban_grading_artifacts/"
    "m35_m36_v2_live_council_gold_full150_20260611"
)
DEFAULT_SHADOW_DIR = Path(
    "artifacts/luban_grading_artifacts/"
    "m35_m36_v2_shadow_candidate_gold_full150_20260611"
)
DEFAULT_MANIFEST = Path("/tmp/m35_m36_v2_council_fixture/manifest.json")
DEFAULT_RAG_CORPUS_ROOT = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库"
)

POSITIVE_STATUSES = {"hit", "partial"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _compact(text: Any) -> str:
    return re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’/／~\\-]+", "", str(text or ""))


def _token_proxy(value: Any) -> int:
    return max(1, round(len(str(value or "")) / 2))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _status_score(status: str, max_score: float) -> float:
    if status == "hit":
        return max_score
    if status == "partial":
        return max_score * 0.5
    return 0.0


def _split_units(criterion: str) -> list[str]:
    text = str(criterion or "")
    text = re.sub(r"^【解析】", "", text).strip()
    units = [
        item.strip()
        for item in re.split(r"(?:；|;|\n|。|，(?=[^，]{2,24}(?:；|。|$)))", text)
        if item.strip()
    ]
    if len(units) <= 1:
        units = [item.strip() for item in re.split(r"[、,，]", text) if item.strip()]
    cleaned: list[str] = []
    for unit in units:
        unit = re.sub(r"^[（(]?\d+[）)]\s*", "", unit).strip()
        unit = re.sub(r"^[①②③④⑤⑥⑦⑧⑨]\s*", "", unit).strip()
        if len(_compact(unit)) >= 2:
            cleaned.append(unit)
    return list(dict.fromkeys(cleaned)) or [text]


def _numbers(text: str) -> list[str]:
    return re.findall(
        r"\d+(?:\.\d+)?\s*(?:万元|亿元|个月|周|天|月|小时|元/m³|元/m3|kg|m³|m3|m2|㎡|%|人|个|t)?",
        text,
        flags=re.I,
    )


def _is_calculation_point(point: dict[str, Any]) -> bool:
    text = str(point.get("criterion") or "")
    policy_type = str(point.get("policy_type") or "").strip().lower()
    return bool(
        policy_type in {"calculation", "calc"}
        or re.search(r"计算|列式|多少|工期|费用|价款|造价|成本|=|＝", text)
    )


def _is_low_signal_unit(unit: str) -> bool:
    compact = _compact(unit)
    if len(compact) < 2:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?", compact):
        return True
    return False


def _numeric_anchors(text: str) -> list[str]:
    anchors: list[str] = []
    for raw in _numbers(text):
        compact = _compact(raw)
        if not compact:
            continue
        has_unit_or_percent = bool(re.search(r"[^\d.]", compact))
        if has_unit_or_percent or len(re.sub(r"\D", "", compact)) >= 2:
            anchors.append(compact)
    return list(dict.fromkeys(anchors))


def _legacy_keywords(point: dict[str, Any]) -> list[str]:
    """Weak legacy proxy: short lexical chunks from the criterion.

    This is a proxy for the older broad keyword/projection behavior, not a live
    RAG replay. The report labels it accordingly.
    """
    text = str(point.get("criterion") or "")
    units = _split_units(text)
    keywords: list[str] = []
    for unit in units:
        compact = _compact(unit)
        if len(compact) >= 3:
            keywords.append(compact[: min(12, len(compact))])
    return list(dict.fromkeys(keywords))[:5]


def _artifact_units(point: dict[str, Any]) -> list[str]:
    """Compiled/artifact-first deterministic units.

    Calculation points use numeric anchors. Other points use split criterion
    units. No synonym expansion, no model call, no RAG lookup.
    """
    criterion = str(point.get("criterion") or "")
    if _is_calculation_point(point):
        nums = _numeric_anchors(criterion)
        if nums:
            return list(dict.fromkeys(nums))
    return [
        _compact(unit)
        for unit in _split_units(criterion)
        if _compact(unit) and not _is_low_signal_unit(unit)
    ]


def _score_legacy(point: dict[str, Any], answer: str) -> tuple[str, float, list[str], dict[str, Any]]:
    answer_c = _compact(answer)
    keywords = _legacy_keywords(point)
    matched = [kw for kw in keywords if kw and kw in answer_c]
    max_score = float(point.get("max_score") or 0.0)
    if matched:
        return "hit", max_score, matched, {"decision": "legacy_keyword_match"}
    return "miss", 0.0, [], {"decision": "legacy_no_keyword_match"}


def _score_artifact(point: dict[str, Any], answer: str) -> tuple[str, float, list[str], dict[str, Any]]:
    answer_c = _compact(answer)
    units = _artifact_units(point)
    matched = [unit for unit in units if unit and unit in answer_c]
    max_score = float(point.get("max_score") or 0.0)
    if not units or not matched:
        return "miss", 0.0, [], {"decision": "no_compiled_unit_match", "unit_count": len(units)}
    if len(matched) == len(units):
        return (
            "hit",
            max_score,
            matched,
            {"decision": "all_compiled_units_matched", "unit_count": len(units)},
        )
    coverage = len(matched) / len(units)
    if not _is_calculation_point(point) and len(units) >= 3 and coverage < 0.15:
        return (
            "miss",
            0.0,
            matched,
            {
                "decision": "downgraded_low_evidence_coverage",
                "unit_count": len(units),
                "matched_count": len(matched),
                "coverage": round(coverage, 6),
            },
        )
    return (
        "partial",
        round(max_score * coverage, 6),
        matched,
        {
            "decision": "partial_compiled_units_matched",
            "unit_count": len(units),
            "matched_count": len(matched),
            "coverage": round(coverage, 6),
        },
    )


def _score_current_rag(
    point: dict[str, Any],
    answer: str,
    retrieved_context: str,
) -> tuple[str, float, list[str], dict[str, Any]]:
    answer_c = _compact(answer)
    context_c = _compact(retrieved_context)
    units = _artifact_units(point)
    context_units = [unit for unit in units if unit and unit in context_c]
    matched = [unit for unit in context_units if unit in answer_c]
    max_score = float(point.get("max_score") or 0.0)
    if not context_units:
        return (
            "miss",
            0.0,
            [],
            {"decision": "rag_context_missing_compiled_units", "unit_count": len(units)},
        )
    if not matched:
        return (
            "miss",
            0.0,
            [],
            {
                "decision": "student_answer_missing_rag_supported_units",
                "rag_supported_unit_count": len(context_units),
            },
        )
    if len(matched) == len(context_units):
        return (
            "hit",
            max_score,
            matched,
            {"decision": "all_rag_supported_units_matched", "rag_supported_unit_count": len(context_units)},
        )
    coverage = len(matched) / len(context_units)
    if not _is_calculation_point(point) and len(context_units) >= 3 and coverage < 0.15:
        return (
            "miss",
            0.0,
            matched,
            {
                "decision": "downgraded_low_rag_supported_coverage",
                "rag_supported_unit_count": len(context_units),
                "matched_count": len(matched),
                "coverage": round(coverage, 6),
            },
        )
    return (
        "partial",
        round(max_score * coverage, 6),
        matched,
        {
            "decision": "partial_rag_supported_units_matched",
            "rag_supported_unit_count": len(context_units),
            "matched_count": len(matched),
            "coverage": round(coverage, 6),
        },
    )


def _load_offline_rag_corpus(root: Path | None) -> list[dict[str, Any]]:
    if root is None or not root.exists():
        return []
    docs: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/FINAL_CLEANED_EXAM_V*.json")):
        try:
            data = _read_json(path)
        except Exception:
            continue
        for chunk in data.get("chunks") or []:
            if not isinstance(chunk, dict):
                continue
            source_meta = chunk.get("source_meta") if isinstance(chunk.get("source_meta"), dict) else {}
            taxonomy = chunk.get("taxonomy") if isinstance(chunk.get("taxonomy"), dict) else {}
            parts = [
                taxonomy.get("node_code"),
                taxonomy.get("node_name"),
                chunk.get("content_markdown"),
            ]
            for exercise in chunk.get("exercises") or []:
                qd = exercise.get("question_data") if isinstance(exercise, dict) else {}
                if not isinstance(qd, dict):
                    continue
                parts.extend(
                    [
                        qd.get("stem"),
                        qd.get("correct_answer"),
                        qd.get("analysis"),
                        qd.get("logic_chain"),
                    ]
                )
            content = "\n".join(str(part) for part in parts if str(part or "").strip())
            if not content.strip():
                continue
            docs.append(
                {
                    "chunk_id": chunk.get("chunk_id") or path.stem,
                    "title": source_meta.get("source") or path.parent.name,
                    "source_year": source_meta.get("exam_year"),
                    "path": str(path),
                    "content": content,
                    "compact": _compact(content),
                }
            )
    return docs


def _query_terms(text: str) -> list[str]:
    compact = _compact(text)
    terms = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z0-9]{2,16}", compact)
    return list(dict.fromkeys(terms))


def _retrieve_current_rag_offline(
    *,
    question: dict[str, Any],
    corpus: list[dict[str, Any]],
    top_k: int = 3,
) -> dict[str, Any]:
    if not corpus:
        return {"status": "not_exercised", "reason": "offline RAG corpus is missing", "sources": []}
    query = str(question.get("stem") or "")
    source_ids = {
        str(ref.get("chunk_id") or "")
        for ref in question.get("source_refs") or []
        if isinstance(ref, dict) and ref.get("chunk_id")
    }
    terms = _query_terms(query)[:120]
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in corpus:
        score = 0.0
        if source_ids and str(doc.get("chunk_id") or "") in source_ids:
            score += 1000.0
        content_c = str(doc.get("compact") or "")
        for term in terms:
            if term and term in content_c:
                score += len(term)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    sources = [
        {
            "chunk_id": doc.get("chunk_id"),
            "title": doc.get("title"),
            "source_year": doc.get("source_year"),
            "score": round(score, 6),
            "content": str(doc.get("content") or "")[:1200],
        }
        for score, doc in scored[:top_k]
    ]
    return {
        "status": "exercised" if sources else "not_exercised",
        "reason": "" if sources else "offline RAG retrieval returned no sources",
        "query": query[:900],
        "source_count": len(sources),
        "sources": sources,
        "content": "\n\n".join(str(source.get("content") or "") for source in sources),
    }


def _questions_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(question.get("question_id") or ""): question
        for question in manifest.get("questions") or []
        if question.get("question_id")
    }


def create_shadow_candidate_gold(*, source_dir: Path, output_dir: Path) -> dict[str, Any]:
    source_answers = source_dir / "student_answers.jsonl"
    source_manifest = source_dir / "manifest.json"
    rows = _read_jsonl(source_answers)
    manifest = _read_json(source_manifest)
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        original_label = row.get("label_authority")
        out = dict(row)
        out["source_label_authority"] = original_label
        out["label_authority"] = "shadow_candidate_gold"
        out["directionality_flag"] = "shadow_candidate_gold"
        out["is_release_truth"] = False
        out["official_score_allowed"] = False
        out["quality_claim_allowed"] = False
        out["shadow_candidate_gold"] = {
            "basis": "m35_m36_v2_live_council_full150",
            "source_label_authority": original_label,
            "release_truth": False,
            "runtime_main_grader": False,
        }
        out_rows.append(out)

    output_dir.mkdir(parents=True, exist_ok=True)
    answers_out = output_dir / "student_answers.jsonl"
    _write_jsonl(answers_out, out_rows)
    shadow_manifest = {
        **manifest,
        "schema_version": "m35_m36_v2_shadow_candidate_gold_full150.v1",
        "source_artifact_dir": str(source_dir),
        "row_count": len(out_rows),
        "label_authority": "shadow_candidate_gold",
        "label_authority_counts": dict(Counter(row["label_authority"] for row in out_rows)),
        "source_label_authority_counts": dict(
            Counter(str(row.get("source_label_authority") or "") for row in out_rows)
        ),
        "sample_bucket_counts": dict(Counter(str(row.get("sample_bucket") or "") for row in out_rows)),
        "is_release_truth": False,
        "official_score_allowed": False,
        "quality_claim_allowed": False,
        "release_truth_blocker": "shadow_candidate_gold_not_governance_signed",
        "student_answers_sha256": _sha256(answers_out),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(shadow_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return shadow_manifest


def _gold_reference(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = {}
    for point in row.get("gold_point_matches") or []:
        point_id = str(point.get("point_id") or "")
        if not point_id:
            continue
        status = str(point.get("status") or "miss")
        max_score = float(point.get("max_score") or 0.0)
        gold[point_id] = {
            "status": status,
            "score": float(point.get("awarded_score") if point.get("awarded_score") is not None else _status_score(status, max_score)),
            "max_score": max_score,
        }
    return gold


def _evaluate_arm(
    *,
    arm: str,
    row: dict[str, Any],
    question: dict[str, Any],
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    predictions: dict[str, dict[str, Any]] = {}
    for point in question.get("scoring_points") or []:
        point_id = str(point.get("point_id") or "")
        if not point_id:
            continue
        if arm == "artifact_first_compiled":
            status, score, evidence, guard = _score_artifact(point, str(row.get("student_answer") or ""))
        elif arm == "current_rag":
            status, score, evidence, guard = _score_current_rag(
                point,
                str(row.get("student_answer") or ""),
                str((retrieval or {}).get("content") or ""),
            )
        else:
            status, score, evidence, guard = _score_legacy(point, str(row.get("student_answer") or ""))
        predictions[point_id] = {
            "status": status,
            "score": score,
            "evidence": evidence,
            "guard": guard,
            "max_score": float(point.get("max_score") or 0.0),
        }
    latency_ms = (time.perf_counter() - started) * 1000
    context_basis = {
        "legacy_keyword_projection": {
            "stem": question.get("stem"),
            "criteria": [p.get("criterion") for p in question.get("scoring_points") or []],
            "mode": "weak_legacy_keyword_projection",
        },
        "artifact_first_compiled": {
            "scoring_points": [
                {
                    "point_id": p.get("point_id"),
                    "policy_type": p.get("policy_type"),
                    "max_score": p.get("max_score"),
                    "units": _artifact_units(p),
                }
                for p in question.get("scoring_points") or []
            ],
            "mode": "compiled_units_no_rag",
        },
        "current_rag": {
            "retrieved_sources": [
                {
                    "chunk_id": source.get("chunk_id"),
                    "title": source.get("title"),
                    "source_year": source.get("source_year"),
                }
                for source in (retrieval or {}).get("sources", [])
            ],
            "retrieved_content": (retrieval or {}).get("content") or "",
            "mode": "offline_current_rag_retrieval_projection",
        },
    }[arm]
    out = {
        "arm": arm,
        "answer_id": row.get("answer_id"),
        "question_id": row.get("question_id"),
        "predictions": predictions,
        "pred_score": round(sum(item["score"] for item in predictions.values()), 6),
        "latency_ms": round(latency_ms, 6),
        "token_proxy": _token_proxy(context_basis) + _token_proxy(row.get("student_answer")),
    }
    if arm == "current_rag":
        out["retrieval"] = {
            "status": (retrieval or {}).get("status"),
            "reason": (retrieval or {}).get("reason") or "",
            "source_count": (retrieval or {}).get("source_count") or 0,
            "sources": context_basis["retrieved_sources"],
        }
    return out


def _arm_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "not_exercised",
            "reason": "no rows evaluated",
        }
    score_abs_errors: list[float] = []
    point_tp = point_fp = point_fn = 0
    fail_open_rows = 0
    evidence_positive = 0
    evidence_with_span = 0
    token_proxy_values: list[float] = []
    latency_values: list[float] = []
    for row in rows:
        gold = row["gold"]
        pred = row["predictions"]
        gold_score = sum(item["score"] for item in gold.values())
        score_abs_errors.append(abs(float(row["pred_score"]) - gold_score))
        gold_pos = {pid for pid, item in gold.items() if item["status"] in POSITIVE_STATUSES}
        pred_pos = {pid for pid, item in pred.items() if item["score"] > 0}
        point_tp += len(gold_pos & pred_pos)
        point_fp += len(pred_pos - gold_pos)
        point_fn += len(gold_pos - pred_pos)
        if pred_pos - gold_pos:
            fail_open_rows += 1
        for pid in pred_pos:
            evidence_positive += 1
            if pred.get(pid, {}).get("evidence"):
                evidence_with_span += 1
        token_proxy_values.append(float(row["token_proxy"]))
        latency_values.append(float(row["latency_ms"]))

    precision = point_tp / (point_tp + point_fp) if point_tp + point_fp else 0.0
    recall = point_tp / (point_tp + point_fn) if point_tp + point_fn else 0.0
    return {
        "status": "exercised",
        "sample_count": len(rows),
        "score_mae": round(sum(score_abs_errors) / len(score_abs_errors), 6),
        "point_precision": round(precision, 6),
        "point_recall": round(recall, 6),
        "fail_open_rate": round(fail_open_rows / len(rows), 6),
        "evidence_positive_count": evidence_positive,
        "evidence_span_rate": round(evidence_with_span / evidence_positive, 6)
        if evidence_positive
        else 0.0,
        "mean_token_proxy": round(sum(token_proxy_values) / len(token_proxy_values), 6),
        "mean_latency_ms": round(sum(latency_values) / len(latency_values), 6),
    }


def build_effectiveness_report(
    *,
    answers_path: Path,
    manifest_path: Path,
    fixture_limit: int,
    rag_corpus_root: Path | None = None,
) -> dict[str, Any]:
    rows = _read_jsonl(answers_path)
    if fixture_limit > 0:
        rows = rows[:fixture_limit]
    manifest = _read_json(manifest_path)
    questions = _questions_by_id(manifest)
    rag_corpus = _load_offline_rag_corpus(rag_corpus_root)
    evaluated: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: list[dict[str, Any]] = []

    for row in rows:
        qid = str(row.get("question_id") or "")
        question = questions.get(qid)
        if not question:
            skipped.append({"answer_id": row.get("answer_id"), "reason": "question_missing"})
            continue
        gold = _gold_reference(row)
        if not gold:
            skipped.append({"answer_id": row.get("answer_id"), "reason": "gold_point_matches_missing"})
            continue
        retrieval = _retrieve_current_rag_offline(question=question, corpus=rag_corpus)
        for arm in ("legacy_keyword_projection", "artifact_first_compiled", "current_rag"):
            if arm == "current_rag" and retrieval.get("status") != "exercised":
                continue
            item = _evaluate_arm(arm=arm, row=row, question=question, retrieval=retrieval)
            item["gold"] = gold
            item["source_label_authority"] = row.get("source_label_authority") or row.get("label_authority")
            item["sample_bucket"] = row.get("sample_bucket")
            evaluated[arm].append(item)

    arm_metrics = {arm: _arm_metrics(values) for arm, values in sorted(evaluated.items())}
    if "current_rag" not in arm_metrics:
        arm_metrics["current_rag"] = {
            "status": "not_exercised",
            "reason": (
                "offline RAG corpus missing or returned no sources; no provider call was made"
            ),
            "corpus_root": str(rag_corpus_root) if rag_corpus_root else "",
        }
    elif isinstance(arm_metrics["current_rag"], dict):
        arm_metrics["current_rag"]["corpus_root"] = str(rag_corpus_root) if rag_corpus_root else ""
        arm_metrics["current_rag"]["corpus_document_count"] = len(rag_corpus)
    arm_metrics["artifact_first_llm_judge"] = {
        "status": "not_exercised_as_runtime",
        "reason": "live council labels are used as shadow reference/audit sample, not as a main runtime arm",
    }

    legacy = arm_metrics.get("legacy_keyword_projection") or {}
    artifact = arm_metrics.get("artifact_first_compiled") or {}
    comparison: dict[str, Any] = {"basis": "artifact_first_compiled_vs_legacy_keyword_projection"}
    if legacy.get("status") == "exercised" and artifact.get("status") == "exercised":
        comparison.update(
            {
                "accuracy_not_worse": artifact["score_mae"] <= legacy["score_mae"],
                "token_proxy_lower": artifact["mean_token_proxy"] < legacy["mean_token_proxy"],
                "latency_lower": artifact["mean_latency_ms"] < legacy["mean_latency_ms"],
                "evidence_not_worse": artifact["evidence_span_rate"] >= legacy["evidence_span_rate"],
                "fail_open_not_worse": artifact["fail_open_rate"] <= legacy["fail_open_rate"],
                "score_mae_delta_vs_legacy": round(artifact["score_mae"] - legacy["score_mae"], 6),
                "token_proxy_delta_vs_legacy": round(
                    artifact["mean_token_proxy"] - legacy["mean_token_proxy"], 6
                ),
                "latency_delta_ms_vs_legacy": round(
                    artifact["mean_latency_ms"] - legacy["mean_latency_ms"], 6
                ),
            }
        )

    return {
        "schema_version": "m35_m36_shadow_effectiveness_ab.v1",
        "goal": "shadow effectiveness, not release truth",
        "fixture": {
            "answers_path": str(answers_path),
            "manifest_path": str(manifest_path),
            "fixture_limit": fixture_limit,
            "evaluated_answer_count": len(rows) - len(skipped),
            "skipped_answer_count": len(skipped),
            "rag_corpus_root": str(rag_corpus_root) if rag_corpus_root else "",
            "rag_corpus_document_count": len(rag_corpus),
        },
        "reference": {
            "authority": "shadow_candidate_gold",
            "is_release_truth": False,
            "official_score_allowed": False,
            "quality_claim_allowed": False,
        },
        "arms": arm_metrics,
        "comparison": comparison,
        "safety": {
            "production_write_count": 0,
            "canonical_truth_written": False,
            "db_write_count": 0,
            "remote_write_count": 0,
            "provider_call_count": 0,
        },
        "skipped": skipped,
        "rows_sample": {
            arm: values[:5]
            for arm, values in evaluated.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-gold-dir", type=Path, default=DEFAULT_GOLD_DIR)
    parser.add_argument("--shadow-output-dir", type=Path, default=DEFAULT_SHADOW_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--rag-corpus-root", type=Path, default=DEFAULT_RAG_CORPUS_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-limit", type=int, default=0)
    args = parser.parse_args()

    shadow_manifest = create_shadow_candidate_gold(
        source_dir=args.source_gold_dir,
        output_dir=args.shadow_output_dir,
    )
    report = build_effectiveness_report(
        answers_path=args.shadow_output_dir / "student_answers.jsonl",
        manifest_path=args.manifest,
        fixture_limit=args.fixture_limit,
        rag_corpus_root=args.rag_corpus_root,
    )
    report["shadow_candidate_gold_manifest"] = {
        "path": str(args.shadow_output_dir / "manifest.json"),
        "row_count": shadow_manifest.get("row_count"),
        "student_answers_sha256": shadow_manifest.get("student_answers_sha256"),
        "label_authority": shadow_manifest.get("label_authority"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
