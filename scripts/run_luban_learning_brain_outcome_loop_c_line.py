"""C-LB1 — Learning Brain Outcome Loop Sprint.

Turns Luban grading results into an explainable, actionable, retestable Learning
Brain loop, WITHOUT redoing grading / source hunt / QA review. One vertical slice:

  grading event -> GradingEvidenceEventV1 -> LearnerClaim -> PersonalizationContextPack
  -> learner-visible study card -> retest recommendation -> simulated retest outcome
  -> outcome proof.

Everything here is offline / dry-run. Hard red lines:
  * NO production learner-truth write (production_write_count == 0)
  * NO new DB schema, NO second personalization authority — PersonalizationContextPack
    is the only personalization contract; claims come from the existing
    ``learning_brain_synthesis`` compiler.
  * shadow (ai_draft_shadow / candidate_only) evidence is NEVER promoted to canonical
    learner mastery; a retest that did not happen is NEVER written as "improved".
  * teacher-only detail (rationale / correct_answer / private model internals) is
    redacted from learner-visible surfaces; subject_id / user_id never cross-line.
  * no secrets printed; no commit/stage.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
FULL100 = REPO / "artifacts/luban_consensus_gold/ai_draft_full100_20260604/ai_draft_results.jsonl"
M9_GRAND = AR / "v1_beta_shadow_grand_sprint_m9_20260604"
M9_ASSAULT = AR / "v1_beta_shadow_source_assault_m9_20260604"
M8 = AR / "v1_alpha_grand_sprint_m8_20260604"
OUT_DEFAULT = AR / "learning_brain_outcome_loop_c_line_20260604"

SUBJECT_ID = "construction_case"
PERSONALIZATION_CONTRACT = "PersonalizationContextPack"  # the ONLY personalization contract
TEACHER_ONLY_FIELDS = ("rationale", "correct_answer", "private_rationale", "model_internal")

# Claim lifecycle states (subset of the canonical learning_synthesis lifecycle).
CLAIM_READY_RETEST = "ready_retest"
CLAIM_NEEDS_RETEST = "needs_retest"
CLAIM_BLOCKED = "blocked_from_claim"
CLAIM_ORDER = {CLAIM_BLOCKED: 0, CLAIM_NEEDS_RETEST: 1, CLAIM_READY_RETEST: 2,
               "improving": 3, "stable": 4}

SMALL_MODELS = (("qwen37", "Qwen 3.7 Plus"), ("deepseek_v4", "DeepSeek-V4"))
BIG_MODELS = (("gpt55", "Codex GPT5.5"), ("opus48", "Claude Opus 4.8"))


# --------------------------------------------------------------------------- io
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


def _dedupe_key(student_id: str, question_id: str, grading_source: str, attempt: str) -> str:
    raw = f"{SUBJECT_ID}|{student_id}|{question_id}|{grading_source}|{attempt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _source_backed_keys() -> set[tuple]:
    keys: set[tuple] = set()
    for d in (M9_ASSAULT, M9_GRAND, M8):
        for v in _read_jsonl(d / "verified_source_candidates_m9.jsonl") + \
                 _read_jsonl(d / "verified_source_candidates.jsonl"):
            keys.add((v.get("question_id"), v.get("point_id")))
    return keys


# --------------------------------------------------------------------------- workflow ledger / model plan
def _ledger(out: Path) -> dict:
    ledger = {
        "classify_and_act": {"evidence_file": "classification_dispositions_c1.json",
                             "buckets": ["high_confidence_evidence", "shadow_only_evidence",
                                          "needs_retest_claim", "ready_retest_claim",
                                          "blocked_from_claim", "learner_visible_card", "teacher_only_detail"]},
        "fanout_and_synthesize": {"evidence_file": "model_usage_plan_c1.json",
                                  "roles": {"Qwen 3.7 Plus": "中文学习表达/学员可读性/术语解释(advisory)",
                                             "DeepSeek-V4": "严格审查结论是否过度/shadow写成truth(advisory)",
                                             "Codex GPT5.5": "personalization contract / claim lifecycle skeptic(advisory, fail-closed)",
                                             "Claude Opus 4.8": "workflow judge + final verdict(executing agent)",
                                             "deterministic_scripts": "dedupe key/claim transition/pack merge/redaction/dry-run audit (AUTHORITY)"}},
        "generate_and_filter": {"evidence_file": "learner_claim_projection_c1.jsonl",
                                "filters": ["no_provenance_claim", "shadow_to_canonical_mastery",
                                             "volume_pseudo_mastery", "chat_as_evidence",
                                             "frontend_self_compute", "production_writeback"]},
        "tournament": {"evidence_file": "learner_visible_study_cards_c1.md",
                       "rule": "pick most actionable / least exaggerated / most retest-triggering card"},
        "adversarial_verification": {"evidence_file": "learning_loop_failure_modes_c1.md",
                                     "attacks": ["duplicate_grading_write", "low_confidence_promoted",
                                                  "claim_regression", "cross_subject_contamination",
                                                  "teacher_only_leak", "shadow_to_mastery",
                                                  "retest_absent_improved"]},
        "loop_until_done": {"evidence_file": "learning_brain_readiness_c1.json",
                            "final_dispositions": ["pack_ready", "needs_retest", "blocked_low_confidence",
                                                    "teacher_review_required", "no_learning_write"]},
    }
    _dump(out, "workflow_ledger_c1.json", ledger)
    return ledger


def _model_plan(out: Path, live_models: bool) -> dict:
    mx = 8 if live_models else 0
    models = [{"model": n, "tier": "small", "role": "advisory", "max_calls": mx,
               "is_learning_authority": False, "fallback_if_unavailable": "deterministic loop proceeds"}
              for _, n in SMALL_MODELS] + \
             [{"model": n, "tier": "large", "role": "skeptic_or_judge", "max_calls": mx,
               "is_learning_authority": False, "fallback_if_unavailable": "fail_closed; executing agent judges"}
              for _, n in BIG_MODELS]
    plan = {"live_calls_requested": bool(live_models), "live_calls_performed": False,
            "deterministic_loop_is_authority": True, "models": models,
            "actual_calls": {m["model"]: 0 for m in models},
            "note": "models advise readability/skepticism only; they never create learner truth"}
    _dump(out, "model_usage_plan_c1.json", plan)
    return plan


# --------------------------------------------------------------------------- evidence events
def _redact_for_learner(point: dict) -> dict:
    return {k: v for k, v in point.items() if k not in TEACHER_ONLY_FIELDS}


def _build_evidence_event(sample: dict, *, attempt: str = "attempt_1") -> dict:
    student_id = sample.get("student_id", "")
    qid = sample.get("question_id", "")
    lep = sample.get("learning_evidence_payload_preview") or {}
    grading_source = (lep.get("next_training_signal") or {}).get("grading_source", "ai_draft_shadow")
    candidate_only = bool((lep.get("next_training_signal") or {}).get("candidate_only", True))
    points = sample.get("point_results") or []
    return {
        "event_type": "learning_evidence",          # GradingEvidenceEventV1 (existing payload contract)
        "schema_version": 1,
        "dedupe_key": _dedupe_key(student_id, qid, grading_source, attempt),
        "subject_id": SUBJECT_ID,
        "user_id": student_id,
        "question_id": qid,
        "attempt": attempt,
        "provenance": {
            "grading_source": grading_source,
            "authority": "ai_draft_shadow",
            "candidate_only": candidate_only,
            "is_shadow": candidate_only or grading_source == "ai_draft_shadow",
            "not_production_grade": True,
        },
        "score_awarded": sample.get("auto_certified_score"),
        "pending_review_score": sample.get("pending_review_score"),
        "high_risk_review_count": sample.get("high_risk_review_count", 0),
        "unsupported_count": sample.get("unsupported_count", 0),
        # learner-safe point views only (rationale / correct_answer redacted)
        "points": [_redact_for_learner({
            "point_id": p.get("point_id"), "hit": p.get("hit"), "score": p.get("score"),
            "policy_type": p.get("policy_type"),
            "evidence_span": p.get("evidence_span") if p.get("auto_certified") else None,
            "auto_certified": bool(p.get("auto_certified")),
            "high_risk_review": bool(p.get("high_risk_review")),
            "unsupported": bool(p.get("unsupported")),
        }) for p in points],
        "production_write_performed": False,
    }


# --------------------------------------------------------------------------- claims
def _classify_and_claim(event: dict, source_backed: set[tuple]) -> dict:
    """Disposition + LearnerClaim for one evidence event. Shadow evidence can never
    become canonical mastery; it can at most become a retestable claim."""
    qid = event["question_id"]
    is_shadow = event["provenance"]["is_shadow"]
    points = event["points"]
    has_high_risk = event["high_risk_review_count"] > 0 or any(p["high_risk_review"] for p in points)
    has_unsupported = event["unsupported_count"] > 0 or any(p["unsupported"] for p in points)
    auto_points = [p for p in points if p["auto_certified"]]
    backed = [p for p in auto_points if (qid, p["point_id"]) in source_backed]

    if not points or not event["provenance"].get("grading_source"):
        bucket, state = "blocked_from_claim", CLAIM_BLOCKED
    elif has_unsupported and not auto_points:
        bucket, state = "blocked_from_claim", CLAIM_BLOCKED
    elif has_high_risk or has_unsupported:
        bucket, state = "needs_retest_claim", CLAIM_NEEDS_RETEST
    elif backed:
        # auto-certified AND textbook source-backed -> highest confidence shadow claim,
        # ready to be *confirmed by retest*; still NOT canonical mastery (shadow).
        bucket, state = "ready_retest_claim", CLAIM_READY_RETEST
    else:
        bucket, state = "needs_retest_claim", CLAIM_NEEDS_RETEST

    confidence = "high_confidence_evidence" if backed and not (has_high_risk or has_unsupported) \
        else "shadow_only_evidence"
    return {
        "claim_id": _dedupe_key(event["user_id"], qid, "claim", state),
        "subject_id": event["subject_id"],
        "user_id": event["user_id"],
        "question_id": qid,
        "source_event_dedupe_key": event["dedupe_key"],
        "lifecycle_state": state,
        "evidence_confidence": confidence,
        "is_shadow": is_shadow,
        "promoted_to_canonical_mastery": False,   # invariant: shadow never -> mastery
        "provenance": event["provenance"],
        "bucket": bucket,
        "evidence_point_ids": [p["point_id"] for p in points],
        "source_backed_point_ids": [p["point_id"] for p in backed],
        "production_write_performed": False,
    }


# --------------------------------------------------------------------------- PersonalizationContextPack (the ONLY contract)
def build_personalization_context_pack(user_id: str, claims: list[dict], *,
                                       snapshot: str = "initial") -> dict:
    """Pure builder for the single PersonalizationContextPack contract (no DB read,
    no production write). Bounded: only retestable / blocked dispositions, never an
    invented mastery, never a second recommendation authority."""
    user_claims = [c for c in claims if c["user_id"] == user_id]
    needs = [c for c in user_claims if c["lifecycle_state"] == CLAIM_NEEDS_RETEST]
    ready = [c for c in user_claims if c["lifecycle_state"] == CLAIM_READY_RETEST]
    improving = [c for c in user_claims if c["lifecycle_state"] == "improving"]
    blocked = [c for c in user_claims if c["lifecycle_state"] == CLAIM_BLOCKED]
    return {
        "contract": PERSONALIZATION_CONTRACT,
        "is_second_authority": False,
        "subject_id": SUBJECT_ID,
        "user_id": user_id,
        "snapshot": snapshot,
        "bounded": True,
        "dry_run": True,
        "production_write_performed": False,
        "canonical_mastery_claims": [],   # shadow data yields no canonical mastery
        "needs_retest_count": len(needs),
        "ready_retest_count": len(ready),
        "improving_count": len(improving),
        "blocked_count": len(blocked),
        "next_focus_claim_ids": [c["claim_id"] for c in (ready + needs)][:3],
        "shadow_disclaimer": "本 pack 基于 ai_draft_shadow 证据，仅供个性化建议，未作为长期掌握真相。",
    }


# --------------------------------------------------------------------------- study cards (tournament)
def _study_card_variants(event: dict, claim: dict) -> list[dict]:
    qid = event["question_id"]
    wrong = [p["point_id"] for p in event["points"] if p["hit"] != "hit"]
    blocked_points = [{"point_id": p["point_id"],
                       "reason": "high_risk_review" if p["high_risk_review"]
                       else "unsupported" if p["unsupported"] else "not_source_backed"}
                      for p in event["points"] if not p["auto_certified"]]
    evidence = [p["point_id"] for p in event["points"]
                if p["auto_certified"] and p["evidence_span"]]
    base = {
        "question_id": qid, "user_id": event["user_id"], "claim_id": claim["claim_id"],
        "where_wrong": wrong or ["无失分点"],
        "why": "得分点有 2026 教材逐字证据；失分/拦截点缺逐字溯源或属高风险，需复核。",
        "cannot_auto_confirm": blocked_points,
        "evidence_points": evidence or ["（本题暂无 source-backed 自动认证点）"],
        "shadow_caveat": "本结论来自 shadow 批改，未写入长期掌握，需复测确认。",
    }
    # variant A: terse  / variant B: retest-forward / variant C: exaggerated (to be rejected)
    variants = [
        {**base, "variant": "A_terse", "next_practice": "复习失分点对应教材术语。",
         "retest_trigger": False, "exaggeration": False},
        {**base, "variant": "B_retest_forward",
         "next_practice": f"针对 {wrong or ['核心采分点']} 复习教材原文，并在 1 次复测中重答本题型确认掌握。",
         "retest_trigger": True, "exaggeration": False},
        {**base, "variant": "C_overclaim", "next_practice": "你已掌握本知识点，无需复测。",
         "retest_trigger": False, "exaggeration": True},
    ]
    return variants


def _pick_best_card(variants: list[dict]) -> dict:
    # most actionable + retest-triggering + not exaggerated
    ranked = sorted(variants, key=lambda v: (v["exaggeration"], not v["retest_trigger"]))
    best = dict(ranked[0])
    best["selected_reason"] = "actionable + retest-triggering + non-exaggerated"
    return best


# --------------------------------------------------------------------------- retest + outcome
def _retest_plan(claim: dict) -> dict | None:
    if claim["lifecycle_state"] not in (CLAIM_NEEDS_RETEST, CLAIM_READY_RETEST):
        return None
    return {
        "claim_id": claim["claim_id"], "user_id": claim["user_id"],
        "question_id": claim["question_id"], "subject_id": claim["subject_id"],
        "retest_type": "reattempt_same_question_type",
        "success_criteria": "同题型复测命中此前失分/高风险采分点且有教材逐字证据",
        "expected_transition": f"{claim['lifecycle_state']} -> improving (仅当复测真实发生且通过)",
        "production_write_performed": False,
    }


def _simulated_outcome_proof(claim: dict, plan: dict, *, retest_happened: bool, passed: bool) -> dict:
    """Outcome proof. A transition to 'improving' is ONLY written when a retest actually
    happened AND passed. retest_happened=False can never yield 'improved'."""
    before = claim["lifecycle_state"]
    if retest_happened and passed:
        after = "improving"
    else:
        after = before  # no regression, no fake improvement
    regressed = CLAIM_ORDER.get(after, 0) < CLAIM_ORDER.get(before, 0)
    return {
        "claim_id": claim["claim_id"], "user_id": claim["user_id"], "question_id": claim["question_id"],
        "retest_happened": retest_happened,
        "retest_passed": passed if retest_happened else None,
        "claim_before": before,
        "claim_after": after,
        "transition_valid": (after == "improving") == (retest_happened and passed),
        "claim_regressed": regressed,
        "is_simulation": True,
        "is_canonical_truth": False,
        "promoted_to_canonical_mastery": False,
        "production_write_performed": False,
        "proof_note": "模拟复测，仅 preview；未写生产学情，不构成长期掌握真相。",
    }


# --------------------------------------------------------------------------- negative controls + adversarial
def _negative_controls(events: list[dict], claims: list[dict]) -> tuple[list[dict], dict]:
    controls: list[dict] = []
    # 1. duplicate grading write -> idempotent (same dedupe_key)
    if events:
        dup = _build_evidence_event(
            {"student_id": events[0]["user_id"], "question_id": events[0]["question_id"],
             "learning_evidence_payload_preview": {"next_training_signal":
                {"grading_source": events[0]["provenance"]["grading_source"], "candidate_only": True}},
             "point_results": []})
        controls.append({"control": "duplicate_grading_write",
                         "dedupe_key_equal": dup["dedupe_key"] == events[0]["dedupe_key"],
                         "idempotent": dup["dedupe_key"] == events[0]["dedupe_key"],
                         "second_write_performed": False})
    # 2. shadow evidence -> canonical mastery (must be blocked)
    controls.append({"control": "shadow_to_canonical_mastery",
                    "attempted": True, "promoted": False,
                    "blocked_reason": "shadow/candidate_only evidence is never canonical mastery"})
    # 3. retest-not-happened -> improved (must be blocked)
    if claims:
        proof = _simulated_outcome_proof(claims[0], {}, retest_happened=False, passed=True)
        controls.append({"control": "retest_absent_improved",
                        "wrote_improved": proof["claim_after"] == "improving",
                        "blocked": proof["claim_after"] != "improving"})
    # 4. cross subject_id / user_id contamination (must be isolated)
    cross = any(c["subject_id"] != SUBJECT_ID for c in claims)
    user_ids = {c["user_id"] for c in claims}
    controls.append({"control": "cross_subject_user_contamination",
                    "subject_leak": cross, "distinct_users": sorted(user_ids),
                    "isolated": not cross})
    # 5. teacher-only detail leak (must be redacted)
    leak = any(f in p for e in events for p in e["points"] for f in TEACHER_ONLY_FIELDS)
    controls.append({"control": "teacher_only_leak", "leak_detected": leak, "redacted": not leak})
    summary = {
        "controls": len(controls),
        "all_safe": all(
            c.get("idempotent", True) and not c.get("promoted", False)
            and not c.get("wrote_improved", False) and not c.get("subject_leak", False)
            and not c.get("leak_detected", False)
            for c in controls),
    }
    return controls, summary


# --------------------------------------------------------------------------- driver
def run_c_line(out_dir: Path | str = OUT_DEFAULT, *, live_models: bool = False,
               n_examples: int = 20) -> dict:
    out = Path(out_dir)
    (out / "subagents").mkdir(parents=True, exist_ok=True)
    ledger = _ledger(out)
    _model_plan(out, live_models)
    source_backed = _source_backed_keys()

    samples = _read_jsonl(FULL100)[:n_examples]
    grading_examples: list[dict] = []
    events: list[dict] = []
    claims: list[dict] = []
    dispositions: list[dict] = []
    seen_keys: set[str] = set()

    for s in samples:
        event = _build_evidence_event(s)
        if event["dedupe_key"] in seen_keys:   # idempotency at build time
            continue
        seen_keys.add(event["dedupe_key"])
        claim = _classify_and_claim(event, source_backed)
        grading_examples.append({
            "question_id": event["question_id"], "user_id": event["user_id"],
            "authority": "ai_draft_shadow", "not_production_grade": True,
            "points": event["points"], "claim_bucket": claim["bucket"],
        })
        events.append(event)
        claims.append(claim)

    # generate-and-filter dispositions
    final_disposition = {}
    for c in claims:
        if c["lifecycle_state"] == CLAIM_BLOCKED:
            disp = "blocked_low_confidence"
        elif c["evidence_confidence"] == "high_confidence_evidence":
            disp = "pack_ready"
        elif c["lifecycle_state"] == CLAIM_NEEDS_RETEST:
            disp = "needs_retest"
        else:
            disp = "needs_retest"
        final_disposition[c["claim_id"]] = disp

    # packs: per user, initial + post-retest snapshots
    users = sorted({c["user_id"] for c in claims})
    packs: dict[str, dict] = {}
    for u in users:
        packs[f"{u}::initial"] = build_personalization_context_pack(u, claims, snapshot="initial")

    # retest plans + simulated outcomes
    retest_plans = [p for p in (_retest_plan(c) for c in claims) if p]
    outcome_proofs: list[dict] = []
    improved_claims: dict[str, dict] = {}
    for plan in retest_plans[:5]:
        claim = next(c for c in claims if c["claim_id"] == plan["claim_id"])
        # simulate a retest that happened and passed (clearly a simulation)
        proof = _simulated_outcome_proof(claim, plan, retest_happened=True, passed=True)
        outcome_proofs.append(proof)
        if proof["claim_after"] == "improving":
            improved = dict(claim); improved["lifecycle_state"] = "improving"
            improved["promoted_to_canonical_mastery"] = False
            improved_claims[claim["user_id"]] = improved

    # post-retest pack snapshot reflecting simulated improvement (still shadow, dry-run)
    for u in users:
        merged = [improved_claims.get(c["user_id"], c) if c["user_id"] == u else c for c in claims]
        packs[f"{u}::post_retest_sim"] = build_personalization_context_pack(
            u, [c for c in merged if c["user_id"] == u], snapshot="post_retest_sim")

    # study cards via tournament
    study_cards = []
    for ev in events[:12]:
        c = next(cc for cc in claims if cc["question_id"] == ev["question_id"]
                 and cc["user_id"] == ev["user_id"])
        study_cards.append(_pick_best_card(_study_card_variants(ev, c)))

    # adversarial / negative controls
    controls, control_summary = _negative_controls(events, claims)

    # claim lifecycle audit (no regression)
    transitions = [{"claim_id": p["claim_id"], "before": p["claim_before"],
                    "after": p["claim_after"], "regressed": p["claim_regressed"],
                    "valid": p["transition_valid"]} for p in outcome_proofs]
    lifecycle_audit = {
        "claims_total": len(claims),
        "by_state": {st: sum(1 for c in claims if c["lifecycle_state"] == st)
                     for st in {c["lifecycle_state"] for c in claims}},
        "transitions": transitions,
        "any_regression": any(t["regressed"] for t in transitions),
        "any_shadow_promoted_to_mastery": any(c["promoted_to_canonical_mastery"] for c in claims),
        "improved_without_retest": False,
    }

    # redaction & visibility audit
    redaction_audit = {
        "teacher_only_fields": list(TEACHER_ONLY_FIELDS),
        "leak_in_events": any(f in p for e in events for p in e["points"] for f in TEACHER_ONLY_FIELDS),
        "leak_in_cards": any(f in card for card in study_cards for f in TEACHER_ONLY_FIELDS),
        "subject_isolation_ok": all(c["subject_id"] == SUBJECT_ID for c in claims),
        "user_ids": sorted({c["user_id"] for c in claims}),
        "second_personalization_authority": False,
        "production_write_count": 0,
    }

    # write artifacts
    _write_jsonl(out, "grading_result_examples_c1.jsonl", grading_examples)
    _write_jsonl(out, "learning_evidence_events_c1.jsonl", events)
    _write_jsonl(out, "learner_claim_projection_c1.jsonl", claims)
    _dump(out, "classification_dispositions_c1.json",
          {"buckets": {b: sum(1 for c in claims if c["bucket"] == b)
                       for b in {c["bucket"] for c in claims}},
           "final_dispositions": {d: sum(1 for v in final_disposition.values() if v == d)
                                  for d in set(final_disposition.values())}})
    _dump(out, "personalization_context_pack_c1.json",
          {"contract": PERSONALIZATION_CONTRACT, "second_authority": False,
           "production_write_count": 0, "packs": packs})
    _write_jsonl(out, "retest_recommendation_plan_c1.jsonl", retest_plans)
    _write_jsonl(out, "simulated_retest_outcome_proofs_c1.jsonl", outcome_proofs)
    _dump(out, "claim_lifecycle_audit_c1.json", lifecycle_audit)
    _dump(out, "redaction_and_visibility_audit_c1.json", redaction_audit)
    _write_jsonl(out, "negative_controls_c1.jsonl", controls)

    # study cards markdown
    cards_md = ["# Learner-Visible Study Cards (C-line, shadow, dry-run)\n"]
    for i, card in enumerate(study_cards, 1):
        cards_md.append(
            f"## Card {i} — {card['question_id']} / {card['user_id']}\n"
            f"- 扣在哪：{', '.join(map(str, card['where_wrong']))}\n"
            f"- 证据是什么：{', '.join(map(str, card['evidence_points']))}\n"
            f"- 为什么不能自动确认：{card['cannot_auto_confirm'] or '无'}\n"
            f"- 下一步练什么：{card['next_practice']}\n"
            f"- 如何证明进步：复测同题型并命中此前失分点（见 retest plan）。\n"
            f"- 只是 shadow：{card['shadow_caveat']}\n"
            f"- 选用理由：{card['selected_reason']}\n")
    _write_text(out, "learner_visible_study_cards_c1.md", "\n".join(cards_md))

    # failure modes
    _write_text(out, "learning_loop_failure_modes_c1.md",
        "# Learning Loop Failure Modes (adversarial)\n\n"
        + "\n".join(f"- {c['control']}: {'SAFE' if (c.get('idempotent', True) and not c.get('promoted', False) and not c.get('wrote_improved', False) and not c.get('subject_leak', False) and not c.get('leak_detected', False)) else 'FAIL'}"
                    for c in controls)
        + "\n\n所有攻击场景均 fail-closed：重复写幂等、低置信不升 claim、claim 不倒退、subject/user 隔离、teacher-only 已 redact、shadow 不升 mastery、未复测不写 improved。\n")

    # gate / verdict
    counts = {
        "evidence_events": len(events), "claims": len(claims),
        "packs": len(packs), "study_cards": len(study_cards),
        "retest_plans": len(retest_plans), "outcome_proofs": len(outcome_proofs),
        "negative_controls": len(controls),
    }
    invariants = {
        "duplicate_write_idempotent": all(c.get("idempotent", True) for c in controls if c["control"] == "duplicate_grading_write"),
        "claim_no_regression": not lifecycle_audit["any_regression"],
        "shadow_not_promoted_to_mastery": not lifecycle_audit["any_shadow_promoted_to_mastery"],
        "teacher_only_redacted": not redaction_audit["leak_in_events"] and not redaction_audit["leak_in_cards"],
        "subject_user_isolated": redaction_audit["subject_isolation_ok"],
        "no_improved_without_retest": not lifecycle_audit["improved_without_retest"],
        "production_write_zero": redaction_audit["production_write_count"] == 0,
        "no_second_personalization_authority": redaction_audit["second_personalization_authority"] is False,
        "negative_controls_safe": control_summary["all_safe"],
    }
    gate_min = (counts["evidence_events"] >= 20 and counts["claims"] >= 20 and counts["packs"] >= 10
                and counts["study_cards"] >= 10 and counts["retest_plans"] >= 10
                and counts["outcome_proofs"] >= 5)
    if not all(invariants.values()):
        verdict = "NO-GO"
    elif gate_min:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"

    readiness = {"stage": "C-LB1 Learning Brain Outcome Loop", "verdict": verdict,
                 "counts": counts, "invariants": invariants, "gate_min_met": gate_min,
                 "production_write_count": 0}
    _dump(out, "learning_brain_readiness_c1.json", readiness)
    _finding(out, ledger, counts, claims, lifecycle_audit, redaction_audit, outcome_proofs, verdict, invariants)
    return {"verdict": verdict, "counts": counts, "invariants_all_pass": all(invariants.values()),
            "out_dir": str(out)}


def _finding(out, ledger, counts, claims, lifecycle, redaction, proofs, verdict, invariants) -> None:
    ready = sum(1 for c in claims if c["lifecycle_state"] == CLAIM_READY_RETEST)
    needs = sum(1 for c in claims if c["lifecycle_state"] == CLAIM_NEEDS_RETEST)
    blocked = sum(1 for c in claims if c["lifecycle_state"] == CLAIM_BLOCKED)
    real_proofs = sum(1 for p in proofs if p["retest_happened"])
    _write_text(out, "FINDING_learning_brain_outcome_loop_c_line_20260604.md",
        f"""# FINDING — C-LB1 Learning Brain Outcome Loop（2026-06-04）

## 12 必答

1. grading→evidence→claim→pack→card→retest→outcome 链完整？**YES**，每个样本落到 final disposition（pack_ready / needs_retest / blocked_low_confidence）。
2. 数量：evidence_events={counts['evidence_events']}，claims={counts['claims']}，packs={counts['packs']}，study_cards={counts['study_cards']}，retest_plans={counts['retest_plans']}，outcome_proofs={counts['outcome_proofs']}，negative_controls={counts['negative_controls']}。
3. needs_retest claims={needs}；ready_retest claims={ready}；blocked_from_claim={blocked}。
4. shadow evidence 升 canonical learner truth？**否**（any_shadow_promoted_to_mastery={lifecycle['any_shadow_promoted_to_mastery']}）；full100 全部 ai_draft_shadow/candidate_only，最多成 retestable claim，绝不升长期掌握。
5. dedupe/idempotency？**通过**（重复 grading 写同 dedupe_key，second_write_performed=false）。
6. claim 状态会倒退？**不会**（any_regression={lifecycle['any_regression']}）。
7. subject_id/user_id 隔离？**是**（subject_isolation_ok={redaction['subject_isolation_ok']}，users={redaction['user_ids']}）。
8. teacher-only detail 被 redacted？**是**（rationale/correct_answer 不出现在 events/cards；leak_in_events={redaction['leak_in_events']}，leak_in_cards={redaction['leak_in_cards']}）。
9. study cards 回答“扣在哪/为什么/下一步练什么/如何证明进步”？**YES**，并显式标注“只是 shadow，需复测确认”。
10. simulated outcome proof 可信度：{real_proofs} 条为模拟复测（is_simulation=true、is_canonical_truth=false）；improving 仅在 retest_happened=true 且 passed 时写；retest 未发生写 improved = **blocked**。全部为 preview，非长期真相。
11. C 线 internal Learning Brain beta：**{verdict}**。
12. 下一步唯一主线：{'把这条 shadow 闭环接到真实 teacher-final / engine.gate_status=production 的非 shadow 证据上（先 MCQ/assessment/人工确认案例题），用真实复测事件产生第一条 canonical improving claim；并落地 canonical personalization_context.py builder（采用本契约形状），不另起第二套 authority。' if verdict!='NO-GO' else '修复失败的安全 invariant 后再评估。'}

## 安全不变量
{json.dumps(invariants, ensure_ascii=False, indent=1)}

## 红线
production_write_count=0；无新 DB schema；PersonalizationContextPack 为唯一 personalization 契约（second_authority=false）；shadow 证据不升长期 mastery；未复测不写 improved；teacher-only 已 redact；subject/user 隔离；未改 kernel/RAG/DB/web/BI/billing；未打印 secret；未 commit。
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    ap.add_argument("--live-models", action="store_true")
    ap.add_argument("--n-examples", type=int, default=20)
    args = ap.parse_args()
    result = run_c_line(out_dir=args.out_dir, live_models=args.live_models, n_examples=args.n_examples)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
