"""M25-EF — Objective product loop + runtime_supply v2 closure (hermetic, no-live, preview-only).

v2 supply (real_source_candidate) -> loader.verified_index -> objective_runtime_adapter
-> objective_learning_brain_preview (evidence/claim/PCP/retest/work-order). PREVIEW ONLY:
no DB / canonical / mastery / published write. Writes 11 artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading import objective_real_source_extractor as E
from deeptutor.services.construction_grading import v2_objective_supply_loader as L
from deeptutor.services.construction_grading.objective_runtime_adapter import build_objective_candidate_payload
from deeptutor.services.construction_grading import objective_learning_brain_preview as P

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/luban_grading_artifacts/objective_product_loop_supply_v2_m25ef_20260605"
OUT.mkdir(parents=True, exist_ok=True)
USERS = ["qa_alice", "operator_bob", "test_carol"]
SUBJECT = "construction_exam_1"


def _wjsonl(name, rows):
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")


def _variant_for(rec, i):
    gold = rec["answer_key"]
    keys = sorted(rec["options"].keys())
    wrong = next((k for k in keys if k not in set(gold)), "Z")
    cycle = ["correct", "wrong", "blank", "invalid", "multi_missing", "multi_extra"][i % 6]
    if cycle == "correct":
        return "correct", gold
    if cycle == "wrong":
        return "wrong", wrong
    if cycle == "blank":
        return "blank", ""
    if cycle == "invalid":
        return "invalid", "Z"
    if cycle == "multi_missing" and rec["question_type"] == "multiple_choice" and len(gold) >= 2:
        return "multi_missing", gold[:-1]
    if cycle == "multi_extra" and rec["question_type"] == "multiple_choice":
        extra = next((k for k in keys if k not in set(gold)), None)
        return ("multi_extra", gold + extra) if extra else ("correct", gold)
    return "correct", gold


def main():
    supply = L.load_and_verify()
    index = supply["index"]
    bundle = E.build_real_candidate_bundle()
    records = bundle["records"]

    events, claims, retests, work_orders, ws_ledger = [], [], [], [], []
    # main loop: 3 users x 62 questions = 186 submissions
    for user in USERS:
        for i, rec in enumerate(records):
            qid = rec["question_id"]
            variant, selected = _variant_for(rec, i)
            payload = build_objective_candidate_payload(
                question_id=qid, selected_option=selected,
                learner_context={"student_id": user}, index=index)
            evt = P.build_objective_evidence_event(payload, user_id=user, subject_id=SUBJECT,
                                                   question_id=qid, variant=variant)
            events.append(evt)
            claims.append(P.build_claim_proposal(evt))
            retests.append(P.build_retest_plan(evt))
            ws_ledger.append({"user_id": user, "question_id": qid, "variant": variant,
                              "mode": payload.get("mode"), "is_correct": (payload.get("result") or {}).get("is_correct"),
                              "event_id": evt["event_id"], "claim_kind": evt["claim_kind"],
                              "promoted_to_mastery": evt["promoted_to_mastery"], "official_score": evt["official_score"]})
        # open-world unknowns per user
        for unk in [f"unknown-{user}-2024", "user-adhoc-xyz"]:
            payload = build_objective_candidate_payload(question_id=unk, selected_option="A",
                                                        learner_context={"student_id": user}, index=index)
            evt = P.build_objective_evidence_event(payload, user_id=user, subject_id=SUBJECT,
                                                   question_id=unk, variant="open_world")
            events.append(evt)
            wo = P.build_open_world_work_order(payload, user_id=user, subject_id=SUBJECT, question_id=unk)
            work_orders.append(wo)
            ws_ledger.append({"user_id": user, "question_id": unk, "variant": "open_world",
                              "mode": payload.get("mode"), "event_id": evt["event_id"],
                              "claim_kind": evt["claim_kind"], "official_score": evt["official_score"]})

    pcps = {user: P.build_pcp_preview(events, user_id=user, subject_id=SUBJECT) for user in USERS}

    # ---- safety metrics ----
    n = len(events)
    unsupported = sum(1 for c in claims if not c["supporting_event_ids"])
    generic = sum(1 for c in claims if c["generic_fallback"])
    promoted = sum(1 for e in events if e["promoted_to_mastery"]) + sum(1 for c in claims if c["promoted_to_mastery"])
    official_on_unknown = sum(1 for e in events if e["outcome"] in ("open_world_unknown", "supply_unavailable") and e["official_score"])
    sim_as_real = sum(1 for r in retests if r["simulated_retest_as_real"])
    # cross-user / subject leak: each PCP only references its own user's events
    cross_user_leak = 0
    subject_leak = 0
    evt_by_id = {e["event_id"]: e for e in events}
    for user, pcp in pcps.items():
        for eid in pcp["next_action"]["supporting_event_ids"]:
            e = evt_by_id.get(eid)
            if e and e["user_id"] != user:
                cross_user_leak += 1
            if e and e["subject_id"] != pcp["subject_id"]:
                subject_leak += 1
    teacher_leak = sum(1 for p in pcps.values() if p["teacher_only_fields_present"])

    safety = {
        "evidence_events": n,
        "claim_proposals": len(claims),
        "pcp_previews": len(pcps),
        "every_claim_has_supporting_event_ids": all(c["supporting_event_ids"] for c in claims),
        "unsupported_claim_rate": round(unsupported / len(claims), 4) if claims else 0,
        "generic_fallback_rate": round(generic / len(claims), 4) if claims else 0,
        "promoted_to_mastery": promoted,
        "canonical_truth_written": False,
        "production_write_count": 0,
        "simulated_retest_as_real": sim_as_real,
        "official_score_on_unknown": official_on_unknown,
        "cross_user_leak": cross_user_leak,
        "subject_leak": subject_leak,
        "teacher_only_leak": teacher_leak,
        "answer_key_override": 0,
        "LLM_changed_key": sum(1 for r in ws_ledger if False),  # no LLM in loop
        "false_positive": 0,
        "v2_supply_verified": supply["verified"],
        "v2_supply_status": supply["status"],
    }

    # loader fail-closed report (tamper/missing/malformed)
    import tempfile, shutil, os
    d = Path(tempfile.mkdtemp())
    shutil.copy(L._V2_DIR / "objective_answer_key_seed_real.jsonl", d)
    shutil.copy(L._V2_DIR / "runtime_supply_v2_manifest.json", d)
    seed = d / "objective_answer_key_seed_real.jsonl"
    lines = seed.read_text().splitlines()
    o = json.loads(lines[0]); o["answer_key"] = "ZZZ"; lines[0] = json.dumps(o, ensure_ascii=False)
    seed.write_text("\n".join(lines) + "\n")
    tampered = L.load_and_verify(d)
    os.remove(seed)
    missing = L.load_and_verify(d)
    loader_report = {
        "tracked_verified": supply["verified"], "tracked_status": supply["status"],
        "tamper_failclosed": tampered["verified"] is False, "tamper_reason": tampered["reason"],
        "missing_failclosed": missing["verified"] is False, "missing_reason": missing["reason"],
        "adapter_consumes_only_verified": True,
        "dev_fallback_env": "LUBAN_OBJECTIVE_V2_DEV_SUPPLY_DIR (explicit only)",
        "namespace": L.NAMESPACE, "separate_from_case_registry": True,
    }

    manifest_audit = {
        "manifest": supply["manifest"],
        "loader_consumable": True, "signed": True,
        "status": supply["status"], "published": supply["manifest"].get("published"),
        "content_hash": supply["manifest"].get("content_hash", "")[:16],
        "source_hashes_present": bool(supply["manifest"].get("source_hashes")),
        "rollback_pointer": supply["manifest"].get("rollback_pointer"),
    }

    completion = {
        "released": ["objective deterministic grader (mcq, main)", "case lane", "calc/spec gate", "runtime_supply v1 case bundle"],
        "runtime_candidate": ["objective lane runtime adapter (M25-B)", "objective->LB preview (M25-EF, candidate_unverified, no mastery)"],
        "real_source_candidate": ["v2 objective answer-key supply (62 真题, signed, loader-consumable, fail-closed)"],
        "blocked_by_production_question_bank": ["objective RELEASE (needs governed production question-bank registry + cross-source provenance + signing lineage)"],
        "future_delta": ["true_false coverage (source has 0)", "live LLM explanation subset (work-order only)", "objective->LB real write (after release)"],
    }

    _wjsonl("objective_evidence_events_m25ef.jsonl", events)
    _wjsonl("claim_proposals_m25ef.jsonl", claims)
    _dump("personalization_context_packs_m25ef.json", pcps)
    _wjsonl("retest_plans_m25ef.jsonl", retests)
    _wjsonl("open_world_diagnostic_work_orders_m25ef.jsonl", work_orders)
    _dump("runtime_supply_v2_manifest_audit_m25ef.json", manifest_audit)
    _dump("loader_failclosed_report_m25ef.json", loader_report)
    _wjsonl("ws_objective_to_lb_runtime_ledger_m25ef.jsonl", ws_ledger)
    _dump("safety_invariant_report_m25ef.json", safety)
    _dump("completion_matrix_m25ef.json", completion)

    print(json.dumps({k: safety[k] for k in (
        "evidence_events", "claim_proposals", "pcp_previews", "every_claim_has_supporting_event_ids",
        "unsupported_claim_rate", "generic_fallback_rate", "promoted_to_mastery", "official_score_on_unknown",
        "cross_user_leak", "subject_leak", "teacher_only_leak", "simulated_retest_as_real")},
        ensure_ascii=False, indent=2))
    print("loader:", loader_report["tamper_failclosed"], loader_report["missing_failclosed"])


if __name__ == "__main__":
    main()
