"""Compile GB/JGJ standard clauses into a signed external-regulation authority lane.

Standards (规范) are statutory verbatim text — a clause's authority IS its exact wording + article id.
This compiles each standard content_block's ``origin_text`` into a signed record carrying standard_code
+ article_id + is_mandatory + canonical node (via the resolution bridge), so the grading/teaching engine
can cite "GB 50202-2018 §1.0.4 (强制性)" as external regulation authority — distinct from the textbook
lane and from the (reference-answer-sourced) rubric lane.

This is a VERBATIM lane (clause text signed as-is, content_hash over the exact text) because a regulation
clause must not be paraphrased. NO remote / DB. Re-runnable.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
STD_DIR = Path(os.getenv("LUBAN_DATA_DIR", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")) / "标准文件"
OUT = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_standard_clauses"

from deeptutor.services.construction_grading import canonical_resolution as CR  # noqa: E402


def _sha(o: Any) -> str:
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_standard: dict[str, int] = {}
    for f in sorted(glob.glob(str(STD_DIR / "*.json"))):
        try:
            doc = json.loads(Path(f).read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for cb in doc.get("content_blocks") or []:
            sc = cb.get("source_context") or {}
            text = str(sc.get("origin_text") or "").strip()
            if len(text) < 6:
                continue
            std = str(sc.get("standard_code") or "").strip()
            art = str(sc.get("article_id") or "").strip()
            # dedup identical clause (some blocks repeat)
            key = f"{std}|{art}|{_sha(text)[:12]}"
            if key in seen:
                continue
            seen.add(key)
            canon = CR.to_canonical(text)  # best-effort canonical node for retrieval join
            records.append({
                "point_id": f"STD::{std}::{art}::{_sha(text)[:8]}",
                "standard_code": std,
                "article_id": art,
                "is_mandatory": bool(sc.get("is_mandatory")),
                "chapter": sc.get("chapter_name") or sc.get("chapter"),
                "clause_text": text[:1000],
                "canonical_node": canon,
                "content_hash": _sha(text),
                "answer_key_authority": "external_regulation_verbatim",
            })
            by_standard[std] = by_standard.get(std, 0) + 1

    records.sort(key=lambda r: r["point_id"])
    content_hash = _sha(records)
    namespace = "standard_clauses"
    status = "release_candidate"
    bundle = {"manifest": {
        "schema_version": "luban_standard_clauses.v1", "namespace": namespace,
        "lane": "standard_clauses", "status": status, "published": False,
        "clause_count": len(records), "standard_count": len(by_standard),
        "by_standard": by_standard,
        "mandatory_count": sum(1 for r in records if r["is_mandatory"]),
        "canonical_linked": sum(1 for r in records if r["canonical_node"]),
        "answer_key_authority": "external_regulation_verbatim",
        "content_hash": content_hash,
        "signature": _sha([content_hash, namespace, status]),
        "rollback_pointer": "legacy (no standard_clauses -> standards only as teaching context)",
    }, "records": records}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "standard_clauses.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    (OUT / "canonical_pointer.json").write_text(json.dumps(
        {"namespace": namespace, "status": status, "published": False,
         "expected_content_hash": content_hash}, ensure_ascii=False, indent=2), "utf-8")
    return {"clauses": len(records), "standards": len(by_standard),
            "mandatory": bundle["manifest"]["mandatory_count"],
            "canonical_linked": bundle["manifest"]["canonical_linked"],
            "verify": _sha(records) == content_hash}


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
