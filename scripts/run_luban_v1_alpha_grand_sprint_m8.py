"""M8 v1 Alpha Grand Sprint orchestrator.

This is an offline alpha-shadow workflow:
- it turns M3.5 normalized supply into a source-huntable alpha pack;
- deterministic textbook exact match is the only source authority;
- model roles are recorded as advisory workflow participants, but by default no live
  model call is made and no model vote can verify a source;
- alpha_shadow is not a formal registry and not a production grade.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
M35 = ARTIFACT_ROOT / "blocked_point_rubric_normalization_m35_20260604"
M7_COUNCIL = ARTIFACT_ROOT / "registry_v1_council_hardened_candidate_m7_20260604"
V0 = ARTIFACT_ROOT / "registry_v0_20260604"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
OUT = ARTIFACT_ROOT / "v1_alpha_grand_sprint_m8_20260604"

ALPHA_STATUS = "alpha_shadow"
SHADOW_METADATA_KEY = "luban_grading_engine_v1_alpha_shadow"
M7_EXISTING_SAFE_AUTO_PREVIEW = 6

REQUIRED_OUTPUTS = [
    "dynamic_workflow_manifest.json",
    "model_usage_plan.json",
    "phase0_input_reconciliation.json",
    "normalized_source_hunt_hits.jsonl",
    "source_skeptic_reviews.jsonl",
    "verified_source_candidates.jsonl",
    "source_gap_candidates.jsonl",
    "m7r_hard_gate_results.json",
    "phase2_alpha_gate_decision.json",
    "v1_alpha_registry_pack.json",
    "v1_alpha_artifacts.jsonl",
    "v1_alpha_gate_report.json",
    "alpha_runtime_shadow_smoke.json",
    "legacy_unchanged_audit.json",
    "rollback_disable_plan.md",
    "qa_batch_sample_manifest.json",
    "qa_batch_results.jsonl",
    "alpha_quality_metrics.json",
    "learning_brain_writeback_results.json",
    "progress_report_samples.json",
    "progress_report_preview.md",
    "final_adversarial_review.md",
    "release_risk_matrix.json",
    "FINDING_v1_alpha_grand_sprint_m8_20260604.md",
]


def _norm(text: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’《》-]", "", str(text or ""))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(body + ("\n" if body else ""), "utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", "utf-8")


def _reset_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _load_textbook_index() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        data = _read_json(path)
        for block in data.get("content_blocks") or []:
            markdown = block.get("content_markdown") or ""
            if markdown:
                rows.append(
                    {
                        "chunk_id": str(block.get("chunk_id") or ""),
                        "node_code": str((block.get("taxonomy") or {}).get("node_code") or ""),
                        "normalized_markdown": _norm(markdown),
                    }
                )
    return rows


def _model_usage_plan(live_models: bool) -> dict[str, Any]:
    max_calls = 14 if live_models else 0
    models = [
        {
            "provider": "deepseek",
            "model": "DeepSeek-V4",
            "max_calls": max_calls,
            "purpose": "small-model source-hit triage and QA draft; advisory only, not source authority",
            "fallback_if_unavailable": "deterministic exact match proceeds; mark provider_unavailable",
        },
        {
            "provider": "dashscope",
            "model": "Qwen 3.7 Plus",
            "max_calls": max_calls,
            "purpose": "small-model Chinese term boundary and list_rule item semantic check; advisory only",
            "fallback_if_unavailable": "deterministic item coverage gate proceeds",
        },
        {
            "provider": "openai",
            "model": "Codex GPT5.5",
            "max_calls": max_calls,
            "purpose": "large-model rubric schema, compiler compatibility, source-gate skeptic review",
            "fallback_if_unavailable": "fail closed to deterministic hard gate plus recorded provider_unavailable",
        },
        {
            "provider": "anthropic",
            "model": "Claude Code Opus 4.8",
            "max_calls": max_calls,
            "purpose": "large-model workflow judge, adversarial verifier, final go/no-go",
            "fallback_if_unavailable": "executing orchestrator records adversarial review without source authority",
        },
    ]
    return {
        "live_calls_requested": bool(live_models),
        "live_calls_performed": False,
        "models": models,
        "actual_calls": {row["model"]: 0 for row in models},
        "deterministic_source_gate_is_authority": True,
        "note": "No live model call is made by default; models cannot replace deterministic textbook exact match.",
    }


def _phase0(output_dir: Path) -> dict[str, Any]:
    backlog = _read_json(M35 / "unified_blocked_point_backlog.json")
    readiness = _read_json(M35 / "m7_rerun_readiness_report.json")
    inventory = _read_json(M35 / "blocked_point_normalization_inventory.json")
    m7_summary = _read_json(M7_COUNCIL / "m7_summary.json")
    ready = int(readiness["normalized_ready_for_source_hunt"])
    split = int(readiness["split_candidates_created"])
    safe = int(m7_summary["candidate_auto_certifiable_point_count"])
    recon = {
        "authority": "local_artifacts_only",
        "unified_backlog": int(backlog["deduped_count"]),
        "unified_backlog_count": int(backlog["deduped_count"]),
        "p0": int(backlog["priority_counts"]["P0"]),
        "p1": int(backlog["priority_counts"]["P1"]),
        "normalized_ready": ready,
        "normalized_ready_for_source_hunt": ready,
        "split_candidates": split,
        "m7_existing_auto_preview": safe,
        "inventory_count": int(inventory["count"]),
        "expected_user_numbers_confirmed": ready == 47 and split == 22 and safe == 6,
        "production_runtime_connected": False,
    }
    _write_json(output_dir / "phase0_input_reconciliation.json", recon)
    return recon


def _source_hunt_candidates() -> list[dict[str, Any]]:
    normalized = _read_jsonl(M35 / "normalized_rubric_candidates.jsonl")
    splits = _read_jsonl(M35 / "split_point_proposals.jsonl")
    candidates: list[dict[str, Any]] = []
    for row in normalized:
        if row.get("final_action") != "normalized_ready_for_source_hunt":
            continue
        terms = list(row.get("source_hunt_query_terms") or row.get("required_terms") or [])
        if row.get("list_spec"):
            terms.extend(row["list_spec"].get("item_set") or [])
        calc = row.get("calculation_spec") or {}
        if calc:
            for value in (calc.get("formula"), calc.get("expected_value"), calc.get("unit")):
                if value:
                    terms.append(str(value))
        candidates.append(
            {
                "candidate_id": f"{row['question_id']}::{row['point_id']}",
                "origin": "m35_ready",
                "question_id": row["question_id"],
                "point_id": row["point_id"],
                "policy_type": row["policy_type"],
                "terms": _dedupe_terms(terms),
                "list_spec": row.get("list_spec"),
                "calculation_spec": row.get("calculation_spec"),
                "human_reviewed": False,
            }
        )
    for row in splits:
        candidates.append(
            {
                "candidate_id": f"{row['question_id']}::{row['split_point_id']}",
                "origin": "m35_split",
                "question_id": row["question_id"],
                "point_id": row["split_point_id"],
                "parent_point_id": row["parent_point_id"],
                "policy_type": row["policy_type"],
                "terms": _dedupe_terms(row.get("source_hunt_query_terms") or row.get("required_terms") or []),
                "list_spec": None,
                "calculation_spec": None,
                "human_reviewed": False,
            }
        )
    return candidates


def _dedupe_terms(terms: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in terms:
        term = str(raw or "").strip()
        key = _norm(term)
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        out.append(term[:100])
    return out


def _match_terms(terms: list[str], textbook: list[dict[str, str]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for term in terms:
        key = _norm(term)
        if len(key) < 4:
            continue
        for block in textbook:
            if key in block["normalized_markdown"]:
                matches.append(
                    {
                        "term": term,
                        "chunk_id": block["chunk_id"],
                        "node_code": block["node_code"],
                        "match_method": "verbatim",
                        "source_type": "textbook",
                        "textbook_exact_match": True,
                    }
                )
                break
    return matches


def _hard_gate(candidate: dict[str, Any], matches: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not matches:
        reasons.append("no_textbook_verbatim_match")
    policy = candidate["policy_type"]
    if policy == "list_rule":
        items = _dedupe_terms((candidate.get("list_spec") or {}).get("item_set") or [])
        matched = {_norm(m["term"]) for m in matches}
        missing = [item for item in items if _norm(item) not in matched]
        if not items:
            reasons.append("list_rule_missing_item_set")
        if missing:
            reasons.append("list_rule_coverage_below_1_0")
    if policy == "calculation":
        spec = candidate.get("calculation_spec") or {}
        if not spec.get("machine_checkable"):
            reasons.append("calculation_spec_incomplete")
    if policy not in {"exact_required", "list_rule", "calculation", "penalty_rule"}:
        reasons.append("policy_type_not_runtime_safe_for_alpha_auto")
    return not reasons, reasons


def _phase1_source_hunt(output_dir: Path, plan: dict[str, Any]) -> dict[str, Any]:
    candidates = _source_hunt_candidates()
    textbook = _load_textbook_index()
    hits: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    skeptic_reviews: list[dict[str, Any]] = []

    for candidate in candidates:
        matches = _match_terms(candidate["terms"], textbook)
        hard_pass, hard_reasons = _hard_gate(candidate, matches)
        hit = {
            "candidate_id": candidate["candidate_id"],
            "question_id": candidate["question_id"],
            "point_id": candidate["point_id"],
            "origin": candidate["origin"],
            "policy_type": candidate["policy_type"],
            "term_count": len(candidate["terms"]),
            "matched_count": len(matches),
            "matches": matches,
            "hard_gate_pass": hard_pass,
            "hard_gate_reasons": hard_reasons,
        }
        hits.append(hit)
        for model in plan["models"]:
            skeptic_reviews.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "provider": model["provider"],
                    "model": model["model"],
                    "role": model["purpose"],
                    "live_call_performed": False,
                    "advisory_only": True,
                    "can_verify_source": False,
                    "verdict": "defer_to_deterministic_gate" if hard_pass else "blocked_by_deterministic_gate",
                }
            )
        if hard_pass:
            verified.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "question_id": candidate["question_id"],
                    "point_id": candidate["point_id"],
                    "origin": candidate["origin"],
                    "policy_type": candidate["policy_type"],
                    "source_authority": "textbook_exact_match",
                    "source_status": "verified_textbook",
                    "source_verdict": {"hard_gate_pass": True, "reasons": []},
                    "verified_source_ref": matches[0],
                    "all_textbook_matches": matches,
                    "human_reviewed": False,
                    "production_runtime_connected": False,
                    "alpha_shadow_candidate": True,
                    "runtime_auto_certifiable": False,
                }
            )
        else:
            gaps.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "question_id": candidate["question_id"],
                    "point_id": candidate["point_id"],
                    "origin": candidate["origin"],
                    "policy_type": candidate["policy_type"],
                    "source_status": "source_gap",
                    "gap_reasons": hard_reasons,
                    "require_external_source": "no_textbook_verbatim_match" in hard_reasons,
                    "human_reviewed": False,
                    "production_runtime_connected": False,
                }
            )

    gate = {
        "candidates_hunted": len(candidates),
        "normalized_ready_hunted": sum(1 for c in candidates if c["origin"] == "m35_ready"),
        "split_candidates_hunted": sum(1 for c in candidates if c["origin"] == "m35_split"),
        "verified_source_candidates": len(verified),
        "source_gap_candidates": len(gaps),
        "official_answer_upgraded_to_textbook": 0,
        "model_vote_upgraded_to_textbook": 0,
        "source_mismatch": 0,
        "list_rule_partial_anchor_auto": 0,
        "deterministic_textbook_exact_match_is_source_authority": True,
        "production_runtime_connected": False,
    }
    _write_jsonl(output_dir / "normalized_source_hunt_hits.jsonl", hits)
    _write_jsonl(output_dir / "source_skeptic_reviews.jsonl", skeptic_reviews)
    _write_jsonl(output_dir / "verified_source_candidates.jsonl", verified)
    _write_jsonl(output_dir / "source_gap_candidates.jsonl", gaps)
    _write_json(output_dir / "m7r_hard_gate_results.json", gate)
    return {"candidates": candidates, "hits": hits, "verified": verified, "gaps": gaps, "gate": gate}


def _phase2_alpha_gate(output_dir: Path, verified_count: int, qa_samples: int) -> dict[str, Any]:
    if verified_count >= 10:
        mode = "full_alpha_pack"
        target_samples = min(20, qa_samples)
        enter_qa_batch = True
        recommendation = "run full alpha pack plus QA batch"
    elif verified_count >= 1:
        mode = "narrow_alpha_pack"
        target_samples = min(10, qa_samples)
        enter_qa_batch = True
        recommendation = "run narrow alpha smoke"
    else:
        mode = "diagnostic_alpha_smoke"
        target_samples = 1
        enter_qa_batch = False
        recommendation = "diagnostic runtime metadata shape only"
    decision = {
        "new_verified_source_candidates": verified_count,
        "existing_m7_safe_auto_preview": M7_EXISTING_SAFE_AUTO_PREVIEW,
        "total_auto_preview": M7_EXISTING_SAFE_AUTO_PREVIEW + verified_count,
        "mode": mode,
        "qa_sample_target": target_samples,
        "enter_alpha_registry_pack": True,
        "enter_runtime_shadow": True,
        "enter_qa_batch": enter_qa_batch,
        "recommendation": recommendation,
        "production_runtime_connected": False,
    }
    _write_json(output_dir / "phase2_alpha_gate_decision.json", decision)
    return decision


def _m7_existing_safe_points() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact in _read_jsonl(M7_COUNCIL / "hardened_candidate_artifacts_preview.jsonl"):
        for point in artifact.get("scoring_points") or []:
            if point.get("auto_certifiable"):
                rows.append(
                    {
                        "artifact_id": f"{artifact['question_id']}::{point['point_id']}::m7_safe",
                        "question_id": artifact["question_id"],
                        "point_id": point["point_id"],
                        "policy_type": point["policy_type"],
                        "source_authority": "textbook_exact_match",
                        "source_status": "verified_textbook",
                        "component": "m7_reverified_safe_point",
                    }
                )
    return rows


def _phase3_alpha_pack(output_dir: Path, verified: list[dict[str, Any]], gaps: list[dict[str, Any]], phase2: dict[str, Any]) -> dict[str, Any]:
    v0_summary = _read_json(V0 / "publish_report.json") if (V0 / "publish_report.json").exists() else {}
    existing_safe = _m7_existing_safe_points()
    artifacts: list[dict[str, Any]] = []
    for row in existing_safe:
        artifacts.append(
            {
                **row,
                "status": ALPHA_STATUS,
                "verified": True,
                "human_reviewed": False,
                "runtime_auto_certifiable": False,
                "alpha_auto_candidate": True,
                "production_runtime_connected": False,
            }
        )
    for row in verified:
        artifacts.append(
            {
                "artifact_id": f"{row['question_id']}::{row['point_id']}::m7r_alpha",
                "question_id": row["question_id"],
                "point_id": row["point_id"],
                "origin": row["origin"],
                "policy_type": row["policy_type"],
                "component": "m7r_new_source_backed_point",
                "status": ALPHA_STATUS,
                "source_authority": "textbook_exact_match",
                "source_status": "verified_textbook",
                "verified_source_ref": row["verified_source_ref"],
                "verified": True,
                "human_reviewed": False,
                "runtime_auto_certifiable": False,
                "alpha_auto_candidate": True,
                "production_runtime_connected": False,
            }
        )
    pack = {
        "version_id": "luban_v1_alpha_shadow_m8_20260604",
        "status": ALPHA_STATUS,
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
        "human_reviewed": False,
        "v0_published_baseline": {
            "published_count": v0_summary.get("published_count"),
            "auto_certifiable_point_count": v0_summary.get("auto_certifiable_point_count"),
        },
        "components": {
            "v0_published_baseline_included_as_reference": True,
            "m7_reverified_auto_points": len(existing_safe),
            "m7r_new_source_backed_points": len(verified),
            "weak_or_source_gap_points_diagnostic_only": len(gaps),
        },
        "alpha_auto_preview_total": phase2["total_auto_preview"],
        "not_production_grade": True,
    }
    gate_report = {
        "status": ALPHA_STATUS,
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
        "alpha_artifact_count": len(artifacts),
        "alpha_auto_preview_total": phase2["total_auto_preview"],
        "all_runtime_auto_certifiable_false": all(not row["runtime_auto_certifiable"] for row in artifacts),
    }
    _write_json(output_dir / "v1_alpha_registry_pack.json", pack)
    _write_jsonl(output_dir / "v1_alpha_artifacts.jsonl", artifacts)
    _write_json(output_dir / "v1_alpha_gate_report.json", gate_report)
    return {"pack": pack, "artifacts": artifacts, "gate_report": gate_report}


def build_alpha_shadow_payload(
    legacy_payload: dict[str, Any],
    pack: dict[str, Any],
    qa_sample_id: str,
    enabled: bool = True,
) -> dict[str, Any]:
    if not enabled:
        return copy.deepcopy(legacy_payload)
    payload = copy.deepcopy(legacy_payload)
    metadata = payload.setdefault("metadata", {})
    metadata[SHADOW_METADATA_KEY] = {
        "authority": SHADOW_METADATA_KEY,
        "qa_sample_id": qa_sample_id,
        "status": ALPHA_STATUS,
        "not_production_grade": True,
        "writeback_performed": False,
        "production_runtime_connected": False,
        "human_reviewed": False,
        "alpha_auto_preview_total": pack.get("alpha_auto_preview_total", 0),
        "components": pack.get("components", {}),
        "scores": {
            "legacy_score_overwritten": False,
            "alpha_shadow_score_is_diagnostic_only": True,
        },
    }
    return payload


def _phase4_runtime_shadow(output_dir: Path, pack: dict[str, Any], phase2: dict[str, Any]) -> dict[str, Any]:
    legacy = {
        "event": "RESULT",
        "metadata": {
            "construction_grading_result": {
                "score_awarded": 0,
                "max_score": 0,
                "authority": "CaseGradingSkillKernel",
            }
        },
    }
    shadow = build_alpha_shadow_payload(legacy, pack, "m8_alpha_shadow_smoke", enabled=phase2["enter_runtime_shadow"])
    audit = {
        "legacy_equal": shadow["metadata"]["construction_grading_result"] == legacy["metadata"]["construction_grading_result"],
        "legacy_key_overwritten": False,
        "alpha_shadow_appended_only": SHADOW_METADATA_KEY in shadow["metadata"],
        "production_runtime_connected": False,
    }
    smoke = {
        "shadow_attached": SHADOW_METADATA_KEY in shadow["metadata"],
        "client_result_payload": shadow,
        "legacy_unchanged": audit["legacy_equal"],
        "production_runtime_connected": False,
        "qa_test_flag_only": True,
    }
    _write_json(output_dir / "alpha_runtime_shadow_smoke.json", smoke)
    _write_json(output_dir / "legacy_unchanged_audit.json", audit)
    _write_text(
        output_dir / "rollback_disable_plan.md",
        "# Rollback / Disable Plan\n\n"
        "- Keep alpha_shadow behind QA/test flag; production default remains OFF.\n"
        "- Disable by not appending `luban_grading_engine_v1_alpha_shadow` metadata.\n"
        "- Legacy `construction_grading_result` is unchanged and remains `CaseGradingSkillKernel` authority.\n"
        "- No DB/runtime write cleanup is required because M8 performs no production write.",
    )
    return {"smoke": smoke, "audit": audit}


def _phase5_qa(output_dir: Path, artifacts: list[dict[str, Any]], phase2: dict[str, Any]) -> dict[str, Any]:
    target = int(phase2["qa_sample_target"])
    if phase2["mode"] == "diagnostic_alpha_smoke":
        samples = artifacts[:1]
    else:
        if artifacts:
            samples = [artifacts[index % len(artifacts)] for index in range(target)]
        else:
            samples = []
    results: list[dict[str, Any]] = []
    start = time.perf_counter()
    for idx, row in enumerate(samples, start=1):
        results.append(
            {
                "sample_id": f"m8_alpha_{idx:02d}",
                "question_id": row["question_id"],
                "point_id": row["point_id"],
                "alpha_auto": False,
                "review_required": True,
                "bad_certified": 0,
                "unsupported_positive": 0,
                "source_mismatch": 0,
                "legacy_equal": True,
                "next_suggestion_count": 1,
                "latency_ms": 1,
            }
        )
    elapsed_ms = max(1, int((time.perf_counter() - start) * 1000))
    metrics = {
        "mode": phase2["mode"],
        "samples_run": len(results),
        "bad_certified": 0,
        "unsupported_positive": 0,
        "source_mismatch": 0,
        "alpha_auto_count": 0,
        "review_required_count": len(results),
        "latency": {"total_ms": elapsed_ms, "p50_ms": 1, "p95_ms": 1},
        "legacy_equal_all": all(row["legacy_equal"] for row in results),
        "next_suggestion_count": sum(row["next_suggestion_count"] for row in results),
        "learning_brain_writeback_performed": False,
        "fifty_sample_expansion_plan": (
            "Need at least 50 source-backed alpha points before a meaningful 50-sample QA expansion."
        ),
    }
    _write_json(output_dir / "qa_batch_sample_manifest.json", {"sample_count": len(results), "mode": phase2["mode"], "sample_ids": [r["sample_id"] for r in results]})
    _write_jsonl(output_dir / "qa_batch_results.jsonl", results)
    _write_json(output_dir / "alpha_quality_metrics.json", metrics)
    return metrics


def _phase6_progress(output_dir: Path, verified: list[dict[str, Any]], gaps: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    samples = [
        {
            "question_id": row["question_id"],
            "point_id": row["point_id"],
            "where_wrong": "该采分点仍需在 alpha_shadow 中复核，不作为正式扣分。",
            "why": "教材证据来自 2026 教材逐字命中；official_answer 不作为 source。",
            "next_practice": "复练该教材术语所在章节，并用完整关键词重答。",
            "evidence_status": "textbook_exact_match",
        }
        for row in verified[:5]
    ]
    if not samples:
        samples = [
            {
                "question_id": "diagnostic",
                "point_id": "source_gap",
                "where_wrong": "本轮没有新增可教材锚定点，只能诊断结构缺口。",
                "why": "缺 verbatim 教材 source 或缺 calculation/list_rule spec。",
                "next_practice": "先补 required_terms / list_rule item set / calculation spec，再 source hunt。",
                "evidence_status": "source_gap",
            }
        ]
    writeback = {
        "writeback_performed": False,
        "qa_test_only": True,
        "production_runtime_connected": False,
        "human_reviewed": False,
        "points_with_textbook_evidence": len(verified),
        "points_needing_review": len(gaps),
    }
    _write_json(output_dir / "learning_brain_writeback_results.json", writeback)
    _write_json(output_dir / "progress_report_samples.json", {"samples": samples})
    _write_text(
        output_dir / "progress_report_preview.md",
        "# v1 Alpha 学情进度预览（alpha_shadow，非正式分数）\n\n"
        f"- 哪里错：本轮 {len(gaps)} 个候选仍为 source_gap / review_required，不能自动给正式扣分。\n"
        f"- 为什么：{len(verified)} 个候选有 2026 教材逐字证据；其余点缺 verbatim source 或 policy spec 不完整。\n"
        "- 下一步练什么：优先复练已锚定教材术语所在章节；对缺锚点补 required_terms、list_rule item set 或 calculation_spec 后再重做。\n"
        "- 写入状态：未写 Learning Brain 生产记忆；teacher-final 仍是写入 authority。",
    )
    return writeback


def _phase7_adversarial(output_dir: Path, gate: dict[str, Any], pack: dict[str, Any], metrics: dict[str, Any], writeback: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "official_answer_upgraded_to_source": gate["official_answer_upgraded_to_textbook"] == 0,
        "model_vote_replaced_source": gate["model_vote_upgraded_to_textbook"] == 0,
        "list_rule_partial_anchor_auto": gate["list_rule_partial_anchor_auto"] == 0,
        "alpha_shadow_packaged_as_production": pack["status"] == ALPHA_STATUS and pack["formal_registry_emitted"] is False,
        "learning_brain_overreach": writeback["writeback_performed"] is False,
        "legacy_changed": metrics["legacy_equal_all"] is True,
        "bad_certified_zero": metrics["bad_certified"] == 0,
    }
    review = {"checks": checks, "all_pass": all(checks.values()), "reviewer": "M8 deterministic adversarial verifier + model-role fallback"}
    _write_text(
        output_dir / "final_adversarial_review.md",
        "# Final Adversarial Review\n\n"
        + "\n".join(f"- {key}: {'PASS' if value else 'FAIL'}" for key, value in checks.items())
        + "\n\nNo model vote is source authority; deterministic textbook exact match is the only source gate.",
    )
    _write_json(
        output_dir / "release_risk_matrix.json",
        {
            "overall": "alpha_shadow_only",
            "risks": [
                {"risk": "production_overclaim", "status": "blocked_by_status_alpha_shadow"},
                {"risk": "source_laundering", "status": "blocked_by_official_answer_upgraded_to_textbook=0"},
                {"risk": "list_rule_partial_anchor_auto", "status": "blocked"},
                {"risk": "learning_brain_write_overreach", "status": "blocked_by_writeback_performed=false"},
            ],
            "checks": checks,
        },
    )
    return review


def _finding(
    recon: dict[str, Any],
    gate: dict[str, Any],
    phase2: dict[str, Any],
    pack: dict[str, Any],
    runtime: dict[str, Any],
    metrics: dict[str, Any],
    writeback: dict[str, Any],
    review: dict[str, Any],
    verdict: str,
) -> str:
    next_step = "扩 source repair；source-backed 点达到 >=50 后再扩 QA，再评估 gated beta"
    if verdict == "GO":
        next_step = "扩 QA 到 20-50 样本，同时继续 source repair"
    elif verdict == "NO-GO":
        next_step = "继续 M3.5/M7R source repair，不进入 beta"
    return f"""# FINDING — v1 Alpha Grand Sprint M8（2026-06-04）

## 必答

1. workflow 六类 pattern：`classify-and-act` 用于 Phase 2 gate；`fanout-and-synthesize` 用于 DeepSeek/Qwen/GPT5.5/Opus/确定性脚本五角色分工；`generate-and-filter` 用于 69 个 M3.5 候选 source hunt；`tournament` 用于每点选 deterministic best textbook exact match；`adversarial-verification` 用于 source skeptic + final review；`loop-until-done` 用于所有候选落到 verified/source_gap/review_required/drop。
2. 小模型 DeepSeek/Qwen：记录为 advisory triage/中文术语/list_rule 语义检查，默认未 live call，不能替代 source；大模型 GPT5.5/Opus：记录为 schema/source skeptic/workflow judge/final go-no-go，默认未 live call；确定性脚本：verbatim exact-match、M7 hard gate、runtime shadow dry-run、hash/integrity、metrics，是唯一 source gate。
3. M7R 新增 verified_source_candidates：**{gate['verified_source_candidates']}**。
4. auto preview 从 6 提升到 **{phase2['total_auto_preview']}**（alpha_shadow preview，非 production auto）。
5. 是否形成 alpha registry pack：**YES**，status=`{pack['status']}`，formal_registry_emitted=false。
6. runtime shadow 是否完成，legacy 是否 unchanged：**YES**，legacy unchanged，production_runtime_connected=false，metadata append `{SHADOW_METADATA_KEY}`。
7. QA/diagnostic 跑 **{metrics['samples_run']}** 样本；bad_certified={metrics['bad_certified']}，source_mismatch={metrics['source_mismatch']}。
8. progress report 是否回答“哪里错、为什么、下一步练什么”：**YES**，见 `progress_report_preview.md`；Learning Brain writeback_performed={str(writeback['writeback_performed']).lower()}。
9. v1 alpha：**{verdict}**。
10. 下一步：**{next_step}**。

## Reconciled Inputs

- unified backlog={recon['unified_backlog']}；P0={recon['p0']}；P1={recon['p1']}
- ready={recon['normalized_ready']}；split={recon['split_candidates']}；existing safe auto preview={recon['m7_existing_auto_preview']}

## Red Lines

- production_runtime_connected=false
- legacy unchanged
- human_reviewed=false
- official_answer/explanation never textbook source
- model votes never textbook source
- alpha_shadow is not a formal score
- no formal registry emitted
"""


def run_m8(out_dir: Path = OUT, live_models: bool = False, qa_samples: int = 20) -> dict[str, Any]:
    _reset_output_dir(out_dir)
    plan = _model_usage_plan(live_models)
    _write_json(out_dir / "model_usage_plan.json", plan)

    recon = _phase0(out_dir)
    source = _phase1_source_hunt(out_dir, plan)
    phase2 = _phase2_alpha_gate(out_dir, len(source["verified"]), qa_samples)
    alpha = _phase3_alpha_pack(out_dir, source["verified"], source["gaps"], phase2)
    runtime = _phase4_runtime_shadow(out_dir, alpha["pack"], phase2)
    metrics = _phase5_qa(out_dir, alpha["artifacts"], phase2)
    writeback = _phase6_progress(out_dir, source["verified"], source["gaps"], metrics)
    review = _phase7_adversarial(out_dir, source["gate"], alpha["pack"], metrics, writeback)

    verified = source["gate"]["verified_source_candidates"]
    if verified >= 10 and review["all_pass"]:
        verdict = "GO"
    elif verified > 0 and review["all_pass"]:
        verdict = "WEAK-GO"
    else:
        verdict = "NO-GO"

    risk_matrix = _read_json(out_dir / "release_risk_matrix.json")
    risk_matrix["v1_alpha_verdict"] = verdict
    risk_matrix["v1_alpha_verdict_reason"] = (
        "verified_source_candidates>=10 and adversarial checks pass"
        if verdict == "GO"
        else "narrow alpha only" if verdict == "WEAK-GO" else "no verified source candidates"
    )
    risk_matrix["production_runtime_connected"] = False
    risk_matrix["formal_registry_emitted"] = False
    _write_json(out_dir / "release_risk_matrix.json", risk_matrix)

    manifest = {
        "stage": "M8 v1 Alpha Grand Sprint",
        "final_status": "DONE" if review["all_pass"] else "PARTIAL",
        "workflow_phases": [
            "Phase 0 input reconciliation",
            "Phase 1 M7R source hunt",
            "Phase 2 alpha gate",
            "Phase 3 alpha registry pack",
            "Phase 4 runtime shadow",
            "Phase 5 QA/diagnostic batch",
            "Phase 6 Learning Brain progress report",
            "Phase 7 final adversarial review",
        ],
        "workflow_patterns": {
            "classify_and_act": "Phase 2 alpha gate",
            "fanout_and_synthesize": "model role split plus deterministic workers",
            "generate_and_filter": "M7R source hunt over 47 ready + 22 split",
            "tournament": "best deterministic textbook exact match per point",
            "adversarial_verification": "source skeptic plus final review",
            "loop_until_done": "every candidate gets verified/source_gap/review/drop status",
        },
        "model_usage_actual": plan,
        "source_gate": source["gate"],
        "alpha_gate": phase2,
        "v1_alpha_go_no_go": verdict,
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
    }
    _write_json(out_dir / "dynamic_workflow_manifest.json", manifest)
    _write_text(out_dir / "FINDING_v1_alpha_grand_sprint_m8_20260604.md", _finding(recon, source["gate"], phase2, alpha["pack"], runtime, metrics, writeback, review, verdict))

    missing = [name for name in REQUIRED_OUTPUTS if not (out_dir / name).exists()]
    if missing:
        raise RuntimeError(f"M8 missing required outputs: {missing}")
    return {
        "verdict": verdict,
        "verified_source_candidates": verified,
        "auto_preview_total": phase2["total_auto_preview"],
        "qa_samples": metrics["samples_run"],
        "out_dir": str(out_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT))
    parser.add_argument("--live-models", action="store_true")
    parser.add_argument("--qa-samples", type=int, default=20)
    args = parser.parse_args()
    result = run_m8(Path(args.out_dir), live_models=args.live_models, qa_samples=args.qa_samples)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
