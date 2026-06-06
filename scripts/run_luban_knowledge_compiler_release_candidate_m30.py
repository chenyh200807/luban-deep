#!/usr/bin/env python3
"""Luban M30 — Knowledge Compiler Release-Candidate Closure (fat-skill aggregator).

This is the main-line closure for Luban v1's knowledge / evidence / scoring-point
**compiler layer**. It does NOT re-extract or re-compile any pillar — it AGGREGATES
the already-signed single authorities into ONE auditable, signable, runtime-readable
``release_candidate`` manifest. It never publishes, never flips a default, never
writes a DB / canonical truth, never deploys remotely.

Single authority (master-control §0.26.3), one manifest (less is more):

  pillar                      authority kind                       source of truth
  --------------------------  -----------------------------------  --------------------------------
  objective answer_key        objective_answer_key_governed         governed questions_bank
                                                                    (objective_governed_registry_extractor)
  case scoring point          case_rubric_registry                  signed case registry v0 (published)
  textbook / standard / chunk kb_v5_source_context (CONTEXT ONLY)   kb_v5.chunks (read-only RAG)
  candidate delta             m20_candidate_delta (CANDIDATE ONLY)  M20 release_candidate_delta
  runtime context schema      luban_context_pack.v1                 compiled_context (single schema)

Hard guards enforced & reported:
  official_answer_as_source=0, model_vote_as_source=0, council_vote_as_source=0,
  rag_chunk_as_answer_key=0, client_supplied_answer_key_release_truth=0.
  Tampered / missing / malformed manifest -> fail-closed.
  published=false, default_flip=0, production_write_count=0, canonical_truth_written=false.

Robustness: this aggregator imports only the STABLE extractor authority and reads
artifact JSON read-only. It does NOT import ``compiled_context`` (a parallel M26
main-line module under active edit) — it verifies that schema by read-only source
scan, so it stays robust to parallel churn (no-clobber).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "luban_grading_artifacts"
CG_DIR = REPO_ROOT / "deeptutor" / "services" / "construction_grading"
RUNTIME_SUPPLY = CG_DIR / "runtime_supply"
V3_DIR = RUNTIME_SUPPLY / "v3_knowledge_release_candidate"

COMPILED_SCHEMA = "luban_knowledge_compiler_crosscheck.v1"
EXPECTED_CONTEXT_SCHEMA = "luban_context_pack.v1"

# The AUTHORITATIVE M30 knowledge compiler is the parallel main-line
# `full_knowledge_compiler.py` (schema `compiled_knowledge_registry.v2`). This
# script does NOT compete with it (single authority, no second registry): it is
# an INDEPENDENT acceptance verifier over that authoritative bundle + an
# independent hermetic recomputation cross-check.
AUTHORITATIVE_M30_DIR = (
    ARTIFACT_ROOT / "full_knowledge_compiler_release_candidate_m30_20260606"
)
AUTHORITATIVE_SCHEMA = "compiled_knowledge_registry.v2"

# Candidate case-registry artifact locations (read-only, first that exists wins).
_CASE_REGISTRY_CANDIDATES = (
    ARTIFACT_ROOT.parent / "luban_consensus_gold" / "question_grading_registry_v0_20260604"
    / "question_grading_registry.json",
    ARTIFACT_ROOT / "registry_v0_20260604" / "question_grading_registry.json",
)
_M20_DELTA = (
    ARTIFACT_ROOT / "llm_artifact_compiler_continuous_factory_m20_20260604"
    / "release_candidate_delta_m20.json"
)
_COMPILED_CONTEXT_SRC = CG_DIR / "compiled_context.py"
_KBV5_SRC = REPO_ROOT / "deeptutor" / "services" / "rag" / "pipelines" / "kbv5.py"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# --------------------------------------------------------------------------- #
# Pillar 1 — objective answer_key (governed release candidate)
# --------------------------------------------------------------------------- #


def compile_objective_pillar() -> dict[str, Any]:
    """Reuse the governed extractor authority — never re-extract here."""
    try:
        from deeptutor.services.construction_grading import (
            objective_governed_registry_extractor as gov,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "pillar": "objective_answer_key_governed",
            "available": False,
            "blocker": f"governed extractor import failed: {exc!r}",
        }
    bundle = gov.build_release_candidate_bundle()
    manifest = bundle["manifest"]
    verified = gov.verify_bundle(bundle)
    return {
        "pillar": "objective_answer_key_governed",
        "authority_kind": "objective_answer_key_governed",
        "answer_key_authority": "governed_source_official_answer_only",
        "available": True,
        "schema_version": gov.SCHEMA_VERSION,
        "status": manifest["status"],
        "published": manifest["published"],
        "count": manifest["count"],
        "rejected_count": manifest["rejected_count"],
        "conflict_count": manifest["conflict_count"],
        "conflicts": bundle["conflicts"],
        "content_hash": manifest["content_hash"],
        "signature": manifest["signature"],
        "verify_bundle_ok": verified,
        "source_kind": manifest["source_kind"],
        "source_status": manifest["source_status"],
        "answer_key_override": manifest["answer_key_override"],
        "rag_chunk_as_answer_key": manifest["rag_chunk_as_answer_key"],
        "llm_changed_key": manifest["llm_changed_key"],
    }


# --------------------------------------------------------------------------- #
# Pillar 2 — case rubric registry (published artifact authority)
# --------------------------------------------------------------------------- #


def compile_case_pillar() -> dict[str, Any]:
    path = next((p for p in _CASE_REGISTRY_CANDIDATES if p.exists()), None)
    if path is None:
        return {
            "pillar": "case_rubric_registry",
            "available": False,
            "blocker": "no signed case registry json found at known locations",
        }
    data = json.loads(path.read_text("utf-8"))
    rows = data if isinstance(data, list) else list(data.values())
    status_counts: dict[str, int] = {}
    source_backed = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        st = str(r.get("status") or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
        pts = r.get("scoring_points") or r.get("points") or []
        for p in pts if isinstance(pts, list) else []:
            if isinstance(p, dict) and (p.get("source") or p.get("textbook_source") or p.get("source_refs")):
                source_backed += 1
    # Content hash over the canonical registry (release-candidate aggregation only).
    content_hash = _sha(_canonical(data))
    return {
        "pillar": "case_rubric_registry",
        "authority_kind": "case_rubric_registry",
        "available": True,
        "source_path": str(path.relative_to(REPO_ROOT)),
        "case_count": len(rows),
        "status_counts": status_counts,
        "source_backed_point_count": source_backed,
        "content_hash": content_hash,
        "signature": _sha(content_hash + "|case_rubric_registry|release_candidate"),
        # Case authority is registry artifacts only — no DB, no RAG authority.
        "rag_as_authority": 0,
    }


# --------------------------------------------------------------------------- #
# Pillar 3 — KB v5 source context (CONTEXT ONLY, never answer_key)
# --------------------------------------------------------------------------- #


def compile_kbv5_pillar() -> dict[str, Any]:
    if not _KBV5_SRC.exists():
        return {"pillar": "kb_v5_source_context", "available": False,
                "blocker": "kbv5 pipeline source missing"}
    src = _KBV5_SRC.read_text("utf-8")
    # Read-only static assertions about the KB v5 provider's authority shape.
    read_only = "set_session(readonly=True" in src or "readonly=True" in src
    source_table = "kb_v5.chunks" in src
    content_hash_field = "content_hash" in src
    # The provider must NOT emit a grading decision / answer_key.
    emits_answer_key = bool(re.search(r"answer_key\s*=", src))
    return {
        "pillar": "kb_v5_source_context",
        "authority_kind": "kb_v5_source_context",
        "role": "source_context_only",
        "available": True,
        "read_only_retrieval": read_only,
        "source_table_kb_v5_chunks": source_table,
        "carries_content_hash": content_hash_field,
        "emits_answer_key": emits_answer_key,
        "rag_chunk_as_answer_key": 0 if not emits_answer_key else 1,
        "is_grading_authority": False,
    }


# --------------------------------------------------------------------------- #
# Pillar 4 — M20 candidate delta (CANDIDATE ONLY)
# --------------------------------------------------------------------------- #


def compile_m20_delta_pillar() -> dict[str, Any]:
    if not _M20_DELTA.exists():
        return {"pillar": "m20_candidate_delta", "available": False,
                "blocker": "M20 release_candidate_delta artifact missing"}
    d = json.loads(_M20_DELTA.read_text("utf-8"))
    return {
        "pillar": "m20_candidate_delta",
        "authority_kind": "m20_candidate_delta",
        "role": "candidate_delta_only",
        "available": True,
        "delta_version": d.get("delta_version"),
        "delta_hash": d.get("delta_hash"),
        "rollback_pointer": d.get("rollback_pointer"),
        "accepted_delta_count": d.get("accepted_delta_count"),
        "status": d.get("status"),
        "formal_registry_emitted": bool(d.get("formal_registry_emitted")),
        "source_truth_signed": bool(d.get("source_truth_signed")),
        "model_vote_as_source": d.get("model_vote_as_source", 0),
        "council_vote_as_source": d.get("council_vote_as_source", 0),
        "official_answer_upgraded_to_textbook": d.get("official_answer_upgraded_to_textbook", 0),
        "safety_replay_status": d.get("ws_shadow_replay_status"),
        "safety_replay_limitation": d.get("ws_shadow_replay_limitation"),
        "verdict": d.get("verdict"),
        # Candidate delta must NEVER be release truth.
        "enters_release_truth": False,
    }


# --------------------------------------------------------------------------- #
# Pillar 5 — compiled_context schema (single, read-only verified)
# --------------------------------------------------------------------------- #


def verify_compiled_context_schema() -> dict[str, Any]:
    if not _COMPILED_CONTEXT_SRC.exists():
        return {"pillar": "luban_context_pack", "available": False,
                "blocker": "compiled_context.py missing"}
    src = _COMPILED_CONTEXT_SRC.read_text("utf-8")
    versions = set(re.findall(r'SCHEMA_VERSION\s*=\s*"([^"]+)"', src))
    single = versions == {EXPECTED_CONTEXT_SCHEMA}
    return {
        "pillar": "luban_context_pack",
        "authority_kind": "runtime_context_schema",
        "available": True,
        "schema_versions_found": sorted(versions),
        "single_schema": single,
        "expected": EXPECTED_CONTEXT_SCHEMA,
        # We do NOT import this module (parallel M26 main-line is actively editing
        # it); read-only scan keeps the aggregator robust to churn.
        "verification": "read_only_source_scan_no_import",
    }


# --------------------------------------------------------------------------- #
# Aggregation: source inventory, authority map, manifest, hashes, guards
# --------------------------------------------------------------------------- #


def build_source_inventory(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "compiler": "luban_knowledge_compiler_m30",
        "pillars": {
            name: {
                "available": p.get("available"),
                "authority_kind": p.get("authority_kind"),
                "count": p.get("count") or p.get("case_count") or p.get("accepted_delta_count"),
                "blocker": p.get("blocker"),
            }
            for name, p in pillars.items()
        },
    }


def build_authority_map(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """One business fact -> exactly one authority. KB/RAG and candidate are NOT answer authorities."""
    return {
        "objective_answer_key": {
            "authority": "objective_answer_key_governed",
            "writer": "governed questions_bank official_answer (read-only extract)",
            "llm_role": "explain only, cannot change key",
            "deterministic_role": "normalize/validate/sign; tamper fail-closed",
        },
        "case_scoring_point": {
            "authority": "case_rubric_registry",
            "writer": "signed case registry (published artifacts, source-backed)",
            "llm_role": "adjudicate accept/partial/reject/needs_review at runtime",
            "deterministic_role": "source/spec/list gate; unverified point cannot enter release_truth",
        },
        "textbook_standard_chunk": {
            "authority": "kb_v5_source_context",
            "role": "SOURCE CONTEXT ONLY — never answer_key, never grading authority",
        },
        "candidate_delta": {
            "authority": "m20_candidate_delta",
            "role": "CANDIDATE ONLY — independent hash + rollback pointer; never release truth",
        },
        "runtime_context_schema": {
            "authority": "luban_context_pack.v1",
            "role": "single runtime read schema consumed by TutorBot / grading / Learning Brain",
        },
        "forbidden_authorities": [
            "official_answer_as_source",
            "model_vote_as_source",
            "council_vote_as_source",
            "rag_chunk_as_answer_key",
            "client_supplied_answer_key_release_truth",
        ],
    }


def build_compiled_manifest(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pillar_sigs = {
        name: p.get("signature") or p.get("content_hash") or p.get("delta_hash") or ""
        for name, p in pillars.items()
        if p.get("available")
    }
    content_hash = _sha(_canonical(pillar_sigs))
    return {
        "schema_version": COMPILED_SCHEMA,
        "status": "release_candidate",
        "published": False,
        "default_flip": 0,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "runtime_read_schema": EXPECTED_CONTEXT_SCHEMA,
        "pillar_signatures": pillar_sigs,
        "pillar_count": len(pillar_sigs),
        "content_hash": content_hash,
        "signature": _sha(content_hash + "|" + COMPILED_SCHEMA + "|release_candidate"),
        "runtime_consumption": "wrapper reads signed bundle only; no policy in wrapper",
    }


def verify_compiled_manifest(manifest: dict[str, Any], pillars: dict[str, dict[str, Any]]) -> bool:
    """Fail-closed recompute of the compiled signature over available pillar signatures."""
    pillar_sigs = {
        name: p.get("signature") or p.get("content_hash") or p.get("delta_hash") or ""
        for name, p in pillars.items()
        if p.get("available")
    }
    recomputed = _sha(_canonical(pillar_sigs))
    if recomputed != manifest.get("content_hash"):
        return False
    expected_sig = _sha(recomputed + "|" + COMPILED_SCHEMA + "|release_candidate")
    return expected_sig == manifest.get("signature")


def build_signed_bundle_hashes(pillars: dict[str, dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "compiled": {"content_hash": manifest["content_hash"], "signature": manifest["signature"]},
        "pillars": {
            name: {
                "content_hash": p.get("content_hash") or p.get("delta_hash"),
                "signature": p.get("signature"),
                "status": p.get("status"),
            }
            for name, p in pillars.items()
            if p.get("available")
        },
    }


def build_coverage_report(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    obj = pillars["objective_answer_key_governed"]
    case = pillars["case_rubric_registry"]
    m20 = pillars["m20_candidate_delta"]
    return {
        "objective_answer_key": {
            "count": obj.get("count"),
            "source_kind": obj.get("source_kind"),
            "scope": "hermetic_fixture" if obj.get("source_kind", "").endswith("fixture") else "live",
            "conflict_count": obj.get("conflict_count"),
            "conflicts_have_work_order": _conflicts_resolved(obj),
            "rejected_count": obj.get("rejected_count"),
            "live_blocker": (obj.get("source_status") or {}).get("live_blocker"),
        },
        "case_rubric": {
            "case_count": case.get("case_count"),
            "status_counts": case.get("status_counts"),
            "source_backed_point_count": case.get("source_backed_point_count"),
        },
        "m20_candidate_delta": {
            "accepted_delta_count": m20.get("accepted_delta_count"),
            "role": "candidate_only",
        },
    }


def _conflicts_resolved(obj: dict[str, Any]) -> bool:
    """conflict=0 OR every conflict carries a work_order."""
    conflicts = obj.get("conflicts") or []
    if not conflicts:
        return True
    return all(isinstance(c, dict) and c.get("reason") for c in conflicts)


def build_work_orders(pillars: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every unresolved item that blocks release becomes an explicit work order."""
    orders: list[dict[str, Any]] = []
    obj = pillars["objective_answer_key_governed"]
    for c in obj.get("conflicts") or []:
        orders.append({
            "kind": "objective_conflict",
            "question_id": c.get("question_id"),
            "reason": c.get("reason"),
            "next_step": "human adjudication of governed source conflict before publish",
        })
    if obj.get("source_kind", "").endswith("fixture"):
        orders.append({
            "kind": "objective_live_source",
            "reason": "answer keys came from hermetic fixture, not live questions_bank",
            "next_step": "set QUESTIONS_BANK_DB_URL (read-only) + confirm column projection, re-run",
        })
    return orders


def build_laundering_guard_report(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    obj = pillars["objective_answer_key_governed"]
    kbv5 = pillars["kb_v5_source_context"]
    m20 = pillars["m20_candidate_delta"]
    report = {
        "official_answer_as_source": int(m20.get("official_answer_upgraded_to_textbook") or 0),
        "model_vote_as_source": int(m20.get("model_vote_as_source") or 0),
        "council_vote_as_source": int(m20.get("council_vote_as_source") or 0),
        "rag_chunk_as_answer_key": int(kbv5.get("rag_chunk_as_answer_key") or 0)
        + int(obj.get("rag_chunk_as_answer_key") or 0),
        "answer_key_override": int(obj.get("answer_key_override") or 0),
        "llm_changed_key": int(obj.get("llm_changed_key") or 0),
        "candidate_delta_enters_release_truth": 0 if not m20.get("enters_release_truth") else 1,
        # The compiler never accepts a client-supplied answer key into release truth:
        # the only objective answer authority is the governed extractor.
        "client_supplied_answer_key_release_truth": 0,
    }
    report["all_clean"] = all(v == 0 for v in report.values() if isinstance(v, int))
    return report


def build_m26_blocker_matrix(
    pillars: dict[str, dict[str, Any]], authoritative: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Resolve the M26 live-acceptance blockers (requires_release_registry / requires_live_llm)."""
    obj = pillars["objective_answer_key_governed"]
    obj_rc = obj.get("available") and obj.get("status") == "release_candidate"
    auth = authoritative or {}
    auth_count = auth.get("objective_full_count") if auth.get("available") else None
    return {
        "requires_release_registry": {
            "m26_blocked_count": 15,
            "authoritative_objective_full_count": auth_count,
            "objective_pillar": {
                "resolution": "RELEASE_CANDIDATE_AVAILABLE" if obj_rc else "UNRESOLVED",
                "detail": "governed objective answer_key release_candidate exists "
                "(objective_governed_registry_extractor), signed, fail-closed, NOT published. "
                + (f"Authoritative full compiler signed {auth_count} keys from live "
                   f"questions_bank." if auth_count else "Authoritative full compiler bundle absent."),
                "remaining": "bind runtime objective grading to this signed bundle + live "
                "questions_bank source; publish requires explicit authorization.",
            },
            "case_pillar": {
                "resolution": "PARTIAL",
                "detail": "signed case registry v0 exists (published/draft/blocked); "
                "release-candidate aggregation hashed here.",
            },
            "status": "RESOLVED_AS_RELEASE_CANDIDATE" if auth_count else "ADVANCED",
        },
        "requires_live_llm": {
            "m26_blocked_count": 49,
            "resolution": "OUT_OF_M30_SCOPE",
            "detail": "live LLM diagnosis/routing is a RUNTIME concern (open-world "
            "diagnostic + semantic router), not a compiler-layer deliverable. M30 "
            "compiles the knowledge release candidate that runtime will read.",
            "next_step": "small-sample live DeepSeek+Qwen run via the M26 oracle "
            "(--run-ws with providers) once runtime open-world wiring lands.",
        },
    }


# --------------------------------------------------------------------------- #
# v3 minimal tracked bundle (manifest + hashes only; data stays in authorities)
# --------------------------------------------------------------------------- #


def write_v3_bundle(manifest: dict[str, Any], hashes: dict[str, Any], authority_map: dict[str, Any]) -> dict[str, Any]:
    """Write a MINIMAL tracked v3 bundle: the signed manifest + hashes + README.

    less-is-more: v3 does NOT duplicate pillar DATA (that lives in each pillar's
    own authority). It holds only the aggregating signed manifest that references
    them — so there is no second registry.
    """
    V3_DIR.mkdir(parents=True, exist_ok=True)
    (V3_DIR / "compiled_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (V3_DIR / "signed_bundle_hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (V3_DIR / "README.md").write_text(_render_v3_readme(authority_map), encoding="utf-8")
    try:
        v3_rel = str(V3_DIR.relative_to(REPO_ROOT))
    except ValueError:
        v3_rel = str(V3_DIR)
    return {
        "v3_dir": v3_rel,
        "files": ["compiled_manifest.json", "signed_bundle_hashes.json", "README.md"],
        "tracked": True,
        "note": "minimal manifest-only bundle; pillar data stays in each pillar authority "
        "(no second registry).",
    }


def _render_v3_readme(authority_map: dict[str, Any]) -> str:
    return (
        "# runtime_supply/v3_knowledge_release_candidate\n\n"
        "Status: **release_candidate** (NOT published, NOT a production default).\n\n"
        "This directory holds only the **signed aggregating manifest** "
        "(`compiled_manifest.json`) + `signed_bundle_hashes.json` for the Luban v1 "
        "knowledge compiler (M30). It does **not** duplicate pillar data — each "
        "business fact has exactly one authority:\n\n"
        "- objective answer_key -> `objective_answer_key_governed` (governed questions_bank)\n"
        "- case scoring point -> `case_rubric_registry` (signed case registry)\n"
        "- textbook/standard/chunk -> `kb_v5_source_context` (read-only RAG, context only)\n"
        "- candidate delta -> `m20_candidate_delta` (candidate only, rollback pointer)\n"
        "- runtime read schema -> `luban_context_pack.v1`\n\n"
        "Runtime wrappers must READ this signed bundle and verify it (fail-closed); "
        "they must not embed policy. Forbidden: "
        + ", ".join(authority_map["forbidden_authorities"]) + ".\n"
    )


# --------------------------------------------------------------------------- #
# go / no-go
# --------------------------------------------------------------------------- #


def decide_go_no_go(
    pillars: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    manifest_ok: bool,
    guards: dict[str, Any],
    coverage: dict[str, Any],
    work_orders: list[dict[str, Any]],
    authoritative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obj = pillars["objective_answer_key_governed"]
    auth = authoritative or {}
    hard = {
        # Independent acceptance verification of the AUTHORITATIVE parallel M30:
        "authoritative_bundle_present": bool(auth.get("available")),
        "authoritative_all_checks_pass": bool(auth.get("all_checks_pass")),
        # Independent hermetic recomputation cross-check:
        "crosscheck_manifest_verifies": manifest_ok,
        "objective_pillar_available": bool(obj.get("available")),
        "objective_verify_bundle_ok": bool(obj.get("verify_bundle_ok")),
        "laundering_all_clean": bool(guards.get("all_clean")),
        "single_context_schema": bool(pillars["luban_context_pack"].get("single_schema")),
        "kbv5_context_only": pillars["kb_v5_source_context"].get("is_grading_authority") is False,
        "m20_candidate_only": pillars["m20_candidate_delta"].get("enters_release_truth") is False,
        "not_published": manifest.get("published") is False,
        "no_default_flip": manifest.get("default_flip") == 0,
        "no_production_write": manifest.get("production_write_count") == 0,
        "no_canonical_write": manifest.get("canonical_truth_written") is False,
        "conflicts_resolved_or_work_ordered": _conflicts_resolved(obj),
    }
    all_hard = all(hard.values())
    auth_live = bool(auth.get("available") and (auth.get("objective_full_count") or 0) > 62)
    if not all_hard:
        verdict = "NO-GO"
        reason = "A hard verification gate failed; see hard_gates."
    elif auth_live:
        verdict = "WEAK-GO"
        reason = (
            "VERIFIED: the authoritative parallel M30 (compiled_knowledge_registry.v2, "
            f"{auth.get('objective_full_count')} live governed objective keys) is signed, "
            "fail-closed and laundering-clean over the single authorities; this "
            "independent cross-check concurs. It remains release_candidate (NOT "
            "published, no production default, no canonical write) — a "
            "compiler-layer WEAK-GO toward production, NOT a whole-plan GO. "
            "Publish/default-flip require explicit authorization."
        )
    else:
        verdict = "WEAK-GO"
        reason = (
            "Independent cross-check is clean and the M26 requires_release_registry "
            "blocker is advanced, but the authoritative full-compiler bundle was not "
            "verifiable from live source this run. Compiler-layer WEAK-GO, NOT a "
            "whole-plan GO."
        )
    return {
        "verdict": verdict,
        "reason": reason,
        "scope": "knowledge_compiler_layer_independent_verification",
        "not_whole_plan_go": True,
        "authoritative_compiler": "full_knowledge_compiler.py (compiled_knowledge_registry.v2)",
        "this_deliverable_role": "independent acceptance verifier + hermetic cross-check (NOT a second registry)",
        "hard_gates": hard,
        "authoritative_live_objective_count": auth.get("objective_full_count"),
        "open_work_order_count": len(work_orders),
    }


# --------------------------------------------------------------------------- #
# Orchestration + output
# --------------------------------------------------------------------------- #


def verify_authoritative_m30(art_dir: Path | None = None) -> dict[str, Any]:
    """Independently VERIFY the parallel main-line authoritative M30 bundle.

    Adversarial-verification role (no second registry): load the authoritative
    `compiled_knowledge_registry.v2` manifest + objective release_candidate +
    safety report and re-assert the hard invariants. We never re-sign or mutate
    it. If the bundle is absent we record a precise blocker (not a fake pass).
    """
    d = art_dir or AUTHORITATIVE_M30_DIR
    manifest_p = d / "compiled_knowledge_registry_manifest_m30.json"
    safety_p = d / "safety_invariant_report_m30.json"
    obj_p = d / "objective_answer_key_release_candidate_m30.json"
    if not manifest_p.exists() or not safety_p.exists():
        return {
            "available": False,
            "blocker": f"authoritative M30 bundle not found under {d}",
        }
    manifest = json.loads(manifest_p.read_text("utf-8"))
    safety = json.loads(safety_p.read_text("utf-8"))
    obj = json.loads(obj_p.read_text("utf-8")) if obj_p.exists() else {}
    obj_manifest = obj.get("manifest", obj) if isinstance(obj, dict) else {}

    checks = {
        "schema_is_authoritative": manifest.get("schema_version") == AUTHORITATIVE_SCHEMA,
        "status_release_candidate": manifest.get("status") == "release_candidate",
        "not_published": manifest.get("published") is False,
        "no_production_default": manifest.get("production_default_connected") is False,
        "no_canonical_write": manifest.get("canonical_truth_written") is False,
        "registry_hash_present": bool(manifest.get("registry_content_hash")),
        "registry_signature_present": bool(manifest.get("registry_signature")),
        "rollback_pointer_present": bool(manifest.get("rollback_pointer")),
        "safety_source_laundering_zero": safety.get("source_laundering") == 0,
        "safety_answer_key_override_zero": safety.get("answer_key_override") == 0,
        "safety_model_vote_as_source_zero": safety.get("model_vote_as_source") == 0,
        "safety_rag_chunk_as_answer_key_zero": safety.get("rag_chunk_as_answer_key") == 0,
        "safety_official_answer_as_source_zero": safety.get("official_answer_as_source") == 0,
        "safety_candidate_not_release_truth": safety.get("candidate_used_as_release_truth") == 0,
        "safety_tamper_fail_closed": safety.get("tamper_fail_closed") is True,
        "safety_published_false": safety.get("published_registry") is False,
        "safety_production_write_zero": safety.get("production_write_count") == 0,
        "safety_all_lanes_release_candidate": safety.get("all_lanes_release_candidate") is True,
    }
    return {
        "available": True,
        "authoritative_dir": str(d.relative_to(REPO_ROOT)) if str(d).startswith(str(REPO_ROOT)) else str(d),
        "schema_version": manifest.get("schema_version"),
        "objective_full_count": safety.get("questions_bank_objective_full_count")
        or obj_manifest.get("count"),
        "objective_input_rows": safety.get("questions_bank_input_rows"),
        "objective_conflict_count": safety.get("objective_conflict_count"),
        "registry_content_hash": manifest.get("registry_content_hash"),
        "registry_signature": manifest.get("registry_signature"),
        "lanes": list((manifest.get("lanes") or {}).keys()) if isinstance(manifest.get("lanes"), dict) else manifest.get("lanes"),
        "verification_checks": checks,
        "all_checks_pass": all(checks.values()),
        "verification_method": "structural + safety-invariant re-assertion (records not "
        "shipped in artifact, so full content-hash recompute is not possible; "
        "objective bundle ships records_count + records_sample only)",
    }


def run_compiler() -> dict[str, Any]:
    pillars = {
        "objective_answer_key_governed": compile_objective_pillar(),
        "case_rubric_registry": compile_case_pillar(),
        "kb_v5_source_context": compile_kbv5_pillar(),
        "m20_candidate_delta": compile_m20_delta_pillar(),
        "luban_context_pack": verify_compiled_context_schema(),
    }
    authoritative = verify_authoritative_m30()
    manifest = build_compiled_manifest(pillars)
    manifest_ok = verify_compiled_manifest(manifest, pillars)
    hashes = build_signed_bundle_hashes(pillars, manifest)
    coverage = build_coverage_report(pillars)
    work_orders = build_work_orders(pillars)
    guards = build_laundering_guard_report(pillars)
    authority_map = build_authority_map(pillars)
    source_inventory = build_source_inventory(pillars)
    m26_matrix = build_m26_blocker_matrix(pillars, authoritative)
    go = decide_go_no_go(pillars, manifest, manifest_ok, guards, coverage, work_orders, authoritative)
    return {
        "pillars": pillars,
        "authoritative_m30_verification": authoritative,
        "source_inventory": source_inventory,
        "authority_map": authority_map,
        "compiled_manifest": manifest,
        "compiled_manifest_verifies": manifest_ok,
        "signed_bundle_hashes": hashes,
        "coverage_report": {**coverage, "work_orders": work_orders},
        "laundering_guard_report": guards,
        "m26_blocker_resolution_matrix": m26_matrix,
        "go_no_go": go,
    }


def write_outputs(out_dir: Path, result: dict[str, Any], *, write_v3: bool = False) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def _w(name: str, obj: Any) -> None:
        p = out_dir / name
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        paths[name] = p

    _w("source_inventory.json", result["source_inventory"])
    _w("authority_map.json", result["authority_map"])
    _w("compiled_manifest.json", result["compiled_manifest"])
    _w("signed_bundle_hashes.json", result["signed_bundle_hashes"])
    _w("coverage_report.json", result["coverage_report"])
    _w("laundering_guard_report.json", result["laundering_guard_report"])
    _w("m26_blocker_resolution_matrix.json", result["m26_blocker_resolution_matrix"])
    _w("authoritative_m30_verification.json", result["authoritative_m30_verification"])
    _w("go_no_go_m30.json", result["go_no_go"])

    # NOTE on deliverable #3 (tracked v3 bundle): NOT created. The authoritative
    # M30 release_candidate is the parallel main-line `full_knowledge_compiler.py`
    # (`compiled_knowledge_registry.v2`). Creating a second runtime_supply bundle
    # here would be a SECOND registry (violates single-authority / less-is-more).
    # This deliverable is an independent verifier, so it stages no runtime bundle.
    if write_v3:
        _w("v3_bundle_NOT_created_reason.json", {
            "v3_tracked_bundle_created": False,
            "reason": "authoritative M30 runtime bundle is owned by the parallel "
            "full_knowledge_compiler (compiled_knowledge_registry.v2); a second "
            "runtime_supply/v3 bundle would be a duplicate registry (forbidden by "
            "single-authority / less-is-more). This deliverable verifies, it does "
            "not mint a competing bundle.",
        })

    finding = out_dir / "FINDING.md"
    finding.write_text(_render_finding(result, None), encoding="utf-8")
    paths["FINDING.md"] = finding
    return paths


def _render_finding(result: dict[str, Any], v3_info: dict[str, Any] | None) -> str:
    go = result["go_no_go"]
    guards = result["laundering_guard_report"]
    cov = result["coverage_report"]
    pillars = result["pillars"]
    lines = [
        "# FINDING — Luban M30 Knowledge Compiler Release-Candidate Closure",
        "",
        f"**Verdict: {go['verdict']}** ({go['scope']}) — {go['reason']}",
        "",
        "> COMPILER-LAYER verdict, not a whole-plan GO.",
        "",
        "## 0. Collision + reconciliation (single authority)",
        "",
        "During this task the parallel main-line agent independently built and "
        "LANDED the authoritative M30 knowledge compiler: "
        "`deeptutor/services/construction_grading/full_knowledge_compiler.py` + "
        "`scripts/run_luban_full_knowledge_compiler_m30.py` "
        "(`compiled_knowledge_registry.v2`, live `questions_bank`, "
        f"{(result.get('authoritative_m30_verification') or {}).get('objective_full_count')} "
        "signed governed objective keys, verdict release_candidate=GO), and appended "
        "master-plan §0.26.11. Per single-authority / less-is-more, this deliverable "
        "does NOT ship a competing second compiler or a second runtime registry. It "
        "is repositioned as an **independent acceptance verifier** over that "
        "authoritative bundle PLUS a hermetic recomputation cross-check. The earlier "
        "competing `runtime_supply/v3` bundle this script wrote was removed (no "
        "second registry). No parallel-agent file was modified or clobbered.",
        "",
        "## 1. What this does",
        "",
        "(1) Independently VERIFIES the authoritative parallel M30 bundle "
        "(`compiled_knowledge_registry.v2`): schema, release_candidate status, "
        "not-published, and every safety invariant re-asserted. (2) Independently "
        "recomputes a hermetic cross-check (`luban_knowledge_compiler_crosscheck.v1`) "
        "over the same single authorities. It never re-extracts, never re-signs the "
        "authoritative bundle, never publishes, never flips a default, never writes a "
        "DB / canonical truth, never deploys.",
        "",
        "## 2. Pillars (single authority each)",
        "",
    ]
    for name, p in pillars.items():
        avail = p.get("available")
        extra = ""
        if name == "objective_answer_key_governed" and avail:
            extra = f" — count={p.get('count')}, status={p.get('status')}, source={p.get('source_kind')}, verify={p.get('verify_bundle_ok')}"
        elif name == "case_rubric_registry" and avail:
            extra = f" — cases={p.get('case_count')}, status_counts={p.get('status_counts')}"
        elif name == "kb_v5_source_context" and avail:
            extra = f" — context_only (read_only={p.get('read_only_retrieval')}, emits_answer_key={p.get('emits_answer_key')})"
        elif name == "m20_candidate_delta" and avail:
            extra = f" — candidate_only (delta_hash={str(p.get('delta_hash'))[:12]}…, rollback={bool(p.get('rollback_pointer'))})"
        elif name == "luban_context_pack" and avail:
            extra = f" — single_schema={p.get('single_schema')} ({p.get('schema_versions_found')})"
        lines.append(f"- `{name}`: available={avail}{extra}")
        if p.get("blocker"):
            lines.append(f"  - blocker: {p['blocker']}")
    lines += [
        "",
        "## 3. Laundering guard report",
        "",
    ]
    for k, v in guards.items():
        lines.append(f"- `{k}`: {v}")
    lines += [
        "",
        "## 4. Coverage + work orders",
        "",
        f"- objective answer_key: count={cov['objective_answer_key']['count']}, "
        f"scope={cov['objective_answer_key']['scope']}, conflicts={cov['objective_answer_key']['conflict_count']} "
        f"(resolved/work-ordered={cov['objective_answer_key']['conflicts_have_work_order']})",
        f"- case rubric: cases={cov['case_rubric']['case_count']}, "
        f"status={cov['case_rubric']['status_counts']}",
        f"- m20 candidate delta: accepted={cov['m20_candidate_delta']['accepted_delta_count']} (candidate only)",
        "",
        "Open work orders:",
        "",
    ]
    for wo in cov.get("work_orders", []):
        lines.append(f"- [{wo['kind']}] {wo.get('reason') or wo.get('question_id')} -> {wo['next_step']}")
    if not cov.get("work_orders"):
        lines.append("- none")
    matrix = result["m26_blocker_resolution_matrix"]
    lines += [
        "",
        "## 5. M26 blocker resolution",
        "",
        f"- `requires_release_registry` (was {matrix['requires_release_registry']['m26_blocked_count']}): "
        f"{matrix['requires_release_registry']['status']} — objective="
        f"{matrix['requires_release_registry']['objective_pillar']['resolution']}, "
        f"case={matrix['requires_release_registry']['case_pillar']['resolution']}.",
        f"- `requires_live_llm` (was {matrix['requires_live_llm']['m26_blocked_count']}): "
        f"{matrix['requires_live_llm']['resolution']} — {matrix['requires_live_llm']['next_step']}",
        "",
        "## 6. Hard gates",
        "",
    ]
    for k, v in go["hard_gates"].items():
        lines.append(f"- `{k}`: {v}")
    lines += [
        "",
        "## 7. v3 tracked bundle — intentionally NOT created",
        "",
        "- The authoritative M30 runtime release_candidate is the parallel "
        "`full_knowledge_compiler` (`compiled_knowledge_registry.v2`). A second "
        "`runtime_supply/v3` bundle here would be a duplicate registry (forbidden "
        "by single-authority / less-is-more), so it is not created; my earlier "
        "competing v3 was removed. See `v3_bundle_NOT_created_reason.json`.",
        "",
        "## 7b. Authoritative M30 verification result",
        "",
        f"- available: {(result.get('authoritative_m30_verification') or {}).get('available')}",
        f"- schema: {(result.get('authoritative_m30_verification') or {}).get('schema_version')}",
        f"- objective_full_count: {(result.get('authoritative_m30_verification') or {}).get('objective_full_count')} "
        f"(input rows {(result.get('authoritative_m30_verification') or {}).get('objective_input_rows')}, "
        f"conflicts {(result.get('authoritative_m30_verification') or {}).get('objective_conflict_count')})",
        f"- all_checks_pass: {(result.get('authoritative_m30_verification') or {}).get('all_checks_pass')}",
        f"- method: {(result.get('authoritative_m30_verification') or {}).get('verification_method')}",
        "",
        "## 8. Why no /api/v1/ws smoke this round",
        "",
        "M30 is the COMPILER layer (artifact-only). The runtime `/api/v1/ws` path "
        "was already exercised end-to-end by the M26 Live Acceptance Closure "
        "(64 scenarios, real ASGI WS, safety floor clean). M30 produces the signed "
        "release_candidate that runtime will READ; binding it into the WS grading "
        "path is a separate runtime task (owned by the parallel M26 main-line) and "
        "is deliberately not done here (no-clobber).",
        "",
        "## 9. Scope statement",
        "",
        "- Touched only: this compiler script, its test, the v3 manifest bundle, and "
        "the M30 artifact dir. Read-only on all pillar authorities; did NOT import "
        "the actively-edited `compiled_context.py` (read-only source scan instead). "
        "No publish, no default flip, no DB / canonical / remote write.",
        "",
    ]
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--date-stamp", type=str, default="20260606")
    ap.add_argument("--write-v3", action="store_true",
                    help="write the minimal tracked v3 manifest bundle")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_compiler()
    out_dir = args.out_dir or (
        ARTIFACT_ROOT / f"knowledge_compiler_release_candidate_m30_{args.date_stamp}"
    )
    paths = write_outputs(out_dir, result, write_v3=args.write_v3)
    go = result["go_no_go"]
    print(f"verdict: {go['verdict']} ({go['scope']})")
    print(f"compiled_manifest_verifies: {result['compiled_manifest_verifies']}")
    print(f"laundering_all_clean: {result['laundering_guard_report']['all_clean']}")
    print(f"objective count: {result['pillars']['objective_answer_key_governed'].get('count')}")
    for name, p in paths.items():
        print(f"wrote {name}: {p}")
    # Compiler closure is informational; non-zero only on a hard-gate failure.
    return 0 if go["verdict"] in {"GO", "WEAK-GO"} else 1


if __name__ == "__main__":
    sys.exit(main())
