"""Runtime supply v2 objective loader (M25-EF, fat skill).

Loads the TRACKED ``runtime_supply/v2_objective_real_candidate`` bundle (seed jsonl + manifest),
verifies content_hash + signature, and returns a verified {question_id: record} index for the
objective runtime adapter. Namespace is SEPARATE from the case registry. Fail-closed on
missing / malformed / tampered / hash-mismatch (returns verified=False; the adapter then
fail-closes and legacy/objective runtime stays uncontaminated).

Default reads the tracked v2 supply (clean-checkout safe). A dev-only artifact fallback is allowed
ONLY behind the explicit env ``LUBAN_OBJECTIVE_V2_DEV_SUPPLY_DIR``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.objective_answer_key_compiler import _canonical, _sha

_REPO = Path(__file__).resolve().parents[3]
_V2_DIR = (
    _REPO / "deeptutor" / "services" / "construction_grading"
    / "runtime_supply" / "v2_objective_real_candidate"
)
_SEED_NAME = "objective_answer_key_seed_real.jsonl"
_MANIFEST_NAME = "runtime_supply_v2_manifest.json"
NAMESPACE = "objective_answer_key_real"
_ALLOWED_STATUS = ("real_source_candidate", "release_candidate")

# M25-H: governed release_candidate supply (preferred over real_source_candidate when valid).
_RC_DIR = (
    _REPO / "deeptutor" / "services" / "construction_grading"
    / "runtime_supply" / "v2_objective_release_candidate"
)
_RC_SEED_NAME = "objective_answer_key_seed_release.jsonl"


def _supply_dir() -> Path:
    dev = os.environ.get("LUBAN_OBJECTIVE_V2_DEV_SUPPLY_DIR", "").strip()
    return Path(dev) if dev else _V2_DIR


def _read_records(seed_path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in seed_path.read_text("utf-8").splitlines() if x.strip()]


def load_and_verify(supply_dir: Path | None = None, *, seed_name: str = _SEED_NAME) -> dict[str, Any]:
    """Return {verified, status, reason, manifest, index}. Fail-closed on any defect."""
    d = supply_dir or _supply_dir()
    seed_path, manifest_path = d / seed_name, d / _MANIFEST_NAME
    if not seed_path.exists() or not manifest_path.exists():
        return {"verified": False, "status": None, "reason": "supply_missing", "manifest": {}, "index": {}}
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        records = _read_records(seed_path)
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "status": None, "reason": f"malformed:{exc}"[:120], "manifest": {}, "index": {}}

    status = str(manifest.get("status") or "")
    if status not in _ALLOWED_STATUS or manifest.get("published"):
        return {"verified": False, "status": status, "reason": "status_not_allowed_or_published",
                "manifest": manifest, "index": {}}

    recomputed = _sha(_canonical(sorted(records, key=lambda r: r.get("question_id", ""))))
    if recomputed != manifest.get("content_hash"):
        return {"verified": False, "status": status, "reason": "content_hash_mismatch",
                "manifest": manifest, "index": {}}
    expected_sig = _sha(recomputed + "|" + NAMESPACE + "|" + status)
    if expected_sig != manifest.get("signature"):
        return {"verified": False, "status": status, "reason": "signature_mismatch",
                "manifest": manifest, "index": {}}

    index = {r["question_id"]: r for r in records if r.get("question_id")}
    return {"verified": True, "status": status, "reason": "ok", "manifest": manifest, "index": index}


def verified_index(supply_dir: Path | None = None) -> dict[str, dict[str, Any]] | None:
    """Verified {question_id: record} index, or None if fail-closed."""
    result = load_and_verify(supply_dir)
    return result["index"] if result["verified"] else None


def load_release_candidate() -> dict[str, Any]:
    """Load + verify the governed release_candidate supply (M25-H). Fail-closed on any defect."""
    return load_and_verify(_RC_DIR, seed_name=_RC_SEED_NAME)


def load_best_available() -> dict[str, Any]:
    """Prefer the governed release_candidate; fall back to real_source_candidate. Explicit + safe:
    never silently uses a stale/unverified artifact — each tier is hash-verified or skipped."""
    rc = load_release_candidate()
    if rc["verified"]:
        rc["tier"] = "release_candidate"
        return rc
    real = load_and_verify(_V2_DIR, seed_name=_SEED_NAME)
    real["tier"] = "real_source_candidate" if real["verified"] else "none"
    real["release_candidate_skipped_reason"] = rc["reason"]
    return real


def verified_index_best() -> dict[str, dict[str, Any]] | None:
    r = load_best_available()
    return r["index"] if r["verified"] else None
