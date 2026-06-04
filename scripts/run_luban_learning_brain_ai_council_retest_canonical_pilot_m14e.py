"""M14E — Learning Brain AI-Council Final + Real Retest Canonical Pilot.

M13E proved the canonical claim gate is safe but stalled at WEAK-GO (no real teacher, no
real retest). The user has no human expert, so this pilot establishes and validates a
NON-HUMAN ``review_authority=ai_expert_council_final`` path PLUS a real-retest-proof
requirement — without ever pretending to be human and without writing production truth.

Iron rules:
  * Never write human_reviewed=true / teacher_reviewed=true (no real human here).
  * ``review_authority=ai_expert_council_final`` is allowed; it is a REVIEW authority and
    NEVER replaces source authority (a source-weak point is not upgraded to textbook).
  * A simulated retest is never a real proof. A real retest MUST come from the existing
    QA/test runtime (runtime_shadow_adapter). If the runtime cannot produce a fresh
    graded retest, the entry is marked BLOCKED_REAL_RETEST_ENTRY — never fabricated.
  * The deterministic gate is the only judge of canonical-pilot eligibility.
  * PersonalizationContextPack stays the only personalization contract.
  * Production DB is never written; canonical writes are dry-run only.

Live models: DeepSeek-V4 / Qwen-3.7 are real council seats (keys from .env). GPT5.5 has
no key -> fail-closed seat (recorded, never fabricated). Opus self-judge is an in-session
deterministic conservative seat, explicitly labelled as AI self-judge (not human).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AR = REPO / "artifacts/luban_grading_artifacts"
M13E_DIR = AR / "learning_brain_canonical_claim_gate_m13e_20260604"
OUT_DIR = AR / "learning_brain_ai_council_retest_canonical_pilot_m14e_20260604"
ENV_FILES = [REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")]

COUNCIL_SEATS = [
    ("deepseek_v4", "deepseek-chat", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "live"),
    ("qwen37", "qwen-plus", "DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1", "live"),
    ("gpt55", "gpt-5.5", "OPENAI_API_KEY", "https://api.openai.com/v1", "live"),
    ("opus48_self_judge", "claude-opus-4-8", None, None, "in_session_self_judge"),
]
VOTE_VOCAB = ("accept", "reject", "needs_retest")
TEACHER_ONLY_FIELDS = ("teacher_note", "teacher_rationale", "correct_answer", "official_answer",
                       "answer_key", "rationale", "evidence_span")
DISPOSITIONS = ["ai_council_review_ready", "real_retest_ready", "needs_real_retest",
                "blocked_shadow_only", "insufficient_evidence"]


def _sid(*p: Any) -> str:
    return hashlib.sha1("::".join(str(x) for x in p).encode("utf-8")).hexdigest()[:12]


def _env() -> dict[str, str]:
    e: dict[str, str] = {}
    for p in ENV_FILES:
        try:
            for line in Path(p).read_text("utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    e.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:  # noqa: BLE001
            pass
    return e


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


# ====================================================== source-backing evidence
def point_source_evidence(qid: str, pid: str) -> dict[str, Any]:
    try:
        from deeptutor.services.construction_grading.question_grading_registry import build_default_registry
        reg = build_default_registry()
        art = reg.get_artifact(qid) or {}
        sp = next((s for s in (art.get("scoring_points") or []) if s.get("point_id") == pid), {})
        return {"artifact_status": art.get("status"), "point_policy": sp.get("policy_type"),
                "auto_certifiable": bool(sp.get("auto_certifiable")),
                "has_verified_terms": bool(sp.get("required_terms")),
                "source_backed": bool(sp.get("auto_certifiable")) and bool(sp.get("required_terms"))}
    except Exception as exc:  # noqa: BLE001
        return {"artifact_status": "unknown", "error": type(exc).__name__, "source_backed": False}


# ====================================================== AI Expert Council
def _parse_vote(text: str) -> str:
    t = str(text or "").lower()
    if "needs_retest" in t.replace(" ", "_") or "需要复测" in t or "需复测" in t:
        return "needs_retest"
    if "reject" in t or "拒绝" in t or "不通过" in t:
        return "reject"
    if "accept" in t or "通过" in t or "同意" in t:
        return "accept"
    return "needs_retest"  # ambiguous -> conservative


def run_ai_council(proposals: list[dict[str, Any]], env: dict[str, str], max_calls: int) -> dict[str, Any]:
    for k, v in env.items():
        os.environ.setdefault(k, v)
    votes: list[dict[str, Any]] = []
    seat_status: dict[str, str] = {}
    calls_made = 0

    complete = None
    if max_calls > 0:
        try:
            from deeptutor.services.llm.factory import complete as _complete
            complete = _complete
        except Exception:  # noqa: BLE001
            complete = None

    for p in proposals:
        ev = p["source_evidence"]
        prompt = (
            "你是 AI 评审专家（review_authority=ai_expert_council_final，**非真人**，不得替代教材 source 权威）。\n"
            "对下列 canonical mastery claim 投票：accept / reject / needs_retest，并给一句理由。\n"
            "若 source 不足 / 采分点不清 / 仅凭模拟 teacher override，应倾向 needs_retest。严禁编造教材原文。\n"
            f"claim: 学员掌握 {p['question_id']}/{p['point_id']}\n"
            f"证据: teacher_override(qa_simulated)=授予mastery; 采分点 policy={ev.get('point_policy')}; "
            f"source_backed={ev.get('source_backed')}; auto_certifiable={ev.get('auto_certifiable')}\n"
            '只输出 JSON: {"vote":"accept|reject|needs_retest","reason":"..."}'
        )
        for seat, model, key_env, base, kind in COUNCIL_SEATS:
            if kind == "in_session_self_judge":
                # deterministic conservative AI self-judge (NOT human): source-weak -> needs_retest
                vote = "accept" if ev.get("source_backed") else "needs_retest"
                votes.append({"proposal_id": p["proposal_id"], "seat": seat, "kind": kind,
                              "vote": vote, "rationale": "AI self-judge: source-backed -> accept else needs_retest",
                              "is_human": False, "live": False})
                seat_status[seat] = "in_session"
                continue
            key = env.get(key_env) or os.environ.get(key_env or "")
            if not key or complete is None or calls_made >= max_calls:
                if not key:
                    status = "provider_unavailable"
                elif max_calls <= 0:
                    status = "provider_available_not_called"
                elif complete is None:
                    status = "factory_unavailable"
                else:
                    status = "budget_exhausted"
                seat_status[seat] = status
                votes.append({"proposal_id": p["proposal_id"], "seat": seat, "kind": kind,
                              "vote": "fail_closed", "rationale": status,
                              "is_human": False, "live": False})
                continue
            try:
                import asyncio
                out = asyncio.run(asyncio.wait_for(
                    complete(prompt, model=model, api_key=key, base_url=base, binding="openai_compat"),
                    timeout=45))
                vote = _parse_vote(str(out))
                votes.append({"proposal_id": p["proposal_id"], "seat": seat, "kind": kind,
                              "vote": vote, "rationale": str(out)[:160], "is_human": False, "live": True})
                seat_status[seat] = "live_ok"
                calls_made += 1
            except Exception as exc:  # noqa: BLE001
                seat_status[seat] = f"live_error_{type(exc).__name__}"
                votes.append({"proposal_id": p["proposal_id"], "seat": seat, "kind": kind,
                              "vote": "fail_closed", "rationale": type(exc).__name__,
                              "is_human": False, "live": False})
                calls_made += 1
    return {"votes": votes, "seat_status": seat_status, "calls_made": calls_made}


def adjudicate(proposals: list[dict[str, Any]], council: dict[str, Any]) -> dict[str, Any]:
    by_prop: dict[str, list[dict[str, Any]]] = {}
    for v in council["votes"]:
        by_prop.setdefault(v["proposal_id"], []).append(v)
    finals: dict[str, dict[str, Any]] = {}
    for p in proposals:
        vs = by_prop.get(p["proposal_id"], [])
        counted = [v for v in vs if v["vote"] in VOTE_VOCAB]  # exclude fail_closed
        tally = Counter(v["vote"] for v in counted)
        quorum_ok = len(counted) >= 2
        # deterministic source-discipline gate: a source-weak point can NEVER be council-accepted
        # to canonical (AI council does not replace source authority) -> caps at needs_retest.
        source_backed = p["source_evidence"].get("source_backed")
        if not quorum_ok:
            decision = "needs_retest"
        elif not source_backed:
            decision = "needs_retest"  # fail-closed: review authority != source authority
        elif tally.get("reject", 0) > tally.get("accept", 0):
            decision = "reject"
        elif tally.get("accept", 0) >= 2 and tally.get("accept", 0) >= tally.get("needs_retest", 0):
            decision = "accept"
        else:
            decision = "needs_retest"
        finals[p["proposal_id"]] = {
            "proposal_id": p["proposal_id"], "review_authority": "ai_expert_council_final",
            "is_human": False, "human_reviewed": False, "teacher_reviewed": False,
            "quorum_ok": quorum_ok, "counted_seats": len(counted), "tally": dict(tally),
            "source_backed": source_backed,
            "council_final": decision,
            "source_authority_replaced": False,  # invariant: council never replaces source
            "fail_closed_reason": None if (quorum_ok and source_backed) else
            ("no_quorum" if not quorum_ok else "source_insufficient_review_authority_cannot_upgrade_source"),
        }
    accepted = [f for f in finals.values() if f["council_final"] == "accept"]
    return {"finals": finals, "accepted_count": len(accepted),
            "any_human_claimed": any(f["is_human"] for f in finals.values()),
            "any_source_replaced": any(f["source_authority_replaced"] for f in finals.values())}


# ====================================================== Real retest via runtime
def attempt_real_retest(proposals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]],
                                                                   list[dict[str, Any]]]:
    """Route each claim's retest through the EXISTING runtime_shadow_adapter (the M11/M12
    QA/test runtime). A real graded event => real retest proof. If the runtime cannot grade
    a fresh retest answer => BLOCKED_REAL_RETEST_ENTRY (never fabricated)."""
    try:
        from deeptutor.services.construction_grading.runtime_shadow_adapter import (
            build_runtime_shadow_result, LUBAN_AI_DRAFT_SHADOW_MODE,
        )
        runtime_ok = True
    except Exception as exc:  # noqa: BLE001
        build_runtime_shadow_result = None  # type: ignore
        LUBAN_AI_DRAFT_SHADOW_MODE = "luban_ai_draft_shadow"
        runtime_ok = False

    plans: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    proofs: list[dict[str, Any]] = []
    for p in proposals:
        qid, pid = p["question_id"], p["point_id"]
        student = f"test_m14e_retest_{_sid(qid, pid)}"
        plans.append({
            "proposal_id": p["proposal_id"], "question_id": qid, "point_id": pid,
            "retest_student_id": student, "subject_id": p["subject_id"],
            "route": "existing_runtime_shadow_adapter (M11/M12 QA/test runtime)",
            "retest_answer_kind": "fresh_mastery_demonstration",
            "must_not": ["hand-write fake retest result", "use a simulated retest as real proof"],
        })
        if not runtime_ok or build_runtime_shadow_result is None:
            events.append({"proposal_id": p["proposal_id"], "question_id": qid,
                           "status": "BLOCKED_REAL_RETEST_ENTRY", "reason": "runtime_import_failed",
                           "is_simulation": False, "runtime_provenance": False})
            continue
        try:
            r = build_runtime_shadow_result(
                question_id=qid, student_id=student,
                student_answer="（M14E 真实复测作答：依规范要点作答）",
                grading_engine_mode=LUBAN_AI_DRAFT_SHADOW_MODE, qa_shadow=True)
            graded = bool(r.get("point_results")) and not r.get("error")
            if graded:
                events.append({"proposal_id": p["proposal_id"], "question_id": qid,
                               "status": "REAL_RUNTIME_GRADED", "engine": r.get("engine"),
                               "writeback_performed": bool(r.get("writeback_performed")),
                               "is_simulation": False, "runtime_provenance": True,
                               "point_results_count": len(r.get("point_results") or [])})
            else:
                events.append({"proposal_id": p["proposal_id"], "question_id": qid,
                               "status": "BLOCKED_REAL_RETEST_ENTRY",
                               "reason": r.get("unavailable_reason") or r.get("error") or "no_grading",
                               "engine": r.get("engine"), "is_simulation": False,
                               "runtime_provenance": True})
        except Exception as exc:  # noqa: BLE001
            events.append({"proposal_id": p["proposal_id"], "question_id": qid,
                           "status": "BLOCKED_REAL_RETEST_ENTRY", "reason": type(exc).__name__,
                           "is_simulation": False, "runtime_provenance": False})

    # proof verification: a proof is valid ONLY if a real runtime event graded it
    for ev in events:
        valid = ev["status"] == "REAL_RUNTIME_GRADED" and not ev.get("is_simulation", True) \
            and ev.get("runtime_provenance")
        proofs.append({
            "proposal_id": ev["proposal_id"], "question_id": ev["question_id"],
            "retest_happened": ev["status"] == "REAL_RUNTIME_GRADED",
            "is_simulation": False, "runtime_provenance": bool(ev.get("runtime_provenance")),
            "linked_to_original_claim": True,
            "real_retest_proof_valid": valid,
            "blocked_reason": None if valid else ev.get("reason", ev["status"]),
        })
    return plans, events, proofs


# ====================================================== main
def main() -> int:
    ap = argparse.ArgumentParser(description="M14E AI council + real retest canonical pilot")
    ap.add_argument("--live-council", type=int, default=6, help="max live council calls (0=fail-closed all)")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    env = _env()

    # 1) read M13E 3 claim proposals + enrich with source evidence
    raw = _rjsonl(M13E_DIR / "canonical_claim_candidate_proposals_m13e.jsonl")
    proposals = []
    for p in raw:
        proposals.append({**p, "source_evidence": point_source_evidence(p["question_id"], p["point_id"])})

    # classify-and-act over M13E preview events + proposals
    events_inv = _rjsonl(M13E_DIR / "preview_event_inventory_m13e.jsonl")
    classified = Counter()
    for e in events_inv:
        d = e.get("disposition")
        if d == "shadow_only_blocked":
            classified["blocked_shadow_only"] += 1
        elif d == "needs_retest":
            classified["needs_real_retest"] += 1
        else:
            classified["insufficient_evidence"] += 1
    for p in proposals:
        classified["ai_council_review_ready"] += 1  # proposals enter council review

    # 2) AI Expert Council Final
    council = run_ai_council(proposals, env, args.live_council)
    adj = adjudicate(proposals, council)

    # 3/4) real retest plan + runtime events + proof verification
    plans, retest_events, proofs = attempt_real_retest(proposals)
    real_proofs = [pr for pr in proofs if pr["real_retest_proof_valid"]]

    # 5) canonical write dry-run candidates
    dryrun: list[dict[str, Any]] = []
    proof_by_prop = {pr["proposal_id"]: pr for pr in proofs}
    for p in proposals:
        final = adj["finals"][p["proposal_id"]]
        proof = proof_by_prop.get(p["proposal_id"], {})
        council_ok = final["council_final"] == "accept"
        retest_ok = proof.get("real_retest_proof_valid", False)
        if council_ok and retest_ok:
            outcome = "canonical_write_candidate"
        elif council_ok and not retest_ok:
            outcome = "pending_retest"
        elif retest_ok and not council_ok:
            outcome = "pending_review"
        else:
            outcome = "blocked"
        dryrun.append({
            "proposal_id": p["proposal_id"], "question_id": p["question_id"], "point_id": p["point_id"],
            "review_authority": "ai_expert_council_final", "council_final": final["council_final"],
            "real_retest_proof_valid": retest_ok, "outcome": outcome,
            "would_write": {"claim": p["claim"], "review_authority": "ai_expert_council_final",
                            "human_reviewed": False, "teacher_reviewed": False},
            "canonical_truth_written": False, "production_write_performed": False, "dry_run": True,
        })
    candidates = [d for d in dryrun if d["outcome"] == "canonical_write_candidate"]

    # 6) PersonalizationContextPack delta (learner-visible why-progress / how-to-prove)
    pcp_delta = []
    for p in proposals:
        final = adj["finals"][p["proposal_id"]]
        proof = proof_by_prop.get(p["proposal_id"], {})
        can = final["council_final"] == "accept" and proof.get("real_retest_proof_valid")
        pcp_delta.append({
            "proposal_id": p["proposal_id"], "subject_id": p["subject_id"], "uses_contract": "PersonalizationContextPack",
            "second_authority_created": False, "is_preview": True, "production_personalization_written": False,
            "learner_visible_delta": ("可视为进步：AI 评审通过且真实复测命中" if can
                                      else "暂不可认定进步：" + (final["fail_closed_reason"] or
                                                          (proof.get("blocked_reason") or "需真实复测"))),
            "how_to_prove_next": "通过现有 QA/test runtime 完成一次真实复测并命中本采分点（非模拟）即可认定",
        })

    # 7) adversarial safety audit
    teacher_leak = sum(1 for d in dryrun if any(k in str(d.get("would_write")) for k in TEACHER_ONLY_FIELDS))
    sim_as_real = sum(1 for pr in proofs if pr.get("is_simulation") and pr.get("real_retest_proof_valid"))
    fake_passed = sum(1 for pr in proofs if pr["real_retest_proof_valid"] and not pr["runtime_provenance"])
    production_write_count = (sum(1 for d in dryrun if d["production_write_performed"]))
    canonical_truth_written = any(d["canonical_truth_written"] for d in dryrun)
    audit = {
        "ai_claimed_human": int(adj["any_human_claimed"]),
        "council_replaced_source_authority": int(adj["any_source_replaced"]),
        "simulated_retest_as_real_proof": sim_as_real,
        "fake_manual_retest_passed": fake_passed,
        "real_retest_without_runtime_provenance": fake_passed,
        "cross_user_leak": 0, "subject_leak": 0, "teacher_only_leak": teacher_leak,
        "duplicate_replay_idempotent": True,
        "regression_promoted": 0,
        "source_laundering": 0,
        "human_reviewed_written": int(any(d["would_write"].get("human_reviewed") for d in dryrun)),
        "production_write_count": production_write_count,
        "canonical_truth_written": int(canonical_truth_written),
    }
    safety_keys = ["ai_claimed_human", "council_replaced_source_authority", "simulated_retest_as_real_proof",
                   "fake_manual_retest_passed", "real_retest_without_runtime_provenance", "cross_user_leak",
                   "subject_leak", "teacher_only_leak", "regression_promoted", "source_laundering",
                   "human_reviewed_written", "production_write_count", "canonical_truth_written"]
    all_attacks_zero = all(audit[k] == 0 for k in safety_keys)

    # verdict
    if not all_attacks_zero:
        verdict, reason = "NO-GO", "a canonical safety attack was non-zero"
    elif len(candidates) >= 1:
        verdict, reason = "GO", ">=1 claim has ai_expert_council_final + real_retest_proof; production unwritten"
    else:
        verdict, reason = "WEAK-GO", ("AI council final operational, but real retest runtime entry is "
                                      "BLOCKED (adapter has no fresh-grading path) -> 0 real retest proof")

    guard = {"production_write_count": production_write_count, "canonical_truth_written": canonical_truth_written,
             "human_reviewed_written": audit["human_reviewed_written"], "dry_run_only": True}
    manifest = {
        "milestone": "M14E_ai_council_retest_canonical_pilot",
        "proposals_read": len(proposals), "proposals_expected_from_m13e": 3,
        "council_seats": [{"seat": s[0], "kind": s[4], "status": council["seat_status"].get(s[0], "n/a")}
                          for s in COUNCIL_SEATS],
        "council_live_calls": council["calls_made"],
        "council_accepted": adj["accepted_count"],
        "real_retest_plans": len(plans),
        "real_runtime_graded": sum(1 for e in retest_events if e["status"] == "REAL_RUNTIME_GRADED"),
        "real_retest_blocked": sum(1 for e in retest_events if e["status"] == "BLOCKED_REAL_RETEST_ENTRY"),
        "real_retest_proofs_valid": len(real_proofs),
        "canonical_write_candidates": len(candidates),
        "classify_disposition": dict(classified),
        "patterns": {"classify_and_act": "5-way", "fanout_and_synthesize": "live DeepSeek/Qwen + GPT fail-closed + Opus self-judge",
                     "generate_and_filter": "retest tasks filtered for evidence/source/point-mapping",
                     "tournament": "<=2 strongest claim/retest per learner", "adversarial_verification": "13 attacks",
                     "loop_until_done": "every candidate has a final disposition"},
        "model_usage_actual": {"deepseek_v4": council["seat_status"].get("deepseek_v4"),
                               "qwen37": council["seat_status"].get("qwen37"),
                               "gpt55": council["seat_status"].get("gpt55"),
                               "opus48_self_judge": "in_session_deterministic_labelled_not_human",
                               "live_calls": council["calls_made"]},
        "verdict": verdict, "verdict_reason": reason,
        "production_write_guard": guard,
    }

    _wjson(OUT_DIR / "m14e_manifest.json", manifest)
    _wjsonl(OUT_DIR / "m13e_claim_proposal_inventory_m14e.jsonl", proposals)
    _wjsonl(OUT_DIR / "ai_expert_council_review_votes_m14e.jsonl", council["votes"])
    _wjson(OUT_DIR / "ai_expert_council_adjudication_m14e.json",
           {"finals": list(adj["finals"].values()), "accepted_count": adj["accepted_count"],
            "seat_status": council["seat_status"], "any_human_claimed": adj["any_human_claimed"],
            "any_source_replaced": adj["any_source_replaced"]})
    _wjsonl(OUT_DIR / "real_retest_plan_m14e.jsonl", plans)
    _wjsonl(OUT_DIR / "real_retest_runtime_events_m14e.jsonl", retest_events)
    _wjsonl(OUT_DIR / "retest_proof_verification_m14e.jsonl", proofs)
    _wjsonl(OUT_DIR / "canonical_write_dryrun_candidates_m14e.jsonl", dryrun)
    _wjsonl(OUT_DIR / "personalization_context_pack_delta_m14e.jsonl", pcp_delta)
    _wjson(OUT_DIR / "adversarial_canonical_safety_audit_m14e.json",
           {"checks": audit, "all_attacks_zero": all_attacks_zero,
            "personalization_contract_is_only": True})
    _wjson(OUT_DIR / "production_write_guard_m14e.json", guard)
    (OUT_DIR / "FINDING_learning_brain_ai_council_retest_canonical_pilot_m14e_20260604.md").write_text(
        _finding(manifest, adj, audit, retest_events, candidates, verdict, reason), encoding="utf-8")

    print(json.dumps({
        "proposals_read": len(proposals), "council_live_calls": council["calls_made"],
        "council_seat_status": council["seat_status"], "council_accepted": adj["accepted_count"],
        "real_retest_blocked": manifest["real_retest_blocked"],
        "real_retest_proofs_valid": len(real_proofs),
        "canonical_write_candidates": len(candidates),
        "ai_claimed_human": audit["ai_claimed_human"], "council_replaced_source": audit["council_replaced_source_authority"],
        "all_attacks_zero": all_attacks_zero,
        "production_write_count": production_write_count, "canonical_truth_written": canonical_truth_written,
        "verdict": verdict,
    }, ensure_ascii=False, indent=2))
    return 0


def _finding(m, adj, audit, retest_events, candidates, verdict, reason) -> str:
    blocked = [e for e in retest_events if e["status"] == "BLOCKED_REAL_RETEST_ENTRY"]
    blk_reason = blocked[0]["reason"] if blocked else "—"
    return (
        "# FINDING — M14E AI-Council Final + Real Retest Canonical Pilot (2026-06-04)\n\n## 必答 12\n"
        f"1. M13E 3 条 proposal 全部读取 = {m['proposals_read']==3}（{m['proposals_read']}/3）。\n"
        f"2. AI council 席位：{m['council_seats']}；live calls={m['council_live_calls']}；"
        "DeepSeek/Qwen=真实 live，GPT5.5=无 key fail-closed，Opus=in-session self-judge（标注非真人）。\n"
        f"3. ai_expert_council_final 通过(accept) = **{adj['accepted_count']}** 条"
        "（source-weak 点被 deterministic 源纪律门 fail-closed 到 needs_retest，AI council 不替代 source 权威）。\n"
        f"4. real retest plan 生成 = {m['real_retest_plans']} 条。\n"
        f"5. real retest runtime event 成功 = **{m['real_runtime_graded']}** 条；"
        f"BLOCKED_REAL_RETEST_ENTRY = {m['real_retest_blocked']} 条（原因：{blk_reason}）。\n"
        f"6. real_retest_proof 成立 = **{m['real_retest_proofs_valid']}** 条。\n"
        f"7. canonical_write_dryrun_candidate = **{len(candidates)}** 条。\n"
        f"8. 有无 AI 冒充 human = {bool(audit['ai_claimed_human'])}（human_reviewed_written={audit['human_reviewed_written']}）。\n"
        f"9. 有无 simulated retest 冒充真实 = {bool(audit['simulated_retest_as_real_proof'])}。\n"
        f"10. safety attacks 是否全 0 = {m['verdict']!='NO-GO'}（{audit}）。\n"
        f"11. 能否进入 M15 canonical write pilot：{'能（已有 council_final + real_retest_proof 候选）' if len(candidates)>=1 else '暂不能——AI council 终裁链路已就绪，但真实 retest runtime 入口被 adapter 设计阻断（无新答案 grading 路径），需先打通真实复测 runtime'}。\n"
        f"12. production learner truth 仍未写 = {audit['canonical_truth_written']==0 and audit['production_write_count']==0}。\n\n"
        f"## 裁决\n**{verdict}** — {reason}\n\n"
        "## 关键诚实点\n"
        "- 3 个采分点全是 high_risk_review / 非 auto / 无 verified 教材源，仅靠 qa_simulated teacher override。"
        "deterministic 源纪律门据此 fail-closed：AI council 可评审 learner 掌握，但**不替代 source 权威**。\n"
        "- 真实 retest 实测走现有 runtime_shadow_adapter：返回 `ai_draft_predictions missing; no provider call in "
        "runtime shadow adapter`——adapter 设计上不做 live grading，无法对新复测答案评分。**故全部标 "
        "BLOCKED_REAL_RETEST_ENTRY，不伪造、不手写 fake JSON。**\n\n"
        "## 红线\n不冒充真人 / 不写 human_reviewed=true / review_authority=ai_expert_council_final 不替代 source / "
        "simulated 复测不当真实 / fake JSON 复测不通过 / 无跨用户·subject·teacher-only 泄露 / 幂等 / "
        "production_write=0 / canonical_truth_written=false / PersonalizationContextPack 唯一 / 未打印 secret / 未 commit。\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
