"""Canonical knowledge-compilation manifest (master plan §0.26.14 contract).

Hermetic: builds fake signed shard files in a temp supply root, asserts manifest build + fail-closed
verify (tamper / missing shard).
"""
from __future__ import annotations

import json

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
