"""Case-rubric data + audit-packet schema v0 (M1) — validator (no fabrication).

This is the data contract that unblocks Registry v1: every NEW gradeable case question
must arrive as an AuditPacket whose published scoring points carry a VERIFIED textbook
anchor. It does NOT compile a registry, touch runtime, or fabricate sources — it only
defines + validates the shape, with the verify-on-write rule as the single gate for
``auto_certifiable``.

Schema entities (see docs/plan/评分引擎与金标工件/2026-06-04-luban-case-rubric-data-schema-v0.md):
  CaseRubricSourceRecord  -> the raw question (text/official_answer/node_code/source_exam)
  RubricCandidate         -> a model/answer-derived scoring point candidate (NOT authority)
  TextbookAnchorEvidence  -> {source_type, chunk_id, textbook_quote, verified, match_method}
  TypedPolicy             -> {policy_type, required_terms, list_spec, numeric_spec, penalty_spec}
  QuestionGradingArtifactDraft scoring point -> {point_id, policy_type, max_score, source_refs, auto_certifiable}
  AuditPacket             -> the full per-question record + quality_gate + provenance
"""
from __future__ import annotations

from typing import Any

TEXTBOOK = "textbook"
OFFICIAL_ANSWER = "official_answer"
NODE_SEED = "node_asset_seed"
ARTIFACT_STATUSES = {"draft", "published", "blocked"}
REVIEW_STATUSES = {"unreviewed", "reviewed", "rejected"}
_REQUIRED_PACKET_FIELDS = (
    "question_id", "question_text", "official_answer", "node_code", "source_exam",
    "rubric_candidates", "textbook_anchor_evidence", "teacher_review_status",
    "artifact_status", "scoring_points", "quality_gate", "provenance",
)


def verify_textbook_anchor(anchor: dict[str, Any]) -> bool:
    """verify-on-write: an anchor is a VERIFIED textbook source iff it is textbook-typed
    with a non-empty chunk_id AND textbook_quote AND a verbatim match. official_answer /
    node seed / semantic-similar anchors are NEVER verified."""
    if not isinstance(anchor, dict):
        return False
    if str(anchor.get("source_type")) != TEXTBOOK:
        return False
    if not str(anchor.get("chunk_id") or "").strip():
        return False
    if not str(anchor.get("textbook_quote") or "").strip():
        return False
    # verbatim is the only accepted match method; semantic/near is not verified.
    return str(anchor.get("match_method") or "") == "verbatim" and bool(anchor.get("verified"))


def _point_has_verified_textbook(point: dict[str, Any]) -> bool:
    return any(verify_textbook_anchor(r) for r in point.get("source_refs") or [])


def _meets_policy_minimum(point: dict[str, Any]) -> bool:
    pt = str(point.get("policy_type") or "")
    if pt == "exact_required":
        return bool(point.get("required_terms"))
    if pt == "list_rule":
        spec = point.get("list_spec") or {}
        return bool(spec.get("denominator")) and bool(spec.get("terms") or point.get("required_terms"))
    if pt == "calculation":
        return point.get("calculation_spec") is not None
    if pt == "penalty_rule":
        return point.get("penalty_rule") is not None or point.get("penalty_spec") is not None
    if pt == "high_risk_review":
        return False  # never auto
    return True


def validate_audit_packet(packet: dict[str, Any]) -> list[str]:
    """Return a list of violation strings; empty list == valid."""
    v: list[str] = []
    for f in _REQUIRED_PACKET_FIELDS:
        if f not in packet:
            v.append(f"missing_field:{f}")
    status = str(packet.get("artifact_status") or "")
    if status not in ARTIFACT_STATUSES:
        v.append(f"bad_artifact_status:{status}")
    if str(packet.get("teacher_review_status") or "") not in REVIEW_STATUSES:
        v.append("bad_teacher_review_status")

    points = packet.get("scoring_points") or []
    auto_points = []
    for sp in points:
        pid = sp.get("point_id")
        for req in ("point_id", "policy_type", "max_score", "source_refs"):
            if req not in sp:
                v.append(f"point_missing_field:{pid}:{req}")
        # verify-on-write: auto_certifiable ⟹ verified textbook anchor + policy minimum
        if sp.get("auto_certifiable"):
            auto_points.append(pid)
            if not _point_has_verified_textbook(sp):
                v.append(f"auto_without_verified_textbook:{pid}")
            if not _meets_policy_minimum(sp):
                v.append(f"auto_without_policy_minimum:{pid}")
        # official_answer-only / weak source must not be auto
        if sp.get("source_status") == "missing_or_weak" and sp.get("auto_certifiable"):
            v.append(f"weak_source_auto:{pid}")

    # draft / blocked must have ZERO auto-certifiable points
    if status in {"draft", "blocked"} and auto_points:
        v.append(f"{status}_has_auto_points:{auto_points}")
    # published must have at least one auto-certifiable point
    if status == "published" and not auto_points:
        v.append("published_without_auto_point")
    return v


def is_valid_audit_packet(packet: dict[str, Any]) -> bool:
    return not validate_audit_packet(packet)


__all__ = [
    "TEXTBOOK", "OFFICIAL_ANSWER", "NODE_SEED",
    "ARTIFACT_STATUSES", "REVIEW_STATUSES",
    "verify_textbook_anchor", "validate_audit_packet", "is_valid_audit_packet",
]
