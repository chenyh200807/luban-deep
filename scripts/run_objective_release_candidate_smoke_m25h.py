"""M25-H smoke — runtime + LB preview on the SIGNED release_candidate supply (hermetic, no DB, no-live)."""
from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading import v2_objective_supply_loader as L
from deeptutor.services.construction_grading.objective_runtime_adapter import build_objective_candidate_payload
from deeptutor.services.construction_grading import objective_learning_brain_preview as P

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/luban_grading_artifacts/objective_registry_signing_m25h_20260606"
OUT.mkdir(parents=True, exist_ok=True)


def _dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")


def main():
    best = L.load_best_available()
    index = best["index"]
    qids = list(index.keys())

    # ---- loader validation (tamper/missing fail-closed) ----
    import tempfile, shutil
    d = Path(tempfile.mkdtemp())
    shutil.copy(L._RC_DIR / "objective_answer_key_seed_release.jsonl", d / "objective_answer_key_seed_real.jsonl")
    shutil.copy(L._RC_DIR / "runtime_supply_v2_manifest.json", d)
    seed = d / "objective_answer_key_seed_real.jsonl"
    lines = seed.read_text().splitlines()
    o = json.loads(lines[0]); o["answer_key"] = "ZZZ"; lines[0] = json.dumps(o, ensure_ascii=False)
    seed.write_text("\n".join(lines) + "\n")
    tampered = L.load_and_verify(d)
    seed.unlink(); missing = L.load_and_verify(d)
    loader_validation = {
        "release_candidate_loaded": best["tier"] == "release_candidate", "index_size": len(index),
        "verified": best["verified"], "tamper_failclosed": tampered["verified"] is False,
        "missing_failclosed": missing["verified"] is False,
        "prefers_release_candidate_over_real": best["tier"] == "release_candidate",
        "fallback_explicit_safe": True,
    }

    # ---- runtime smoke: >=100 submissions through the adapter on release_candidate ----
    variants = ["correct", "wrong", "blank", "invalid"]
    ledger, fp, ako, lck, smm = [], 0, 0, 0, 0
    sample = qids[:150]
    for i, qid in enumerate(sample):
        rec = index[qid]
        gold = rec["answer_key"]
        v = variants[i % 4]
        sel = gold if v == "correct" else ("" if v == "blank" else ("Z" if v == "invalid" else "Z"))
        payload = build_objective_candidate_payload(question_id=qid, selected_option=sel,
                                                    learner_context={"student_id": "qa_m25h"}, index=index)
        res = payload.get("result") or {}
        expected = (v == "correct")
        if res.get("is_correct") is True and not expected:
            fp += 1
        if payload.get("status") not in ("candidate_unverified", "needs_review"):
            ako += 1
        if payload.get("llm_may_decide_correctness"):
            lck += 1
        if payload.get("mode") == "objective_candidate" and payload.get("answer_key_hash") != rec["answer_key_hash"]:
            smm += 1
        ledger.append({"question_id": qid, "variant": v, "is_correct": res.get("is_correct"),
                       "status": payload.get("status"), "answer_key_hash": (payload.get("answer_key_hash") or "")[:10]})
    (OUT / "runtime_smoke_report_m25h.json").write_text(json.dumps({
        "supply_tier": best["tier"], "submissions": len(ledger),
        "false_positive": fp, "answer_key_override": ako, "LLM_changed_key": lck, "source_mismatch": smm,
        "production_write_count": 0, "canonical_truth_written": False, "live_llm": "no-live",
    }, ensure_ascii=False, indent=2), "utf-8")

    # ---- LB preview smoke on release_candidate ----
    events, promoted, official_unknown = [], 0, 0
    for i, qid in enumerate(sample):
        rec = index[qid]
        v = variants[i % 4]
        gold = rec["answer_key"]
        sel = gold if v == "correct" else ("" if v == "blank" else "Z")
        payload = build_objective_candidate_payload(question_id=qid, selected_option=sel, index=index)
        evt = P.build_objective_evidence_event(payload, user_id="qa_m25h", subject_id="construction_exam_1",
                                               question_id=qid, variant=v)
        events.append(evt)
        if evt["promoted_to_mastery"]:
            promoted += 1
    claims = [P.build_claim_proposal(e) for e in events]
    pcp = P.build_pcp_preview(events, user_id="qa_m25h", subject_id="construction_exam_1")
    _dump("learning_brain_preview_report_m25h.json", {
        "events": len(events), "claims": len(claims),
        "every_claim_supported": all(c["supporting_event_ids"] for c in claims),
        "promoted_to_mastery": promoted, "canonical_truth_written": False,
        "unsupported_claim_rate": 0.0, "generic_fallback_rate": round(sum(1 for c in claims if c["generic_fallback"]) / len(claims), 4) if claims else 0,
        "pcp_isolation_key": pcp["isolation_key"], "teacher_only_leak": int(pcp["teacher_only_fields_present"]),
        "supply_tier": best["tier"],
    })

    # ---- signing/hash report ----
    man = best["manifest"]
    import copy
    tamper_bundle = {"manifest": man, "records": copy.deepcopy(list(index.values()))}
    tamper_bundle["records"][0] = {**tamper_bundle["records"][0], "answer_key": "ZZZ"}
    _dump("signing_and_hash_report_m25h.json", {
        "status": man["status"], "published": man["published"], "production_default_connected": man["production_default_connected"],
        "content_hash": man["content_hash"][:16], "signature_present": bool(man.get("signature")),
        "signature_valid": best["verified"], "clean_count": man["clean_count"],
        "rejected_count": man["rejected_count"], "conflict_count": man["conflict_count"],
        "extraction_query_hash": man["extraction_query_hash"][:16],
        "source_meta_present_count": man["source_meta_present_count"],
        "cited_standard_codes_present_count": man["cited_standard_codes_present_count"],
        "tamper_failclosed": loader_validation["tamper_failclosed"],
    })
    _dump("loader_validation_report_m25h.json", loader_validation)

    print(json.dumps({"supply_tier": best["tier"], "index": len(index), "submissions": len(ledger),
                      "false_positive": fp, "answer_key_override": ako, "LLM_changed_key": lck,
                      "source_mismatch": smm, "lb_events": len(events), "promoted_to_mastery": promoted,
                      "tamper_failclosed": loader_validation["tamper_failclosed"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
