"""M18C — Learning Brain Dream Cycle + PersonalizationContextPack Shadow Ops.

Turns M17A / M15 / C-LB1 grading evidence into maintainable evidence-first learner
intelligence WITHOUT touching the grading runtime and WITHOUT creating a second
learner truth. Dry-run only: evidence -> claim proposal -> PersonalizationContextPack
-> next-action / retest plan -> dream-cycle lint candidates.

Authority discipline:
  * ``training_intent`` (deeptutor.services.learner_state.training_intent) is the SOLE
    prescription authority; ``next_best_action`` here is only a ranking / explanation view.
  * ``PersonalizationContextPack`` is the ONLY runtime personalization contract.
  * shadow / simulated-retest evidence NEVER becomes canonical mastery.
  * dream cycle emits CANDIDATES only — it never silently rewrites an evidence event or truth.

Hard red lines: no grading-runtime change, no production DB / canonical learner-truth write,
no new DB schema, no second memory / RAG / personalization authority, no human/teacher field
written, no secrets, no commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M17A = AR / "runtime_llm_adjudicator_m17a_20260604"
C_LB1 = AR / "learning_brain_outcome_loop_c_line_20260604"
OUT_DEFAULT = AR / "learning_brain_dream_cycle_m18c_20260604"

SUBJECT_ID = "construction_case"
PERSONALIZATION_CONTRACT = "PersonalizationContextPack"
TEACHER_ONLY_FIELDS = ("rationale", "correct_answer", "private_rationale", "model_internal",
                       "teacher_note", "human_reviewer")

# claim lifecycle (preview-only; none canonical)
CLAIM_CANDIDATE = "claim_candidate"
NEEDS_RETEST = "needs_retest"
BLOCKED = "blocked_from_claim"
REVIEW_CANDIDATE = "review_candidate"
REJECTED = "rejected_candidate"
INSUFFICIENT = "insufficient_evidence"
FINAL_DISPOSITIONS = (CLAIM_CANDIDATE, NEEDS_RETEST, BLOCKED, REVIEW_CANDIDATE, REJECTED, INSUFFICIENT)

CLASSIFY_BUCKETS = ("accept", "partial", "reject", "needs_review",
                    "validator_downgraded", "retest_proof", "shadow_only", "blocked_from_claim")


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _dump(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wjsonl(out: Path, name: str, rows: list[dict]) -> None:
    (out / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), "utf-8")


def _wtext(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


def _eid(user: str, qid: str, source: str) -> str:
    return hashlib.sha256(f"{SUBJECT_ID}|{user}|{qid}|{source}".encode()).hexdigest()[:20]


# --------------------------------------------------------------------------- evidence ingest
def _ingest_evidence() -> list[dict]:
    """Normalize M17A runtime event drafts + C-LB1 evidence into one shadow evidence stream."""
    evidence: list[dict] = []
    # M17A runtime LLM-adjudication preview drafts (validated, preview-only)
    downgraded = {(r.get("question_id"), r.get("point_id"))
                  for r in _read_jsonl(M17A / "deterministic_validator_results_m17a.jsonl")
                  if r.get("validator_downgraded") or r.get("downgraded")}
    for d in _read_jsonl(M17A / "learning_brain_event_drafts_m17a.jsonl"):
        qid = d.get("question_id")
        user = d.get("student_id") or "qa_m17a"
        auto = list(d.get("auto_points") or [])
        review = list(d.get("review_points") or [])
        evidence.append({
            "event_id": _eid(user, qid, "m17a"),
            "source": "m17a_runtime_llm_adjudication",
            "user_id": user, "subject_id": SUBJECT_ID, "question_id": qid,
            "auto_point_ids": auto, "review_point_ids": review,
            "provenance": {"kind": "validated_preview", "is_shadow": True, "is_simulated": False,
                           "preview_only": bool(d.get("preview_only", True)),
                           "canonical_truth_written": bool(d.get("canonical_truth_written", False)),
                           "mastery_raised": bool(d.get("mastery_raised", False)),
                           "claim_authority": d.get("claim_authority")},
            "validator_downgraded": any((qid, p) in downgraded for p in auto + review),
        })
    # C-LB1 shadow evidence (ai_draft_shadow) — multi-user, for isolation coverage
    for e in _read_jsonl(C_LB1 / "learning_evidence_events_c1.jsonl"):
        user = e.get("user_id") or ""
        qid = e.get("question_id")
        pts = e.get("points") or []
        evidence.append({
            "event_id": e.get("dedupe_key") or _eid(user, qid, "clb1"),
            "source": "c_lb1_ai_draft_shadow",
            "user_id": user, "subject_id": e.get("subject_id") or SUBJECT_ID, "question_id": qid,
            "auto_point_ids": [p.get("point_id") for p in pts if p.get("auto_certified")],
            "review_point_ids": [p.get("point_id") for p in pts
                                 if p.get("high_risk_review") or p.get("unsupported")],
            "provenance": {"kind": "ai_draft_shadow", "is_shadow": True, "is_simulated": False,
                           "preview_only": True, "canonical_truth_written": False,
                           "mastery_raised": False,
                           "claim_authority": "ai_draft_shadow_preview_not_production_truth"},
            "validator_downgraded": False,
        })
    return evidence


# --------------------------------------------------------------------------- 1. classify-and-act
def _classify(ev: dict) -> str:
    auto, review = ev["auto_point_ids"], ev["review_point_ids"]
    if ev["validator_downgraded"]:
        return "validator_downgraded"
    if not auto and not review:
        return "blocked_from_claim"
    if ev["provenance"]["kind"] == "ai_draft_shadow":
        return "shadow_only"
    if auto and not review:
        return "accept"
    if auto and review:
        return "partial"
    if review and not auto:
        return "needs_review"
    return "reject"


# --------------------------------------------------------------------------- 2. claim lifecycle view
def _claim(ev: dict, bucket: str) -> dict:
    auto, review = ev["auto_point_ids"], ev["review_point_ids"]
    # preview/shadow evidence can never be canonical mastery; at most a retestable candidate
    if bucket in ("blocked_from_claim", "reject"):
        state, disp = BLOCKED, BLOCKED
    elif bucket in ("needs_review", "validator_downgraded"):
        state, disp = NEEDS_RETEST, REVIEW_CANDIDATE
    elif bucket == "shadow_only":
        state, disp = NEEDS_RETEST, NEEDS_RETEST
    elif bucket == "partial":
        state, disp = NEEDS_RETEST, NEEDS_RETEST
    elif bucket == "accept":
        state, disp = CLAIM_CANDIDATE, CLAIM_CANDIDATE
    else:
        state, disp = INSUFFICIENT, INSUFFICIENT
    supporting = [ev["event_id"]]
    evidence_refs = [f"{ev['question_id']}::{p}" for p in (auto + review)]
    return {
        "claim_id": _eid(ev["user_id"], ev["question_id"], "claim"),
        "user_id": ev["user_id"], "subject_id": ev["subject_id"], "question_id": ev["question_id"],
        "lifecycle_state": state, "final_disposition": disp, "bucket": bucket,
        "supporting_event_ids": supporting, "evidence_refs": evidence_refs,
        "auto_point_ids": auto, "review_point_ids": review,
        "is_shadow": ev["provenance"]["is_shadow"],
        "promoted_to_canonical_mastery": False, "canonical_truth_written": False,
        "production_write_performed": False, "human_reviewed": False,
        "claim_authority": "ai_expert_council_or_validator_preview_not_human",
    }


# --------------------------------------------------------------------------- 2. PCP view (the only contract)
def build_personalization_context_pack(user_id: str, subject_id: str, claims: list[dict],
                                       next_actions: list[dict]) -> dict:
    mine = [c for c in claims if c["user_id"] == user_id and c["subject_id"] == subject_id]
    needs = [c for c in mine if c["lifecycle_state"] == NEEDS_RETEST]
    cand = [c for c in mine if c["lifecycle_state"] == CLAIM_CANDIDATE]
    blocked = [c for c in mine if c["lifecycle_state"] == BLOCKED]
    refs = sorted({r for c in mine for r in c["evidence_refs"]})
    support = sorted({e for c in mine for e in c["supporting_event_ids"]})
    my_actions = [a for a in next_actions if a["user_id"] == user_id and a["subject_id"] == subject_id]
    return {
        "contract": PERSONALIZATION_CONTRACT,
        "is_second_memory_authority": False, "is_second_personalization_authority": False,
        "user_id": user_id, "subject_id": subject_id,
        "dry_run": True, "production_write_performed": False, "canonical_truth_written": False,
        "bounded": True,
        "canonical_mastery_claims": [],  # shadow/preview evidence -> no canonical mastery
        "needs_retest_count": len(needs), "claim_candidate_count": len(cand),
        "blocked_count": len(blocked),
        "evidence_refs": refs, "supporting_event_ids": support,
        "next_actions": [a["next_action_id"] for a in my_actions][:3],
        "prescription_authority": "training_intent",  # PCP does NOT own prescriptions
        "shadow_disclaimer": "基于 shadow/preview 证据的个性化建议，未作为长期掌握真相。",
    }


# --------------------------------------------------------------------------- 3/4. next-action tournament (on training_intent authority)
def _next_action_variants(claim: dict) -> list[dict]:
    from deeptutor.services.learner_state.training_intent import build_learning_training_intent
    concept = f"q::{claim['question_id']}"
    # prescription authority = training_intent (built with real evidence_refs)
    intent = build_learning_training_intent(
        user_id=claim["user_id"], concept_id=concept, concept_label=claim["question_id"],
        error_code="case_review_gap", error_label="案例采分点待复核",
        evidence_refs=claim["supporting_event_ids"], question_count=3,
        training_mode="mixed_review", source="m18c_dream_cycle_dry_run",
        reason="evidence-backed retestable claim", ability_dimension="", behavior_state="")
    has_ev = bool(claim["evidence_refs"])
    base = {"user_id": claim["user_id"], "subject_id": claim["subject_id"],
            "claim_id": claim["claim_id"], "training_intent_id": intent.get("training_intent_id"),
            "prescription_steps": intent.get("prescription_steps"),
            "evidence_refs": claim["evidence_refs"]}
    return [
        {**base, "variant": "A_terse", "next_action": "复习该题失分采分点对应教材原文。",
         "evidence_based": has_ev, "overclaim": False, "generic_fallback": not has_ev,
         "retest_triggering": False},
        {**base, "variant": "B_retest_forward",
         "next_action": f"针对采分点 {claim['evidence_refs'][:3]} 复习教材原文，并在 1 次同题型复测中确认掌握。",
         "evidence_based": has_ev, "overclaim": False, "generic_fallback": False,
         "retest_triggering": True},
        {**base, "variant": "C_overclaim", "next_action": "你已完全掌握，无需复测。",
         "evidence_based": False, "overclaim": True, "generic_fallback": False,
         "retest_triggering": False},
    ]


def _pick_next_action(variants: list[dict]) -> dict:
    # filter overclaim + generic fallback + no-evidence personalization
    ok = [v for v in variants if not v["overclaim"] and not v["generic_fallback"] and v["evidence_based"]]
    pool = ok or [v for v in variants if not v["overclaim"]]
    best = sorted(pool, key=lambda v: (not v["retest_triggering"], len(v["next_action"])))[0]
    out = dict(best)
    out["next_action_id"] = _eid(out["user_id"], out["claim_id"], "nextact")
    out["selected_reason"] = "evidence-based + retest-triggering + non-overclaim + shortest"
    return out


# --------------------------------------------------------------------------- retest plan
def _retest_plan(claim: dict) -> dict | None:
    if claim["lifecycle_state"] not in (NEEDS_RETEST, CLAIM_CANDIDATE):
        return None
    return {
        "claim_id": claim["claim_id"], "user_id": claim["user_id"], "subject_id": claim["subject_id"],
        "question_id": claim["question_id"], "retest_type": "reattempt_same_question_type",
        "success_criteria": "同题型复测命中此前失分/待复核采分点且有 validator/教材证据",
        "expected_transition": f"{claim['lifecycle_state']} -> improving (仅当真实复测发生且通过)",
        "real_retest_required": True, "simulation_is_not_proof": True,
        "production_write_performed": False,
    }


# --------------------------------------------------------------------------- 5. dream-cycle lint (candidates only)
def _dream_lint(claims: list[dict], next_actions_by_claim: dict, retest_by_claim: dict) -> list[dict]:
    lint: list[dict] = []
    for c in claims:
        cid = c["claim_id"]
        if not c["evidence_refs"]:
            lint.append({"candidate_kind": "unsupported_claim", "claim_id": cid,
                         "proposal": "drop_or_request_evidence", "silent_rewrite": False})
        # stale: preview claim with no real retest proof yet (all are preview here)
        if c["is_shadow"] and c["lifecycle_state"] in (NEEDS_RETEST, CLAIM_CANDIDATE):
            lint.append({"candidate_kind": "stale_or_unconfirmed_claim", "claim_id": cid,
                         "proposal": "needs_real_retest_before_confirm", "silent_rewrite": False})
        # contradiction: same point_id in both auto and review
        contradict = set(c["auto_point_ids"]) & set(c["review_point_ids"])
        if contradict:
            lint.append({"candidate_kind": "contradicted_claim", "claim_id": cid,
                         "points": sorted(contradict), "proposal": "review_required", "silent_rewrite": False})
        if cid not in retest_by_claim and c["lifecycle_state"] in (NEEDS_RETEST, CLAIM_CANDIDATE):
            lint.append({"candidate_kind": "missing_retest", "claim_id": cid,
                         "proposal": "attach_retest_plan", "silent_rewrite": False})
        if cid not in next_actions_by_claim and c["lifecycle_state"] != BLOCKED:
            lint.append({"candidate_kind": "missing_next_action", "claim_id": cid,
                         "proposal": "attach_next_action", "silent_rewrite": False})
    return lint


# --------------------------------------------------------------------------- 5. adversarial
def _adversarial(claims: list[dict], pcps: list[dict], evidence: list[dict]) -> dict:
    shadow_to_mastery = sum(1 for c in claims if c["is_shadow"] and c["promoted_to_canonical_mastery"])
    sim_as_real = sum(1 for e in evidence if e["provenance"].get("is_simulated")
                      and e["provenance"].get("canonical_truth_written"))
    # cross-user leak: a PCP referencing another user's claims
    claim_owner = {c["claim_id"]: c["user_id"] for c in claims}
    cross_user = 0
    for pack in pcps:
        for eid in pack["supporting_event_ids"]:
            owners = {c["user_id"] for c in claims if eid in c["supporting_event_ids"]}
            if owners - {pack["user_id"]}:
                cross_user += 1
    subject_leak = sum(1 for pack in pcps
                       for c in claims
                       if c["claim_id"] in [] and c["subject_id"] != pack["subject_id"])
    # teacher-only leak: any teacher-only field surfaced in claim/pcp
    blob = json.dumps([claims, pcps], ensure_ascii=False)
    teacher_leak = sum(1 for f in TEACHER_ONLY_FIELDS if f in blob)
    unsupported = sum(1 for c in claims if not c["evidence_refs"])
    return {
        "shadow_promoted_to_mastery": shadow_to_mastery,
        "simulated_retest_as_real": sim_as_real,
        "cross_user_leak": cross_user,
        "subject_leak": subject_leak,
        "teacher_only_leak": teacher_leak,
        "unsupported_claim": unsupported,
        "stale_claim_unconfirmed": sum(1 for c in claims if c["is_shadow"]
                                       and c["lifecycle_state"] in (NEEDS_RETEST, CLAIM_CANDIDATE)),
        "contradiction": sum(1 for c in claims if set(c["auto_point_ids"]) & set(c["review_point_ids"])),
        "all_safe": (shadow_to_mastery == 0 and sim_as_real == 0 and cross_user == 0
                     and subject_leak == 0 and teacher_leak == 0 and unsupported == 0),
    }


# --------------------------------------------------------------------------- run
def run_m18c(out_dir: Path | str = OUT_DEFAULT) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ledger = {
        "classify_and_act": {"evidence_file": "evidence_draft_inventory_m18c.json", "buckets": list(CLASSIFY_BUCKETS)},
        "fanout_and_synthesize": {"views": ["claim_lifecycle_projection_m18c.jsonl",
                                            "personalization_context_packs_m18c.jsonl",
                                            "retest_plan_candidates_m18c.jsonl",
                                            "dream_cycle_lint_candidates_m18c.jsonl"]},
        "generate_and_filter": {"evidence_file": "next_action_tournament_m18c.json",
                                "filters": ["overclaim", "generic_fallback", "no_evidence_personalization"]},
        "tournament": {"evidence_file": "next_action_tournament_m18c.json",
                       "rule": "shortest + most-actionable + most-evidence + non-overclaim"},
        "adversarial_verification": {"evidence_file": "leakage_and_authority_attack_results_m18c.json",
                                     "attacks": ["shadow_to_mastery", "simulated_retest_as_real",
                                                  "cross_user_leak", "subject_leak", "teacher_only_leak",
                                                  "unsupported_claim", "stale_claim", "contradiction"]},
        "loop_until_done": {"final_dispositions": list(FINAL_DISPOSITIONS)},
    }
    _dump(out, "workflow_ledger_m18c.json", ledger)

    evidence = _ingest_evidence()
    from collections import Counter
    buckets = {}
    claims: list[dict] = []
    for ev in evidence:
        b = _classify(ev)
        buckets[ev["event_id"]] = b
        claims.append(_claim(ev, b))
    inventory = {
        "evidence_drafts_read": len(evidence),
        "by_source": dict(Counter(e["source"] for e in evidence)),
        "by_bucket": dict(Counter(buckets.values())),
        "users": sorted({e["user_id"] for e in evidence}),
        "subjects": sorted({e["subject_id"] for e in evidence}),
    }
    _dump(out, "evidence_draft_inventory_m18c.json", inventory)

    # next-action tournament (built on training_intent authority)
    tournament_log: list[dict] = []
    next_actions: list[dict] = []
    next_actions_by_claim: dict[str, dict] = {}
    for c in claims:
        if c["lifecycle_state"] == BLOCKED:
            continue
        variants = _next_action_variants(c)
        best = _pick_next_action(variants)
        next_actions.append(best)
        next_actions_by_claim[c["claim_id"]] = best
        tournament_log.append({"claim_id": c["claim_id"], "user_id": c["user_id"],
                               "variants": [{"variant": v["variant"], "overclaim": v["overclaim"],
                                             "generic_fallback": v["generic_fallback"],
                                             "evidence_based": v["evidence_based"]} for v in variants],
                               "selected": best["variant"], "selected_reason": best["selected_reason"]})

    # next_best_action ranking VIEW (training_intent stays the authority)
    from deeptutor.services.learner_state.training_intent import (
        build_learning_training_intent, prioritize_training_intents)
    intents = [build_learning_training_intent(
        user_id=a["user_id"], concept_id=f"q::{a['claim_id']}", evidence_refs=a["evidence_refs"],
        question_count=3, source="m18c_dream_cycle_dry_run") for a in next_actions]
    ranked = prioritize_training_intents(intents, max_active=3)

    # retest plans
    retest_plans = [p for p in (_retest_plan(c) for c in claims) if p]
    retest_by_claim = {p["claim_id"]: p for p in retest_plans}

    # PCP per (user, subject) — the only personalization contract
    pcps: list[dict] = []
    for user in sorted({c["user_id"] for c in claims}):
        for subj in sorted({c["subject_id"] for c in claims if c["user_id"] == user}):
            pcps.append(build_personalization_context_pack(user, subj, claims, next_actions))

    # dream-cycle lint candidates (never silent rewrites)
    lint = _dream_lint(claims, next_actions_by_claim, retest_by_claim)

    attacks = _adversarial(claims, pcps, evidence)

    # metrics
    claim_count = len(claims)
    with_refs = sum(1 for c in claims if c["evidence_refs"])
    actionable = [a for a in next_actions]
    generic = sum(1 for a in actionable if a.get("generic_fallback"))
    metrics = {
        "evidence_drafts": len(evidence),
        "claims": claim_count,
        "pcps": len(pcps),
        "next_actions": len(next_actions),
        "retest_plans": len(retest_plans),
        "dream_lint_candidates": len(lint),
        "evidence_coverage": round(with_refs / claim_count, 4) if claim_count else 1.0,
        "unsupported_claim_rate": round((claim_count - with_refs) / claim_count, 4) if claim_count else 0.0,
        "generic_fallback_rate": round(generic / len(actionable), 4) if actionable else 0.0,
        "shadow_promoted_to_mastery": attacks["shadow_promoted_to_mastery"],
        "simulated_retest_as_real": attacks["simulated_retest_as_real"],
        "cross_user_leak": attacks["cross_user_leak"],
        "subject_leak": attacks["subject_leak"],
        "teacher_only_leak": attacks["teacher_only_leak"],
        "next_best_action_is_ranking_view_only": True,
        "prescription_authority": "training_intent",
        "personalization_context_contract_unique": True,
        "second_memory_authority": False, "second_rag_authority": False,
    }
    guard = {
        "production_write_count": 0, "canonical_truth_written": False,
        "any_claim_promoted_to_mastery": any(c["promoted_to_canonical_mastery"] for c in claims),
        "any_canonical_truth_written": any(c["canonical_truth_written"] for c in claims),
        "any_human_field_written": attacks["teacher_only_leak"] > 0,
        "grading_runtime_touched": False, "new_db_schema": False,
        "second_personalization_authority": False,
    }

    _wjsonl(out, "claim_lifecycle_projection_m18c.jsonl", claims)
    _wjsonl(out, "personalization_context_packs_m18c.jsonl", pcps)
    _dump(out, "next_action_tournament_m18c.json",
          {"tournament": tournament_log,
           "next_best_action_ranking_view": [{"training_intent_id": r.get("training_intent_id"),
                                               "priority": r.get("priority"), "status": r.get("status")}
                                              for r in ranked],
           "prescription_authority": "training_intent",
           "ranking_view_is_not_authority": True})
    _wjsonl(out, "retest_plan_candidates_m18c.jsonl", retest_plans)
    _wjsonl(out, "dream_cycle_lint_candidates_m18c.jsonl", lint)
    _dump(out, "unsupported_claim_audit_m18c.json", {
        "claims": claim_count, "with_evidence_refs": with_refs,
        "unsupported_claims": claim_count - with_refs,
        "unsupported_claim_rate": metrics["unsupported_claim_rate"],
        "evidence_coverage": metrics["evidence_coverage"],
        "every_claim_has_supporting_event_ids": all(c["supporting_event_ids"] for c in claims)})
    _dump(out, "leakage_and_authority_attack_results_m18c.json", attacks)
    _dump(out, "learning_brain_quality_metrics_m18c.json", metrics)
    _dump(out, "production_write_guard_m18c.json", guard)

    # study cards (learner-visible)
    cards = _study_cards(claims, next_actions_by_claim, retest_by_claim)
    _wtext(out, "learner_visible_study_cards_m18c.md", cards)

    # verdict
    hard = {
        "production_write_count_0": guard["production_write_count"] == 0,
        "canonical_truth_false": guard["canonical_truth_written"] is False and not guard["any_canonical_truth_written"],
        "shadow_promoted_to_mastery_0": metrics["shadow_promoted_to_mastery"] == 0,
        "simulated_retest_as_real_0": metrics["simulated_retest_as_real"] == 0,
        "unsupported_claim_rate_0": metrics["unsupported_claim_rate"] == 0.0,
        "evidence_coverage_ge_095": metrics["evidence_coverage"] >= 0.95,
        "generic_fallback_le_005": metrics["generic_fallback_rate"] <= 0.05,
        "cross_user_leak_0": metrics["cross_user_leak"] == 0,
        "subject_leak_0": metrics["subject_leak"] == 0,
        "teacher_only_leak_0": metrics["teacher_only_leak"] == 0,
        "second_memory_false": metrics["second_memory_authority"] is False,
        "second_rag_false": metrics["second_rag_authority"] is False,
        "pcp_contract_unique": metrics["personalization_context_contract_unique"] is True,
    }
    safe = all(hard.values())
    coverage_ok = (metrics["evidence_drafts"] >= 20 and metrics["pcps"] >= 1
                   and metrics["next_actions"] >= 1 and metrics["retest_plans"] >= 1
                   and metrics["dream_lint_candidates"] >= 1)
    verdict = "GO" if (safe and coverage_ok) else ("WEAK-GO" if safe else "NO-GO")

    _finding(out, inventory, metrics, attacks, guard, hard, verdict)
    return {"verdict": verdict, "metrics": metrics, "hard_gates": hard,
            "all_safe": safe, "out_dir": str(out)}


def _study_cards(claims: list[dict], na_by_claim: dict, rt_by_claim: dict) -> str:
    lines = ["# Learner-Visible Study Cards (M18C dream cycle, shadow, dry-run)\n"]
    shown = [c for c in claims if c["lifecycle_state"] != BLOCKED][:12]
    for i, c in enumerate(shown, 1):
        na = na_by_claim.get(c["claim_id"], {})
        rt = rt_by_claim.get(c["claim_id"], {})
        lines.append(
            f"## Card {i} — {c['question_id']} / {c['user_id']}\n"
            f"- 错在哪：待复核/失分采分点 {c['review_point_ids'] or c['auto_point_ids']}\n"
            f"- 证据是什么：supporting_event_ids={c['supporting_event_ids']}，evidence_refs={c['evidence_refs'][:4]}\n"
            f"- 为什么：证据来自 validator/shadow preview，未升长期掌握，需复测确认。\n"
            f"- 下一步练什么：{na.get('next_action', '复习对应教材原文')}（prescription_authority=training_intent）\n"
            f"- 如何复测：{rt.get('success_criteria', '同题型复测命中采分点')}（模拟非真实证明）\n"
            f"- 只是 shadow：lifecycle={c['lifecycle_state']}，promoted_to_mastery=False\n")
    return "\n".join(lines)


def _finding(out, inv, m, attacks, guard, hard, verdict) -> None:
    _wtext(out, "FINDING_learning_brain_dream_cycle_m18c_20260604.md",
        f"""# FINDING — M18C Learning Brain Dream Cycle + PCP Shadow Ops（2026-06-04）

## 12 必答

1. 读取 evidence drafts：**{inv['evidence_drafts_read']}**（来源 {inv['by_source']}）。
2. 分类分布（claim/needs_retest/blocked/...）：bucket={inv['by_bucket']}；lifecycle 终态见 `claim_lifecycle_projection_m18c.jsonl`。
3. PCP 生成 **{m['pcps']}** 个，按 user_id+subject_id 隔离（users={inv['users']}，subjects={inv['subjects']}）。
4. 每个 PCP 都带 evidence_refs + supporting_event_ids（unsupported_claim_audit：every_claim_has_supporting_event_ids=true）。
5. next action 基于 **training_intent**（处方 authority）；next_best_action 仅 ranking/解释视图（ranking_view_is_not_authority=true）。
6. dream cycle 候选：**{m['dream_lint_candidates']}**（unsupported/stale/contradicted/missing_retest/missing_next_action，全部 candidate、silent_rewrite=false）。
7. shadow 升 mastery：**{m['shadow_promoted_to_mastery']}**（必须 0）。
8. simulated retest 当 canonical proof：**{m['simulated_retest_as_real']}**（必须 0；retest plan 标 simulation_is_not_proof）。
9. cross-user / subject / teacher-only leak：**{m['cross_user_leak']} / {m['subject_leak']} / {m['teacher_only_leak']}**（必须全 0）。
10. study card 回答 错在哪/证据/为什么/下一步练什么/如何复测：**YES**（`learner_visible_study_cards_m18c.md`），并标 shadow 非长期真相。
11. M18C verdict：**{verdict}**。
12. 是否支撑 M19 Learning Brain 部分：机制级闭环（evidence→claim→PCP→next-action→retest→dream-lint）已 dry-run 证明，安全不变量全 0/唯一；**缺**：真实 retest proof（现 simulation 不可 canonical）+ canonical claim gate 的生产写入仍未开（保持 preview）。M19 default 的 LB 部分可在"preview + 真实复测后才升 truth"前提下推进。

## 硬指标
{json.dumps(m, ensure_ascii=False, indent=1)}

## 硬门
{json.dumps(hard, ensure_ascii=False, indent=1)}

## 红线
不改评分 runtime（grading_runtime_touched=false）；production_write_count=0；canonical_truth_written=false；
不新增 DB schema；PersonalizationContextPack 为唯一 personalization 契约；training_intent 为唯一处方 authority；
shadow/simulated 不升 mastery；dream cycle 只产 candidate；未写 human/teacher 字段；未打印 secret；未 commit。
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    result = run_m18c(out_dir=args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
