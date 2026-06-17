"""M7 — AI Expert Council Final -> Registry v1 Candidate Compiler Hardening.

Fixes the M5A over-credit root cause IN THE COMPILER: a list_rule point may only be
auto_certifiable when EVERY list item has its own verified textbook verbatim anchor
(coverage == 1.0). A single anchor covering N items can never auto-certify the list.

Pipeline (all deterministic, offline, candidate-only):
  1. read every M5D council-final decision (25 points over 9 disputed questions);
  2. re-VERIFY each ``approve_with_repaired_anchor`` point by an INDEPENDENT 2026-textbook
     exact-match (never trust the council label as a source authority);
  3. only points that pass re-verification become ``auto_certifiable`` in a hardened
     CANDIDATE preview; everything else (split/rewrite/drop/require_external/keep_draft)
     is blocked from auto;
  4. prove with the existing in-memory runtime gate that the candidate preview does NOT
     unlock auto-certification (status candidate_dry_run != published).

Hard boundaries: no formal Registry v1, no production runtime / DB / RAG / kernel / web /
BI / billing, no live LLM, no commit. v0 is read-only and integrity-audited, never touched.

Outputs -> artifacts/luban_grading_artifacts/registry_v1_council_hardened_candidate_m7_20260604/
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Reuse the SAME deterministic verbatim machinery + M5D source verdict (single definition).
from scripts.build_luban_case_rubric_term_alignment_m5a import _load_textbook
from scripts.build_luban_case_rubric_source_court_m5d import (
    _term_hits,
    _list_coverage,
    _source_verdict,
)
from scripts.luban_case_rubric_schema import verify_textbook_anchor
from deeptutor.services.construction_grading.artifact_runtime_gate import (
    resolve_runtime_artifact_gate,
)
from deeptutor.services.construction_grading.question_grading_registry import (
    QuestionGradingRegistry,
)

ART = REPO / "artifacts" / "luban_grading_artifacts"
M5A = ART / "case_rubric_term_alignment_m5a_20260604"
M5D = ART / "ai_expert_council_source_court_m5d_20260604"
V0_DIR = ART / "registry_v0_20260604"
OUT = ART / "registry_v1_council_hardened_candidate_m7_20260604"

VERSION_ID = "qga_v1_council_hardened_candidate_m7_20260604"
SCHEMA_VERSION = "question_grading_artifact.v1_council_hardened_candidate"
PACKAGE_STATUS = "candidate_dry_run"

# The ONLY council action that is even eligible for auto — and only after re-verification.
AUTO_ELIGIBLE_ACTION = "approve_with_repaired_anchor"
BLOCKED_ACTIONS = {
    "split_point": "split_proposal_required_before_auto_certification",
    "rewrite_point": "policy_rewrite_required_before_auto_certification",
    "require_external_source": "external_source_required_before_auto_certification",
    "drop_point": "non_scoring_point_dropped",
    "keep_draft": "semantic_or_subquorum_draft_not_auto_certifiable",
}

HARD_GATE_RULES = {
    "schema_version": "luban_compiler_hard_gate_rules.v0",
    "source_authority": "textbook_exact_match_only",
    "final_authority_note": "ai_expert_council_final is a triage authority; it can NEVER substitute for textbook source authority",
    "rules": [
        "list_rule auto_certifiable REQUIRES coverage == 1.0 (every list item has its own verified textbook verbatim anchor)",
        "list_rule with denominator=N and a single anchor covering N items => downgrade (split_point/keep_draft), never auto",
        "council_action approve_with_repaired_anchor is NOT verified by itself; it must pass an independent deterministic exact-match re-verification",
        "council_action split_point => emit split proposal, never auto",
        "council_action require_external_source / rewrite_point / drop_point / keep_draft => never auto",
        "source_authority in {textbook_exact_match, source_gap} only",
        "human_reviewed = false; formal Registry v1 NOT emitted; production runtime NOT connected",
    ],
}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _dir_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(f.relative_to(path)).encode("utf-8"))
        digest.update(f.read_bytes())
    return digest.hexdigest()


def _packet(qid: str) -> dict[str, Any]:
    return json.loads((M5A / "refined_audit_packets" / f"{qid}.json").read_text("utf-8"))


def _point_in_packet(packet: dict[str, Any], pid: str) -> dict[str, Any] | None:
    for sp in packet.get("scoring_points") or []:
        if str(sp.get("point_id")) == pid:
            return sp
    return None


def _reverify_exact_match(point: dict[str, Any], tb_norm: list[str]) -> dict[str, Any]:
    """Independent deterministic exact-match re-verification of a point's repaired anchor.

    Does NOT trust the M5D approve label or the M5A verified flag — it re-runs the verbatim
    membership test against the 2026 textbook from scratch."""
    vrefs = [r for r in (point.get("source_refs") or []) if verify_textbook_anchor(r)]
    confirmed = []
    for r in vrefs:
        quote = str(r.get("textbook_quote") or "")
        hit = _term_hits(quote, tb_norm)
        confirmed.append({"chunk_id": r.get("chunk_id"), "textbook_quote": quote, "verbatim_recheck_hit": hit})
    passed = bool(confirmed) and all(c["verbatim_recheck_hit"] for c in confirmed)
    return {"verified_textbook_anchor_count": len(vrefs), "reverified_anchors": confirmed,
            "reverification_passed": passed}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tb = _load_textbook()
    tb_norm = [md for _, _, md in tb]

    council = json.loads((M5D / "source_anchor_dispute_council_results.json").read_text("utf-8"))

    # ---- 1. read + classify every M5D point ----
    input_points: list[dict[str, Any]] = []
    for q in council:
        for p in q["point_decisions"]:
            input_points.append({"question_id": q["question_id"], **p})
    action_counts = Counter(p["council_action"] for p in input_points)
    m5d_input_audit = {
        "m5d_source": str(M5D.relative_to(REPO)),
        "disputed_questions": len(council),
        "total_points_read": len(input_points),
        "by_council_action": dict(action_counts),
        "all_points_classified": all("council_action" in p for p in input_points),
        "final_authority_seen": sorted({q["final_authority"] for q in council}),
        "human_reviewed_any": any(q.get("human_reviewed") for q in council),
    }
    _write_json(OUT / "m5d_council_input_audit.json", m5d_input_audit)

    # ---- 2. re-verify the approve points; 3. compile per-point gate ----
    reverif: list[dict[str, Any]] = []
    list_rule_audit: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    # per-question -> list of compiled scoring points
    compiled_q: dict[str, dict[str, Any]] = {}

    for ip in input_points:
        qid, pid, action = ip["question_id"], ip["point_id"], ip["council_action"]
        packet = _packet(qid)
        sp = _point_in_packet(packet, pid) or {}
        policy = str(sp.get("policy_type") or ip.get("policy_type") or "")

        # list_rule coverage audit (every list_rule point, regardless of action)
        if policy == "list_rule":
            cov = _list_coverage(sp, tb_norm)
            list_rule_audit.append({
                "question_id": qid, "point_id": pid, "council_action": action,
                "denominator": cov["denominator"], "verified_term_hits": cov["verified_term_hits"],
                "coverage": cov["coverage"], "auto_eligible_by_coverage": cov["coverage"] >= 1.0,
            })

        auto_certifiable = False
        gate_reason = None
        if action == AUTO_ELIGIBLE_ACTION:
            rv = _reverify_exact_match(sp, tb_norm)
            # extra hard gate: a list_rule can only auto if FULL coverage too.
            list_ok = True
            if policy == "list_rule":
                list_ok = _list_coverage(sp, tb_norm)["coverage"] >= 1.0
            auto_certifiable = bool(rv["reverification_passed"] and list_ok)
            gate_reason = None if auto_certifiable else "reverification_or_coverage_failed"
            reverif.append({
                "question_id": qid, "point_id": pid, "policy_type": policy,
                "council_action": action, "list_full_coverage": list_ok,
                **rv, "compiled_auto_certifiable": auto_certifiable,
            })
        else:
            gate_reason = BLOCKED_ACTIONS.get(action, "blocked")
            blocked.append({"question_id": qid, "point_id": pid, "policy_type": policy,
                            "council_action": action, "block_reason": gate_reason})

        comp = compiled_q.setdefault(qid, {
            "question_id": qid, "version_id": VERSION_ID, "schema_version": SCHEMA_VERSION,
            "status": PACKAGE_STATUS, "final_authority": "ai_expert_council_final",
            "source_authority_model": "textbook_exact_match_or_source_gap",
            "human_reviewed": False, "scoring_points": [],
        })
        sverdict = _source_verdict(sp, tb_norm) if sp else {"source_status": "source_gap"}
        comp["scoring_points"].append({
            "point_id": pid, "policy_type": policy,
            "council_action": action,
            "auto_certifiable": auto_certifiable,
            "source_status": "ok" if auto_certifiable else "blocked_or_weak",
            "source_authority": "textbook_exact_match" if auto_certifiable else "source_gap",
            "gate_reason": gate_reason,
        })

    # quality_gates per question (shape compatible with QuestionGradingRegistry)
    artifacts = []
    for qid, comp in compiled_q.items():
        auto_n = sum(1 for s in comp["scoring_points"] if s["auto_certifiable"])
        comp["quality_gates"] = {
            "auto_certifiable_point_count": auto_n,
            "total_point_count": len(comp["scoring_points"]),
            "unsupported_required_terms": [],
        }
        artifacts.append(comp)

    _write_json(OUT / "repaired_anchor_reverification.json", {
        "approve_points_total": len(reverif),
        "reverification_passed_count": sum(1 for r in reverif if r["compiled_auto_certifiable"]),
        "points": reverif,
    })
    _write_json(OUT / "list_rule_coverage_audit.json", {
        "list_rule_point_count": len(list_rule_audit),
        "auto_eligible_by_full_coverage_count": sum(1 for r in list_rule_audit if r["auto_eligible_by_coverage"]),
        "partial_coverage_auto_blocked": all(not r["auto_eligible_by_coverage"] for r in list_rule_audit),
        "points": list_rule_audit,
    })
    _write_json(OUT / "blocked_by_council_action.json", {
        "blocked_point_count": len(blocked),
        "by_action": dict(Counter(b["council_action"] for b in blocked)),
        "points": blocked,
    })

    # ---- hardened candidate preview (registry + artifacts.jsonl) ----
    total_points = sum(len(a["scoring_points"]) for a in artifacts)
    total_auto = sum(a["quality_gates"]["auto_certifiable_point_count"] for a in artifacts)
    preview = {
        "version_id": VERSION_ID, "schema_version": SCHEMA_VERSION, "package_status": PACKAGE_STATUS,
        "simulation_only": True, "formal_registry_emitted": False, "production_runtime_connected": False,
        "final_authority": "ai_expert_council_final", "source_authority": "textbook_exact_match",
        "human_reviewed": False,
        "question_count": len(artifacts), "point_count": total_points,
        "auto_certifiable_point_count": total_auto,
        "questions": [{
            "question_id": a["question_id"], "status": a["status"],
            "auto_certifiable_point_count": a["quality_gates"]["auto_certifiable_point_count"],
            "total_point_count": a["quality_gates"]["total_point_count"],
        } for a in artifacts],
    }
    _write_json(OUT / "hardened_candidate_registry_preview.json", preview)
    (OUT / "hardened_candidate_artifacts_preview.jsonl").write_text(
        "".join(json.dumps(a, ensure_ascii=False, sort_keys=True) + "\n" for a in artifacts), "utf-8")

    # ---- runtime gate dry-run: candidate registry must NOT unlock auto ----
    reg = QuestionGradingRegistry(artifacts)
    gate_rows = []
    auto_allowed = 0
    point_auto_after_gate = 0
    for a in artifacts:
        gate = resolve_runtime_artifact_gate(a["question_id"], registry=reg)
        if gate.auto_certification_allowed:
            auto_allowed += 1
        # at runtime, candidate_dry_run status != published => every point downgraded
        for s in a["scoring_points"]:
            allowed = gate.auto_certification_allowed and gate.point_auto_certification.get(s["point_id"], False)
            if allowed:
                point_auto_after_gate += 1
        gate_rows.append({
            "question_id": a["question_id"], "artifact_status": gate.artifact_status,
            "auto_certification_allowed": gate.auto_certification_allowed,
            "blocked_reason": gate.blocked_reason,
        })
    runtime_results = {
        "mode": "dry_run_only",
        "used_existing_runtime_gate": "deeptutor.services.construction_grading.artifact_runtime_gate",
        "candidate_registry_loaded_in_memory": True,
        "production_runtime_connected": False,
        "formal_runtime_connected": False,
        "version_id": VERSION_ID,
        "summary": {
            "question_count": len(artifacts),
            "artifact_status_counts": dict(Counter(r["artifact_status"] for r in gate_rows)),
            "artifact_auto_certification_allowed_count": auto_allowed,
            "point_auto_certified_after_gate_count": point_auto_after_gate,
            "compiled_candidate_auto_certifiable_point_count": total_auto,
        },
        "questions": gate_rows,
    }
    _write_json(OUT / "runtime_gate_dry_run_results.json", runtime_results)

    # ---- v0 integrity audit (read-only; never overwrite/delete/supersede) ----
    v0_files = sorted(p.name for p in V0_DIR.glob("*")) if V0_DIR.exists() else []
    v0_audit = {
        "v0_dir": str(V0_DIR.relative_to(REPO)),
        "v0_exists": V0_DIR.exists(),
        "v0_file_count": len(v0_files),
        "v0_files": v0_files,
        "v0_dir_digest_sha256": _dir_digest(V0_DIR) if V0_DIR.exists() else None,
        "v0_overwritten_by_m7": False,
        "v0_deleted_by_m7": False,
        "v0_superseded": False,
        "note": "M7 reads nothing from and writes nothing to v0; v0 remains the only canonical published registry.",
    }
    _write_json(OUT / "v0_integrity_audit.json", v0_audit)

    _write_json(OUT / "compiler_hard_gate_rules.json", HARD_GATE_RULES)

    summary = {
        "version_id": VERSION_ID,
        "m5d_points_read": len(input_points),
        "approve_points": action_counts.get(AUTO_ELIGIBLE_ACTION, 0),
        "approve_points_passing_reverification": sum(1 for r in reverif if r["compiled_auto_certifiable"]),
        "list_rule_partial_auto_blocked": all(not r["auto_eligible_by_coverage"] for r in list_rule_audit),
        "blocked_from_auto_point_count": len(blocked),
        "candidate_question_count": len(artifacts),
        "candidate_point_count": total_points,
        "candidate_auto_certifiable_point_count": total_auto,
        "runtime_point_auto_certified_after_gate": point_auto_after_gate,
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
        "v0_superseded": False,
    }
    _write_json(OUT / "m7_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
