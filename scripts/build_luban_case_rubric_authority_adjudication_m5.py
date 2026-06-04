"""M5 authority adjudication and Registry v1 promotion simulation.

This stage is a deterministic authority gate. It merges M3/M4/source-lookup
facts, records model-jury unavailability honestly, and writes a promotion
simulation package. It never emits a formal Registry v1.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.luban_case_rubric_schema import TEXTBOOK, verify_textbook_anchor


M3_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
M4_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_anchor_refinement_m4_20260604"
M4_QUALITY_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_quality_m4_20260604"
SOURCE_LOOKUP_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_source_lookup_20260604"
OUT_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_authority_adjudication_m5_20260604"

JURY_MODELS = ["gpt55_codex", "opus48_dynamic", "deepseek_v4", "qwen37"]
AUTO_POLICY_TYPES = {"exact_required", "list_rule", "calculation", "penalty_rule"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _clean_dir(path: Path, suffix: str = "*") -> None:
    path.mkdir(parents=True, exist_ok=True)
    for old in path.glob(suffix):
        if old.is_file():
            old.unlink()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _load_packets() -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    # M4 is the refined view of the M3 30-question / 138-point set.
    for path in sorted((M4_DIR / "refined_audit_packets").glob("*.json")):
        packet = _read_json(path)
        packet["_m5_input_source"] = "m4_anchor_refinement"
        packets.append(packet)
    # Source lookup is a separate 4-question / 12-point side package.
    for path in sorted((SOURCE_LOOKUP_DIR / "audit_packets_source_lookup").glob("*.json")):
        packet = _read_json(path)
        packet["_m5_input_source"] = "m4_source_lookup"
        packets.append(packet)
    return packets


def _load_policy_gap_rows() -> dict[tuple[str, str], list[str]]:
    rows: dict[tuple[str, str], list[str]] = {}
    path = M4_DIR / "policy_gap_audit.json"
    if path.exists():
        data = _read_json(path)
        if isinstance(data, list):
            for row in data:
                rows[(row["question_id"], row["point_id"])] = list(row.get("gaps") or [])
    return rows


def _verified_source_refs(point: dict[str, Any]) -> list[dict[str, Any]]:
    return [ref for ref in point.get("source_refs") or [] if verify_textbook_anchor(ref)]


def _weak_source_refs(point: dict[str, Any]) -> list[dict[str, Any]]:
    weak: list[dict[str, Any]] = []
    for ref in point.get("source_refs") or []:
        if not verify_textbook_anchor(ref):
            weak.append(ref)
    lookup = point.get("source_lookup") or {}
    selected = lookup.get("selected_source")
    if selected and lookup.get("decision") in {"official_weak", "source_gap"}:
        weak.append(selected)
    return weak


def _source_status(point: dict[str, Any]) -> str:
    lookup = point.get("source_lookup") or {}
    if lookup.get("decision") == "source_gap":
        return "source_gap"
    if _verified_source_refs(point):
        return "verified_textbook"
    if lookup.get("decision") == "verified_standard":
        return "external_source_required"
    weak_refs = _weak_source_refs(point)
    if any(ref.get("source_type") in {"official_answer", "exam_explanation"} for ref in weak_refs):
        return "official_weak"
    if weak_refs:
        return "missing"
    return "missing"


def _computed_policy_gaps(point: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    policy = str(point.get("policy_type") or "")
    if policy == "exact_required" and not point.get("required_terms"):
        gaps.append("exact_required_without_required_terms")
    if policy == "list_rule":
        spec = point.get("list_spec") or {}
        if not spec.get("denominator"):
            gaps.append("list_rule_without_denominator")
        if not (spec.get("terms") or point.get("required_terms")):
            gaps.append("list_rule_without_item_set")
    if policy == "calculation":
        spec = point.get("calculation_spec")
        if not spec:
            gaps.append("calculation_without_spec")
        else:
            expected = str((spec or {}).get("expected_expression_or_value") or "")
            if expected and not re.search(r"\d", expected):
                gaps.append("calculation_spec_non_numeric")
    if policy == "penalty_rule" and not (point.get("penalty_rule") or point.get("penalty_spec")):
        gaps.append("penalty_rule_without_trigger")
    if policy == "high_risk_review":
        gaps.append("high_over_credit_risk")
    if policy and policy not in AUTO_POLICY_TYPES:
        gaps.append(f"unsupported_policy_type_for_auto:{policy}")
    return gaps


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _candidate_status(packet: dict[str, Any]) -> str:
    return str(
        packet.get("artifact_candidate_status")
        or packet.get("registry_disposition")
        or ("published_candidate_not_final" if packet.get("artifact_status") == "published" else "draft_candidate")
    )


def _fact_for_point(packet: dict[str, Any], point: dict[str, Any], policy_rows: dict[tuple[str, str], list[str]]) -> dict[str, Any]:
    key = (packet["question_id"], point["point_id"])
    verified_refs = _verified_source_refs(point)
    weak_refs = _weak_source_refs(point)
    status = _source_status(point)
    policy_gaps = _dedupe([*policy_rows.get(key, []), *_computed_policy_gaps(point)])
    if status != "verified_textbook":
        policy_gaps = _dedupe([*policy_gaps, "no_verified_textbook_anchor"])
    return {
        "input_source": packet.get("_m5_input_source"),
        "question_id": packet["question_id"],
        "point_id": point["point_id"],
        "policy_type": point.get("policy_type") or "",
        "max_score": point.get("max_score"),
        "label": point.get("label") or "",
        "question_text": packet.get("question_text") or "",
        "official_answer": packet.get("official_answer") or "",
        "source_status": status,
        "verified_source_ref": verified_refs[0] if verified_refs else None,
        "weak_source_ref": weak_refs[0] if weak_refs else None,
        "policy_gaps": policy_gaps,
        "auto_certifiable_before": bool(point.get("auto_certifiable")),
        "candidate_status_before": _candidate_status(packet),
        "source_exam": packet.get("source_exam") or "",
        "node_code": packet.get("node_code") or "",
    }


def build_unified_authority_fact_table() -> list[dict[str, Any]]:
    policy_rows = _load_policy_gap_rows()
    facts: list[dict[str, Any]] = []
    for packet in _load_packets():
        for point in packet.get("scoring_points") or []:
            facts.append(_fact_for_point(packet, point, policy_rows))
    return facts


def _llm_recommendation_counts(suggestion: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for vote in suggestion.get("votes") or []:
        rec = vote.get("recommended_decision")
        if rec:
            counts[rec] += 1
    return counts


def decide_point_authority(fact: dict[str, Any]) -> dict[str, Any]:
    source_status = fact.get("source_status") or "missing"
    policy_gaps = list(fact.get("policy_gaps") or [])
    llm = fact.get("llm_jury_suggestion") or {}
    llm_counts = _llm_recommendation_counts(llm)
    decision = "external_source_required"
    if source_status == "verified_textbook" and not policy_gaps:
        decision = "auto_certifiable"
    elif source_status == "official_weak":
        decision = "review_required_official_weak"
    elif any(gap for gap in policy_gaps if gap not in {"no_verified_textbook_anchor"}):
        decision = "rewrite_needed"
    elif source_status in {"missing", "source_gap", "external_source_required"}:
        decision = "external_source_required"

    # LLM jury can only down-rank; it cannot bypass the deterministic hard gate.
    if llm_counts.get("reject", 0) >= 3:
        decision = "reject_candidate"
    elif llm_counts.get("rewrite", 0) >= 3 and decision == "auto_certifiable":
        decision = "rewrite_needed"
    elif llm_counts.get("needs_external_source", 0) >= 1 and decision == "auto_certifiable":
        decision = "external_source_required"
    if source_status == "official_weak" and decision == "auto_certifiable":
        decision = "review_required_official_weak"
    return {
        "point_authority_decision": decision,
        "auto_certifiable_final": decision == "auto_certifiable",
        "source_status_final": source_status,
        "deterministic_gate": "pass" if decision == "auto_certifiable" else "blocked",
        "gate_reasons": policy_gaps or ([] if source_status == "verified_textbook" else [source_status]),
    }


def decide_question_status(point_decisions: list[dict[str, Any]]) -> str:
    if not point_decisions:
        return "blocked_candidate"
    decisions = [row["point_authority_decision"] for row in point_decisions]
    if all(decision == "reject_candidate" for decision in decisions):
        return "blocked_candidate"
    auto_count = sum(1 for decision in decisions if decision == "auto_certifiable")
    coverage = auto_count / len(decisions)
    if any(decision in {"external_source_required", "reject_candidate"} for decision in decisions):
        return "po_review_required"
    if coverage < 0.5:
        return "po_review_required"
    if any(decision == "rewrite_needed" for decision in decisions):
        return "draft_review_candidate"
    if auto_count == len(decisions):
        return "publish_ready_candidate"
    return "draft_review_candidate"


def _jury_unavailable_for_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": fact["question_id"],
        "point_id": fact["point_id"],
        "review_source": "model_jury_authority_advice",
        "reviewer_type": "llm_jury",
        "available_models": [],
        "provider_unavailable": JURY_MODELS,
        "votes": [],
        "votes_fabricated": False,
        "consensus": "provider_unavailable",
        "allowed_role": "advice_only_not_source_authority",
    }


def _write_jury_votes(out_dir: Path, facts: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    vote_dir = out_dir / "model_jury_votes"
    _clean_dir(vote_dir, "*.json")
    votes: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in facts:
        vote = _jury_unavailable_for_fact(fact)
        votes[(fact["question_id"], fact["point_id"])] = vote
        _write_json(vote_dir / f"{_safe_filename(fact['question_id'])}__{_safe_filename(fact['point_id'])}.json", vote)
    return votes


def _adjudicate(facts: list[dict[str, Any]], jury_votes: dict[tuple[str, str], dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        fact_with_jury = {**fact, "llm_jury_suggestion": jury_votes[(fact["question_id"], fact["point_id"])]}
        decision = decide_point_authority(fact_with_jury)
        row = {**fact, **decision, "llm_jury_suggestion": jury_votes[(fact["question_id"], fact["point_id"])]}
        rows.append(row)
        by_question[fact["question_id"]].append(row)
    question_summary: dict[str, Any] = {}
    for question_id, point_rows in by_question.items():
        auto_count = sum(1 for row in point_rows if row["point_authority_decision"] == "auto_certifiable")
        question_summary[question_id] = {
            "question_id": question_id,
            "point_count": len(point_rows),
            "auto_certifiable_point_count": auto_count,
            "source_coverage": auto_count / len(point_rows) if point_rows else 0,
            "question_authority_status": decide_question_status(point_rows),
            "candidate_status_before": point_rows[0].get("candidate_status_before"),
            "input_source": point_rows[0].get("input_source"),
        }
    return rows, question_summary


def _write_taxonomy(path: Path) -> None:
    text = """# Authority Decision Taxonomy

## Point Authority Decision

- `auto_certifiable`: verified textbook source plus complete deterministic policy.
- `review_required_official_weak`: official answer / explanation only; never auto-certifiable.
- `external_source_required`: missing/source_gap/external source candidate; needs auditable source before promotion.
- `rewrite_needed`: source may exist, but policy shape is incomplete or unsupported for runtime auto-certification.
- `reject_candidate`: model/PO review may reject; deterministic gate never upgrades a rejected point.

## Question Authority Status

- `publish_ready_candidate`: every point is auto-certifiable and source coverage is at least 50%.
- `draft_review_candidate`: enough source coverage for a draft, but some points need rewrite/review.
- `po_review_required`: source coverage below 50%, external source required, or high over-credit/source risk.
- `blocked_candidate`: no usable point authority remains.

Hard gate: LLM jury advice can only down-rank or request rewrite/source review. It cannot turn `official_weak`, `missing`, or generated quotes into verified source authority.
"""
    path.write_text(text, "utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "question_id", "point_id", "policy_type", "max_score", "source_status",
        "point_authority_decision", "auto_certifiable_before", "auto_certifiable_final",
        "candidate_status_before", "input_source", "policy_gaps",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: (";".join(row[field]) if field == "policy_gaps" else row.get(field, "")) for field in fields})


def _rewrite_recommendations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "question_id": row["question_id"],
            "point_id": row["point_id"],
            "label": row.get("label"),
            "policy_type": row.get("policy_type"),
            "policy_gaps": row.get("policy_gaps") or [],
            "recommended_action": "rewrite point label/required_terms/policy spec before registry promotion",
        }
        for row in rows
        if row["point_authority_decision"] == "rewrite_needed"
    ]


def _external_source_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "question_id": row["question_id"],
            "point_id": row["point_id"],
            "label": row.get("label"),
            "source_status": row.get("source_status"),
            "weak_source_ref": row.get("weak_source_ref"),
            "needed_source": "textbook_or_standard_verbatim_source_ref",
        }
        for row in rows
        if row["point_authority_decision"] in {"external_source_required", "review_required_official_weak"}
    ]


def _po_review_queue(rows: list[dict[str, Any]], question_summary: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in rows:
        if row["point_authority_decision"] != "auto_certifiable":
            queue.append(
                {
                    "question_id": row["question_id"],
                    "point_id": row["point_id"],
                    "decision": row["point_authority_decision"],
                    "question_authority_status": question_summary[row["question_id"]]["question_authority_status"],
                    "risk_notes": row.get("policy_gaps") or row.get("source_status"),
                }
            )
    return queue


def _simulation(rows: list[dict[str, Any]], question_summary: dict[str, Any]) -> dict[str, Any]:
    point_counts = Counter(row["point_authority_decision"] for row in rows)
    question_counts = Counter(row["question_authority_status"] for row in question_summary.values())
    m4_impact = _read_json(M4_DIR / "registry_impact_simulation_m4.json")
    return {
        "simulation_only": True,
        "formal_registry_emitted": False,
        "publish_ready_candidate_count": question_counts.get("publish_ready_candidate", 0),
        "draft_review_candidate_count": question_counts.get("draft_review_candidate", 0),
        "po_review_required_count": question_counts.get("po_review_required", 0),
        "blocked_candidate_count": question_counts.get("blocked_candidate", 0),
        "auto_certifiable_point_count": point_counts.get("auto_certifiable", 0),
        "review_required_point_count": point_counts.get("review_required_official_weak", 0),
        "external_source_required_point_count": point_counts.get("external_source_required", 0),
        "rejected_point_count": point_counts.get("reject_candidate", 0),
        "rewrite_needed_point_count": point_counts.get("rewrite_needed", 0),
        "delta_vs_m4": {
            "m4_auto_certifiable_points": m4_impact.get("auto_certifiable_points"),
            "m5_auto_certifiable_points": point_counts.get("auto_certifiable", 0),
            "auto_certifiable_delta": point_counts.get("auto_certifiable", 0) - int(m4_impact.get("auto_certifiable_points") or 0),
            "m4_published_candidate_not_final": m4_impact.get("published_candidate_not_final"),
            "m5_publish_ready_candidate": question_counts.get("publish_ready_candidate", 0),
        },
    }


def _write_po_packets(out_dir: Path, rows: list[dict[str, Any]], question_summary: dict[str, Any]) -> None:
    packet_dir = out_dir / "po_review_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    for old in packet_dir.glob("*.md"):
        old.unlink()
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_question[row["question_id"]].append(row)
    for question_id, point_rows in by_question.items():
        first = point_rows[0]
        lines = [
            f"# PO Review Packet: {question_id}",
            "",
            "## Stem",
            first.get("question_text") or "",
            "",
            "## Official Answer",
            first.get("official_answer") or "",
            "",
            "## Scoring Points",
        ]
        for row in point_rows:
            lines.extend(
                [
                    f"- {row['point_id']} `{row.get('policy_type')}` {row.get('label')}",
                    f"  - decision: {row['point_authority_decision']}",
                    f"  - verified textbook anchor: {row.get('verified_source_ref')}",
                    f"  - weak source: {row.get('weak_source_ref')}",
                    f"  - policy gaps: {row.get('policy_gaps')}",
                    f"  - LLM jury suggestions: {row.get('llm_jury_suggestion', {}).get('consensus')}",
                ]
            )
        lines.extend(
            [
                "",
                "## Recommended Action",
                f"recommended action: {question_summary[question_id]['question_authority_status']}",
                "",
                "## Risk Notes",
                "Do not promote weak source, unsupported policy, or LLM advice into source authority.",
                "",
                "## Provenance",
                f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
                f"- input_source: {first.get('input_source')}",
                "- builder: scripts/build_luban_case_rubric_authority_adjudication_m5.py",
            ]
        )
        (packet_dir / f"{_safe_filename(question_id)}.md").write_text("\n".join(lines) + "\n", "utf-8")


def _finding(rows: list[dict[str, Any]], question_summary: dict[str, Any], simulation: dict[str, Any]) -> str:
    source_counts = Counter(row["source_status"] for row in rows)
    point_counts = Counter(row["point_authority_decision"] for row in rows)
    question_counts = Counter(row["question_authority_status"] for row in question_summary.values())
    provider_unavailable = JURY_MODELS
    verdict = "WEAK-GO" if simulation["auto_certifiable_point_count"] else "NO-GO"
    return f"""# FINDING case rubric authority adjudication M5 20260604

1. 输入：{len(question_summary)} 题，{len(rows)} 点。
2. source_status：verified_textbook={source_counts.get('verified_textbook', 0)}，official_weak={source_counts.get('official_weak', 0)}，missing={source_counts.get('missing', 0)}，external_source_required={source_counts.get('external_source_required', 0)}，source_gap={source_counts.get('source_gap', 0)}。
3. auto_certifiable point 最终：{point_counts.get('auto_certifiable', 0)}。
4. review_required_official_weak：{point_counts.get('review_required_official_weak', 0)}。
5. rewrite_needed：{point_counts.get('rewrite_needed', 0)}。
6. reject_candidate：{point_counts.get('reject_candidate', 0)}。
7. external_source_required：{point_counts.get('external_source_required', 0)}。
8. question status：publish_ready_candidate={question_counts.get('publish_ready_candidate', 0)}，draft_review_candidate={question_counts.get('draft_review_candidate', 0)}，po_review_required={question_counts.get('po_review_required', 0)}，blocked_candidate={question_counts.get('blocked_candidate', 0)}。
9. LLM jury 覆盖率：0/{len(rows)}，provider_unavailable={provider_unavailable}。未伪造 vote。
10. LLM 是否尝试把 weak 升 verified：NO。本轮无真实 LLM vote；即使存在，hard gate 也不能上调 weak。
11. 是否生成正式 registry：NO。
12. 是否伪造 source_ref/textbook_quote/human review/LLM vote：NO。
13. 是否可以进入 M6 Registry v1 candidate compile：{verdict}。只能编译严格标注的 candidate simulation，不能当正式 registry。
14. 下一步最小任务：只取 `auto_certifiable` 点生成 M6 candidate compile dry-run，并把 `rewrite_needed` / `official_weak` 队列交 PO 或外部源补齐。
"""


def build_authority_adjudication_m5(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = build_unified_authority_fact_table()
    jury_votes = _write_jury_votes(out_dir, facts)
    rows, question_summary = _adjudicate(facts, jury_votes)
    simulation = _simulation(rows, question_summary)

    _write_json(out_dir / "unified_authority_fact_table.json", facts)
    _write_taxonomy(out_dir / "authority_decision_taxonomy.md")
    _write_json(out_dir / "authority_adjudication.json", {"points": rows, "questions": question_summary})
    _write_csv(out_dir / "point_authority_matrix.csv", rows)
    _write_json(out_dir / "question_authority_summary.json", list(question_summary.values()))
    _write_json(out_dir / "rewrite_recommendations.json", _rewrite_recommendations(rows))
    _write_json(out_dir / "external_source_required_queue.json", _external_source_queue(rows))
    _write_json(out_dir / "po_review_queue.json", _po_review_queue(rows, question_summary))
    _write_json(out_dir / "registry_v1_promotion_candidate_simulation.json", simulation)
    _write_po_packets(out_dir, rows, question_summary)
    (out_dir / "FINDING_case_rubric_authority_adjudication_m5_20260604.md").write_text(_finding(rows, question_summary, simulation), "utf-8")
    return {"out_dir": str(out_dir), "points": len(rows), "questions": len(question_summary), "simulation": simulation}


if __name__ == "__main__":
    print(json.dumps(build_authority_adjudication_m5(), ensure_ascii=False, indent=2))
