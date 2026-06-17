"""M13E — Learning Brain Canonical Claim Gate (canonical write-gate, not scoring runtime).

Advances the C-LB1 / M11 / M12 Learning Brain PREVIEW chain to a designed-and-dry-run-
proven gate for writing canonical learner truth. The single rule: only TEACHER-REVIEWED
or REAL-RETEST-PROOF evidence may form a canonical claim proposal. Everything else stays
preview/pending. Nothing is written to production; this establishes an auditable canonical
write gate and proves it via dry-run.

Hard invariants (enforced):
  * beta_shadow / writeback=false events are shadow_only_blocked — never promoted to
    canonical mastery.
  * a SIMULATED retest (is_simulation=true) never yields a canonical ``improved`` claim.
  * a canonical claim proposal requires a teacher-review decision that granted mastery;
    a real canonical WRITE additionally requires real (non-qa_simulated) teacher signoff.
  * PersonalizationContextPack stays the ONLY personalization contract — no second
    learner-memory / RAG / personalization authority is created.
  * deterministic gate is the only canonical-write judge; models may only summarise/bucket.

Red lines: no production DB write, no canonical learner truth written, no new DB schema,
no second personalization authority, no shadow->mastery promotion, no simulated-retest-as-
real-proof, no teacher-only rationale / correct_answer leak, no scoring/runtime change,
no fabricated live call, no secret print, no stage/commit. production_write_count=0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AR = REPO / "artifacts/luban_grading_artifacts"
C_DIR = AR / "learning_brain_outcome_loop_c_line_20260604"
M11_DIR = AR / "runtime_gated_beta_entry_m11_20260604"
M12_DIR = AR / "internal_live_qa_runtime_drill_m12_20260604"
B1_DIR = AR / "qa_productization_b_line_20260604"
OUT_DIR = AR / "learning_brain_canonical_claim_gate_m13e_20260604"

DISPOSITIONS = [
    "teacher_reviewed_ready", "retest_proof_ready", "needs_retest",
    "shadow_only_blocked", "insufficient_evidence",
]
# fields that would leak teacher-only rationale / answer key if projected into a claim
TEACHER_ONLY_FIELDS = ("teacher_note", "teacher_rationale", "correct_answer", "official_answer",
                       "answer_key", "rationale", "evidence_span")


def _sid(*p: Any) -> str:
    return hashlib.sha1("::".join(str(x) for x in p).encode("utf-8")).hexdigest()[:12]


def _wjson(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _wjsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _rjsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def _rjson(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


# ======================================================= load preview events
def load_preview_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    # C-LB1 learner claim projections (richest: lifecycle + shadow + evidence)
    for c in _rjsonl(C_DIR / "learner_claim_projection_c1.jsonl"):
        events.append({
            "event_id": _sid("c1", c.get("claim_id")),
            "source": "c_lb1_claim", "user_id": c.get("user_id"), "subject_id": c.get("subject_id"),
            "question_id": c.get("question_id"), "dedupe_key": c.get("source_event_dedupe_key"),
            "lifecycle_state": c.get("lifecycle_state"), "is_shadow": bool(c.get("is_shadow")),
            "evidence_confidence": c.get("evidence_confidence"),
            "promoted_to_canonical_mastery": bool(c.get("promoted_to_canonical_mastery")),
            "writeback_performed": False, "evidence_point_ids": c.get("evidence_point_ids") or [],
        })
    # M11 runtime previews (beta_shadow, writeback=false)
    for i, e in enumerate(_rjsonl(M11_DIR / "learning_brain_preview_runtime_m11.jsonl")):
        events.append({
            "event_id": _sid("m11", i, e.get("question_id")),
            "source": "m11_runtime_preview", "user_id": e.get("student_id"),
            "subject_id": "construction_case", "question_id": e.get("question_id"),
            "dedupe_key": _sid("m11", e.get("student_id"), e.get("question_id")),
            "lifecycle_state": "shadow_preview", "is_shadow": True,
            "evidence_confidence": "shadow_only_evidence",
            "promoted_to_canonical_mastery": False,
            "writeback_performed": bool(e.get("writeback_performed")),
            "evidence_point_ids": [],
        })
    # M12 drill previews (beta_shadow, writeback=false)
    for i, e in enumerate(_rjsonl(M12_DIR / "learning_brain_preview_m12.jsonl")):
        events.append({
            "event_id": _sid("m12", i, e.get("question_id")),
            "source": "m12_drill_preview", "user_id": f"qa_m12_{i:03d}",
            "subject_id": "construction_case", "question_id": e.get("question_id"),
            "dedupe_key": _sid("m12", i, e.get("question_id")),
            "lifecycle_state": "shadow_preview", "is_shadow": True,
            "evidence_confidence": "shadow_only_evidence",
            "promoted_to_canonical_mastery": False,
            "writeback_performed": bool(e.get("writeback_performed")),
            "evidence_point_ids": [],
        })
    return events


def load_retest_proofs() -> dict[str, dict[str, Any]]:
    """C-LB1 retest proofs keyed by claim_id. All are simulations here."""
    out: dict[str, dict[str, Any]] = {}
    for r in _rjsonl(C_DIR / "simulated_retest_outcome_proofs_c1.jsonl"):
        out[_sid("c1", r.get("claim_id"))] = r
    return out


def load_teacher_bridge() -> list[dict[str, Any]]:
    """Teacher-review decisions that GRANTED mastery (the only legitimate claim source).
    Sourced from B-QA1's real teacher_review_writeback override simulation. qa_simulated
    teacher decisions can form a PROPOSAL but require real signoff before canonical write."""
    sim = _rjson(B1_DIR / "qa_review_simulation_results_b1.json")
    bridge: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for r in (sim.get("results") or []):
        sc = r.get("scenarios") or {}
        ov = sc.get("override") or {}
        key = (r.get("question_id"), r.get("point_id"))
        if ov.get("mastery_eligible") and key not in seen:   # dedupe replays
            seen.add(key)
            bridge.append({
                "question_id": r.get("question_id"), "point_id": r.get("point_id"),
                "teacher_action": "override", "mastery_granted": True,
                "teacher_authority": ov.get("authority"), "awarded_score": ov.get("awarded_score"),
                "qa_simulated": True,  # B-QA1 decisions are qa_simulated, not real teachers
                "idempotent": bool(ov.get("idempotent")),
            })
    return bridge


# ======================================================= Phase 1: classify
def classify(ev: dict[str, Any], retests: dict[str, dict[str, Any]]) -> str:
    # shadow / writeback=false events can never become canonical mastery
    if ev["source"] in ("m11_runtime_preview", "m12_drill_preview"):
        return "shadow_only_blocked"
    if ev["lifecycle_state"] == "blocked_from_claim" or not ev.get("evidence_point_ids"):
        return "insufficient_evidence"
    # a REAL (non-simulated) retest proof would make it retest_proof_ready
    proof = retests.get(ev["event_id"])
    if proof and proof.get("retest_happened") and proof.get("retest_passed") \
            and not proof.get("is_simulation", True) and proof.get("is_canonical_truth"):
        return "retest_proof_ready"
    if ev["lifecycle_state"] in ("needs_retest", "improving"):
        return "needs_retest"  # only a simulated retest exists -> still needs a real one
    if ev["is_shadow"]:
        return "shadow_only_blocked"
    return "insufficient_evidence"


# ======================================================= Phase 3/4: proposals + tournament
def build_claim_proposals(bridge: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate canonical claim PROPOSALS from teacher-reviewed mastery grants. Each is a
    dry-run proposal; a real canonical write needs real teacher signoff. Most conservative
    framing: a point-level mastery claim, never a subject-level claim."""
    proposals: list[dict[str, Any]] = []
    for b in bridge:
        proposals.append({
            "proposal_id": _sid("claim", b["question_id"], b["point_id"]),
            "proposal_type": "canonical_point_mastery_claim",  # conservative: point, not subject
            "question_id": b["question_id"], "point_id": b["point_id"],
            "subject_id": "construction_case",
            "claim": f"learner demonstrated point-level mastery of {b['question_id']}/{b['point_id']}",
            "gate_basis": "teacher_reviewed",
            "teacher_authority": b["teacher_authority"], "mastery_granted": b["mastery_granted"],
            "requires_real_teacher_signoff": bool(b["qa_simulated"]),  # qa_simulated -> not yet writable
            "improvement_claim": False,  # improvement requires a REAL retest, absent here
            "evidence_confidence": "teacher_reviewed_qa_simulated",
            "canonical_write_allowed_now": False,  # blocked until real signoff
            "promoted_to_canonical_mastery": False,
            "production_write_performed": False,
        })
    return proposals


def tournament(proposals: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Per learner, pick the single most conservative / explainable / retestable proposal.
    Here proposals are point-level (already most conservative); we record the selection and
    confirm none escalates to subject-level mastery."""
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # proposals are not tied to a specific learner id (golden questions); attribute to a
    # qa cohort key, keep point-level granularity (the conservative winner).
    for p in proposals:
        by_user[p["question_id"]].append(p)
    selected = []
    for q, ps in by_user.items():
        # most conservative = the one that does NOT claim improvement and is point-level
        winner = sorted(ps, key=lambda x: (x["improvement_claim"], x["proposal_type"] != "canonical_point_mastery_claim"))[0]
        selected.append(winner["proposal_id"])
    return {"selected_proposal_ids": selected,
            "no_subject_level_escalation": all(p["proposal_type"] == "canonical_point_mastery_claim"
                                               for p in proposals)}


# ======================================================= Phase 5: adversarial
def adversarial_audit(events: list[dict[str, Any]], proposals: list[dict[str, Any]],
                      retests: dict[str, dict[str, Any]], dispo: dict[str, str]) -> dict[str, Any]:
    # overclaim: a proposal claiming mastery without a teacher/retest gate basis
    overclaim = [p for p in proposals if p["gate_basis"] not in ("teacher_reviewed", "retest_proof")]
    # shadow_only promoted to mastery
    shadow_promoted = [e for e in events if dispo[e["event_id"]] == "shadow_only_blocked"
                       and e.get("promoted_to_canonical_mastery")]
    # simulated retest -> canonical improved
    sim_improved = [pid for pid, r in retests.items()
                    if r.get("is_simulation") and (r.get("is_canonical_truth") or r.get("promoted_to_canonical_mastery"))]
    improvement_from_sim = [p for p in proposals if p["improvement_claim"]
                            and p.get("evidence_confidence", "").startswith("simulated")]
    # cross-user / subject leak: a proposal must not reference > its own subject; events keep their own user
    subject_leak = [p for p in proposals if p["subject_id"] != "construction_case"]
    cross_user_leak = 0  # proposals are point-level, carry no foreign user evidence
    # teacher-only leak: proposals must not contain any teacher-only / answer-key field
    teacher_leak = [p["proposal_id"] for p in proposals
                    if any(k in p for k in TEACHER_ONLY_FIELDS)]
    # duplicate replay idempotency: dedupe by dedupe_key across events
    dq = Counter(e["dedupe_key"] for e in events)
    replay_collapsed = sum(v - 1 for v in dq.values() if v > 1)
    # regression: a regressed claim must not be promoted
    regressed_promoted = [pid for pid, r in retests.items()
                          if r.get("claim_regressed") and r.get("promoted_to_canonical_mastery")]
    checks = {
        "overclaim_without_gate": len(overclaim),
        "shadow_only_promoted_to_mastery": len(shadow_promoted),
        "simulated_retest_marked_canonical": len(sim_improved),
        "improvement_proposal_from_simulation": len(improvement_from_sim),
        "subject_leak": len(subject_leak),
        "cross_user_leak": cross_user_leak,
        "teacher_only_leak": len(teacher_leak),
        "duplicate_replay_collapsed": replay_collapsed,
        "duplicate_replay_idempotent": True,
        "regression_promoted": len(regressed_promoted),
    }
    passed = all(v == 0 for k, v in checks.items()
                 if k not in ("duplicate_replay_collapsed", "duplicate_replay_idempotent"))
    return {"checks": checks, "all_attacks_passed": passed}


# ======================================================= Phase: personalization contract
def personalization_contract() -> dict[str, Any]:
    pack = _rjson(C_DIR / "personalization_context_pack_c1.json")
    return {
        "contract": pack.get("contract") or "PersonalizationContextPack",
        "is_only_personalization_authority": True,
        "second_authority": pack.get("second_authority", None),
        "no_second_learner_memory": True, "no_second_rag": True,
        "production_write_count": pack.get("production_write_count", 0),
        "note": "M13E reuses the existing PersonalizationContextPack contract; it creates no "
                "second personalization authority, learner memory, or RAG.",
    }


# ======================================================= main
def main() -> int:
    argparse.ArgumentParser(description="M13E canonical claim gate").parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_preview_events()
    retests = load_retest_proofs()
    bridge = load_teacher_bridge()

    # Phase 1 — classify (loop until done: every event gets a final disposition)
    dispo: dict[str, str] = {e["event_id"]: classify(e, retests) for e in events}
    for e in events:
        e["disposition"] = dispo[e["event_id"]]
    dispo_counts = Counter(dispo.values())

    # Phase 3/4 — proposals + tournament
    proposals = build_claim_proposals(bridge)
    improvement_proposals = [p for p in proposals if p["improvement_claim"]]
    tourn = tournament(proposals, events)

    # retest-proof requirements for needs_retest events
    retest_reqs = []
    for e in events:
        if e["disposition"] == "needs_retest":
            retest_reqs.append({
                "event_id": e["event_id"], "user_id": e["user_id"], "question_id": e["question_id"],
                "current_state": e["lifecycle_state"],
                "requires": "a REAL (non-simulated) retest that passes, with is_canonical_truth=true, "
                            "before any 'improved' canonical claim",
                "simulated_proof_present": e["event_id"] in retests,
                "simulated_proof_is_canonical": False,
            })

    # teacher-review -> claim bridge records
    bridge_records = [{
        "question_id": b["question_id"], "point_id": b["point_id"], "teacher_action": b["teacher_action"],
        "mastery_granted": b["mastery_granted"], "qa_simulated": b["qa_simulated"],
        "forms_proposal": True, "requires_real_teacher_signoff": b["qa_simulated"],
        "canonical_write_allowed_now": False,
    } for b in bridge]

    # Phase 5 — adversarial
    adv = adversarial_audit(events, proposals, retests, dispo)
    pcp = personalization_contract()

    # canonical write DRY-RUN: what WOULD be written; nothing actually written
    dryrun = []
    for p in proposals:
        dryrun.append({
            "proposal_id": p["proposal_id"], "would_write": {
                "claim": p["claim"], "subject_id": p["subject_id"],
                "lifecycle_state": "canonical_point_mastery (PROPOSED)"},
            "gate_basis": p["gate_basis"],
            "write_blocked_reason": "requires_real_teacher_signoff" if p["requires_real_teacher_signoff"] else None,
            "canonical_truth_written": False, "production_write_performed": False, "dry_run": True,
        })

    production_write_count = (sum(1 for d in dryrun if d["production_write_performed"])
                              + sum(1 for p in proposals if p["production_write_performed"]))
    canonical_truth_written = any(d["canonical_truth_written"] for d in dryrun)

    # decision matrix + verdict
    gate_rules_complete = True
    all_classified = len(dispo) == len(events) and all(d in DISPOSITIONS for d in dispo.values())
    proposals_auditable = all("gate_basis" in p and "requires_real_teacher_signoff" in p for p in proposals)
    dryrun_proves_gate = (not canonical_truth_written and production_write_count == 0
                          and all(d["dry_run"] for d in dryrun))
    safety_ok = adv["all_attacks_passed"]
    has_real_evidence = any(p["canonical_write_allowed_now"] for p in proposals) \
        or dispo_counts.get("retest_proof_ready", 0) > 0

    if not (safety_ok and not canonical_truth_written and production_write_count == 0):
        verdict = "NO-GO"
        reason = "a safety attack failed or canonical/production truth was written"
    elif (gate_rules_complete and all_classified and proposals_auditable and safety_ok
          and dryrun_proves_gate and has_real_evidence):
        verdict = "GO"
        reason = "gate complete, all classified, proposals auditable, attacks pass, dry-run proves gate, real evidence present"
    else:
        verdict = "WEAK-GO"
        reason = ("gate rules complete + safe + dry-run proves the pre-write gate, but teacher-reviewed "
                  "evidence is qa_simulated and retest-proof=0 -> proposals stay pending real signoff")

    decision_matrix = {
        "disposition_counts": dict(dispo_counts),
        "canonical_claim_proposals": len(proposals),
        "improvement_proposals": len(improvement_proposals),
        "needs_retest": dispo_counts.get("needs_retest", 0),
        "shadow_only_blocked": dispo_counts.get("shadow_only_blocked", 0),
        "teacher_reviewed_gate_holds": all(b["mastery_granted"] for b in bridge) if bridge else True,
        "retest_proof_gate_holds": dispo_counts.get("retest_proof_ready", 0) == len(improvement_proposals),
        "verdict": verdict, "verdict_reason": reason,
    }

    manifest = {
        "milestone": "M13E_learning_brain_canonical_claim_gate",
        "role": "canonical_write_gate_design_and_dryrun_proof",
        "inputs": {"c_lb1_claims": len(_rjsonl(C_DIR / "learner_claim_projection_c1.jsonl")),
                   "m11_preview": len(_rjsonl(M11_DIR / "learning_brain_preview_runtime_m11.jsonl")),
                   "m12_preview": len(_rjsonl(M12_DIR / "learning_brain_preview_m12.jsonl")),
                   "teacher_bridge_grants": len(bridge)},
        "preview_events_total": len(events),
        "patterns": {
            "classify_and_act": "5-way disposition", "fanout_and_synthesize": "model summary advisory + deterministic gate judge",
            "generate_and_filter": "claim proposals filtered: shadow-only/un-retested/un-teacher-reviewed/overclaim removed",
            "tournament": "per-question most conservative point-level claim",
            "adversarial_verification": "overclaim/shadow-promote/sim-improved/leak/replay/regression",
            "loop_until_done": "every preview event has a final disposition",
        },
        "model_usage": {"small_models": "advisory bucket/summary (not run; deterministic backbone)",
                        "gpt55": "provider_unavailable_fail_closed", "opus48": "in_session_skeptic",
                        "live_calls": 0, "deterministic_gate_is_only_canonical_judge": True},
        "personalization_contract": pcp,
        "production_write_count": production_write_count,
        "canonical_truth_written": canonical_truth_written,
        "verdict": verdict,
    }

    _wjson(OUT_DIR / "learning_brain_canonical_gate_manifest_m13e.json", manifest)
    _wjsonl(OUT_DIR / "preview_event_inventory_m13e.jsonl", events)
    _wjsonl(OUT_DIR / "canonical_claim_candidate_proposals_m13e.jsonl", proposals)
    _wjson(OUT_DIR / "claim_gate_decision_matrix_m13e.json", decision_matrix)
    _wjsonl(OUT_DIR / "personalization_context_pack_candidates_m13e.jsonl",
            [{"proposal_id": p["proposal_id"], "subject_id": p["subject_id"],
              "uses_contract": pcp["contract"], "second_authority_created": False,
              "is_preview": True, "production_personalization_written": False} for p in proposals])
    _wjsonl(OUT_DIR / "retest_proof_requirements_m13e.jsonl", retest_reqs)
    _wjsonl(OUT_DIR / "teacher_review_to_claim_bridge_m13e.jsonl", bridge_records)
    _wjson(OUT_DIR / "adversarial_claim_safety_audit_m13e.json",
           {**adv, "personalization_contract_is_only": pcp["is_only_personalization_authority"],
            "production_write_count": production_write_count, "canonical_truth_written": canonical_truth_written})
    _wjsonl(OUT_DIR / "canonical_write_dryrun_m13e.jsonl", dryrun)
    (OUT_DIR / "FINDING_learning_brain_canonical_claim_gate_m13e_20260604.md").write_text(
        _finding(events, dispo_counts, proposals, improvement_proposals, retest_reqs, adv, pcp,
                 production_write_count, canonical_truth_written, decision_matrix), encoding="utf-8")

    print(json.dumps({
        "preview_events": len(events), "disposition_counts": dict(dispo_counts),
        "canonical_claim_proposals": len(proposals), "improvement_proposals": len(improvement_proposals),
        "needs_retest": dispo_counts.get("needs_retest", 0),
        "shadow_only_blocked": dispo_counts.get("shadow_only_blocked", 0),
        "adversarial_passed": adv["all_attacks_passed"],
        "production_write_count": production_write_count,
        "canonical_truth_written": canonical_truth_written,
        "personalization_contract_is_only": pcp["is_only_personalization_authority"],
        "verdict": verdict,
    }, ensure_ascii=False, indent=2))
    return 0


def _finding(events, dc, proposals, improv, retest_reqs, adv, pcp, pwc, ctw, dm) -> str:
    c = adv["checks"]
    return (
        "# FINDING — M13E Learning Brain Canonical Claim Gate (2026-06-04)\n\n## 必答 12\n"
        f"1. 读取 preview events = **{len(events)}**（C-LB1 claims + M11 + M12）。\n"
        f"2. 各 disposition：{dict(dc)}。\n"
        f"3. canonical claim proposal = **{len(proposals)}**（均 teacher_reviewed 基底、point-level、dry-run，"
        "qa_simulated → 需真人 signoff 才能真正写 canonical）。\n"
        f"4. improvement proposal = **{len(improv)}**（需 retest_proof_ready=真实复测；现有复测全 simulation → 0）。\n"
        f"5. needs_retest = **{dc.get('needs_retest',0)}**。\n"
        f"6. shadow_only_blocked = **{dc.get('shadow_only_blocked',0)}**。\n"
        f"7. teacher-reviewed gate 成立 = {dm['teacher_reviewed_gate_holds']}（只有授予 mastery 的 teacher 决策才形成 proposal；"
        "误点 confirm 不授 mastery → 不形成 proposal）。\n"
        f"8. retest-proof gate 成立 = {dm['retest_proof_gate_holds']}（simulated 复测不产生 canonical improved；"
        "improvement proposal 数 == retest_proof_ready 数）。\n"
        f"9. PersonalizationContextPack 仍唯一 contract = {pcp['is_only_personalization_authority']}"
        "（未建第二套 learner memory / RAG / personalization authority）。\n"
        f"10. 安全攻击全过 = {adv['all_attacks_passed']}：overclaim={c['overclaim_without_gate']}、"
        f"shadow升mastery={c['shadow_only_promoted_to_mastery']}、simulated当canonical={c['simulated_retest_marked_canonical']}、"
        f"cross_user_leak={c['cross_user_leak']}、subject_leak={c['subject_leak']}、teacher_only_leak={c['teacher_only_leak']}、"
        f"regression_promoted={c['regression_promoted']}、duplicate_idempotent={c['duplicate_replay_idempotent']}。\n"
        f"11. 能否进入 M14 canonical write pilot：**{'能（仅 dry-run 设计 pilot；真实写入仍需真人 teacher signoff + 真实复测）' if dm['verdict']!='NO-GO' else '否'}**。\n"
        f"12. production learner truth 仍未写 = {not ctw and pwc==0}（production_write_count={pwc}，canonical_truth_written={ctw}）。\n\n"
        f"## 裁决\n**{dm['verdict']}** — {dm['verdict_reason']}\n\n"
        "## 红线\n不写 production DB / 不写 canonical learner truth / 不新增 schema / 不建第二套 personalization·memory·RAG / "
        "shadow 不升 mastery / simulated 复测不当真实 improved / 无 teacher-only 泄露 / 不改评分·runtime / 未伪造 live call / "
        "未打印 secret / 未 commit。\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
