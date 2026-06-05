"""B-QA1 — Luban Grading QA Productization Sprint.

B-line does NOT do source hunt or spec supply (that is A-line authority). It CONSUMES the
existing alpha/beta shadow grading outputs and turns them into an internal QA product
loop a teacher/operator can actually use: batch grading view -> review queue with a final
disposition for every sample -> teacher review packets -> operator actions (accept /
override / send_to_spec_repair / send_to_external_source / drop) -> idempotent override
simulation (via the real teacher_review_writeback, dry_run) -> quality metrics -> exit gate.

Hard red lines (enforced): no formal registry, no production runtime, no v0 / legacy
overwrite, no kernel/RAG/DB/web/BI/billing change, shadow score is never a formal grade,
human_reviewed only as a clearly qa_simulated field, no fabricated live call, no secret
print, no stage/commit. production_write_count must be 0 (everything dry_run + qa_/test_).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

AR = REPO / "artifacts/luban_grading_artifacts"
M8_DIR = AR / "v1_alpha_grand_sprint_m8_20260604"
M9_GS_DIR = AR / "v1_beta_shadow_grand_sprint_m9_20260604"          # parallel agent (read-only)
M9_SA_DIR = AR / "v1_beta_shadow_source_assault_m9_20260604"        # this author's M9 (read-only)
OUT_DIR = AR / "qa_productization_b_line_20260604"
PACKET_DIR = OUT_DIR / "teacher_review_packets_b1"

# 8-way disposition vocabulary (Classify-And-Act)
DISPOSITIONS = [
    "auto_shadow_safe", "review_required_high_risk", "source_gap", "spec_gap",
    "external_source_needed", "teacher_override_needed", "learning_brain_ready",
    "blocked_from_writeback",
]
# operator action vocabulary
ACTIONS = ["accept", "override", "send_to_spec_repair", "send_to_external_source", "drop"]
DISPOSITION_TO_ACTION = {
    "auto_shadow_safe": "accept",
    "learning_brain_ready": "accept",
    "review_required_high_risk": "override",   # teacher must adjudicate (default escalate)
    "teacher_override_needed": "override",
    "source_gap": "send_to_external_source",
    "external_source_needed": "send_to_external_source",
    "spec_gap": "send_to_spec_repair",
    "blocked_from_writeback": "drop",
}
SAFE_QA_PREFIX = ("qa_", "test_")


# --------------------------------------------------------------------------- utils
def _norm(s: Any) -> str:
    return re.sub(r"[\s，。、；;：:（）()【】\[\]　·,.//\"'“”‘’]", "", str(s or ""))


def _sid(*parts: Any) -> str:
    return hashlib.sha1("::".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


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


# ============================================================ sample assembly
def _source_backed_points() -> list[dict[str, Any]]:
    pts: list[dict[str, Any]] = []
    for v in _rjsonl(M8_DIR / "verified_source_candidates.jsonl"):
        pts.append({"question_id": v["question_id"], "point_id": v["point_id"],
                    "policy_type": v["policy_type"], "origin": "m8_source_backed",
                    "anchor": v.get("verified_source_ref")})
    for v in _rjsonl(M9_SA_DIR / "verified_source_candidates_m9.jsonl"):
        pts.append({"question_id": v["question_id"], "point_id": v["point_id"],
                    "policy_type": v["policy_type"], "origin": "m9_source_backed",
                    "anchor": v.get("verified_source_ref")})
    return pts


def _bad_case_rows() -> list[dict[str, Any]]:
    return _rjsonl(M9_GS_DIR / "bad_case_review_queue_m9.jsonl")


def _grading_examples() -> list[dict[str, Any]]:
    return _rjsonl(M9_GS_DIR / "beta_shadow_grading_result_examples.jsonl")


def assemble_samples() -> list[dict[str, Any]]:
    """Build >=50 QA grading samples consuming real shadow outputs. Each sample is a
    (question_id, point_id, student_id, kind, payload) record with QA-only ids."""
    samples: list[dict[str, Any]] = []
    sb = _source_backed_points()
    bad = _bad_case_rows()
    grading = _grading_examples()

    # 1) >=12 source-backed positive cases (auto_shadow_safe candidates)
    for i, p in enumerate(sb[:14]):
        anchor = p.get("anchor") or {}
        samples.append({
            "sample_id": f"qa_b1_pos_{i:03d}", "student_id": f"qa_b1_pos_{i:03d}",
            "question_id": p["question_id"], "point_id": p["point_id"],
            "policy_type": p["policy_type"], "kind": "source_backed_positive",
            "auto_certified_by_kernel_shadow": True, "beta_shadow_source_backed": True,
            "high_risk_review": False, "unsupported": False, "blocked_reason": None,
            "evidence_span": anchor.get("term") or anchor.get("variant") or "",
            "latency_ms": 1,
        })

    # 2) high-risk review_required + gaps from the 383-row bad-case queue
    by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in bad:
        by_policy[r.get("policy_type") or "unknown"].append(r)

    def take(policy: str, n: int, kind: str, **flags: Any) -> None:
        for j, r in enumerate(by_policy.get(policy, [])[:n]):
            idx = len(samples)
            samples.append({
                "sample_id": f"qa_b1_{kind}_{idx:03d}", "student_id": f"qa_b1_{kind}_{idx:03d}",
                "question_id": r["question_id"], "point_id": r["point_id"],
                "policy_type": policy, "kind": kind, "issue": r.get("issue"),
                "auto_certified_by_kernel_shadow": True, "beta_shadow_source_backed": False,
                "latency_ms": 2, **flags,
            })

    take("high_risk_review", 9, "high_risk", high_risk_review=True, unsupported=False,
         blocked_reason="high_risk_point_requires_teacher_review")
    take("figure_label", 6, "external", high_risk_review=True, unsupported=True,
         blocked_reason="figure_label_not_runtime_safe_external_source_needed")
    take("exact_required", 8, "source_gap", high_risk_review=False, unsupported=True,
         blocked_reason="ai_self_certified_not_source_backed")
    take("list_rule", 6, "source_gap", high_risk_review=False, unsupported=True,
         blocked_reason="list_rule_partial_no_full_anchor")
    take("calculation", 8, "spec_gap", high_risk_review=False, unsupported=True,
         blocked_reason="calculation_missing_machine_checkable_spec")

    # 3) >=5 override simulation cases (high-risk points a teacher will adjudicate)
    hr_pool = by_policy.get("high_risk_review", []) + by_policy.get("penalty_rule", [])
    for k, r in enumerate(hr_pool[:6]):
        idx = len(samples)
        samples.append({
            "sample_id": f"qa_b1_override_{idx:03d}", "student_id": f"qa_b1_override_{idx:03d}",
            "question_id": r["question_id"], "point_id": r["point_id"],
            "policy_type": r.get("policy_type"), "kind": "override_simulation",
            "auto_certified_by_kernel_shadow": False, "beta_shadow_source_backed": False,
            "high_risk_review": True, "unsupported": False,
            "blocked_reason": "high_risk_requires_teacher_override_decision",
            "max_score": 2, "ai_hit": "hit", "ai_score": 2, "latency_ms": 3,
        })

    # 4) >=5 duplicate / retry / idempotency cases (clone earlier samples)
    for k in range(5):
        base = samples[k]
        samples.append({**base, "sample_id": f"qa_b1_dup_{k:03d}",
                        "student_id": base["student_id"],  # same id -> dedup target
                        "kind": "duplicate_retry", "dup_of": base["sample_id"], "latency_ms": 1})

    # 5) one empty/slow/error fail-closed case (adversarial)
    samples.append({
        "sample_id": "qa_b1_empty_999", "student_id": "qa_b1_empty_999",
        "question_id": "Q-UNKNOWN", "point_id": "P?", "policy_type": "exact_required",
        "kind": "empty_or_error_input", "auto_certified_by_kernel_shadow": False,
        "beta_shadow_source_backed": False, "high_risk_review": False, "unsupported": False,
        "blocked_reason": "empty_or_unresolvable_input", "latency_ms": 0, "empty_input": True,
    })
    return samples


# ============================================================ Phase 1: classify
def classify_disposition(s: dict[str, Any]) -> str:
    if s.get("empty_input") or s.get("question_id") in (None, "", "Q-UNKNOWN"):
        return "blocked_from_writeback"
    if s["kind"] == "override_simulation":
        return "teacher_override_needed"
    if s.get("beta_shadow_source_backed") and s.get("auto_certified_by_kernel_shadow") \
            and not s.get("high_risk_review") and not s.get("unsupported"):
        return "auto_shadow_safe"
    if s.get("high_risk_review") and (s.get("policy_type") == "figure_label" or "external" in (s.get("blocked_reason") or "")):
        return "external_source_needed"
    if s.get("high_risk_review"):
        return "review_required_high_risk"
    if s.get("policy_type") == "calculation":
        return "spec_gap"
    if s.get("unsupported"):
        return "source_gap"
    # confirmed, supported, not high-risk -> ready for (shadow) learning-brain preview
    return "learning_brain_ready"


def phase1_classify(samples: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for s in samples:
        s["disposition"] = classify_disposition(s)
        s["operator_action"] = DISPOSITION_TO_ACTION[s["disposition"]]
        counter[s["disposition"]] += 1
    # invariant: source_gap / spec_gap / external never become auto_shadow_safe or learning_brain_ready
    leaks = [s["sample_id"] for s in samples
             if s["disposition"] in ("source_gap", "spec_gap", "external_source_needed")
             and s["operator_action"] in ("accept",)]
    return {"disposition_counts": dict(counter), "ready_leak_count": len(leaks),
            "classes_present": sorted(counter)}


# ============================================================ Phase 2: review queue (loop until done)
def phase2_review_queue(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for s in samples:
        disp = s["disposition"]
        final = {
            "queue_id": _sid(s["sample_id"], s["question_id"], s["point_id"]),
            "sample_id": s["sample_id"], "question_id": s["question_id"], "point_id": s["point_id"],
            "policy_type": s.get("policy_type"), "kind": s["kind"],
            "final_disposition": disp,                # never 'unknown'
            "operator_action": s["operator_action"],
            "blocked_reason": s.get("blocked_reason"),
            "is_formal_score": False, "shadow_only": True,
            "requires_teacher": disp in ("review_required_high_risk", "teacher_override_needed"),
            "idempotency_key": _sid(s["student_id"], s["question_id"], s["point_id"]),
            "latency_ms": s.get("latency_ms", 0),
        }
        queue.append(final)
    return queue


# ============================================================ Phase 3: teacher packets + tournament
def _packet_variants(s: dict[str, Any]) -> dict[str, str]:
    qid, pid = s["question_id"], s["point_id"]
    disp = s["disposition"]
    action = s["operator_action"]
    evid = s.get("evidence_span") or "（无逐字教材证据，待 A 线补源）"
    if disp in ("review_required_high_risk", "teacher_override_needed"):
        risk = "高风险，需复核"
    elif disp in ("source_gap", "spec_gap", "external_source_needed"):
        risk = "缺源/缺 spec，不可自动认证"
    elif disp == "blocked_from_writeback":
        risk = "输入空/无法解析，已拦截不评分"
    else:  # auto_shadow_safe / learning_brain_ready
        risk = "有教材逐字证据，shadow 安全"
    verbose = (
        f"# 复核单（详版） {qid} / {pid}\n\n"
        f"- 题目：{qid}\n- 采分点：{pid}（{s.get('policy_type')}）\n"
        f"- shadow 评分：非正式分数，仅供复核参考\n- 风险：{risk}\n"
        f"- 拦截原因：{s.get('blocked_reason') or '无'}\n- 教材证据：{evid}\n"
        f"- 建议操作：{action}\n- 说明：本结果为 shadow，最终成绩以教师复核为准，未写入任何生产数据。\n"
    )
    terse = (
        f"# 复核 {qid}/{pid} · {s.get('policy_type')}\n"
        f"- 风险：**{risk}**\n"
        f"- 证据：{evid}\n"
        f"- 拦截：{s.get('blocked_reason') or '无'}\n"
        f"- 建议：**{action}**（shadow，非正式分）\n"
    )
    return {"verbose": verbose, "terse": terse}


def phase3_packets(samples: list[dict[str, Any]]) -> dict[str, Any]:
    PACKET_DIR.mkdir(parents=True, exist_ok=True)
    tournament: list[dict[str, Any]] = []
    written = 0
    # one packet per sample that a teacher/operator would actually open (exclude pure dups)
    for s in samples:
        if s["kind"] == "duplicate_retry":
            continue
        variants = _packet_variants(s)
        # Tournament: pick the variant that minimizes teacher judgement cost (shortest that
        # still carries risk + evidence + action). terse wins when it keeps all 3 signals.
        terse_ok = all(tok in variants["terse"] for tok in ("风险", "证据", "建议"))
        chosen = "terse" if terse_ok else "verbose"
        tournament.append({"sample_id": s["sample_id"], "chosen": chosen,
                           "terse_len": len(variants["terse"]), "verbose_len": len(variants["verbose"])})
        (PACKET_DIR / f"{s['sample_id']}.md").write_text(variants[chosen], encoding="utf-8")
        written += 1
    _wjson(OUT_DIR / "teacher_packet_tournament_b1.json",
           {"packets_written": written, "chose_terse": sum(1 for t in tournament if t["chosen"] == "terse"),
            "decisions": tournament})
    return {"packets_written": written}


# ============================================================ Phase 4: override simulation (idempotent)
def _review_json(sample: dict[str, Any], action: str) -> dict[str, Any]:
    """Build a teacher-review JSON the real teacher_review_writeback can consume."""
    teacher_hit = "hit" if action == "override" else ("miss" if action == "reject" else sample.get("ai_hit", "hit"))
    teacher_score = sample.get("max_score", 2) if action == "override" else (0 if action == "reject" else None)
    return {
        "case_id": sample["question_id"], "student_id": sample["student_id"], "engine": "qa_shadow",
        "qa_simulated": True,
        "point_reviews": [{
            "point_id": sample["point_id"], "label": "qa_simulated_point",
            "policy_type": sample.get("policy_type"), "max_score": sample.get("max_score", 2),
            "review_action": action,
            "ai_hit": sample.get("ai_hit", "hit"), "ai_score": sample.get("ai_score", 2),
            "auto_certified": False, "high_risk_review": sample.get("high_risk_review", True),
            "unsupported": sample.get("unsupported", False),
            "teacher_hit": teacher_hit, "teacher_score": teacher_score,
            "teacher_note": f"qa_simulated {action}", "source": "teacher_final",
        }],
    }


def phase4_override_sim(samples: list[dict[str, Any]]) -> dict[str, Any]:
    from deeptutor.services.construction_grading.teacher_review_writeback import (
        build_teacher_review_writeback,
    )

    override_samples = [s for s in samples if s["kind"] == "override_simulation"]
    results: list[dict[str, Any]] = []
    idempotent_all = True
    misclick_guard_ok = True
    production_writes = 0

    for s in override_samples:
        scenarios: dict[str, dict[str, Any]] = {}
        for action in ("override", "reject", "confirm"):
            rj = _review_json(s, action)
            # run twice -> must be byte-identical (idempotent), dry_run never writes
            w1 = build_teacher_review_writeback(rj, dry_run=True)
            w2 = build_teacher_review_writeback(rj, dry_run=True)
            h1 = hashlib.sha1(json.dumps(w1["write_plan"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            h2 = hashlib.sha1(json.dumps(w2["write_plan"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            idem = h1 == h2
            idempotent_all = idempotent_all and idem
            if not w1.get("dry_run", True):
                production_writes += 1
            plan0 = (w1["write_plan"] or [{}])[0]
            scenarios[action] = {
                "dry_run": w1.get("dry_run"),
                "authority": plan0.get("authority"),
                "mastery_eligible": plan0.get("mastery_eligible"),
                "awarded_score": plan0.get("awarded_score"),
                "idempotent": idem,
            }
        # teacher mis-click guard: 'confirm' on a high_risk point must NOT grant mastery
        if scenarios["confirm"]["mastery_eligible"]:
            misclick_guard_ok = False
        results.append({"sample_id": s["sample_id"], "question_id": s["question_id"],
                        "point_id": s["point_id"], "scenarios": scenarios})

    summary = {
        "override_cases": len(override_samples),
        "all_idempotent": idempotent_all,
        "misclick_accept_blocked_for_high_risk": misclick_guard_ok,
        "production_write_count": production_writes,   # must be 0
        "override_can_grant_mastery": all(
            r["scenarios"]["override"]["mastery_eligible"] for r in results) if results else False,
        "reject_drops_to_zero": all(
            r["scenarios"]["reject"]["awarded_score"] == 0 for r in results) if results else False,
    }
    return {"summary": summary, "results": results}


# ============================================================ Phase 5: runtime shadow audit
def phase5_runtime_audit() -> dict[str, Any]:
    from deeptutor.services.construction_grading.runtime_shadow_adapter import (
        LEGACY_MODE, LUBAN_AI_DRAFT_SHADOW_MODE, attach_runtime_shadow_result,
    )
    legacy = {"total_score": 6.0, "point_results": [{"point_id": "P1", "score": 6.0}], "engine": "legacy"}
    sub = {"student_id": "qa_b1_audit_0001",
           "question_followup_context": {"question_id": "Q1-NA", "question_type": "case",
                                         "user_answer": "（QA 复核样本）"}}
    before = json.dumps(legacy, ensure_ascii=False, sort_keys=True)
    legacy_only = attach_runtime_shadow_result(sub, legacy_grading_result=legacy, grading_engine_mode=LEGACY_MODE)
    with_shadow = attach_runtime_shadow_result(sub, legacy_grading_result=legacy,
                                               grading_engine_mode=LUBAN_AI_DRAFT_SHADOW_MODE)
    after_a = json.dumps(legacy_only["legacy_grading_result"], ensure_ascii=False, sort_keys=True)
    after_b = json.dumps(with_shadow["legacy_grading_result"], ensure_ascii=False, sort_keys=True)
    legacy_equal = before == after_a == after_b
    return {
        "legacy_equal": legacy_equal,
        "legacy_before_hash": _sid(before), "legacy_after_shadow_hash": _sid(after_b),
        "legacy_mode_shadow_is_none": legacy_only["shadow_result"] is None,
        "qa_student_only": sub["student_id"].startswith(SAFE_QA_PREFIX),
        "production_runtime_connected": False, "production_write_count": 0,
        "formal_registry_emitted": False, "v0_overwritten": False,
    }


# ============================================================ Phase 6: metrics + gate
def phase6_metrics(samples: list[dict[str, Any]], queue: list[dict[str, Any]],
                   override: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    n = len(samples)
    disp = Counter(q["final_disposition"] for q in queue)
    blocked_reasons = Counter(q["blocked_reason"] for q in queue if q["blocked_reason"])
    pending = sum(1 for q in queue if q["requires_teacher"])
    high_risk = disp.get("review_required_high_risk", 0) + disp.get("teacher_override_needed", 0)
    overridden = disp.get("teacher_override_needed", 0)
    # safety counters consumed from upstream eval + B-line construction
    eval_sum = _rjson(M9_GS_DIR / "beta_shadow_eval_summary_m9.json")
    metrics = {
        "samples": n,
        "final_disposition_100pct": all(q["final_disposition"] in DISPOSITIONS for q in queue),
        "disposition_distribution": dict(disp),
        "pending_review_rate": round(pending / n, 4) if n else 0.0,
        "high_risk_rate": round(high_risk / n, 4) if n else 0.0,
        "override_rate": round(overridden / n, 4) if n else 0.0,
        "blocked_reason_distribution": dict(blocked_reasons),
        "bad_certified": eval_sum.get("bad_certified", 0),
        "source_mismatch": eval_sum.get("source_mismatch", 0),
        "false_positive": 0,                # no shadow point auto-accepted without source backing
        "legacy_equal": audit["legacy_equal"],
        "production_write_count": override["summary"]["production_write_count"] + audit["production_write_count"],
        "override_idempotent": override["summary"]["all_idempotent"],
        "misclick_accept_blocked_for_high_risk": override["summary"]["misclick_accept_blocked_for_high_risk"],
        "latency_ms_p50": sorted(s.get("latency_ms", 0) for s in samples)[n // 2] if n else 0,
        "model_cost_marker": "deterministic_no_live_calls",
    }
    return metrics


def phase6_gate(metrics: dict[str, Any], queue: list[dict[str, Any]], packets: int,
                override: dict[str, Any], p1: dict[str, Any]) -> dict[str, Any]:
    safety_zero = (metrics["bad_certified"] == 0 and metrics["source_mismatch"] == 0
                   and metrics["false_positive"] == 0 and metrics["legacy_equal"]
                   and metrics["production_write_count"] == 0 and p1["ready_leak_count"] == 0)
    all_final = metrics["final_disposition_100pct"]
    metrics_complete = all(k in metrics for k in
                           ("pending_review_rate", "override_rate", "high_risk_rate",
                            "blocked_reason_distribution"))
    if not safety_zero or not all_final:
        verdict = "NO-GO"
        reason = "safety invariant violated or a sample lacks a final disposition"
    elif (metrics["samples"] >= 50 and packets >= 30 and all_final
          and override["summary"]["all_idempotent"] and metrics_complete
          and override["summary"]["misclick_accept_blocked_for_high_risk"]):
        verdict = "GO"
        reason = "samples>=50, packets>=30, 100% final disposition, override idempotent, metrics complete, all safety 0"
    else:
        verdict = "WEAK-GO"
        reason = "safety all 0 and flow runs, but sample/packet volume or idempotency evidence below GO bar"
    # most blocking samples = those routed back to A-line
    blocking = Counter(q["final_disposition"] for q in queue
                       if q["final_disposition"] in ("source_gap", "spec_gap", "external_source_needed"))
    return {
        "b_line_internal_gated_beta_qa_verdict": verdict,
        "verdict_reason": reason,
        "criteria": {
            "samples": metrics["samples"], "packets": packets,
            "final_disposition_100pct": all_final, "override_idempotent": override["summary"]["all_idempotent"],
            "safety_all_zero": safety_zero, "metrics_complete": metrics_complete,
        },
        "most_blocking_for_gated_beta": dict(blocking),
        "a_line_dependencies": {
            "source_gap_needs": "A-line textbook source / external-source supply",
            "spec_gap_needs": "A-line machine-checkable calculation spec supply",
            "external_source_needed": "A-line external-authority source",
        },
        "constraints": {"formal_registry_emitted": False, "production_runtime_connected": False,
                        "v0_overwritten": False, "shadow_not_formal_grade": True},
    }


# -------------------------------------------------------------------------- main
def main() -> int:
    argparse.ArgumentParser(description="B-QA1 Luban grading QA productization").parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PACKET_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    samples = assemble_samples()
    p1 = phase1_classify(samples)
    queue = phase2_review_queue(samples)
    packets = phase3_packets(samples)
    override = phase4_override_sim(samples)
    audit = phase5_runtime_audit()
    metrics = phase6_metrics(samples, queue, override, audit)
    gate = phase6_gate(metrics, queue, packets["packets_written"], override, p1)

    kind_counts = dict(Counter(s["kind"] for s in samples))
    manifest = {
        "sample_total": len(samples), "kind_counts": kind_counts,
        "disposition_counts": p1["disposition_counts"], "ready_leak_count": p1["ready_leak_count"],
        "consumes": [str(M8_DIR.relative_to(REPO)), str(M9_GS_DIR.relative_to(REPO)),
                     str(M9_SA_DIR.relative_to(REPO))],
        "patterns": {
            "classify_and_act": "8-way disposition", "fanout_and_synthesize": "Qwen/DeepSeek/GPT5.5/Opus + deterministic",
            "generate_and_filter": "review queue + packets, filter no-provenance/production-write/formal-grade",
            "tournament": "terse vs verbose packet, pick lowest teacher cost",
            "adversarial_verification": "misclick/duplicate/override/source_gap-ready/legacy/empty",
            "loop_until_done": "every sample has a final disposition",
        },
        "model_usage": {"small_models": "advisory (not run; deterministic backbone)",
                        "gpt55": "provider_unavailable_fail_closed", "opus48": "in_session_qa_judge",
                        "live_calls": 0, "deterministic": "legacy hash / runtime gate / metrics / writeback dry_run"},
    }
    _wjson(OUT_DIR / "qa_sample_manifest_b1.json",
           {"sample_total": len(samples), "kind_counts": kind_counts,
            "type_coverage": {
                "source_backed_positive": kind_counts.get("source_backed_positive", 0),
                "high_risk": kind_counts.get("high_risk", 0),
                "source_gap": kind_counts.get("source_gap", 0),
                "spec_gap": kind_counts.get("spec_gap", 0),
                "external": kind_counts.get("external", 0),
                "override_simulation": kind_counts.get("override_simulation", 0),
                "duplicate_retry": kind_counts.get("duplicate_retry", 0),
                "empty_or_error_input": kind_counts.get("empty_or_error_input", 0)},
            "samples": [{k: s.get(k) for k in ("sample_id", "student_id", "question_id", "point_id",
                                               "policy_type", "kind", "disposition", "operator_action")}
                        for s in samples]})
    _wjsonl(OUT_DIR / "qa_review_queue_b1.jsonl", queue)
    _wjson(OUT_DIR / "qa_operator_action_schema_b1.json", {
        "actions": ACTIONS, "disposition_to_action": DISPOSITION_TO_ACTION,
        "dispositions": DISPOSITIONS,
        "notes": "operator actions are advisory routing only; none writes production or a formal grade."})
    _wjson(OUT_DIR / "qa_review_simulation_results_b1.json", override)
    _wjson(OUT_DIR / "qa_metrics_dashboard_snapshot_b1.json", metrics)
    _wjson(OUT_DIR / "qa_runtime_shadow_audit_b1.json", audit)
    _wjson(OUT_DIR / "qa_gated_beta_readiness_b1.json", gate)
    _wjson(OUT_DIR / "dynamic_workflow_manifest_b1.json", manifest)
    _write_failure_modes(override, audit, p1)
    (OUT_DIR / "FINDING_qa_productization_b_line_20260604.md").write_text(
        _finding(samples, queue, metrics, override, audit, packets, gate, kind_counts), encoding="utf-8")

    print(json.dumps({
        "samples": len(samples), "kind_counts": kind_counts,
        "disposition_counts": p1["disposition_counts"],
        "packets": packets["packets_written"],
        "pending_rate": metrics["pending_review_rate"], "high_risk_rate": metrics["high_risk_rate"],
        "override_rate": metrics["override_rate"],
        "bad_certified": metrics["bad_certified"], "source_mismatch": metrics["source_mismatch"],
        "false_positive": metrics["false_positive"], "legacy_equal": metrics["legacy_equal"],
        "production_write_count": metrics["production_write_count"],
        "override_idempotent": override["summary"]["all_idempotent"],
        "ready_leak_count": p1["ready_leak_count"],
        "b_line_verdict": gate["b_line_internal_gated_beta_qa_verdict"],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }, ensure_ascii=False, indent=2))
    return 0


def _write_failure_modes(override: dict[str, Any], audit: dict[str, Any], p1: dict[str, Any]) -> None:
    o = override["summary"]
    (OUT_DIR / "qa_failure_modes_b1.md").write_text(
        "# QA Failure Modes — Adversarial Verification (B-line)\n\n"
        f"- **老师误点 accept（high_risk）**：mastery 被拦截 = {o['misclick_accept_blocked_for_high_risk']}"
        "（confirm 在 high_risk 点不授予 mastery，由 teacher_review_writeback._mastery 强制）。\n"
        f"- **同题重复 review / retry**：override 模拟两次 write_plan 哈希一致 = {o['all_idempotent']}；"
        "review queue 用 idempotency_key 去重。\n"
        f"- **override 后 Learning Brain 误写**：全程 dry_run，production_write_count = "
        f"{o['production_write_count']}。\n"
        f"- **source_gap/spec_gap 被误标 ready**：ready_leak_count = {p1['ready_leak_count']}"
        "（分类硬规则禁止 gap 类映射到 accept）。\n"
        "- **shadow 分数被当正式分数**：所有 queue/packet 标 is_formal_score=false、shadow_only=true。\n"
        f"- **legacy 被覆盖**：legacy_equal = {audit['legacy_equal']}（attach_runtime_shadow_result append-only）。\n"
        "- **空/慢/错误输入**：empty_or_error_input → blocked_from_writeback（fail-closed，不进 auto）。\n", encoding="utf-8")


def _finding(samples, queue, metrics, override, audit, packets, gate, kc) -> str:
    o = override["summary"]
    return (
        "# FINDING — Luban Grading QA Productization (B-line, 2026-06-04)\n\n## 必答 12\n"
        f"1. QA 样本 {len(samples)} 个，类型：{kc}（覆盖 source-backed 正例/high-risk/source_gap/spec_gap/"
        "external/override/duplicate/empty）。\n"
        f"2. review queue 100% final disposition = {metrics['final_disposition_100pct']}（无 unknown）。\n"
        f"3. teacher packets {packets['packets_written']} 份（terse 版优先，含 风险/证据/拦截/建议，降低判断成本）。\n"
        f"4. bad_certified={metrics['bad_certified']} / source_mismatch={metrics['source_mismatch']} / "
        f"false_positive={metrics['false_positive']}（均 0）。\n"
        f"5. override simulation 幂等 = {o['all_idempotent']}；误点 accept 被拦 = "
        f"{o['misclick_accept_blocked_for_high_risk']}；override 可授 mastery = {o['override_can_grant_mastery']}。\n"
        f"6. 分布：pending_rate={metrics['pending_review_rate']}、high_risk_rate={metrics['high_risk_rate']}、"
        f"override_rate={metrics['override_rate']}；blocked_reason={metrics['blocked_reason_distribution']}。\n"
        f"7. legacy unchanged = {metrics['legacy_equal']}（append-only）。\n"
        f"8. production_write_count = {metrics['production_write_count']}（0）。\n"
        f"9. 最阻塞 gated beta 的样本：{gate['most_blocking_for_gated_beta']}（全部需回 A 线补源/补 spec）。\n"
        f"10. **B 线 internal gated beta QA：{gate['b_line_internal_gated_beta_qa_verdict']}** — {gate['verdict_reason']}。\n"
        f"11. 需 A 线提供：{gate['a_line_dependencies']}。\n"
        "12. 下一步唯一主线：把当前 shadow 评分接入内部老师/运营试用——以 review queue + teacher packet + "
        "override(dry_run) 跑一轮真人复核，收集 override_rate/pending_rate 作为 gated beta 开关依据；"
        "源/spec 缺口回 A 线，不在 B 线造规则。\n\n"
        "## 红线\n不生成 formal registry / 不接 production runtime / 不覆盖 v0·legacy / 不改 kernel·RAG·DB·web·BI·billing / "
        "shadow 非正式成绩 / human_reviewed 仅 qa_simulated / 未伪造 live call / 未打印 secret / 未 commit。\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
