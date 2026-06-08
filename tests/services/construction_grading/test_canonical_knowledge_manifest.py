"""Canonical knowledge-compilation manifest (master plan §0.26.14 contract).

Hermetic: builds fake signed shard files in a temp supply root, asserts manifest build + fail-closed
verify (tamper / missing shard).
"""
from __future__ import annotations

import json

import pytest

from deeptutor.services.construction_grading import canonical_knowledge_manifest as M


def _shard(d, name, content_hash, records=3):
    sub = d / name
    sub.mkdir()
    (sub / "bundle.json").write_text(json.dumps(
        {"manifest": {"namespace": name, "content_hash": content_hash},
         "records": list(range(records))}), "utf-8")
    return {"lane": name, "path": f"{name}/bundle.json", "namespace": name,
            "content_hash": content_hash, "record_count": records, "tier": "answer_authority"}


def test_source_inventory_pins_files(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("x", "utf-8")
    b = tmp_path / "b.json"
    b.write_text("y", "utf-8")
    inv = M.source_inventory([a, b, tmp_path / "missing.json"])
    assert inv["file_count"] == 2 and "a.json" in inv["files"]
    assert inv["inventory_hash"]  # combined hash present
    # changing a file changes the inventory hash
    a.write_text("changed", "utf-8")
    assert M.source_inventory([a, b])["inventory_hash"] != inv["inventory_hash"]


def test_build_and_verify_manifest(tmp_path):
    s1 = _shard(tmp_path, "objective_answer_key", "h1")
    s2 = _shard(tmp_path, "case_rubric", "h2")
    inv = M.source_inventory([])
    man = M.build_manifest([s2, s1], inv, version="v1", producer="test", rollback_pointer="legacy")
    # §0.26.14 required fields all present
    for k in ("schema_version", "status", "published", "version", "content_hash", "signature",
              "rollback_pointer", "shards", "producer", "source_inventory_hash"):
        assert k in man
    assert man["shard_count"] == 2 and man["published"] is False
    ok, reason = M.verify_manifest(man, tmp_path)
    assert ok is True and reason == "ok"


def test_verify_fails_on_tampered_shard(tmp_path):
    s1 = _shard(tmp_path, "objective_answer_key", "h1")
    man = M.build_manifest([s1], M.source_inventory([]), version="v1", producer="t", rollback_pointer="x")
    # tamper the shard's on-disk content_hash
    p = tmp_path / "objective_answer_key" / "bundle.json"
    b = json.loads(p.read_text("utf-8"))
    b["manifest"]["content_hash"] = "TAMPERED"
    p.write_text(json.dumps(b), "utf-8")
    ok, reason = M.verify_manifest(man, tmp_path)
    assert ok is False and "shard_hash_mismatch" in reason


def test_verify_fails_on_missing_shard(tmp_path):
    s1 = _shard(tmp_path, "objective_answer_key", "h1")
    man = M.build_manifest([s1], M.source_inventory([]), version="v1", producer="t", rollback_pointer="x")
    (tmp_path / "objective_answer_key" / "bundle.json").unlink()
    ok, reason = M.verify_manifest(man, tmp_path)
    assert ok is False and "missing_shard" in reason


# --- G3: promote release_candidate -> published (M33-ACT) ---

def test_promote_to_published_rebinds_status_keeps_content_hash(tmp_path):
    s1 = _shard(tmp_path, "objective_answer_key", "h1")
    man = M.build_manifest([s1], M.source_inventory([]), version="v2", producer="t", rollback_pointer="v1")
    assert man["status"] == "release_candidate" and man["published"] is False

    pub = M.promote_to_published(man, superseded_version="v1", published_at="2026-06-08T00:00:00+08:00")

    assert pub["status"] == "published" and pub["published"] is True
    assert pub["content_hash"] == man["content_hash"]     # content unchanged -> provenance intact
    assert pub["signature"] != man["signature"]           # signature rebinds the new status
    assert pub["superseded_version"] == "v1"              # supersession recorded
    assert pub["published_at"] == "2026-06-08T00:00:00+08:00"
    assert pub["rollback_pointer"] == "v1"                # rollback pointer preserved
    assert man["status"] == "release_candidate"           # original untouched (immutable)
    # a published manifest still verifies fail-closed against the on-disk shards
    ok, reason = M.verify_manifest(pub, tmp_path)
    assert ok is True and reason == "ok"


def test_promote_to_published_rejects_already_published(tmp_path):
    s1 = _shard(tmp_path, "objective_answer_key", "h1")
    man = M.build_manifest([s1], M.source_inventory([]), version="v1", producer="t", rollback_pointer="x")
    pub = M.promote_to_published(man, superseded_version=None, published_at="t")
    with pytest.raises(ValueError):
        M.promote_to_published(pub, superseded_version=None, published_at="t")


def test_promote_to_published_rejects_non_release_candidate(tmp_path):
    bad = {"status": "draft", "published": False, "content_hash": "h", "signature": "s"}
    with pytest.raises(ValueError):
        M.promote_to_published(bad, superseded_version=None, published_at="t")


def test_promote_to_published_does_not_share_shards_with_input(tmp_path):
    # immutable: mutating the promoted manifest's shards must not leak back into the input
    s1 = _shard(tmp_path, "objective_answer_key", "h1")
    man = M.build_manifest([s1], M.source_inventory([]), version="v1", producer="t", rollback_pointer="x")
    pub = M.promote_to_published(man, superseded_version=None, published_at="t")
    pub["shards"].append({"lane": "injected"})
    assert len(man["shards"]) == 1 and all(s.get("lane") != "injected" for s in man["shards"])


def test_promote_to_published_rejects_foreign_namespace(tmp_path):
    # a release_candidate carrying a non-canonical namespace must not be promoted (the re-sign binds the
    # constant NAMESPACE, so a foreign namespace would yield a signature inconsistent with its own field)
    bad = {
        "status": "release_candidate",
        "published": False,
        "content_hash": "h",
        "namespace": "evil",
    }
    with pytest.raises(ValueError):
        M.promote_to_published(bad, superseded_version=None, published_at="t")
