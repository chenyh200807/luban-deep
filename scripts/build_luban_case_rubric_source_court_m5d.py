"""M5D — AI Expert Council Source Court over the 9 source_anchor_disputes.

Replaces the *human PO* sign-off with an honestly-labelled multi-model AI Expert Council
that renders a per-point `council_final` decision. It does NOT certify a registry, touch
runtime, fabricate sources, or call any human authority.

Single hard rule (unchanged from M1-M5A): the ONLY source authority is a 2026-textbook
verbatim exact match. Models (incl. this orchestrating Opus role) may only judge whether an
anchor SEMANTICALLY supports a point — they can never manufacture a source. The Aggregator is
deterministic and gated on textbook coverage, NOT on a simple model majority.

Council roles (4):
  - chief_rubric_architect        = gpt55 (Codex)        [reused M5B live jury vote]
  - strict_grading_prosecutor     = deepseek_v4          [reused M5B live jury vote]
  - chinese_domain_semantics_rev  = qwen37               [reused M5B live jury vote]
  - workflow_judge_adversarial    = opus48 (this model)  [offline genuine judgment, council_inputs/]

No new live API calls: the 3 external roles reuse the 33 real jury votes captured in
case_rubric_jury_live_m5b_20260604/; the 4th role is this orchestrating model's own offline
review. votes_fabricated=false everywhere; human_reviewed=false; no sanctioned-cache substitution.

Outputs -> artifacts/luban_grading_artifacts/ai_expert_council_source_court_m5d_20260604/
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Reuse the SAME deterministic verbatim machinery as M5A (single source-authority definition).
from scripts.build_luban_case_rubric_term_alignment_m5a import (
    _load_textbook,
    _norm,
    _clean_term,
)
from scripts.luban_case_rubric_schema import verify_textbook_anchor

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "luban_grading_artifacts"
M5A = ART / "case_rubric_term_alignment_m5a_20260604"
JURY_LIVE = ART / "case_rubric_jury_live_m5b_20260604"
PO_M5C = ART / "case_rubric_po_review_m5c_20260604"
OUT = ART / "ai_expert_council_source_court_m5d_20260604"
OPUS_VOTES = OUT / "council_inputs" / "opus_workflow_judge_votes.json"

# Map the 3 reused external jurors onto council roles.
EXTERNAL_ROLE = {
    "gpt55": "chief_rubric_architect",
    "deepseek_v4": "strict_grading_prosecutor",
    "qwen37": "chinese_domain_semantics_reviewer",
}
OPUS_ROLE = "workflow_judge_adversarial"

# Meta / error-restatement detectors (these are NOT scoring points).
_META_PAT = re.compile(r"^[（(]?\s*注[:：]|只需写出|不妥之处|错误之处|题目上缺少")


def _is_meta_or_error_restatement(label: str) -> bool:
    return bool(_META_PAT.search(str(label or "")))


def _term_hits(term: str, tb_norm: list[str]) -> bool:
    """Deterministic verbatim membership: cleaned, normalised term must appear in some block."""
    tn = _norm(_clean_term(term))
    if len(tn) < 3:
        return False
    return any(tn in md for md in tb_norm)


def _verified_textbook_refs(point: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (point.get("source_refs") or []) if verify_textbook_anchor(r)]


def _list_coverage(point: dict[str, Any], tb_norm: list[str]) -> dict[str, Any]:
    """For a list_rule point, recompute per-term verbatim coverage against the 2026 textbook."""
    spec = point.get("list_spec") or {}
    terms = list(spec.get("terms") or point.get("required_terms") or [])
    denom = int(spec.get("denominator") or len(terms) or 0)
    per_term = [{"term": t, "verbatim_textbook_hit": _term_hits(t, tb_norm)} for t in terms]
    hits = sum(1 for x in per_term if x["verbatim_textbook_hit"])
    coverage = round(hits / denom, 3) if denom else 0.0
    return {"denominator": denom, "verified_term_hits": hits, "coverage": coverage, "per_term": per_term}


def _source_verdict(point: dict[str, Any], tb_norm: list[str]) -> dict[str, Any]:
    """Deterministic textbook-only source authority verdict for one scoring point."""
    label = str(point.get("label") or "")
    policy = str(point.get("policy_type") or "")
    vrefs = _verified_textbook_refs(point)

    if _is_meta_or_error_restatement(label):
        return {"source_status": "meta_or_error_restatement", "verified_textbook_anchors": len(vrefs),
                "coverage": 0.0, "list": None}

    if policy == "list_rule":
        cov = _list_coverage(point, tb_norm)
        if cov["denominator"] and cov["coverage"] >= 1.0:
            status = "textbook_exact_match"
        elif cov["verified_term_hits"] >= 1:
            status = "textbook_partial_coverage"
        else:
            status = "source_gap"
        return {"source_status": status, "verified_textbook_anchors": len(vrefs),
                "coverage": cov["coverage"], "list": cov}

    # exact_required: the point's own primary term must be verbatim-present.
    if policy == "exact_required":
        primary = (point.get("required_terms") or [label])[0]
        hit = bool(vrefs) or _term_hits(primary, tb_norm)
        return {"source_status": "textbook_exact_match" if hit else "source_gap",
                "verified_textbook_anchors": len(vrefs), "coverage": 1.0 if hit else 0.0, "list": None}

    # semantic_allowed / figure_label: never verbatim-certifiable as a whole.
    if vrefs:
        # anchor covers only a fragment of a long compound point => over-credit.
        compound = len(re.findall(r"[、，,]", label)) >= 1 and len(_norm(label)) >= 22
        return {"source_status": "semantic_fragment_only" if compound else "semantic_supported",
                "verified_textbook_anchors": len(vrefs), "coverage": 0.0, "list": None}
    return {"source_status": "source_gap", "verified_textbook_anchors": 0, "coverage": 0.0, "list": None}


def _council_decision(source: dict[str, Any], votes: dict[str, str], policy: str) -> dict[str, Any]:
    """Deterministic Aggregator. Hard gate = textbook source verdict; model votes are evidence,
    NEVER a publish majority. Returns one of the 6 council actions."""
    status = source["source_status"]
    accepts = sum(1 for v in votes.values() if v == "accept")
    rejects = sum(1 for v in votes.values() if v == "reject")

    if status == "meta_or_error_restatement":
        action, publishable = "drop_point", False
        reason = "非采分内容(作答提示/错误情形复述)，无独立教材依据。"
    elif status == "textbook_exact_match":
        if accepts >= 3:
            action, publishable = "approve_with_repaired_anchor", True
            reason = f"教材 verbatim 全覆盖且 council {accepts}/4 接受，锚定为修复后的 source authority。"
        else:
            action, publishable = "keep_draft", False
            reason = f"教材 verbatim 覆盖达标，但 council 仅 {accepts}/4 接受(reject={rejects})，留 draft 待复核。"
    elif status == "textbook_partial_coverage":
        action, publishable = "split_point", False
        reason = (f"list 仅 {source['list']['verified_term_hits']}/{source['list']['denominator']} 项 "
                  f"verbatim 命中(coverage={source['coverage']})；拆分：命中项可自动认证，其余需教师/外部源。")
    elif status == "semantic_fragment_only":
        action, publishable = "rewrite_point", False
        reason = "复合句的 verbatim 锚只覆盖碎片，semantic 不可自动认证；改写为以命中分句为界的小采分点。"
    elif status == "semantic_supported":
        action, publishable = "keep_draft", False
        reason = "semantic_allowed 即便有锚也不进入自动认证，按策略留 draft。"
    else:  # source_gap
        action, publishable = "require_external_source", False
        reason = "0 个 verbatim 教材锚，属真实 source gap，需外部/教材源补齐后方可入库。"
    return {"council_action": action, "point_publishable": publishable, "aggregator_reason": reason,
            "council_accepts": accepts, "council_rejects": rejects}


def _load_external_votes(qid: str) -> dict[str, dict[str, str]]:
    """Return {point_id: {role: decision}} from the 3 reused live jury vote files."""
    out: dict[str, dict[str, str]] = {}
    for model, role in EXTERNAL_ROLE.items():
        f = JURY_LIVE / "model_votes" / f"{qid}__{model}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text("utf-8"))
        for pr in data.get("point_reviews") or []:
            pid = str(pr.get("point_id"))
            out.setdefault(pid, {})[role] = str(pr.get("decision") or "")
    return out


def _opus_votes_index() -> dict[tuple[str, str], dict[str, Any]]:
    data = json.loads(OPUS_VOTES.read_text("utf-8"))
    # normalise opus action vocab -> the per-point accept/non-accept signal used by the aggregator.
    idx = {}
    for v in data["votes"]:
        idx[(v["question_id"], v["point_id"])] = v
    return idx


def _opus_decision(judge_action: str) -> str:
    return "accept" if judge_action == "accept" else "reject"


def main() -> None:
    (OUT / "per_point_source_court_packets").mkdir(parents=True, exist_ok=True)

    tb = _load_textbook()
    tb_norm = [md for _, _, md in tb]

    # The 9 disputed questions (from M5C queue: source_anchor_dispute == true).
    queue = json.loads((PO_M5C / "po_review_queue_final.json").read_text("utf-8"))
    disputes = [q["question_id"] for q in queue if q.get("source_anchor_dispute")]

    opus_idx = _opus_votes_index()
    results: list[dict[str, Any]] = []

    for qid in disputes:
        packet = json.loads((M5A / "refined_audit_packets" / f"{qid}.json").read_text("utf-8"))
        ext = _load_external_votes(qid)
        point_results = []
        for pt in packet.get("scoring_points") or []:
            pid = str(pt.get("point_id"))
            policy = str(pt.get("policy_type") or "")
            source = _source_verdict(pt, tb_norm)

            votes = dict(ext.get(pid, {}))
            opus = opus_idx.get((qid, pid))
            if opus:
                votes[OPUS_ROLE] = _opus_decision(opus["judge_action"])

            decision = _council_decision(source, votes, policy)
            point_results.append({
                "point_id": pid,
                "policy_type": policy,
                "label_preview": str(pt.get("label") or "")[:90].replace("\n", " "),
                "source_verdict": source,
                "council_votes": votes,
                "opus_judge_action": (opus or {}).get("judge_action"),
                "opus_rationale": (opus or {}).get("rationale"),
                **decision,
            })

        publishable_pts = [p for p in point_results if p["point_publishable"]]
        all_resolved_to_publish = bool(point_results) and all(p["point_publishable"] for p in point_results)
        council_final_status = "council_approved" if all_resolved_to_publish else "council_not_publish"
        blocking = [{"point_id": p["point_id"], "council_action": p["council_action"]}
                    for p in point_results if not p["point_publishable"]]

        results.append({
            "question_id": qid,
            "final_authority": "ai_expert_council_final",
            "source_authority": "textbook_exact_match",
            "human_reviewed": False,
            "votes_fabricated": False,
            "council_roles": list(EXTERNAL_ROLE.values()) + [OPUS_ROLE],
            "council_final_status": council_final_status,
            "publishable_points": len(publishable_pts),
            "total_points": len(point_results),
            "blocking_points": blocking,
            "point_decisions": point_results,
        })

    # ----- write results json -----
    (OUT / "source_anchor_dispute_council_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), "utf-8")

    # ----- per-point packets (.md) -----
    for r in results:
        lines = [f"# Source-Court Packet — {r['question_id']}", "",
                 f"- council_final_status: **{r['council_final_status']}**",
                 f"- final_authority: `{r['final_authority']}` (human_reviewed={r['human_reviewed']}, votes_fabricated={r['votes_fabricated']})",
                 f"- publishable_points: {r['publishable_points']}/{r['total_points']}", ""]
        for p in r["point_decisions"]:
            sv = p["source_verdict"]
            lines += [f"## {p['point_id']} [{p['policy_type']}] → **{p['council_action']}**",
                      f"- label: {p['label_preview']}",
                      f"- source_status: `{sv['source_status']}` (verified_tb_anchors={sv['verified_textbook_anchors']}, coverage={sv['coverage']})"]
            if sv.get("list"):
                terms = ", ".join(f"{t['term']}{'✓' if t['verbatim_textbook_hit'] else '✗'}" for t in sv["list"]["per_term"])
                lines.append(f"- list_terms: {terms}")
            votes_s = ", ".join(f"{role}={dec}" for role, dec in p["council_votes"].items())
            lines += [f"- council_votes: {votes_s}",
                      f"- opus_judge: {p['opus_judge_action']} — {p['opus_rationale']}",
                      f"- aggregator: {p['aggregator_reason']}", ""]
        (OUT / "per_point_source_court_packets" / f"{r['question_id']}.md").write_text("\n".join(lines), "utf-8")

    # ----- council results md -----
    by_action: dict[str, int] = {}
    for r in results:
        for p in r["point_decisions"]:
            by_action[p["council_action"]] = by_action.get(p["council_action"], 0) + 1
    approved_q = [r["question_id"] for r in results if r["council_final_status"] == "council_approved"]

    md = ["# AI Expert Council — Source Court Results (M5D)", "",
          f"- disputed questions reviewed: **{len(results)}**",
          f"- council_approved (publishable as-is): **{len(approved_q)}** {approved_q}",
          f"- council_not_publish: **{len(results) - len(approved_q)}**",
          "",
          "## Per-point council actions",
          ""]
    for a, n in sorted(by_action.items(), key=lambda x: -x[1]):
        md.append(f"- `{a}`: {n}")
    md += ["", "## Per-question", ""]
    for r in results:
        md.append(f"- **{r['question_id']}** → {r['council_final_status']} "
                  f"({r['publishable_points']}/{r['total_points']} publishable); "
                  f"blocking={[b['point_id']+':'+b['council_action'] for b in r['blocking_points']]}")
    (OUT / "source_anchor_dispute_council_results.md").write_text("\n".join(md), "utf-8")

    summary = {
        "disputed_questions": len(results),
        "council_approved": len(approved_q),
        "council_not_publish": len(results) - len(approved_q),
        "by_council_action": by_action,
        "final_authority": "ai_expert_council_final",
        "human_reviewed": False,
        "votes_fabricated": False,
        "new_live_api_calls": 0,
        "reused_live_jury_votes": 33,
        "council_roles": list(EXTERNAL_ROLE.values()) + [OPUS_ROLE],
        "formal_registry_emitted": False,
    }
    (OUT / "source_court_summary_m5d.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
