"""Build the `waterproof` topic shard (master plan §0.26.15 M32 input).

M32's vertical slice is the waterproofing topic. This carves the waterproof/屋面/防水 canonical nodes
out of the verify-gated four-source unified bundle into a focused, signed TOPIC SHARD the grading /
open-world diagnostic can load as scoped context — without a new broad compiler campaign. Teaching tier
(textbook portion references already-signed records; official scoring stays verbatim-only). It registers
under the canonical knowledge manifest as lane `topic_waterproof`.

NO remote / DB / production. Re-runnable.

Usage: python scripts/run_luban_waterproof_topic_shard.py
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply"
UNIFIED = SUPPLY / "v_canonical_unified_knowledge" / "canonical_unified_knowledge.json"
OUT = SUPPLY / "v_topic_waterproof"
_NS = "topic_waterproof"
_KW = ("防水", "屋面", "卷材", "涂膜", "渗漏", "保温隔热", "地下室防水", "种植屋面")

from deeptutor.services.construction_grading import knowledge_unification as KU  # noqa: E402


def _sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def run() -> dict[str, Any]:
    bundle = json.loads(UNIFIED.read_text("utf-8"))
    if not KU.verify_unified_bundle(bundle):
        raise SystemExit("ERROR: unified bundle failed verify — aborting topic shard build.")
    nodes = {c: n for c, n in (bundle.get("nodes") or {}).items()
             if any(k in (n.get("name_path") or "") for k in _KW)}
    if not nodes:
        raise SystemExit("ERROR: no waterproof nodes found.")
    content_hash = _sha256(nodes)
    counts = {k: sum((n.get("counts") or {}).get(k, 0) for n in nodes.values())
              for k in ("textbook", "standard", "lecture", "question")}
    shard = {
        "manifest": {
            "schema_version": "luban_topic_shard.v1", "namespace": _NS,
            "status": "release_candidate", "published": False,
            "tier": "teaching_context_not_answer_key", "official_score_allowed": False,
            "topic": "waterproof", "node_count": len(nodes), "source_counts": counts,
            "derived_from": "canonical_unified_knowledge",
            "content_hash": content_hash,
            "signature": _sha256([content_hash, _NS, "release_candidate"]),
        },
        "nodes": nodes,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "topic_waterproof.json").write_text(
        json.dumps(shard, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    return {"namespace": _NS, "nodes": len(nodes), "source_counts": counts,
            "verify": _sha256(nodes) == content_hash, "out": str(OUT)}


def main() -> int:
    r = run()
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
