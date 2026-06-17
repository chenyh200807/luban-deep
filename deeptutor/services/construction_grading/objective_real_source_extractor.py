"""Objective real-source answer-key extractor (M25-C, fat skill).

READ-ONLY extraction of a real objective answer-key seed from the tracked exam-quality fixture
(``deeptutor/services/benchmark/fixtures/exam_quality_bank.json`` — 一级建造师《建筑实务》历史真题
2023-2025; ``answer_authority = exact_question.correct_answer 字母为唯一权威``; provenance = public
past exam papers, eval ground-truth, non-PII).

Authority rules (hard):
  * ``correct_answer`` letter(s) are the ONLY scoring authority; no LLM, no RAG chunk, no model/council
    vote may become an answer_key.
  * Status is ``real_source_candidate`` (NOT release): a single eval fixture with one blocked year
    (2024) is real-source-backed but not a signed production question-bank registry.
  * official_answer is a seed; bundle is never ``published`` / release authority.
  * Adversarial gates reject malformed key / answer-not-in-options / multi-select invalid, and queue
    duplicate-stem-different-key and same-id-different-options conflicts. Never guesses.

Deterministic gate (hash / schema / signing / conflict / rollback) lives here; the fixture is the
source. Clean-checkout safe (reads a tracked fixture, no gitignored dependency).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.objective_answer_key_compiler import (
    _canonical,
    _normalize_answer_key,
    _sha,
)
from deeptutor.services.construction_grading.normalization import normalize_options

_REPO = Path(__file__).resolve().parents[3]
SOURCE = _REPO / "deeptutor" / "services" / "benchmark" / "fixtures" / "exam_quality_bank.json"
_V2_DIR = (
    _REPO / "deeptutor" / "services" / "construction_grading"
    / "runtime_supply" / "v2_objective_real_candidate"
)

SCHEMA_VERSION = "luban_objective_answer_key.v2_real_candidate"
NAMESPACE = "objective_answer_key_real"
STATUS = "real_source_candidate"


def _option_keys(options: dict[str, str]) -> set[str]:
    return {str(k).strip().upper() for k in options.keys()}


def extract(source: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Read-only extraction. Returns {candidates, rejected, conflicts}. Never raises on bad rows."""
    src = source or SOURCE
    payload = json.loads(src.read_text("utf-8")) if src.exists() else {}
    provenance = str(payload.get("provenance") or "")
    source_label = str(payload.get("source") or "")
    questions = payload.get("questions") or []

    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_qid_options: dict[str, str] = {}
    seen_stem_key: dict[str, str] = {}

    for q in questions:
        qid = str(q.get("question_id") or "").strip()
        year = str(q.get("year") or "").strip()
        qtype = str(q.get("type") or "").strip()
        eq = q.get("exact_question") if isinstance(q.get("exact_question"), dict) else {}
        options = normalize_options(eq.get("options"))
        raw_key = str(eq.get("correct_answer") or "").strip()
        stem = str(eq.get("stem") or "").strip()

        if not qid or not raw_key or not options:
            rejected.append({"question_id": qid, "reason": "missing_id_key_or_options"})
            continue

        answer_letters = {c for c in raw_key.upper() if c.isalpha()}
        if not answer_letters or not answer_letters.issubset(_option_keys(options)):
            rejected.append({"question_id": qid, "reason": "answer_not_in_options", "raw_key": raw_key})
            continue
        if qtype == "single_choice" and len(answer_letters) != 1:
            rejected.append({"question_id": qid, "reason": "single_choice_multi_answer", "raw_key": raw_key})
            continue
        if qtype == "multiple_choice" and len(answer_letters) < 1:
            rejected.append({"question_id": qid, "reason": "multi_choice_empty", "raw_key": raw_key})
            continue

        answer_key = _normalize_answer_key(qtype, raw_key)
        options_hash = _sha(_canonical(options))
        stem_hash = _sha(stem)

        # conflict gates
        if qid in seen_qid_options and seen_qid_options[qid] != options_hash:
            conflicts.append({"question_id": qid, "reason": "same_id_different_options"})
            continue
        if stem_hash in seen_stem_key and seen_stem_key[stem_hash] != answer_key:
            conflicts.append({"question_id": qid, "reason": "duplicate_stem_different_key", "stem_hash": stem_hash})
            continue
        seen_qid_options[qid] = options_hash
        seen_stem_key[stem_hash] = answer_key

        candidates.append({
            "question_id": qid,
            "year": year,
            "paper": "",
            "section": "",
            "question_type": qtype,
            "options": options,
            "official_answer": raw_key,
            "answer_key": answer_key,
            "stem_hash": stem_hash,
            "options_hash": options_hash,
            "answer_key_hash": _sha(answer_key),
            "source_ref": {
                "kind": "public_exam_paper",
                "source": source_label,
                "fixture": "deeptutor/services/benchmark/fixtures/exam_quality_bank.json",
                "year": year,
            },
            "provenance": provenance,
        })

    return {"candidates": candidates, "rejected": rejected, "conflicts": conflicts}


def build_real_candidate_bundle(source: Path | None = None) -> dict[str, Any]:
    """Build a self-sealed real-source-candidate bundle (status=real_source_candidate)."""
    src = source or SOURCE
    extracted = extract(src)
    records = sorted(extracted["candidates"], key=lambda r: r["question_id"])
    content_hash = _sha(_canonical(records))
    source_hash = _sha(src.read_bytes().decode("utf-8")) if src.exists() else ""
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "status": STATUS,  # real_source_candidate (NOT release; single eval fixture, 2024 blocked)
        "release_authority": None,
        "published": False,
        "official_answer_role": "seed_from_public_exam_papers",
        "count": len(records),
        "rejected_count": len(extracted["rejected"]),
        "conflict_count": len(extracted["conflicts"]),
        "content_hash": content_hash,
        "source_hashes": {"exam_quality_bank.json": source_hash},
        "signature": _sha(content_hash + "|" + NAMESPACE + "|" + STATUS),
        "separate_from_case_registry": True,
        "rollback_pointer": "legacy (bundle missing / hash mismatch -> fail-closed; objective lane absent)",
    }
    return {"manifest": manifest, "records": records,
            "rejected": extracted["rejected"], "conflicts": extracted["conflicts"]}


def verify_real_bundle(bundle: dict[str, Any]) -> bool:
    """Fail-closed: recompute content_hash over records AND signature over (hash|namespace|status)."""
    manifest = bundle.get("manifest") or {}
    records = bundle.get("records") or []
    recomputed = _sha(_canonical(records))
    if recomputed != manifest.get("content_hash"):
        return False
    expected_sig = _sha(recomputed + "|" + NAMESPACE + "|" + str(manifest.get("status")))
    return expected_sig == manifest.get("signature")


def write_tracked_seed(bundle: dict[str, Any] | None = None) -> tuple[Path, Path]:
    """Persist the minimal tracked seed + manifest under runtime_supply/v2_objective_real_candidate."""
    b = bundle or build_real_candidate_bundle()
    _V2_DIR.mkdir(parents=True, exist_ok=True)
    seed_path = _V2_DIR / "objective_answer_key_seed_real.jsonl"
    manifest_path = _V2_DIR / "runtime_supply_v2_manifest.json"
    seed_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in b["records"]), "utf-8"
    )
    manifest_path.write_text(json.dumps(b["manifest"], ensure_ascii=False, indent=2) + "\n", "utf-8")
    return seed_path, manifest_path
