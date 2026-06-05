"""Build the M6 Registry v1 candidate dry-run package.

This compiler is intentionally offline and candidate-only. It projects M5's
final authority adjudication into a sealed dry-run artifact package, then proves
with the existing in-memory runtime gate that candidate statuses do not unlock
auto-certification.

Hard boundaries:
- no formal Registry v1 output
- no production runtime connection
- no DB, RAG authority, CaseGradingSkillKernel, BI, billing, or web changes
- M5 authority_adjudication is the only source for point auto-certification
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deeptutor.services.construction_grading.artifact_runtime_gate import (
    apply_runtime_artifact_gate,
    resolve_runtime_artifact_gate,
)
from deeptutor.services.construction_grading.question_grading_registry import (
    QuestionGradingRegistry,
)


M5_DIR = (
    REPO_ROOT
    / "artifacts/luban_grading_artifacts/case_rubric_authority_adjudication_m5_20260604"
)
V0_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/registry_v0_20260604"
# M5R jury review overlay (real 3-model heterogeneous jury). Overlay-only: it may gate which
# M5 publish-ready questions stay candidate, but NEVER upgrades a weak source to verified.
M5R_DIR = REPO_ROOT / "artifacts/luban_grading_artifacts/case_rubric_jury_review_m5r_20260604"
OUT_DIR = (
    REPO_ROOT
    / "artifacts/luban_grading_artifacts/registry_v1_candidate_dry_run_m6_20260604"
)

VERSION_ID = "qga_v1_candidate_dry_run_m6_20260604"
SCHEMA_VERSION = "question_grading_artifact.v1_candidate_dry_run"
PACKAGE_STATUS = "candidate_dry_run"

REQUIRED_M5_FILES = (
    "authority_adjudication.json",
    "point_authority_matrix.csv",
    "question_authority_summary.json",
    "registry_v1_promotion_candidate_simulation.json",
    "po_review_queue.json",
)

EXPECTED_COUNTS = {
    "question_count": 34,
    "point_count": 150,
    "auto_certifiable_point_count": 25,
    "review_required_official_weak_point_count": 112,
    "rewrite_needed_point_count": 13,
    "publish_ready_candidate_question_count": 2,
    "draft_review_candidate_question_count": 5,
    "po_review_required_question_count": 27,
    "blocked_candidate_question_count": 0,
    "llm_jury_covered_point_count": 0,
}

QUESTION_STATUS_TO_ARTIFACT_STATUS = {
    "publish_ready_candidate": "candidate_dry_run",
    "draft_review_candidate": "draft_review",
    "po_review_required": "po_review_required",
    "blocked_candidate": "blocked_candidate",
}

BLOCK_REASONS = {
    "review_required_official_weak": "official_weak_requires_po_or_source_review",
    "rewrite_needed": "policy_rewrite_required_before_auto_certification",
    "external_source_required": "external_source_required_before_auto_certification",
    "reject_candidate": "candidate_rejected_before_auto_certification",
}

FORMAL_REGISTRY_FILES = {
    "registry_v1.json",
    "question_grading_registry_v1.json",
    "question_grading_artifacts_v1.jsonl",
    "question_grading_registry.json",
    "question_grading_artifacts.jsonl",
}


class RegistryCandidateCompileBlocked(RuntimeError):
    """Raised when M6 refuses to emit a candidate package."""

    def __init__(self, audit: dict[str, Any]) -> None:
        self.audit = audit
        reasons = audit.get("blocking_reasons") or ["candidate compile blocked"]
        super().__init__("; ".join(reasons))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )


def _stable_hash(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dir_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(file.relative_to(path)).encode("utf-8"))
        digest.update(file.read_bytes())
    return digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_m5_inputs(m5_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_M5_FILES if not (m5_dir / name).exists()]
    if missing:
        return {"missing_input_files": missing}
    return {
        "missing_input_files": [],
        "authority_adjudication": _read_json(m5_dir / "authority_adjudication.json"),
        "point_authority_matrix": _read_csv_rows(m5_dir / "point_authority_matrix.csv"),
        "question_authority_summary": _read_json(m5_dir / "question_authority_summary.json"),
        "simulation": _read_json(m5_dir / "registry_v1_promotion_candidate_simulation.json"),
        "po_review_queue": _read_json(m5_dir / "po_review_queue.json"),
    }


def _llm_jury_has_real_coverage(point: dict[str, Any]) -> bool:
    suggestion = point.get("llm_jury_suggestion") or {}
    return bool(suggestion.get("available_models") or suggestion.get("votes"))


def _count_m5(authority_adjudication: dict[str, Any]) -> dict[str, int]:
    points = authority_adjudication.get("points") or []
    questions = authority_adjudication.get("questions") or {}
    point_decisions = Counter(p.get("point_authority_decision") for p in points)
    question_statuses = Counter(q.get("question_authority_status") for q in questions.values())
    return {
        "question_count": len(questions),
        "point_count": len(points),
        "auto_certifiable_point_count": sum(
            1
            for p in points
            if p.get("point_authority_decision") == "auto_certifiable"
            and p.get("auto_certifiable_final") is True
        ),
        "review_required_official_weak_point_count": point_decisions.get(
            "review_required_official_weak", 0
        ),
        "rewrite_needed_point_count": point_decisions.get("rewrite_needed", 0),
        "publish_ready_candidate_question_count": question_statuses.get(
            "publish_ready_candidate", 0
        ),
        "draft_review_candidate_question_count": question_statuses.get(
            "draft_review_candidate", 0
        ),
        "po_review_required_question_count": question_statuses.get("po_review_required", 0),
        "blocked_candidate_question_count": question_statuses.get("blocked_candidate", 0),
        "llm_jury_covered_point_count": sum(1 for p in points if _llm_jury_has_real_coverage(p)),
    }


def _audit_m5_inputs(m5_dir: Path, loaded: dict[str, Any]) -> dict[str, Any]:
    audit: dict[str, Any] = {
        "stage": "M6 Registry v1 Candidate Compile Dry-Run",
        "source_authority": str(m5_dir),
        "required_input_files": list(REQUIRED_M5_FILES),
        "missing_input_files": loaded.get("missing_input_files", []),
        "expected_counts": dict(EXPECTED_COUNTS),
        "formal_registry_allowed": False,
        "input_gate_status": "blocked",
        "exact_expected_counts_match": False,
        "blocking_reasons": [],
    }
    if audit["missing_input_files"]:
        audit["blocking_reasons"].append(
            "missing_required_m5_inputs:" + ",".join(audit["missing_input_files"])
        )
        return audit

    authority = loaded["authority_adjudication"]
    points = authority.get("points") or []
    questions = authority.get("questions") or {}
    summary = loaded["question_authority_summary"]
    simulation = loaded["simulation"]
    matrix = loaded["point_authority_matrix"]
    po_queue = loaded["po_review_queue"]

    counts = _count_m5(authority)
    matrix_decisions = Counter(row.get("point_authority_decision") for row in matrix)
    summary_statuses = Counter(row.get("question_authority_status") for row in summary)
    point_ids = {(p.get("question_id"), p.get("point_id")) for p in points}
    matrix_ids = {(r.get("question_id"), r.get("point_id")) for r in matrix}
    po_ids = {(r.get("question_id"), r.get("point_id")) for r in po_queue}
    non_auto_ids = {
        (p.get("question_id"), p.get("point_id"))
        for p in points
        if p.get("point_authority_decision") != "auto_certifiable"
    }
    decision_auto_mismatch = [
        {"question_id": p.get("question_id"), "point_id": p.get("point_id")}
        for p in points
        if (p.get("point_authority_decision") == "auto_certifiable")
        != (p.get("auto_certifiable_final") is True)
    ]

    cross_file = {
        "matrix_row_count": len(matrix),
        "matrix_decision_counts": dict(matrix_decisions),
        "matrix_ids_match_authority": matrix_ids == point_ids,
        "summary_question_count": len(summary),
        "summary_status_counts": dict(summary_statuses),
        "summary_matches_authority_questions": set(q.get("question_id") for q in summary)
        == set(questions),
        "simulation_only": simulation.get("simulation_only") is True,
        "simulation_formal_registry_emitted": simulation.get("formal_registry_emitted") is True,
        "simulation_counts": {
            "publish_ready_candidate_question_count": int(
                simulation.get("publish_ready_candidate_count", -1)
            ),
            "draft_review_candidate_question_count": int(
                simulation.get("draft_review_candidate_count", -1)
            ),
            "po_review_required_question_count": int(
                simulation.get("po_review_required_count", -1)
            ),
            "blocked_candidate_question_count": int(
                simulation.get("blocked_candidate_count", -1)
            ),
            "auto_certifiable_point_count": int(
                simulation.get("auto_certifiable_point_count", -1)
            ),
            "review_required_official_weak_point_count": int(
                simulation.get("review_required_point_count", -1)
            ),
            "rewrite_needed_point_count": int(
                simulation.get("rewrite_needed_point_count", -1)
            ),
        },
        "po_review_queue_point_count": len(po_queue),
        "po_review_queue_matches_non_auto_points": po_ids == non_auto_ids,
        "decision_auto_flag_mismatches": decision_auto_mismatch,
        "llm_votes_fabricated_count": sum(
            1
            for p in points
            if (p.get("llm_jury_suggestion") or {}).get("votes_fabricated") is True
        ),
    }
    audit["m5_counts"] = counts
    audit["cross_file_consistency"] = cross_file

    blocking: list[str] = []
    for key, expected in EXPECTED_COUNTS.items():
        if counts.get(key) != expected:
            blocking.append(f"expected_count_mismatch:{key}:{counts.get(key)}!={expected}")
    if len(matrix) != counts["point_count"] or matrix_ids != point_ids:
        blocking.append("point_authority_matrix_does_not_match_authority_adjudication")
    if len(summary) != counts["question_count"] or not cross_file[
        "summary_matches_authority_questions"
    ]:
        blocking.append("question_authority_summary_does_not_match_authority_adjudication")
    for key, expected in (
        ("publish_ready_candidate_question_count", counts["publish_ready_candidate_question_count"]),
        ("draft_review_candidate_question_count", counts["draft_review_candidate_question_count"]),
        ("po_review_required_question_count", counts["po_review_required_question_count"]),
        ("blocked_candidate_question_count", counts["blocked_candidate_question_count"]),
        ("auto_certifiable_point_count", counts["auto_certifiable_point_count"]),
        (
            "review_required_official_weak_point_count",
            counts["review_required_official_weak_point_count"],
        ),
        ("rewrite_needed_point_count", counts["rewrite_needed_point_count"]),
    ):
        if cross_file["simulation_counts"].get(key) != expected:
            blocking.append(f"simulation_count_mismatch:{key}")
    if simulation.get("simulation_only") is not True:
        blocking.append("m5_simulation_only_flag_not_true")
    if simulation.get("formal_registry_emitted") is not False:
        blocking.append("m5_claims_formal_registry_emitted")
    if len(po_queue) != 125 or po_ids != non_auto_ids:
        blocking.append("po_review_queue_does_not_match_non_auto_points")
    if decision_auto_mismatch:
        blocking.append("point_decision_auto_flag_mismatch")
    if cross_file["llm_votes_fabricated_count"]:
        blocking.append("m5_contains_fabricated_llm_votes")
    if (m5_dir / "registry_v1.json").exists():
        blocking.append("formal_registry_file_exists_in_m5_dir")

    audit["blocking_reasons"] = blocking
    audit["exact_expected_counts_match"] = not blocking
    audit["input_gate_status"] = "pass" if not blocking else "blocked"
    return audit


def _normalize_source_ref(ref: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ref:
        return None
    return {
        "source_type": ref.get("source_type"),
        "chunk_id": ref.get("chunk_id") or "",
        "quote": ref.get("textbook_quote") or ref.get("quote") or "",
        "verified": bool(ref.get("verified")),
        "match_method": ref.get("match_method") or "",
    }


def _source_refs_for_point(point: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    verified = _normalize_source_ref(point.get("verified_source_ref"))
    weak = _normalize_source_ref(point.get("weak_source_ref"))
    if verified:
        refs.append(verified)
    if weak:
        refs.append(weak)
    return refs


def _status_reason(status: str) -> str:
    return {
        "candidate_dry_run": "m5_publish_ready_candidate_but_formal_registry_forbidden",
        "draft_review": "m5_draft_review_candidate_requires_review_before_publish",
        "po_review_required": "m5_po_review_required_before_publish",
        "blocked_candidate": "m5_blocked_candidate",
    }.get(status, "m5_candidate_not_published")


def _candidate_point(point: dict[str, Any]) -> dict[str, Any]:
    decision = str(point.get("point_authority_decision") or "")
    auto = decision == "auto_certifiable" and point.get("auto_certifiable_final") is True
    return {
        "point_id": point.get("point_id"),
        "label": point.get("label") or "",
        "max_score": point.get("max_score"),
        "policy_type": point.get("policy_type") or "",
        "auto_certifiable": auto,
        "runtime_auto_certification_allowed": False,
        "source_status": point.get("source_status_final") or point.get("source_status"),
        "source_refs": _source_refs_for_point(point),
        "policy_gaps": list(point.get("policy_gaps") or []),
        "m5_authority": {
            "point_authority_decision": decision,
            "auto_certifiable_final": point.get("auto_certifiable_final") is True,
            "source_status_final": point.get("source_status_final"),
            "deterministic_gate": point.get("deterministic_gate"),
            "gate_reasons": list(point.get("gate_reasons") or []),
            "llm_jury_consensus": (point.get("llm_jury_suggestion") or {}).get("consensus"),
            "llm_jury_votes_fabricated": bool(
                (point.get("llm_jury_suggestion") or {}).get("votes_fabricated")
            ),
        },
    }


def _build_candidate_artifacts(authority_adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    questions = authority_adjudication.get("questions") or {}
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in authority_adjudication.get("points") or []:
        by_question[str(point["question_id"])].append(point)

    artifacts: list[dict[str, Any]] = []
    for question_id in sorted(questions):
        question = questions[question_id]
        point_rows = sorted(by_question[question_id], key=lambda row: str(row.get("point_id") or ""))
        scoring_points = [_candidate_point(point) for point in point_rows]
        auto_count = sum(1 for point in scoring_points if point["auto_certifiable"])
        decision_counts = Counter(
            point["m5_authority"]["point_authority_decision"] for point in scoring_points
        )
        artifact_status = QUESTION_STATUS_TO_ARTIFACT_STATUS[
            question["question_authority_status"]
        ]
        verified_points = sum(
            1 for point in scoring_points if point.get("source_status") == "verified_textbook"
        )
        artifact = {
            "artifact_id": f"{question_id}::{VERSION_ID}",
            "question_id": question_id,
            "schema_version": SCHEMA_VERSION,
            "version_id": VERSION_ID,
            "package_status": PACKAGE_STATUS,
            "status": artifact_status,
            "status_reason": _status_reason(artifact_status),
            "question_authority_status": question["question_authority_status"],
            "stem": point_rows[0].get("question_text") if point_rows else "",
            "official_answer": point_rows[0].get("official_answer") if point_rows else "",
            "scoring_points": scoring_points,
            "source_profile": {
                "verified_points": verified_points,
                "weak_points": len(scoring_points) - verified_points,
                "verified_rate": round(verified_points / len(scoring_points), 6)
                if scoring_points
                else 0,
                "m5_source_coverage": question.get("source_coverage"),
            },
            "quality_gates": {
                "auto_certifiable_point_count": auto_count,
                "review_required_official_weak_point_count": decision_counts.get(
                    "review_required_official_weak", 0
                ),
                "rewrite_needed_point_count": decision_counts.get("rewrite_needed", 0),
                "formal_publish_allowed": False,
                "runtime_auto_certification_allowed": False,
                "unsupported_required_terms": [],
                "blocked_reasons": [
                    BLOCK_REASONS.get(decision, decision)
                    for decision, count in sorted(decision_counts.items())
                    if decision != "auto_certifiable" and count
                ],
            },
            "provenance": {
                "compiled_from": "M5 authority_adjudication.json",
                "compiler": "scripts/build_luban_registry_v1_candidate_dry_run.py",
                "source_authority": str(M5_DIR),
                "formal_registry_emitted": False,
                "production_runtime_connected": False,
                "database_touched": False,
                "rag_used_as_authority": False,
            },
        }
        artifact["provenance"]["content_hash"] = _stable_hash(artifact)
        artifacts.append(artifact)
    return artifacts


def _build_registry_index(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(artifact["status"] for artifact in artifacts)
    total_points = sum(len(artifact["scoring_points"]) for artifact in artifacts)
    auto_points = sum(
        1
        for artifact in artifacts
        for point in artifact["scoring_points"]
        if point["auto_certifiable"]
    )
    index = {
        "version_id": VERSION_ID,
        "schema_version": "question_grading_registry.v1_candidate_dry_run",
        "package_status": PACKAGE_STATUS,
        "simulation_only": True,
        "formal_registry_emitted": False,
        "questions": {},
        "summary": {
            "total_questions": len(artifacts),
            "total_scoring_points": total_points,
            "auto_certifiable_point_count": auto_points,
            "question_status_counts": dict(status_counts),
        },
    }
    for artifact in artifacts:
        index["questions"][artifact["question_id"]] = {
            "artifact_id": artifact["artifact_id"],
            "status": artifact["status"],
            "status_reason": artifact["status_reason"],
            "question_authority_status": artifact["question_authority_status"],
            "auto_certifiable_point_count": artifact["quality_gates"][
                "auto_certifiable_point_count"
            ],
            "total_scoring_points": len(artifact["scoring_points"]),
            "content_hash": artifact["provenance"]["content_hash"],
            "runtime_auto_certification_allowed": False,
        }
    return index


def _build_publish_report(
    audit: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    registry = _build_registry_index(artifacts)
    decision_counts = Counter(
        point["m5_authority"]["point_authority_decision"]
        for artifact in artifacts
        for point in artifact["scoring_points"]
    )
    return {
        "version_id": VERSION_ID,
        "package_status": PACKAGE_STATUS,
        "simulation_only": True,
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
        "case_grading_skill_kernel_touched": False,
        "rag_used_as_authority": False,
        "database_touched": False,
        "m5_input_gate_status": audit["input_gate_status"],
        "m5_counts_match_exactly": audit["exact_expected_counts_match"],
        "total_questions": registry["summary"]["total_questions"],
        "total_scoring_points": registry["summary"]["total_scoring_points"],
        "auto_certifiable_point_count": registry["summary"]["auto_certifiable_point_count"],
        "blocked_from_auto_certification_point_count": registry["summary"][
            "total_scoring_points"
        ]
        - registry["summary"]["auto_certifiable_point_count"],
        "question_status_counts": registry["summary"]["question_status_counts"],
        "point_decision_counts": dict(decision_counts),
        "m7_verdict": (
            "WEAK-GO for M7 jury/PO/QA dry-run; "
            "NO-GO for formal Registry v1 publish/runtime connection"
        ),
        "next_task": (
            "M7 should run PO/jury/QA dry-run on the candidate package, repair weak "
            "official/rewrite points, then re-enter M6. Do not wire candidate output "
            "to production runtime."
        ),
    }


def _build_blocked_points(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        for point in artifact["scoring_points"]:
            decision = point["m5_authority"]["point_authority_decision"]
            if decision == "auto_certifiable":
                continue
            rows.append(
                {
                    "question_id": artifact["question_id"],
                    "point_id": point["point_id"],
                    "decision": decision,
                    "policy_type": point["policy_type"],
                    "source_status": point["source_status"],
                    "auto_certifiable": False,
                    "runtime_auto_certification_allowed": False,
                    "block_reason": BLOCK_REASONS.get(decision, decision),
                    "gate_reasons": point["m5_authority"]["gate_reasons"],
                    "policy_gaps": point["policy_gaps"],
                }
            )
    decision_counts = Counter(row["decision"] for row in rows)
    return {
        "version_id": VERSION_ID,
        "summary": {
            "blocked_point_count": len(rows),
            "decision_counts": dict(decision_counts),
            "auto_certification_allowed_count": 0,
        },
        "points": rows,
    }


def _build_po_carryover(
    authority_adjudication: dict[str, Any],
    po_review_queue: list[dict[str, Any]],
    extra_downgraded: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    questions = authority_adjudication.get("questions") or {}
    po_questions = [
        {
            "question_id": question_id,
            "question_authority_status": row["question_authority_status"],
            "point_count": row["point_count"],
            "auto_certifiable_point_count": row["auto_certifiable_point_count"],
            "source_coverage": row["source_coverage"],
            "carryover_reason": "m5_po_review_required_before_registry_publish",
        }
        for question_id, row in sorted(questions.items())
        if row.get("question_authority_status") == "po_review_required"
    ]
    # M5R-overlay downgrades: M5 publish-ready questions the jury did not clear join the PO queue.
    for artifact in sorted(extra_downgraded or [], key=lambda a: a["question_id"]):
        qrow = questions.get(artifact["question_id"], {})
        po_questions.append({
            "question_id": artifact["question_id"],
            "question_authority_status": artifact["question_authority_status"],
            "point_count": qrow.get("point_count", len(artifact.get("scoring_points") or [])),
            "auto_certifiable_point_count": qrow.get("auto_certifiable_point_count"),
            "source_coverage": qrow.get("source_coverage"),
            "carryover_reason": "m5r_jury_not_cleared_downgraded_to_po_review",
            "m5r_decision": (artifact.get("m5r_overlay") or {}).get("m5r_decision"),
        })
    points = [
        {
            "question_id": row["question_id"],
            "point_id": row["point_id"],
            "decision": row["decision"],
            "question_authority_status": row["question_authority_status"],
            "risk_notes": row.get("risk_notes") or [],
            "recommended_action": BLOCK_REASONS.get(row["decision"], row["decision"]),
        }
        for row in po_review_queue
    ]
    return {
        "version_id": VERSION_ID,
        "summary": {
            "po_review_required_question_count": len(po_questions),
            "non_auto_certifiable_point_count": len(points),
            "point_decision_counts": dict(Counter(point["decision"] for point in points)),
        },
        "questions": po_questions,
        "points": points,
    }


def _load_v0_summary(v0_dir: Path) -> dict[str, Any]:
    registry = _read_json(v0_dir / "question_grading_registry.json")
    publish = _read_json(v0_dir / "publish_report.json")
    artifacts = [
        json.loads(line)
        for line in (v0_dir / "question_grading_artifacts.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    return {
        "version_id": registry.get("version_id") or publish.get("version_id"),
        "total_questions": publish.get("total_questions", len(artifacts)),
        "total_scoring_points": publish.get(
            "total_scoring_points",
            sum(len(artifact.get("scoring_points") or []) for artifact in artifacts),
        ),
        "auto_certifiable_point_count": publish.get("auto_certifiable_point_count"),
        "status_counts": registry.get("summary") or {},
        "question_ids": sorted(registry.get("questions") or {}),
    }


def _build_v0_diff(
    v0_dir: Path,
    v0_digest_before: str,
    v0_digest_after: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    v0 = _load_v0_summary(v0_dir)
    candidate_ids = sorted(artifact["question_id"] for artifact in artifacts)
    v0_ids = set(v0["question_ids"])
    candidate_id_set = set(candidate_ids)
    total_points = sum(len(artifact["scoring_points"]) for artifact in artifacts)
    auto_points = sum(
        1
        for artifact in artifacts
        for point in artifact["scoring_points"]
        if point["auto_certifiable"]
    )
    return {
        "version_id": VERSION_ID,
        "v0_read_only_reference": True,
        "v0_digest_before": v0_digest_before,
        "v0_digest_after": v0_digest_after,
        "v0_overwritten": v0_digest_before != v0_digest_after,
        "v0": {
            "version_id": v0["version_id"],
            "total_questions": v0["total_questions"],
            "total_scoring_points": v0["total_scoring_points"],
            "auto_certifiable_point_count": v0["auto_certifiable_point_count"],
            "status_counts": v0["status_counts"],
        },
        "v1_candidate": {
            "version_id": VERSION_ID,
            "package_status": PACKAGE_STATUS,
            "total_questions": len(artifacts),
            "total_scoring_points": total_points,
            "auto_certifiable_point_count": auto_points,
            "status_counts": dict(Counter(artifact["status"] for artifact in artifacts)),
        },
        "question_id_diff": {
            "overlap_count": len(v0_ids & candidate_id_set),
            "v0_only_count": len(v0_ids - candidate_id_set),
            "candidate_only_count": len(candidate_id_set - v0_ids),
            "overlap_question_ids": sorted(v0_ids & candidate_id_set),
            "candidate_only_question_ids": sorted(candidate_id_set - v0_ids),
        },
        "interpretation": (
            "M6 is a separate candidate dry-run namespace. It does not replace or "
            "supersede registry_v0_20260604."
        ),
    }


def _build_runtime_gate_dry_run(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    registry = QuestionGradingRegistry(artifacts)
    question_rows: list[dict[str, Any]] = []
    total_auto_after_gate = 0
    total_pending_after_gate = 0
    for artifact in artifacts:
        gate = resolve_runtime_artifact_gate(artifact["question_id"], registry=registry)
        draft = {
            "point_results": [
                {
                    "point_id": point["point_id"],
                    "score": point.get("max_score") or 0,
                    "auto_certified": True,
                    "high_risk_review": False,
                    "unsupported": False,
                }
                for point in artifact["scoring_points"]
            ]
        }
        gated = apply_runtime_artifact_gate(draft, gate)
        total_auto_after_gate += gated["auto_certified_count"]
        total_pending_after_gate += gated["high_risk_review_count"] + gated["unsupported_count"]
        question_rows.append(
            {
                "question_id": artifact["question_id"],
                "candidate_artifact_status": artifact["status"],
                "gate_artifact_status": gate.artifact_status,
                "gate_auto_certification_allowed": gate.auto_certification_allowed,
                "candidate_auto_certifiable_point_count": artifact["quality_gates"][
                    "auto_certifiable_point_count"
                ],
                "point_auto_certified_after_gate_count": gated["auto_certified_count"],
                "blocked_or_pending_after_gate_count": gated["high_risk_review_count"]
                + gated["unsupported_count"],
                "effective_block_reason": gate.blocked_reason
                or f"{gate.artifact_status}_not_published",
            }
        )
    return {
        "version_id": VERSION_ID,
        "mode": "dry_run_only",
        "formal_runtime_connected": False,
        "production_runtime_connected": False,
        "candidate_registry_loaded_in_memory": True,
        "used_existing_runtime_gate": (
            "deeptutor.services.construction_grading.artifact_runtime_gate"
        ),
        "summary": {
            "question_count": len(artifacts),
            "artifact_status_counts": dict(Counter(row["gate_artifact_status"] for row in question_rows)),
            "artifact_auto_certification_allowed_count": sum(
                1 for row in question_rows if row["gate_auto_certification_allowed"]
            ),
            "point_auto_certified_after_gate_count": total_auto_after_gate,
            "blocked_or_pending_after_gate_count": total_pending_after_gate,
        },
        "questions": question_rows,
    }


def _candidate_registry_schema() -> str:
    return f"""# M6 Candidate Registry Schema

Version: `{VERSION_ID}`

This is a candidate dry-run schema, not a formal Registry v1 schema.

## Top-level registry

- `version_id`: fixed to `{VERSION_ID}`
- `package_status`: fixed to `candidate_dry_run`
- `simulation_only`: `true`
- `formal_registry_emitted`: `false`
- `questions`: map of `question_id -> candidate index row`
- `summary`: total question / point / candidate status counts

## Candidate artifact

- `schema_version`: `{SCHEMA_VERSION}`
- `status`: one of `candidate_dry_run`, `draft_review`, `po_review_required`, `blocked_candidate`
- `question_authority_status`: copied from M5
- `scoring_points[].auto_certifiable`: copied only from M5 final authority decision
- `scoring_points[].runtime_auto_certification_allowed`: always `false` in M6
- `provenance.formal_registry_emitted`: always `false`
- `provenance.production_runtime_connected`: always `false`

## Publish boundary

`candidate_dry_run` is deliberately not `published`. The existing
`ArtifactRuntimeGate` only allows auto-certification for `published` artifacts, so
M6 cannot unlock runtime auto-certification.
"""


def _render_finding(
    audit: dict[str, Any],
    report: dict[str, Any],
    blocked: dict[str, Any],
    runtime: dict[str, Any],
    diff: dict[str, Any],
    carryover: dict[str, Any],
    m5r_overlay: dict[str, Any],
) -> str:
    status_counts = report["question_status_counts"]
    decision_counts = report["point_decision_counts"]
    return f"""# FINDING Registry v1 Candidate Compile Dry-Run M6 20260604 (M5R overlay)

1. M5 counts match exactly: YES. M5 authority input is {audit['m5_counts']['question_count']} questions / {audit['m5_counts']['point_count']} points, with {audit['m5_counts']['auto_certifiable_point_count']} auto-certifiable, {audit['m5_counts']['review_required_official_weak_point_count']} official-weak review, and {audit['m5_counts']['rewrite_needed_point_count']} rewrite-needed points.
2. Formal Registry v1 generated: NO. `formal_registry_emitted=false`; no `registry_v1.json`, `question_grading_registry_v1.json`, or formal `question_grading_artifacts_v1.jsonl` is emitted.
3. Candidate counts: questions={report['total_questions']}, points={report['total_scoring_points']}, auto_certifiable_points={report['auto_certifiable_point_count']}, statuses={status_counts}.
4. Weak/rewrite blocked from auto-certification: YES. blocked_points={blocked['summary']['blocked_point_count']}, decisions={blocked['summary']['decision_counts']}; every blocked point has `runtime_auto_certification_allowed=false`.
5. Runtime gate proof: dry-run only. `ArtifactRuntimeGate` was loaded in memory, production_runtime_connected=false, artifact_auto_certification_allowed_count={runtime['summary']['artifact_auto_certification_allowed_count']}, point_auto_certified_after_gate_count={runtime['summary']['point_auto_certified_after_gate_count']}.
6. v0 not overwritten: YES. v0_read_only_reference=true and v0_overwritten={diff['v0_overwritten']}.
7. v0 vs v1 candidate diff: v0 has {diff['v0']['total_questions']} questions / {diff['v0']['total_scoring_points']} points / {diff['v0']['auto_certifiable_point_count']} auto points; M6 candidate has {diff['v1_candidate']['total_questions']} questions / {diff['v1_candidate']['total_scoring_points']} points / {diff['v1_candidate']['auto_certifiable_point_count']} auto points; overlap={diff['question_id_diff']['overlap_count']}.
8. PO review carryover: question-level po_review_required={carryover['summary']['po_review_required_question_count']}; point-level non-auto carryover={carryover['summary']['non_auto_certifiable_point_count']}, decisions={carryover['summary']['point_decision_counts']}.
9. LLM jury / provider status: real LLM jury coverage is {audit['m5_counts']['llm_jury_covered_point_count']}/{audit['m5_counts']['point_count']}; provider-unavailable advice remains non-authoritative and cannot promote weak sources.
10. M7 verdict: WEAK-GO for candidate-only jury/PO/QA dry-run; NO-GO for formal Registry v1 publish/runtime connection.
11. Next task: run M7 on this sealed candidate package, repair `review_required_official_weak` and `rewrite_needed` points with PO/external evidence, then re-run M6 before any formal publish decision.

## M5R jury overlay (real 3-model heterogeneous jury)

- M5R reviewed: {m5r_overlay.get('m5r_reviewed_question_count')} questions; jury_cleared (decision==publish_candidate): {m5r_overlay.get('m5r_jury_cleared_question_ids')}; needs_po_review: {m5r_overlay.get('m5r_needs_po_review_question_count')}.
- Overlay rule: a question stays `candidate_dry_run` ONLY if M5 publish-ready AND M5R jury-cleared. `candidate_dry_run_after_overlay`={m5r_overlay.get('candidate_dry_run_after_overlay_question_ids')}; M5 publish-ready questions the jury did not clear are DOWNGRADED to `po_review_required`: {m5r_overlay.get('downgraded_to_po_review_question_ids')}.
- **The jury never upgraded a weak source to verified**: source_status_upgraded_by_jury={m5r_overlay.get('source_status_upgraded_by_jury')}. The overlay only narrows the candidate set; auto_certifiable counts come solely from M5 deterministic authority.

## Boundary recap

- package_status: `{report['package_status']}`
- point_decision_counts: {decision_counts}
- no DB, no CaseGradingSkillKernel, no RAG-as-authority, no BI/billing/web path
"""


def _blocked_report(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "version_id": VERSION_ID,
        "package_status": "blocked",
        "simulation_only": True,
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
        "m5_input_gate_status": audit["input_gate_status"],
        "m5_counts_match_exactly": audit["exact_expected_counts_match"],
        "blocking_reasons": audit["blocking_reasons"],
    }


def _load_m5r_summary(m5r_dir: Path) -> dict[str, dict[str, Any]]:
    """M5R jury question-level decisions ({qid: {decision, quorum_met, ...}}); {} if absent."""
    path = m5r_dir / "question_decision_summary.json"
    if not path.exists():
        return {}
    data = _read_json(path)
    return data if isinstance(data, dict) else {}


def _apply_m5r_overlay(
    artifacts: list[dict[str, Any]], m5r: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Overlay the real M5R jury onto M5 candidates.

    Rule: a question stays ``candidate_dry_run`` ONLY if M5 marked it publish-ready AND the
    M5R jury cleared it (decision == publish_candidate). Any M5 publish-ready question the jury
    did NOT clear is DOWNGRADED to ``po_review_required`` (never upgraded). The jury never
    changes auto_certifiable or source_status — overlay only narrows the candidate set.
    """
    jury_cleared = {qid for qid, row in m5r.items()
                    if isinstance(row, dict) and row.get("decision") == "publish_candidate"}
    reviewed = set(m5r)
    needs_po = {qid for qid, row in m5r.items()
                if isinstance(row, dict) and row.get("decision") == "needs_po_review"}
    downgraded: list[str] = []
    kept: list[str] = []
    for artifact in artifacts:
        qid = artifact["question_id"]
        m5r_decision = (m5r.get(qid) or {}).get("decision") if qid in reviewed else "not_reviewed"
        overlay = {
            "m5r_reviewed": qid in reviewed,
            "m5r_decision": m5r_decision,
            "jury_cleared": qid in jury_cleared,
            "source_status_upgraded_by_jury": False,  # invariant: jury never upgrades source
        }
        if artifact["status"] == "candidate_dry_run":
            if qid in jury_cleared:
                kept.append(qid)
            else:
                artifact["status"] = "po_review_required"
                artifact["status_reason"] = "m5_publish_ready_but_m5r_jury_not_cleared_po_review"
                overlay["downgraded_from"] = "candidate_dry_run"
                downgraded.append(qid)
        artifact["m5r_overlay"] = overlay
        # status may have changed -> recompute the content hash deterministically
        artifact["provenance"]["content_hash"] = ""
        artifact["provenance"]["content_hash"] = _stable_hash(artifact)
    audit = {
        "version_id": VERSION_ID,
        "m5r_source": str(M5R_DIR),
        "overlay_rule": (
            "candidate_dry_run requires M5 publish_ready_candidate AND M5R jury decision "
            "== publish_candidate; jury may only narrow (downgrade), never upgrade source_status."
        ),
        "m5r_reviewed_question_count": len(reviewed),
        "m5r_jury_cleared_question_ids": sorted(jury_cleared),
        "m5r_needs_po_review_question_count": len(needs_po),
        "source_status_upgraded_by_jury": False,
        "candidate_dry_run_after_overlay_question_ids": sorted(kept),
        "downgraded_to_po_review_question_ids": sorted(downgraded),
    }
    return audit, downgraded


def build_registry_v1_candidate_dry_run(
    *,
    out_dir: str | Path = OUT_DIR,
    m5_dir: str | Path = M5_DIR,
    v0_dir: str | Path = V0_DIR,
    m5r_dir: str | Path = M5R_DIR,
) -> dict[str, Any]:
    out_path = Path(out_dir)
    m5_path = Path(m5_dir)
    v0_path = Path(v0_dir)
    if _is_relative_to(out_path, v0_path):
        audit = {
            "stage": "M6 Registry v1 Candidate Compile Dry-Run",
            "source_authority": str(m5_path),
            "input_gate_status": "blocked",
            "exact_expected_counts_match": False,
            "blocking_reasons": ["out_dir_must_not_be_inside_registry_v0_dir"],
        }
        raise RegistryCandidateCompileBlocked(audit)

    out_path.mkdir(parents=True, exist_ok=True)
    loaded = _load_m5_inputs(m5_path)
    audit = _audit_m5_inputs(m5_path, loaded)
    _write_json(out_path / "m5_input_audit.json", audit)
    if audit["input_gate_status"] != "pass":
        _write_json(out_path / "candidate_publish_report.json", _blocked_report(audit))
        raise RegistryCandidateCompileBlocked(audit)

    v0_digest_before = _dir_digest(v0_path)
    authority = loaded["authority_adjudication"]
    artifacts = _build_candidate_artifacts(authority)
    # M5R jury overlay: narrow candidate_dry_run to jury-cleared questions only (never upgrade).
    m5r_summary = _load_m5r_summary(Path(m5r_dir))
    m5r_overlay_audit, m5r_downgraded = _apply_m5r_overlay(artifacts, m5r_summary)
    registry_index = _build_registry_index(artifacts)
    report = _build_publish_report(audit, artifacts)
    blocked = _build_blocked_points(artifacts)
    carryover = _build_po_carryover(authority, loaded["po_review_queue"],
                                    extra_downgraded=[a for a in artifacts if a["question_id"] in set(m5r_downgraded)])
    runtime = _build_runtime_gate_dry_run(artifacts)
    v0_digest_after = _dir_digest(v0_path)
    diff = _build_v0_diff(v0_path, v0_digest_before, v0_digest_after, artifacts)
    finding = _render_finding(audit, report, blocked, runtime, diff, carryover, m5r_overlay_audit)

    _write_json(out_path / "question_grading_registry_v1_candidate.json", registry_index)
    (out_path / "question_grading_artifacts_v1_candidate.jsonl").write_text(
        "\n".join(json.dumps(artifact, ensure_ascii=False, sort_keys=True) for artifact in artifacts)
        + "\n",
        "utf-8",
    )
    _write_json(out_path / "candidate_publish_report.json", report)
    _write_json(out_path / "v0_vs_v1_candidate_diff.json", diff)
    _write_json(out_path / "runtime_gate_dry_run_results.json", runtime)
    _write_json(out_path / "blocked_from_auto_certification.json", blocked)
    _write_json(out_path / "po_review_carryover_queue.json", carryover)
    _write_json(out_path / "m5r_overlay_audit.json", m5r_overlay_audit)
    (out_path / "candidate_registry_schema.md").write_text(
        _candidate_registry_schema(),
        "utf-8",
    )
    (out_path / "FINDING_registry_v1_candidate_dry_run_m6_20260604.md").write_text(
        finding,
        "utf-8",
    )

    formal_written = [name for name in FORMAL_REGISTRY_FILES if (out_path / name).exists()]
    if formal_written:
        audit = {
            **audit,
            "input_gate_status": "blocked",
            "blocking_reasons": [f"formal_registry_file_present:{name}" for name in formal_written],
        }
        raise RegistryCandidateCompileBlocked(audit)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--m5-dir", default=str(M5_DIR))
    parser.add_argument("--v0-dir", default=str(V0_DIR))
    args = parser.parse_args()

    report = build_registry_v1_candidate_dry_run(
        out_dir=args.out_dir,
        m5_dir=args.m5_dir,
        v0_dir=args.v0_dir,
    )
    print(
        "registry v1 candidate dry-run -> "
        f"{args.out_dir} "
        f"questions={report['total_questions']} "
        f"points={report['total_scoring_points']} "
        f"auto={report['auto_certifiable_point_count']} "
        "formal_registry_emitted=false"
    )


if __name__ == "__main__":
    main()
