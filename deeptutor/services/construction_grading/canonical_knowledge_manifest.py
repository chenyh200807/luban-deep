"""Canonical knowledge-compilation manifest (master plan §0.26.14 contract).

The knowledge-compilation pillar must be consumed as ONE canonical manifest pointing to signed lane
shards — not a huge JSON, not thousands of unmanifested files. This module builds + verifies that
manifest: it pins the /2026 SOURCE corpus into a ``source_inventory_hash`` (so any source change is
detectable) and references each runtime-supply lane shard by pinned ``content_hash``. Runtime consumes
only manifest-pointed shards (no directory scanning / mtime / filename guessing).

Authority: this manifest is an INDEX over already-signed shards; it mints no new truth. Grading
authority stays on each shard's own signature; teaching shards stay teaching-tier. Fail-closed on a
missing/mismatched shard hash.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_canonical_knowledge_manifest.v1"
NAMESPACE = "canonical_knowledge_manifest"

# runtime_supply dir name -> §0.26.14 lane. Only these are indexed as canonical shards.
_LANE_MAP = {
    "v_textbook_knowledge_full": "source_context",
    "v3_objective_records_released_m31": "objective_answer_key",
    "v_slice_case_rubric": "case_rubric",
    "v_canonical_knowledge_graph": "concept_graph",
    "v_canonical_unified_knowledge": "learning_mapping",
}


def _sha256(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_inventory(source_files: list[Path]) -> dict[str, Any]:
    """Pin the /2026 source corpus: per-file sha256 + a combined inventory hash. Solidifies the data so
    a compile is reproducible from a known source state and any drift is auditable."""
    files = {}
    for p in sorted(source_files):
        if p.exists() and p.is_file():
            files[p.name] = {"sha256": _file_sha256(p), "bytes": p.stat().st_size}
    return {"file_count": len(files), "files": files, "inventory_hash": _sha256(files)}


def build_manifest(
    shards: list[dict[str, Any]],
    inventory: dict[str, Any],
    *,
    version: str,
    producer: str,
    rollback_pointer: str,
) -> dict[str, Any]:
    """Assemble the canonical manifest over signed shards + the pinned source inventory.

    ``shards`` items: {lane, path, namespace, content_hash, record_count, tier}. content_hash binds the
    canonical manifest to the exact shard bytes; signature is over (content_hash|namespace|status)."""
    shards_sorted = sorted(shards, key=lambda s: str(s.get("lane")))
    content_hash = _sha256({"shards": shards_sorted, "source_inventory_hash": inventory.get("inventory_hash")})
    status = "release_candidate"
    return {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "status": status,
        "published": False,
        "version": version,
        "producer": producer,
        "rollback_pointer": rollback_pointer,
        "source_inventory_hash": inventory.get("inventory_hash"),
        "source_file_count": inventory.get("file_count"),
        "shards": shards_sorted,
        "shard_count": len(shards_sorted),
        "content_hash": content_hash,
        "signature": _sha256([content_hash, NAMESPACE, status]),
    }


def verify_manifest(manifest: dict[str, Any], supply_root: Path) -> tuple[bool, str]:
    """Fail-closed: recompute manifest content_hash/signature AND re-check every shard file's
    content_hash against the live bytes on disk (tamper / missing shard -> fail)."""
    shards = manifest.get("shards") or []
    recomputed = _sha256({"shards": shards, "source_inventory_hash": manifest.get("source_inventory_hash")})
    if recomputed != manifest.get("content_hash"):
        return (False, "manifest_content_hash_mismatch")
    if _sha256([recomputed, manifest.get("namespace"), manifest.get("status")]) != manifest.get("signature"):
        return (False, "manifest_signature_mismatch")
    for s in shards:
        p = supply_root / str(s.get("path") or "")
        if not p.exists():
            return (False, f"missing_shard:{s.get('lane')}")
        try:
            on_disk = (json.loads(p.read_text("utf-8")).get("manifest") or {}).get("content_hash")
        except Exception:  # noqa: BLE001
            return (False, f"unreadable_shard:{s.get('lane')}")
        if on_disk != s.get("content_hash"):
            return (False, f"shard_hash_mismatch:{s.get('lane')}")
    return (True, "ok")


def enumerate_shards(supply_root: Path) -> list[dict[str, Any]]:
    """Read the signed lane bundles under runtime_supply into shard descriptors (pinned hashes)."""
    out: list[dict[str, Any]] = []
    # fixed lanes + any topic shard (v_topic_<name> -> lane "topic_<name>")
    lanes = dict(_LANE_MAP)
    for td in sorted(supply_root.glob("v_topic_*")):
        if td.is_dir():
            lanes[td.name] = "topic_" + td.name[len("v_topic_"):]
    for dirname, lane in lanes.items():
        d = supply_root / dirname
        if not d.is_dir():
            continue
        bundle = next((f for f in sorted(d.glob("*.json")) if "pointer" not in f.name), None)
        if bundle is None:
            continue
        try:
            doc = json.loads(bundle.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        m = doc.get("manifest") or {}
        rec = doc.get("records")
        nodes = doc.get("nodes")
        out.append({
            "lane": lane,
            "path": str(bundle.relative_to(supply_root)),
            "namespace": m.get("namespace"),
            "content_hash": m.get("content_hash"),
            "record_count": (len(rec) if isinstance(rec, list) else len(nodes) if isinstance(nodes, dict) else None),
            "tier": m.get("tier") or ("answer_authority" if lane in ("objective_answer_key", "case_rubric", "source_context") else "teaching"),
        })
    return out


__all__ = ["SCHEMA_VERSION", "NAMESPACE", "source_inventory", "build_manifest",
           "verify_manifest", "enumerate_shards"]
