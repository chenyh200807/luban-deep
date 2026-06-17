"""Objective Answer-Key Compiler (M25-A, fat skill).

Compiles single-choice / multiple-choice / true-false seed rows into a SIGNED,
deterministic objective answer-key bundle whose namespace is SEPARATE from the case
rubric registry (master plan §0.25.3 / §0.25.4 red line: no shared mutable registry).

Authority rules (hard):
  * The compiled ``answer_key`` is the ONLY grading authority for the objective lane.
  * ``official_answer`` is a SEED only — it never makes a row ``release``; release needs
    question-bank authority + source provenance (not available for synthetic/seed input),
    so compiled rows stay ``status="candidate"``.
  * No LLM is called here; no model/council/official-answer is treated as a textbook source.
  * Load is fail-closed: a tampered bundle fails ``verify_objective_bundle``.

This module is policy (fat skill). Wrappers only route/flag/append.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.normalization import (
    normalize_choice_letters,
    normalize_options,
)

_REPO = Path(__file__).resolve().parents[3]
_SEED = (
    _REPO
    / "deeptutor"
    / "services"
    / "construction_grading"
    / "runtime_supply"
    / "v2_objective_candidate"
    / "objective_answer_key_seed.jsonl"
)

SCHEMA_VERSION = "luban_objective_answer_key.v2_candidate"
NAMESPACE = "objective_answer_key"

_TRUE_TOKENS = ("对", "正确", "true", "t", "yes", "y", "√", "1")
_FALSE_TOKENS = ("错", "错误", "false", "f", "no", "n", "×", "0")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_answer_key(question_type: str, raw: Any) -> str:
    """Order-independent canonical answer key. true_false -> 'T'/'F'; choice -> sorted letters."""
    qt = (question_type or "").strip().lower()
    value = str(raw or "").strip()
    if qt in ("true_false", "judge", "judgement", "judgment", "tf"):
        low = value.lower()
        if low in _TRUE_TOKENS:
            return "T"
        if low in _FALSE_TOKENS:
            return "F"
        return ""
    # single / multiple choice: normalize to sorted unique letters (order-independent)
    letters = normalize_choice_letters(value)
    return "".join(sorted(set(letters)))


def compile_objective_answer_key_row(seed: dict[str, Any]) -> dict[str, Any]:
    """Compile ONE objective seed row into a signed candidate answer-key record."""
    question_id = str(seed.get("question_id") or seed.get("id") or "").strip()
    question_type = str(seed.get("question_type") or "").strip()
    stem = str(seed.get("stem") or "").strip()
    options = normalize_options(seed.get("options"))
    answer_key = _normalize_answer_key(question_type, seed.get("official_answer"))
    source_refs = list(seed.get("source_refs") or [])
    record = {
        "question_id": question_id,
        "question_type": question_type,
        "answer_key": answer_key,
        "option_metadata": options,
        "source_refs": source_refs,
        "stem_hash": _sha(stem),
        "options_hash": _sha(_canonical(options)),
        "answer_key_hash": _sha(answer_key),
        # official_answer is only a seed; never auto-promote to release authority.
        "status": "candidate",
        "provenance": str(seed.get("provenance") or "official_answer_seed"),
        "synthetic_example": bool(seed.get("synthetic_example", False)),
    }
    return record


def compile_objective_answer_keys(seed_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile seed rows -> a deterministic, self-sealed candidate bundle."""
    records = [compile_objective_answer_key_row(r) for r in seed_rows if (r.get("question_id") or r.get("id"))]
    records.sort(key=lambda r: r["question_id"])
    content_hash = _sha(_canonical(records))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "status": "candidate",
        "release_authority": None,  # release needs question-bank authority + provenance (absent here)
        "count": len(records),
        "content_hash": content_hash,
        "signature": _sha(content_hash + "|" + NAMESPACE + "|" + SCHEMA_VERSION),
        "separate_from_case_registry": True,
        "official_answer_role": "seed_only",
    }
    return {"manifest": manifest, "records": records}


def verify_objective_bundle(bundle: dict[str, Any]) -> bool:
    """Fail-closed integrity check: recompute content_hash + signature over records."""
    manifest = bundle.get("manifest") or {}
    records = bundle.get("records") or []
    recomputed = _sha(_canonical(records))
    if recomputed != manifest.get("content_hash"):
        return False
    expected_sig = _sha(recomputed + "|" + NAMESPACE + "|" + SCHEMA_VERSION)
    return expected_sig == manifest.get("signature")


def load_objective_seed(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the tracked synthetic seed (clean-checkout safe; no gitignored dependency)."""
    seed_path = path or _SEED
    if not seed_path.exists():
        return []
    return [json.loads(line) for line in seed_path.read_text("utf-8").splitlines() if line.strip()]


def build_candidate_bundle_from_seed(path: Path | None = None) -> dict[str, Any]:
    return compile_objective_answer_keys(load_objective_seed(path))
