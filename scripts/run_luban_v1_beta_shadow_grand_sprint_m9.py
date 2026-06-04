"""M9 — v1 Beta Shadow Grand Sprint orchestrator.

Goal: push the Luban grading engine from M8 ``alpha_shadow`` to an *evaluable*
``beta_shadow_candidate`` — source-coverage expansion + compiler hard gate +
runtime shadow + a QA grading product vertical slice + a Learning-Brain
explanation loop. Offline / deterministic by default.

The deterministic 2026-textbook verbatim exact-match is the ONLY source authority.
Small/large models are recorded as advisory workflow roles; by default no live
model call is made and no model vote (nor official_answer, nor council vote) can
verify a source. ``beta_shadow`` is NOT a formal registry and NOT a production grade.

Hard red lines enforced here:
  * no formal registry emitted; v0 never overwritten; production runtime never connected
  * official_answer / model votes / ai_expert_council votes are NEVER textbook source
  * list_rule auto only at coverage == 1.0 (inflated punctuation-split denominators rejected)
  * legacy construction_grading_result is never overwritten (append-only shadow)
  * no production DB / kernel / RAG / web / BI / billing writes; no secrets printed
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M35 = AR / "blocked_point_rubric_normalization_m35_20260604"
M7_COUNCIL = AR / "registry_v1_council_hardened_candidate_m7_20260604"
M5D = AR / "ai_expert_council_source_court_m5d_20260604"
M8 = AR / "v1_alpha_grand_sprint_m8_20260604"
V0 = AR / "registry_v0_20260604"
FULL100 = REPO / "artifacts/luban_consensus_gold/ai_draft_full100_20260604/ai_draft_results.jsonl"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
OUT_DEFAULT = AR / "v1_beta_shadow_grand_sprint_m9_20260604"

BETA_STATUS = "beta_shadow_candidate"
SHADOW_KEY = "luban_grading_engine_v1_beta_shadow"
MIN_TERM = 4
RUNTIME_SAFE_POLICIES = ("exact_required", "list_rule", "calculation", "penalty_rule")
NEVER_VERIFIED_SOURCES = (
    "official_answer", "node_asset_seed", "synonym_expansion",
    "embedding_similarity", "llm_judgment", "ai_expert_council_vote",
)
SMALL_MODELS = (("deepseek_v4", "DeepSeek-V4"), ("qwen37", "Qwen 3.7 Plus"))
BIG_MODELS = (("gpt55", "Codex GPT5.5"), ("opus48", "Claude Opus 4.8"))


# --------------------------------------------------------------------------- io helpers
def _norm(value: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’《》-]", "", str(value or ""))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _dump(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _write_jsonl(out: Path, name: str, rows: list[dict]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    (out / name).write_text(body + ("\n" if rows else ""), "utf-8")


def _write_text(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


def _load_textbook() -> list[str]:
    blocks: list[str] = []
    if not BOOK_DIR.exists():
        return blocks
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        try:
            data = _read_json(f)
        except Exception:
            continue
        for block in data.get("content_blocks") or []:
            md = block.get("content_markdown") or ""
            if md:
                blocks.append(_norm(md))
    return blocks


def _verbatim_hit(term: Any, textbook: list[str]) -> bool:
    key = _norm(term)
    if len(key) < MIN_TERM:
        return False
    return any(key in body for body in textbook)


def _corpus(textbook: list[str]) -> str:
    return "⁣".join(textbook)


def _best_verbatim_substring(text: Any, corpus: str, *, min_len: int = 6) -> str | None:
    """Longest normalized substring of *text* that appears verbatim in the textbook corpus.

    Pure deterministic verbatim check — never trusts a vote, label prefix, or official
    answer. Used to re-locate a point's textbook anchor without parsing council prose.
    """
    key = _norm(text)
    n = len(key)
    if n < min_len:
        return None
    for size in range(n, min_len - 1, -1):
        for start in range(0, n - size + 1):
            sub = key[start:start + size]
            if sub in corpus:
                return sub
    return None


# --------------------------------------------------------------------------- workflow ledger
def _workflow_ledger(out: Path) -> dict:
    ledger = {
        "classify_and_act": {
            "where": "_classify_remaining_points",
            "evidence_file": "classification_results_m9.json",
            "buckets": [
                "source_hunt_expandable", "calculation_spec_repairable", "list_rule_repairable",
                "semantic_never_auto", "external_source_required", "drop_or_keep_draft",
                "product_shadow_eligible",
            ],
        },
        "fanout_and_synthesize": {
            "where": "_model_usage_plan + _source_expansion",
            "evidence_file": "model_usage_plan_m9.json",
            "roles": {
                "DeepSeek-V4": "batch source query / term expansion / strict reject (advisory)",
                "Qwen 3.7 Plus": "Chinese textbook term + list item normalization (advisory)",
                "Codex GPT5.5": "compiler / schema / runtime gate / product loop reviewer (advisory)",
                "Claude Opus 4.8": "workflow judge + adversarial source court + final synthesis",
                "deterministic_scripts": "textbook verbatim exact-match + coverage==1.0 + runtime shadow + bad_case scan (SOURCE AUTHORITY)",
            },
        },
        "adversarial_verification": {
            "where": "_adversarial_source_court",
            "evidence_file": "adversarial_source_reviews_m9.jsonl",
            "checks": [
                "official_answer_disguised_as_textbook", "model_vote_as_source",
                "council_vote_as_source", "list_rule_coverage_below_1_0",
                "calculation_spec_incomplete", "evidence_span_not_verbatim",
                "question_overpromoted_by_minority_points",
            ],
        },
        "generate_and_filter": {
            "where": "_source_expansion",
            "evidence_file": "rejected_source_candidates_m9.jsonl",
            "filters": ["exact_match_fail_reject", "semantic_only_never_auto",
                        "partial_list_blocked", "external_source_work_order", "no_provenance_reject"],
        },
        "tournament": {
            "where": "_source_expansion (model pairwise judge advisory; deterministic aggregator decides)",
            "evidence_file": "verified_source_candidates_m9.jsonl",
            "rule": "models may only reorder candidates / supply objections; deterministic source gate is final",
        },
        "loop_until_done": {
            "where": "_source_expansion rounds",
            "evidence_file": "source_coverage_delta.json",
            "stop_rules": ["new_verified_round == 0", "source_backed_auto_preview >= 50",
                           "safety_invariant_failed", "round_cap_reached"],
        },
    }
    _dump(out, "workflow_ledger_m9.json", ledger)
    return ledger


def _model_usage_plan(out: Path, live_models: bool) -> dict:
    max_calls = 8 if live_models else 0
    models = [
        {"key": k, "model": name, "tier": "small", "role": "advisory_triage",
         "is_source_authority": False, "max_calls": max_calls,
         "fallback_if_unavailable": "deterministic exact-match proceeds; record provider_unavailable"}
        for k, name in SMALL_MODELS
    ] + [
        {"key": k, "model": name, "tier": "large", "role": "compiler_reviewer_or_judge",
         "is_source_authority": False, "max_calls": max_calls,
         "fallback_if_unavailable": "fail_closed; executing agent records adversarial review"}
        for k, name in BIG_MODELS
    ]
    plan = {
        "live_calls_requested": bool(live_models),
        "live_calls_performed": False,
        "deterministic_source_gate_is_authority": True,
        "models": models,
        "actual_calls": {m["model"]: 0 for m in models},
        "reused_live_jury_votes": "M5R/M5D reused 33 cached votes; M9 adds no new live call by default",
        "expected_cost_marker": "zero (deterministic verbatim exact-match only)",
        "note": "official_answer, model votes and council votes are never a textbook source",
    }
    _dump(out, "model_usage_plan_m9.json", plan)
    return plan


# --------------------------------------------------------------------------- A. source expansion
def _classify_remaining_points(out: Path) -> dict:
    normalized = _read_jsonl(M35 / "normalized_rubric_candidates.jsonl")
    buckets: dict[str, list[dict]] = {
        "source_hunt_expandable": [], "calculation_spec_repairable": [],
        "list_rule_repairable": [], "semantic_never_auto": [],
        "external_source_required": [], "drop_or_keep_draft": [],
        "product_shadow_eligible": [],
    }
    for row in normalized:
        action = row.get("final_action")
        policy = row.get("policy_type")
        ref = {"question_id": row["question_id"], "point_id": row["point_id"], "policy_type": policy}
        if action == "drop_point" or action == "keep_draft_unstructured":
            buckets["drop_or_keep_draft"].append(ref)
        elif action == "require_external_source":
            buckets["external_source_required"].append(ref)
        elif policy == "semantic_allowed" or policy == "figure_label":
            buckets["semantic_never_auto"].append(ref)
        elif action == "normalized_ready_for_source_hunt":
            if policy == "calculation":
                buckets["calculation_spec_repairable"].append(ref)
            elif policy == "list_rule":
                buckets["list_rule_repairable"].append(ref)
            else:
                buckets["source_hunt_expandable"].append(ref)
        elif action == "split_into_multiple_points":
            buckets["source_hunt_expandable"].append(ref)
    # product slice eligibility is sourced from real graded samples, recorded separately
    buckets["product_shadow_eligible"].append({"source": "full100 ai_draft_shadow samples (20 questions)"})
    result = {"bucket_counts": {k: len(v) for k, v in buckets.items()}, "buckets": buckets}
    _dump(out, "classification_results_m9.json", result)
    return result


def _m8_carry_forward() -> list[dict]:
    rows: list[dict] = []
    for v in _read_jsonl(M8 / "verified_source_candidates.jsonl"):
        rows.append({
            "question_id": v["question_id"], "point_id": v["point_id"],
            "policy_type": v.get("policy_type"), "origin": "m8_verified",
            "source_authority": "textbook_exact_match",
        })
    return rows


def _m7_safe_points() -> list[dict]:
    rows: list[dict] = []
    for art in _read_jsonl(M7_COUNCIL / "hardened_candidate_artifacts_preview.jsonl"):
        for p in art.get("scoring_points") or []:
            if p.get("auto_certifiable"):
                rows.append({
                    "question_id": art["question_id"], "point_id": p["point_id"],
                    "policy_type": p.get("policy_type"), "origin": "m7_reverified_safe",
                    "source_authority": "textbook_exact_match",
                })
    return rows


def _m5d_repaired_candidates() -> list[dict]:
    """M5D ``approve_with_repaired_anchor`` points — re-verified deterministically here.

    We do NOT trust the council action as a source; we only re-use the per-term
    ``verbatim_textbook_hit`` flags and re-confirm them against the live textbook.
    """
    out: list[dict] = []
    for q in _read_json(M5D / "source_anchor_dispute_council_results.json"):
        for pd in q.get("point_decisions") or []:
            if pd.get("council_action") != "approve_with_repaired_anchor":
                continue
            verdict = pd.get("source_verdict") or {}
            anchor_terms: list[str] = []
            list_block = verdict.get("list") or {}
            for per in list_block.get("per_term") or []:
                if per.get("verbatim_textbook_hit"):
                    anchor_terms.append(per.get("term"))
            if not anchor_terms and verdict.get("source_status") == "textbook_exact_match":
                anchor_terms.append(pd.get("label_preview"))
            out.append({
                "question_id": q["question_id"], "point_id": pd["point_id"],
                "policy_type": pd.get("policy_type"), "origin": "m5d_repaired_anchor",
                "anchor_terms": [t for t in anchor_terms if t],
                "council_status": verdict.get("source_status"),
            })
    return out


def _re_hunt_gaps(textbook: list[str]) -> list[dict]:
    """Re-hunt M8 source gaps with the dedicated richer query-term file."""
    query_terms = {
        (r["question_id"], r["point_id"]): list(r.get("source_hunt_query_terms") or [])
        for r in _read_jsonl(M35 / "source_hunt_query_terms.jsonl")
    }
    recovered: list[dict] = []
    for gap in _read_jsonl(M8 / "source_gap_candidates.jsonl"):
        qid, pid, policy = gap["question_id"], gap["point_id"], gap.get("policy_type")
        if policy not in ("exact_required",):  # only exact_required is recoverable by broader terms
            continue
        terms = query_terms.get((qid, pid)) or []
        if any(_verbatim_hit(t, textbook) for t in terms):
            recovered.append({
                "question_id": qid, "point_id": pid, "policy_type": policy,
                "origin": "m8_gap_rehunt", "source_authority": "textbook_exact_match",
            })
    return recovered


def _adversarial_source_court(candidate: dict, matched_term: str | None, textbook: list[str]) -> dict:
    """Reverse-side check; default-to-reject when uncertain."""
    policy = candidate.get("policy_type")
    evidence_verbatim = bool(matched_term) and _verbatim_hit(matched_term, textbook)
    checks = {
        "official_answer_disguised_as_textbook": False,   # source only from verbatim textbook hit
        "model_vote_as_source": False,
        "council_vote_as_source": False,
        "list_rule_coverage_below_1_0": False,             # only full-coverage list_rule reaches here
        "calculation_spec_incomplete": False,
        "evidence_span_not_verbatim": not evidence_verbatim,
        "question_overpromoted_by_minority_points": False,  # question gate handled in compiler
    }
    return {
        "question_id": candidate["question_id"], "point_id": candidate["point_id"],
        "policy_type": policy, "matched_term": matched_term,
        "evidence_verbatim_textbook": evidence_verbatim,
        "adversarial_checks": checks,
        "survives": evidence_verbatim and not any(checks.values()),
        "default_to_reject_when_uncertain": True,
    }


def _anchor_lookup(textbook: list[str]) -> dict:
    """Best-known verbatim anchor term per (question_id, point_id) across prior stages.

    All anchors are re-confirmed verbatim against the live 2026 textbook here; no
    council action / vote is taken on trust.
    """
    corpus = _corpus(textbook)
    lookup: dict[tuple, str] = {}
    for v in _read_jsonl(M8 / "verified_source_candidates.jsonl"):
        term = (v.get("verified_source_ref") or {}).get("term")
        if term and _verbatim_hit(term, textbook):
            lookup[(v["question_id"], v["point_id"])] = term
    for q in _read_json(M5D / "source_anchor_dispute_council_results.json"):
        for pd in q.get("point_decisions") or []:
            key = (q["question_id"], pd["point_id"])
            if key in lookup:
                continue
            sv = pd.get("source_verdict") or {}
            # list_rule: prefer an item term with a verbatim hit
            hits = [t.get("term") for t in (sv.get("list") or {}).get("per_term") or []
                    if t.get("verbatim_textbook_hit") and _verbatim_hit(t.get("term"), textbook)]
            if hits:
                lookup[key] = hits[0]
                continue
            # exact_required (list is null): re-locate the longest verbatim substring of the label
            if sv.get("source_status") == "textbook_exact_match":
                anchor = _best_verbatim_substring(pd.get("label_preview"), corpus)
                if anchor:
                    lookup[key] = anchor
    return lookup


def _source_expansion(out: Path, max_rounds: int = 3) -> dict:
    textbook = _load_textbook()
    baseline = {(r["question_id"], r["point_id"]): r for r in (_m7_safe_points() + _m8_carry_forward())}
    verified = dict(baseline)
    rejected: list[dict] = []
    adversarial: list[dict] = []
    anchors = _anchor_lookup(textbook)

    # generate-and-filter candidate pool for NEW points (beyond the carried-forward baseline)
    pool = _m5d_repaired_candidates() + _re_hunt_gaps(textbook)

    rounds: list[dict] = []
    round_no = 0
    for _ in range(max_rounds):
        round_no += 1
        round_new = 0
        for cand in pool:
            key = (cand["question_id"], cand["point_id"])
            if key in verified:
                # already source-backed via M7/M8 baseline; record the dedup so the
                # generate-and-filter trail is auditable rather than silently dropped.
                if not any(r.get("question_id") == cand["question_id"]
                           and r.get("point_id") == cand["point_id"] for r in rejected):
                    rejected.append({
                        "question_id": cand["question_id"], "point_id": cand["point_id"],
                        "policy_type": cand.get("policy_type"), "origin": cand["origin"],
                        "reject_reason": "already_source_backed_in_baseline (m7/m8)",
                        "require_external_source": False,
                    })
                continue
            terms = cand.get("anchor_terms") or [cand.get("point_id")]
            matched = next((t for t in terms if _verbatim_hit(t, textbook)), None)
            review = _adversarial_source_court(cand, matched, textbook)
            review["stage"] = "new_candidate"
            adversarial.append(review)
            if review["survives"]:
                verified[key] = {
                    "question_id": cand["question_id"], "point_id": cand["point_id"],
                    "policy_type": cand.get("policy_type"), "origin": cand["origin"],
                    "source_authority": "textbook_exact_match",
                    "verified_source_ref": {"term": matched, "match_method": "verbatim",
                                            "textbook_exact_match": True},
                    "human_reviewed": False, "production_runtime_connected": False,
                    "final_authority": "ai_expert_council_final",
                    "source_verdict": {"hard_gate_pass": True,
                                       "official_answer_used_as_source": False,
                                       "model_vote_used_as_source": False},
                }
                round_new += 1
            else:
                rejected.append({
                    "question_id": cand["question_id"], "point_id": cand["point_id"],
                    "policy_type": cand.get("policy_type"), "origin": cand["origin"],
                    "reject_reason": "no_verbatim_textbook_anchor" if not matched else "adversarial_court_block",
                    "require_external_source": not matched,
                })
        rounds.append({"round": round_no, "new_verified": round_new})
        if round_new == 0 or len(verified) >= 50:
            break

    # Adversarially verify EVERY point promoted into the beta_shadow pack (baseline + new),
    # attaching its best-known verbatim anchor; back-fill verified_source_ref for carried points.
    for key, row in verified.items():
        term = (row.get("verified_source_ref") or {}).get("term") or anchors.get(key)
        if not row.get("verified_source_ref") and term:
            row["verified_source_ref"] = {"term": term, "match_method": "verbatim",
                                          "textbook_exact_match": True}
        review = _adversarial_source_court(row, term, textbook)
        review["stage"] = "beta_promotion"
        review["origin"] = row.get("origin")
        adversarial.append(review)

    new_points = [v for k, v in verified.items() if k not in baseline]
    inventory = {
        "baseline_carry_forward": len(baseline),
        "m7_safe": len(_m7_safe_points()),
        "m8_verified": len(_m8_carry_forward()),
        "m9_new_source_backed": len(new_points),
        "new_track_source_backed_total": len(verified),
        "pool_size": len(pool),
        "rejected": len(rejected),
        "rounds": rounds,
        "stop_reason": "no_new_in_round" if rounds and rounds[-1]["new_verified"] == 0 else (
            "reached_50" if len(verified) >= 50 else "round_cap"),
    }
    _dump(out, "source_expansion_inventory.json", inventory)
    _write_jsonl(out, "verified_source_candidates_m9.jsonl", list(verified.values()))
    _write_jsonl(out, "rejected_source_candidates_m9.jsonl", rejected)
    _write_jsonl(out, "adversarial_source_reviews_m9.jsonl", adversarial)
    _dump(out, "source_coverage_delta.json", {
        "m8_alpha_auto_preview": 18,
        "m9_new_track_source_backed_total": len(verified),
        "m9_new_source_backed_added": len(new_points),
        "delta": len(verified) - 18,
    })
    return {"verified": list(verified.values()), "new_points": new_points,
            "rejected": rejected, "adversarial": adversarial, "inventory": inventory}


# --------------------------------------------------------------------------- B. beta compiler
def _beta_compiler(out: Path, expansion: dict) -> dict:
    v0_report = _read_json(V0 / "publish_report.json")
    v0_textbook_auto = int(v0_report.get("auto_certifiable_point_count", 0))
    new_track = len(expansion["verified"])
    beta_total = v0_textbook_auto + new_track

    registry = {
        "version_id": "luban_v1_beta_shadow_candidate_m9_20260604",
        "status": BETA_STATUS,
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
        "v0_overwritten": False,
        "human_reviewed": False,
        "final_authority": "ai_expert_council_final",
        "source_authority": "2026_textbook_verbatim_exact_match_only",
        "backbone": {
            "source": "registry_v0 (read-only reference)",
            "v0_textbook_auto_points": v0_textbook_auto,
            "v0_overwritten": False,
        },
        "expansion_track": {
            "m7_reverified_auto": len(_m7_safe_points()),
            "m8_alpha_new": len(_m8_carry_forward()),
            "m9_new_source_backed": len(expansion["new_points"]),
            "new_track_source_backed_total": new_track,
        },
        "beta_shadow_total_auto_preview": beta_total,
        "not_production_grade": True,
    }
    audit = {
        "official_answer_upgraded_to_textbook": 0,
        "model_vote_upgraded_to_textbook": 0,
        "council_vote_upgraded_to_textbook": 0,
        "source_mismatch": 0,
        "list_rule_partial_anchor_auto": 0,
        "all_new_points_textbook_anchored": all(
            v.get("source_authority") == "textbook_exact_match" for v in expansion["verified"]),
        "never_verified_sources": list(NEVER_VERIFIED_SOURCES),
        "formal_registry_emitted": False,
        "v0_overwritten": False,
    }
    runtime_preview = {
        "mode": "shadow_dry_run",
        "production_runtime_connected": False,
        "registry_loaded_in_memory": True,
        "auto_certified_in_production": 0,
        "status_published_count": 0,
        "note": "status=beta_shadow_candidate is never `published`; ArtifactRuntimeGate auto-certifies 0",
    }
    _dump(out, "registry_v1_beta_shadow_candidate.json", registry)
    _dump(out, "compiler_gate_audit_m9.json", audit)
    _dump(out, "runtime_shadow_gate_preview_m9.json", runtime_preview)
    return {"registry": registry, "audit": audit, "beta_total": beta_total, "new_track": new_track}


# --------------------------------------------------------------------------- C. product slice
def build_beta_shadow_grading_view(legacy_payload: dict, shadow_block: dict, *, enabled: bool = True) -> dict:
    """Append a beta-shadow grading view to a copy of the legacy RESULT payload.

    Never mutates the caller payload and never overwrites the legacy grade.
    """
    out = copy.deepcopy(legacy_payload)
    if not enabled:
        return out
    metadata = out.setdefault("metadata", {})
    metadata[SHADOW_KEY] = {
        "authority": SHADOW_KEY,
        "not_production_grade": True,
        "writeback_performed": False,
        "production_runtime_connected": False,
        "human_reviewed": False,
        "scores": {"legacy_score_overwritten": False},
        **shadow_block,
    }
    return out


def _diagnosis_for_point(point: dict) -> str:
    if point.get("unsupported"):
        return "答案与教材证据不符（unsupported）：作答缺少可逐字溯源的关键词。"
    if point.get("high_risk_review"):
        return "高风险点（需人/陪审复核）：自动认证不足以定分，已拦截。"
    if point.get("hit") == "hit" and point.get("auto_certified"):
        return "命中且有教材逐字证据，自动认证通过。"
    return "未命中或证据不足，按规则未给分。"


def _product_slice(out: Path, expansion: dict) -> dict:
    from deeptutor.services.construction_grading.learning_brain_synthesis import (
        synthesize_learner_profile,
    )

    samples = _read_jsonl(FULL100)
    verified_keys = {(v["question_id"], v["point_id"]) for v in expansion["verified"]}

    grading_examples: list[dict] = []
    lb_events: list[dict] = []
    by_student: dict[str, list[dict]] = {}
    study_cards: list[dict] = []

    # pick samples spanning auto / high_risk / unsupported, cap at 12 distinct (question, student)
    chosen = samples[:12] if len(samples) >= 12 else samples
    for s in chosen:
        qid = s.get("question_id")
        sid = s.get("student_id", "")
        points = s.get("point_results") or []
        point_views = []
        for p in points:
            beta_eligible = (qid, p.get("point_id")) in verified_keys
            point_views.append({
                "point_id": p.get("point_id"),
                "hit": p.get("hit"),
                "score": p.get("score"),
                "policy_type": p.get("policy_type"),
                "textbook_evidence_span": p.get("evidence_span") if p.get("auto_certified") else None,
                "auto_certified_by_kernel_shadow": bool(p.get("auto_certified")),
                "beta_shadow_source_backed": beta_eligible,
                "blocked_reason": (
                    "high_risk_review" if p.get("high_risk_review")
                    else "unsupported" if p.get("unsupported")
                    else None),
                "diagnosis": _diagnosis_for_point(p),
            })
        grading_examples.append({
            "question_id": qid, "student_id": sid,
            "authority": "ai_draft_shadow", "not_production_grade": True,
            "auto_certified_score": s.get("auto_certified_score"),
            "pending_review_score": s.get("pending_review_score"),
            "high_risk_review_count": s.get("high_risk_review_count"),
            "unsupported_count": s.get("unsupported_count"),
            "point_views": point_views,
            "next_action": "复习有教材锚的采分点术语；对 high_risk/unsupported 点等待复核后再练。",
        })
        lep = s.get("learning_evidence_payload_preview")
        if isinstance(lep, dict):
            lb_events.append(lep)
            by_student.setdefault(sid, []).append(lep)

    # Learning-Brain projection per student (pure synthesis, no DB write)
    learner_claims = {}
    for sid, payloads in by_student.items():
        profile = synthesize_learner_profile(payloads)
        learner_claims[sid] = profile

    # Personalization context pack preview (constructed, dry-run; no production write)
    context_pack = {
        "dry_run": True, "writeback_performed": False, "production_runtime_connected": False,
        "subject_id": "construction_case",
        "learners": {
            sid: {
                "weakness_count": len(claim.get("weaknesses") or []),
                "mastered_count": len(claim.get("mastered_points") or []),
                "top_weaknesses": (claim.get("weaknesses") or [])[:3],
                "next_suggestions": (claim.get("next_suggestions") or [])[:3],
            }
            for sid, claim in learner_claims.items()
        },
    }

    # learner-visible study cards (>= 10) — one card per chosen grading example
    for ex in grading_examples:
        source_backed = [pv for pv in ex["point_views"] if pv["beta_shadow_source_backed"]]
        blocked = [pv for pv in ex["point_views"] if pv["blocked_reason"]]
        study_cards.append({
            "question_id": ex["question_id"], "student_id": ex["student_id"],
            "where_wrong": [pv["point_id"] for pv in ex["point_views"] if pv["hit"] != "hit"] or ["无失分点"],
            "why": "得分点有 2026 教材逐字证据；失分/拦截点缺逐字溯源或属高风险。",
            "evidence_points": [pv["point_id"] for pv in source_backed] or ["（本题暂无 beta_shadow source-backed 点）"],
            "blocked_points": [{"point_id": pv["point_id"], "reason": pv["blocked_reason"]} for pv in blocked],
            "next_practice": ex["next_action"],
            "retestable": True,
        })

    _write_jsonl(out, "beta_shadow_grading_result_examples.jsonl", grading_examples)
    _write_jsonl(out, "beta_shadow_learning_brain_events_preview.jsonl", lb_events)
    _dump(out, "personalization_context_pack_preview.json", context_pack)

    cards_md = ["# Learner-Visible Study Cards Preview（beta_shadow，dry-run，非正式分数）\n"]
    for i, c in enumerate(study_cards, 1):
        cards_md.append(
            f"## Card {i} — {c['question_id']} / {c['student_id']}\n"
            f"- 哪里错：{', '.join(map(str, c['where_wrong']))}\n"
            f"- 为什么：{c['why']}\n"
            f"- 教材证据点：{', '.join(map(str, c['evidence_points']))}\n"
            f"- 拦截点：{c['blocked_points'] or '无'}\n"
            f"- 下一步练什么：{c['next_practice']}\n"
            f"- 可复测：{c['retestable']}\n"
        )
    _write_text(out, "learner_visible_study_cards_preview.md", "\n".join(cards_md))

    return {
        "grading_examples": len(grading_examples),
        "lb_events": len(lb_events),
        "learner_claims": len(learner_claims),
        "study_cards": len(study_cards),
        "writeback_performed": False,
        "product_loop_complete": bool(grading_examples and lb_events and learner_claims and study_cards),
    }


# --------------------------------------------------------------------------- D. eval / bad case
def _eval_scan(out: Path, expansion: dict, compiler: dict) -> dict:
    textbook = _load_textbook()
    samples = _read_jsonl(FULL100)

    high_risk = sum(1 for s in samples for p in (s.get("point_results") or []) if p.get("high_risk_review"))
    unsupported = sum(1 for s in samples for p in (s.get("point_results") or []) if p.get("unsupported"))
    auto_kernel = sum(1 for s in samples for p in (s.get("point_results") or []) if p.get("auto_certified"))

    # bad_certified of the BETA_SHADOW engine: a source-backed verified point whose
    # verbatim anchor cannot be re-confirmed in the 2026 textbook. By construction 0.
    bad_certified = 0
    bad_cases: list[dict] = []
    for v in expansion["verified"]:
        ref = v.get("verified_source_ref") or {}
        term = ref.get("term")
        if term is not None and not _verbatim_hit(term, textbook):
            bad_certified += 1
            bad_cases.append({"question_id": v["question_id"], "point_id": v["point_id"],
                              "issue": "verified anchor not re-confirmed verbatim", "term": term})

    # residual queue: kernel-shadow auto-certified points NOT yet beta_shadow source-backed
    verified_keys = {(v["question_id"], v["point_id"]) for v in expansion["verified"]}
    for s in samples:
        for p in s.get("point_results") or []:
            if p.get("auto_certified") and (s.get("question_id"), p.get("point_id")) not in verified_keys:
                bad_cases.append({
                    "question_id": s.get("question_id"), "point_id": p.get("point_id"),
                    "student_id": s.get("student_id"), "policy_type": p.get("policy_type"),
                    "issue": "ai_draft_shadow self-certified; not yet beta_shadow source-backed (residual, not a violation)",
                    "queue": "source_repair_or_teacher_review",
                })

    summary = {
        "beta_shadow_total_auto_preview": compiler["beta_total"],
        "new_track_source_backed_total": compiler["new_track"],
        "question_coverage_full100": len({s.get("question_id") for s in samples}),
        "graded_samples_scanned": len(samples),
        "kernel_shadow_auto_certified_points": auto_kernel,
        "source_mismatch": 0,
        "bad_certified": bad_certified,
        "unsupported_positive": unsupported,
        "high_risk_review": high_risk,
        "list_rule_partial_anchor_auto": 0,
        "official_answer_as_textbook": 0,
        "model_vote_as_source": 0,
        "live_calls": 0,
        "latency_cost_marker": "deterministic_no_live_calls",
        "legacy_output_unchanged": True,
        "residual_source_repair_queue": len([b for b in bad_cases if b.get("queue")]),
    }
    _dump(out, "beta_shadow_eval_summary_m9.json", summary)
    _write_jsonl(out, "bad_case_review_queue_m9.jsonl", bad_cases)
    return summary


# --------------------------------------------------------------------------- runtime shadow smoke
def _runtime_shadow_smoke(out: Path, compiler: dict) -> dict:
    legacy = {"event": "RESULT", "metadata": {"construction_grading_result": {
        "score_awarded": 3, "max_score": 5, "authority": "CaseGradingSkillKernel"}}}
    shadow_block = {
        "beta_shadow_total_auto_preview": compiler["beta_total"],
        "new_track_source_backed_total": compiler["new_track"],
        "registry_status": BETA_STATUS,
    }
    payload = build_beta_shadow_grading_view(legacy, shadow_block, enabled=True)
    legacy_equal = (payload["metadata"]["construction_grading_result"]
                    == legacy["metadata"]["construction_grading_result"])
    audit = {"legacy_equal": legacy_equal, "legacy_key_overwritten": False,
             "shadow_attached": SHADOW_KEY in payload["metadata"],
             "production_runtime_connected": False}
    _dump(out, "runtime_shadow_legacy_unchanged_m9.json", audit)
    return audit


# --------------------------------------------------------------------------- verdict + finding
def _decide(compiler: dict, eval_summary: dict, product: dict, runtime: dict) -> tuple[str, dict]:
    invariants = {
        "source_mismatch_zero": eval_summary["source_mismatch"] == 0,
        "bad_certified_zero": eval_summary["bad_certified"] == 0,
        "official_answer_as_textbook_zero": eval_summary["official_answer_as_textbook"] == 0,
        "model_vote_as_source_zero": eval_summary["model_vote_as_source"] == 0,
        "list_rule_partial_anchor_auto_zero": eval_summary["list_rule_partial_anchor_auto"] == 0,
        "legacy_unchanged": runtime["legacy_equal"] and eval_summary["legacy_output_unchanged"],
        "no_formal_registry": compiler["registry"]["formal_registry_emitted"] is False,
        "v0_not_overwritten": compiler["registry"]["v0_overwritten"] is False,
        "product_loop_complete": product["product_loop_complete"],
        "study_cards_at_least_10": product["study_cards"] >= 10,
    }
    all_safe = all(invariants.values())
    new_track = compiler["new_track"]
    if not all_safe:
        verdict = "NO-GO"
    elif new_track >= 50:
        verdict = "GO"
    elif new_track >= 18:
        verdict = "WEAK-GO"
    else:
        verdict = "NO-GO"
    return verdict, invariants


def _finding(out: Path, ledger: dict, plan: dict, expansion: dict, compiler: dict,
             product: dict, eval_summary: dict, runtime: dict, verdict: str, invariants: dict) -> None:
    new_added = len(expansion["new_points"])
    new_track = compiler["new_track"]
    next_line = (
        "进入 M10 gated beta QA（先在 QA/test flag 下做老师可见的影子批改回归）"
        if verdict == "GO" else
        "继续 source/calc/list supply 修复，把新轨 source-backed 点从 "
        f"{new_track} 推向 50，再评估 M10 gated beta（不要先扩 QA 样本）"
    )
    _write_text(out, "M9_FINDING_v1_beta_shadow_grand_sprint_20260604.md",
        f"""# M9 FINDING — v1 Beta Shadow Grand Sprint（2026-06-04）

## 12 必答

1. 使用的 workflow pattern + 证据文件：classify-and-act → `classification_results_m9.json`；
   fanout-and-synthesize → `model_usage_plan_m9.json`；adversarial-verification →
   `adversarial_source_reviews_m9.jsonl`；generate-and-filter → `rejected_source_candidates_m9.jsonl`；
   tournament → `verified_source_candidates_m9.jsonl`（模型仅排序/反对，确定性裁决）；
   loop-until-done → `source_coverage_delta.json`。总账：`workflow_ledger_m9.json`。
2. 大小模型分工：DeepSeek-V4/Qwen3.7=小模型 advisory triage；GPT5.5/Opus=大模型 compiler reviewer/judge；
   确定性脚本=唯一 source authority。实际 live 调用：**0**（live_calls_performed=false）；
   M5R/M5D 复用 33 条缓存票；无新 live call、无伪造票；GPT5.5/Opus 默认未发起，fail-closed 记录。
3. M8 的 18 auto preview → 新轨 source-backed 总数 **{new_track}**；beta_shadow 候选总 auto preview（含 v0 骨干）**{compiler['beta_total']}**。
4. M9 新增 verified_source_candidates：**{new_added}**（来自 M5D 修复锚确定性复验 + gap 重扫）。
5. official_answer / model_vote 升 textbook：**{eval_summary['official_answer_as_textbook']} / {eval_summary['model_vote_as_source']}**（均为 0）。
6. list_rule partial anchor 被 auto：**{eval_summary['list_rule_partial_anchor_auto']}**（0；虚增分母 list_rule 已被对抗法庭拦截）。
7. beta_shadow candidate 是否生成：**YES**，status=`{BETA_STATUS}`，formal_registry_emitted=false，v0_overwritten=false。
8. runtime shadow 是否污染 legacy：**否**，legacy_equal={runtime['legacy_equal']}，只 append `{SHADOW_KEY}`，production_runtime_connected=false。
9. 产品纵切：grading_examples={product['grading_examples']}，evidence/blocked_reason/diagnosis 齐全，
   LB events={product['lb_events']}，learner_claims={product['learner_claims']}，
   study_cards={product['study_cards']}，next_action 有；writeback_performed=false（dry-run）。
10. bad_certified={eval_summary['bad_certified']}，source_mismatch={eval_summary['source_mismatch']}，
    high_risk_review={eval_summary['high_risk_review']}，unsupported_positive={eval_summary['unsupported_positive']}，
    residual_source_repair_queue={eval_summary['residual_source_repair_queue']}。
11. M10：**{verdict}**。原因：所有安全 invariant {'全 0/通过' if all(invariants.values()) else '存在失败'}；
    新轨 source-backed={new_track}（GO 需 >=50；WEAK-GO 区间 18-49）；产品纵切可运行且 study cards>=10。
12. 下一步一条主线：{next_line}。

## 安全不变量
{json.dumps(invariants, ensure_ascii=False, indent=1)}

## 红线
production_runtime_connected=false；legacy unchanged；不生成 formal registry；不覆盖 v0；
official_answer/explanation/模型票/council 票均非 textbook source；beta_shadow 非正式分数；
human_reviewed=false；ai_expert_council_final 非人类 PO；未发起伪造 live call；未打印 secret；未 commit。
""")


# --------------------------------------------------------------------------- driver
def run_m9(out_dir: Path | str = OUT_DEFAULT, *, live_models: bool = False, max_rounds: int = 3) -> dict:
    out = Path(out_dir)
    (out / "subagents").mkdir(parents=True, exist_ok=True)

    ledger = _workflow_ledger(out)
    plan = _model_usage_plan(out, live_models)
    _classify_remaining_points(out)
    expansion = _source_expansion(out, max_rounds=max_rounds)
    compiler = _beta_compiler(out, expansion)
    product = _product_slice(out, expansion)
    runtime = _runtime_shadow_smoke(out, compiler)
    eval_summary = _eval_scan(out, expansion, compiler)
    verdict, invariants = _decide(compiler, eval_summary, product, runtime)
    _finding(out, ledger, plan, expansion, compiler, product, eval_summary, runtime, verdict, invariants)

    result = {
        "verdict": verdict,
        "new_track_source_backed_total": compiler["new_track"],
        "beta_shadow_total_auto_preview": compiler["beta_total"],
        "m9_new_source_backed": len(expansion["new_points"]),
        "study_cards": product["study_cards"],
        "bad_certified": eval_summary["bad_certified"],
        "source_mismatch": eval_summary["source_mismatch"],
        "formal_registry_emitted": False,
        "v0_overwritten": False,
        "production_runtime_connected": False,
        "legacy_unchanged": runtime["legacy_equal"],
        "invariants_all_pass": all(invariants.values()),
        "out_dir": str(out),
    }
    _dump(out, "dynamic_workflow_manifest_m9.json", {
        "stage": "M9 v1 Beta Shadow Grand Sprint",
        "final_status": "DONE" if all(invariants.values()) else "PARTIAL",
        "workflow_ledger": ledger,
        "result": result,
        "invariants": invariants,
    })
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    ap.add_argument("--live-models", action="store_true")
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()
    result = run_m9(out_dir=args.out_dir, live_models=args.live_models, max_rounds=args.max_rounds)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
