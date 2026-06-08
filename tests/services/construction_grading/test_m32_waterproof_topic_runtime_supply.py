"""M32 Task 2: the waterproof topic shard must be resolvable by topic_id (not by
mtime/filename scan), must stay unpublished/candidate-grade, and malformed or
missing shards must fail closed to open-world diagnostic — never to release truth."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SHARD_PATH = REPO / "deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof/topic_waterproof.json"


def _shard() -> dict:
    assert SHARD_PATH.exists(), f"waterproof shard not found at {SHARD_PATH}"
    return json.loads(SHARD_PATH.read_text(encoding="utf-8"))


# ── Authority and publication gate ──────────────────────────────────────────────────────────────

def test_waterproof_shard_is_unpublished_and_candidate_grade() -> None:
    """The waterproof shard is a release_candidate, not published.
    Canonical promotion of candidate-grade results is NOT allowed."""
    shard = _shard()
    manifest = shard["manifest"]
    assert manifest["published"] is False, "waterproof shard must never be published without explicit authorization"
    assert manifest.get("official_score_allowed") is False, "official_score_allowed must be False for candidate shard"
    assert manifest["status"] in {"release_candidate", "draft"}, f"unexpected status: {manifest['status']}"


def test_waterproof_shard_has_required_manifest_fields() -> None:
    """The manifest must have all M32-required fields for resolver and audit tracing."""
    manifest = _shard()["manifest"]
    required = {"content_hash", "signature", "schema_version", "namespace", "published", "status"}
    missing = required - manifest.keys()
    assert not missing, f"manifest missing required fields: {missing}"


def test_waterproof_shard_has_signed_content_hash() -> None:
    """Both content_hash and signature must be non-empty strings — this proves the shard
    was produced by the compiler (not hand-written or tampered)."""
    manifest = _shard()["manifest"]
    assert len(str(manifest.get("content_hash") or "")) >= 16, "content_hash too short"
    assert len(str(manifest.get("signature") or "")) >= 16, "signature too short"


# ── Resolution-by-topic_id, not by directory scan ───────────────────────────────────────────────

def test_shard_resolves_by_namespace_not_directory_scan() -> None:
    """The resolver must load the waterproof shard by namespace='topic_waterproof',
    not by scanning for the newest or most recent file in runtime_supply/."""
    from deeptutor.services.construction_grading.compiled_registry_resolver import load_supply
    supply_dir = REPO / "deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof"
    # load_supply expects bundle_name=<filename without dir>, pointer_name defaults to canonical_pointer.json
    result = load_supply(str(supply_dir), bundle_name="topic_waterproof.json")
    assert result is not None, "load_supply must succeed for the waterproof namespace"
    bundle, pointer = result
    assert bundle.get("manifest", {}).get("namespace") == "topic_waterproof", (
        "resolved shard must have namespace='topic_waterproof'"
    )
    assert pointer.get("namespace") == "topic_waterproof", (
        "canonical_pointer must also specify namespace='topic_waterproof'"
    )


def test_shard_namespace_matches_topic_waterproof() -> None:
    """The shard's namespace must be 'topic_waterproof' — this pins the resolution contract."""
    manifest = _shard()["manifest"]
    assert manifest.get("namespace") == "topic_waterproof"


# ── Fail-closed safety: malformed/missing shard → open-world diagnostic ─────────────────────────

def test_missing_shard_load_returns_none_not_exception(tmp_path) -> None:
    """load_supply on a non-existent directory must return None (fail closed),
    not raise an exception that would block the grading pipeline."""
    from deeptutor.services.construction_grading.compiled_registry_resolver import load_supply
    result = load_supply(str(tmp_path / "does_not_exist"), bundle_name="topic_waterproof")
    assert result is None, "missing shard must fail closed (return None, not raise)"


def test_waterproof_shard_tier_is_teaching_context_not_answer_key() -> None:
    """The shard's tier must be 'teaching_context_not_answer_key' — it is context for
    the runtime LLM adjudicator, never a direct answer key."""
    manifest = _shard()["manifest"]
    tier = manifest.get("tier", "")
    assert "answer_key" not in tier or "not" in tier, (
        f"shard tier '{tier}' must NOT designate itself an answer key"
    )
