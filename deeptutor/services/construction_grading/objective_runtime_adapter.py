"""Objective runtime adapter (M25-B, fat skill).

Bridges the compiled objective answer-key CANDIDATE bundle to the runtime: looks a question up
by ``question_id``, builds a scoped GradingPacket, grades deterministically, and returns an
append-only ``candidate_unverified`` payload. Never claims official truth, never auto-promotes
to release, never writes production / canonical truth. Fail-closed on a missing / malformed /
tampered bundle; fail-OPEN (open-world diagnostic) when the question is not in the bank.

ALL policy lives here / in the compiler / grader (fat skills). The deep_question wrapper only
does flag + cohort + append.
"""
from __future__ import annotations

from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading import full_knowledge_compiler as _FKC
from deeptutor.services.construction_grading import objective_answer_key_compiler as _C
from deeptutor.services.construction_grading.compiled_context import (
    build_luban_context_pack,
    build_pack_from_question_context,
)
from deeptutor.services.construction_grading.grading_packet_builder import build_grading_packet
from deeptutor.services.construction_grading.objective_grader import grade_objective_submission

_log = logging.getLogger(__name__)

AUTHORITY = "luban_grading_engine_objective_candidate"

# ----------------------------- M31 governed lane -----------------------------
# The SIGNED M30 governed objective release_candidate registry (full_knowledge_compiler lane,
# namespace ``objective_answer_key_full``). Persisted as a tracked runtime supply by the M31
# runner (master plan §0.26.12 step 0); the runtime loads ONLY this tracked bundle, never the
# untracked artifact dir. A governed hit scores in-bank objective answers as CONTROLLED
# release-truth (``official_score_allowed=True``); a miss / tamper falls through to the candidate
# lane (which itself falls through to open-world). Default-OFF gating lives in the deep_question
# thin wrapper; policy lives here (fat skill).
GOVERNED_AUTHORITY = "luban_grading_engine_m31_governed_objective"
_GOVERNED_NAMESPACE = "objective_answer_key_full"  # hard-wired; NEVER read from the manifest
_GOVERNED_DIR = Path(__file__).parent / "runtime_supply" / "v3_objective_records_released_m31"
_GOVERNED_BUNDLE = _GOVERNED_DIR / "objective_answer_key_release_candidate_m31.json"
_GOVERNED_POINTER = _GOVERNED_DIR / "canonical_pointer_m31.json"


@lru_cache(maxsize=1)
def _candidate_index() -> tuple[bool, dict[str, dict[str, Any]]]:
    """Load + verify the tracked candidate bundle once. Returns (verified, {question_id: record})."""
    bundle = _C.build_candidate_bundle_from_seed()
    if not _C.verify_objective_bundle(bundle):
        return (False, {})
    index = {r["question_id"]: r for r in bundle.get("records", []) if r.get("question_id")}
    return (True, index)


def _fail_closed(reason: str) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "mode": "objective_candidate",
        "status": "candidate_bundle_unavailable",
        "fail_closed": True,
        "unavailable_reason": reason[:200],
        "not_production_grade": True,
        "writeback_performed": False,
    }


def _open_world(question_id: str, selected_option: Any) -> dict[str, Any]:
    """Not-in-bank: fail-open teaching/diagnostic. Never an official score."""
    ctx = {"status": "unresolved", "question_id": question_id}
    packet = build_grading_packet(ctx, selected_option=selected_option)
    pack = build_luban_context_pack(resolution=ctx)
    return {
        "authority": AUTHORITY,
        "mode": "open_world_fail_open",
        "status": "needs_review",
        "label": "unverified_diagnostic",
        "official_answer_claimed": False,
        "auto_score": False,
        "packet": packet,
        "compiled_context": pack.to_dict(),
        "compiler_work_order": {
            "kind": "objective_answer_key_candidate",
            "question_id": question_id,
            "reason": "question_id not in candidate bundle; route to compiler candidate, not release",
            "promote_to_release": False,
        },
        "not_production_grade": True,
        "writeback_performed": False,
    }


@lru_cache(maxsize=1)
def _governed_index() -> tuple[bool, dict[str, dict[str, Any]], str]:
    """Load + fail-closed verify the TRACKED signed governed bundle once.

    Reads ONLY the tracked v3 bundle + canonical pointer (never the untracked artifact dir).
    Four deterministic gates, ALL required (else ``(False, {}, reason)`` and the caller falls
    through to the candidate lane — a governed tamper is NOT a global fail-closed):
      1. ``verify_lane_bundle`` recomputes content_hash over records + signature (internal tamper).
      2. status == ``release_candidate`` and not ``published`` (never published authority at runtime).
      3. AUTHENTICITY: ``manifest.content_hash`` must equal the canonical pointer's committed
         ``expected_content_hash`` — the keyless signature only proves internal consistency, so the
         trust boundary is the tracked path + the pinned hash (master plan §0.26.12).
      4. namespace pinned to the hard-wired constant (never trust the manifest's own namespace).
    """
    if not _GOVERNED_BUNDLE.exists() or not _GOVERNED_POINTER.exists():
        return (False, {}, "absent")
    try:
        bundle = json.loads(_GOVERNED_BUNDLE.read_text(encoding="utf-8"))
        pointer = json.loads(_GOVERNED_POINTER.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — must never raise into the runtime
        return (False, {}, f"unreadable:{exc}")
    manifest = bundle.get("manifest") or {}
    if not _FKC.verify_lane_bundle(bundle, _GOVERNED_NAMESPACE):
        _log.warning("M31 governed bundle rejected: %s", "verify_lane_bundle_failed")
        return (False, {}, "verify_lane_bundle_failed")
    if manifest.get("status") != "release_candidate" or manifest.get("published") is True:
        _log.warning("M31 governed bundle rejected: %s", "status_gate_failed")
        return (False, {}, "status_gate_failed")
    expected = str(pointer.get("expected_content_hash") or "").strip()
    if not expected or str(manifest.get("content_hash") or "") != expected:
        _log.warning("M31 governed bundle rejected: %s", "pinned_hash_mismatch")
        return (False, {}, "pinned_hash_mismatch")
    if manifest.get("namespace") != _GOVERNED_NAMESPACE:
        _log.warning("M31 governed bundle rejected: %s", "namespace_mismatch")
        return (False, {}, "namespace_mismatch")
    index = {
        r["question_id"]: r
        for r in bundle.get("records", [])
        if isinstance(r, dict) and r.get("question_id")
    }
    return (True, index, str(pointer.get("coverage") or "unknown"))


def _governed_payload(
    record: dict[str, Any],
    *,
    qid: str,
    selected_option: Any,
    learner_context: dict[str, Any] | None,
    coverage: str,
) -> dict[str, Any]:
    """Governed release-candidate payload: deterministic grade + controlled release-truth pack.

    The answer key comes ONLY from the signed bundle record. Release authority is granted ONLY via
    the trusted ``governed_registry_status`` kwarg of ``build_pack_from_question_context`` (F1):
    a context-supplied ``registry_status`` can NOT flip ``official_score_allowed``. The LLM never
    decides correctness; objective grading is 100% deterministic.
    """
    raw_key = record.get("answer_key")
    answer_key = "".join(raw_key) if isinstance(raw_key, list) else str(raw_key or "")
    ctx = {
        "status": "resolved",  # literal; never sourced from untrusted/free-text input
        "question_id": qid,
        "question_type": record.get("question_type"),
        "answer_key": answer_key,  # signed-bundle authority ONLY
        "source_refs": record.get("source_refs") or [],
        # NOTE: no registry_status in ctx — build_pack_from_question_context ignores it (F1);
        # authority is granted solely via the governed_registry_status kwarg below.
    }
    packet = build_grading_packet(
        ctx,
        learner_context=learner_context or {},
        selected_option=selected_option,
        answer_key=answer_key,
    )
    pack = build_pack_from_question_context(
        ctx,
        learner_context=learner_context or {},
        governed_registry_status="release_candidate",  # the ONLY release-grant seam
    )
    grade = grade_objective_submission(
        answer_key=answer_key,
        selected=selected_option,
        question_type=str(record.get("question_type") or ""),
        option_metadata=record.get("option_metadata"),
    )
    policy = pack.to_dict().get("diagnostic_policy", {})
    return {
        "authority": GOVERNED_AUTHORITY,
        "mode": "governed_objective_release_candidate",
        "lane": packet["lane"],
        "coverage": coverage,
        "answer_key_hash": record.get("answer_key_hash"),
        "selected_option": selected_option,
        "option_metadata": record.get("option_metadata"),
        "source_refs": record.get("source_refs") or [],
        "result": grade,
        "compiled_context": pack.to_dict(),
        "llm_may_decide_correctness": False,
        "authority_kind": "objective_answer_key_governed",
        "status": "release_candidate",
        "release_truth": bool(pack.official_score_allowed),
        "official_score_allowed": bool(pack.official_score_allowed),
        "controlled_official": bool(policy.get("controlled_official")),
        "client_supplied_registry_status_ignored": True,
        # release_candidate is CONTROLLED official, not published; never a canonical/production write.
        "not_production_grade": False,
        "writeback_performed": False,
    }


def build_governed_objective_payload(
    *,
    question_id: str,
    selected_option: Any,
    learner_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """M31 entry: governed signed registry hit -> controlled release-truth; else candidate lane.

    Priority: (1) governed signed bundle hit -> release-grade payload; (2) governed miss / tamper /
    bundle unavailable -> fall through to the candidate lane (``build_objective_candidate_payload``),
    which itself falls through to open-world for not-in-bank questions. This keeps the M25-B candidate
    lane byte-identical and never globally fail-closes a governed-only failure.
    """
    qid = str(question_id or "").strip()
    try:
        gov_verified, gov_index, coverage = _governed_index()
    except Exception:  # noqa: BLE001 — governed failure must never break legacy or candidate lane
        gov_verified, gov_index, coverage = False, {}, "index_error"
    if gov_verified and qid and qid in gov_index:
        try:
            return _governed_payload(
                gov_index[qid],
                qid=qid,
                selected_option=selected_option,
                learner_context=learner_context,
                coverage=coverage,
            )
        except Exception:  # noqa: BLE001 — a scoring crash must fall through, not error the turn
            _log.warning("M31 governed payload build failed for qid=%s; falling through", qid, exc_info=True)
    return build_objective_candidate_payload(
        question_id=qid,
        selected_option=selected_option,
        learner_context=learner_context,
    )


def build_objective_candidate_payload(
    *,
    question_id: str,
    selected_option: Any,
    learner_context: dict[str, Any] | None = None,
    index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Append-only objective candidate payload. Fail-closed on tamper; fail-open on not-in-bank.

    ``index`` optionally injects a pre-verified {question_id: record} map (e.g. the M25-C
    real-source candidate bundle). When omitted, the tracked synthetic candidate bundle is
    loaded + verified. Either way answer_key is the sole authority; the LLM cannot decide
    correctness; status stays candidate_unverified (never release)."""
    qid = str(question_id or "").strip()
    if index is not None:
        verified = bool(index)
    else:
        try:
            verified, index = _candidate_index()
        except Exception as exc:  # noqa: BLE001 — must never break legacy
            return _fail_closed(f"index_error:{exc}")
    if not verified:
        return _fail_closed("candidate_bundle_failed_verification")  # tamper / malformed -> fail-closed
    if not qid or qid not in index:
        return _open_world(qid, selected_option)

    record = index[qid]
    answer_key = str(record.get("answer_key") or "")
    ctx = {
        "status": "resolved",
        "question_id": qid,
        "question_type": record.get("question_type"),
        "answer_key": answer_key,
        # candidate bundle is NOT a signed release: the pack must report official_score_allowed=False.
        "registry_status": "candidate",
        "source_refs": record.get("source_refs") or [],
    }
    packet = build_grading_packet(
        ctx,
        learner_context=learner_context or {},
        selected_option=selected_option,
        answer_key=answer_key,
    )
    pack = build_luban_context_pack(resolution=ctx, learner_context=learner_context or {})
    grade = grade_objective_submission(
        answer_key=answer_key,
        selected=selected_option,
        question_type=str(record.get("question_type") or ""),
        option_metadata=record.get("option_metadata"),
    )
    return {
        "authority": AUTHORITY,
        "mode": "objective_candidate",
        "lane": packet["lane"],
        "answer_key_hash": record.get("answer_key_hash"),
        "selected_option": selected_option,
        "option_metadata": record.get("option_metadata"),
        "source_refs": record.get("source_refs") or [],
        "result": grade,
        "compiled_context": pack.to_dict(),
        "llm_may_decide_correctness": False,
        "authority_kind": "objective_answer_key_candidate",
        "status": "candidate_unverified",
        "not_production_grade": True,
        "writeback_performed": False,
    }
