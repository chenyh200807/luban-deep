"""M21S — Build the minimal, signed, versioned runtime supply bundle.

Extracts ONLY the data the runtime grader actually needs from the (gitignored) review artifacts
into a small TRACKED bundle, so a clean checkout (no artifacts) can load the supply. Review-only
material (raw LLM votes, FINDINGs, latency ledgers, QA sample logs, full review packets) is NOT
included — only runtime-scoring fields.

Source (gitignored review artifacts, read-only):
  - M10 non_textbook_rubric_authority_factory: machine specs, list specs, review/external keys,
    residual authority inventory (textbook_verbatim_auto subset only)
  - M7/M8/M9 verified source candidates (point keys + verified textbook terms)
  - M16 registry_v1_release_candidate.json (already signed: hash + rollback pointer)

Target (tracked): deeptutor/services/construction_grading/runtime_supply/v1_limited_default/
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts/luban_grading_artifacts"
DEFAULT_BUNDLE = REPO / "deeptutor/services/construction_grading/runtime_supply/v1_limited_default"

M10_DIR = ART / "non_textbook_rubric_authority_factory_m10_20260604"
TYPED_POLICY = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_typed_policy_packet.json"
TYPED_POLICY_2 = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_typed_policy_packet.json"
M8 = ART / "v1_alpha_grand_sprint_m8_20260604/verified_source_candidates.jsonl"
M9 = ART / "v1_beta_shadow_source_assault_m9_20260604/verified_source_candidates_m9.jsonl"
M7 = ART / "registry_v1_council_hardened_candidate_m7_20260604/hardened_candidate_artifacts_preview.jsonl"
REGISTRY = ART / "controlled_production_runtime_flip_m16_20260604/registry_v1_release_candidate.json"

EXCLUDED_REVIEW_CATEGORIES = [
    "raw_llm_votes", "ai_council_votes", "FINDING_*.md", "latency_token_cost_ledgers",
    "qa_sample_logs", "go_no_go / verdict reports", "review packets full text", "adversarial reviews",
    "workflow ledgers / manifests",
]


def _rjsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()] if p.exists() else []


def _wjsonl(p: Path, rows: list[dict[str, Any]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _file_sha(p: Path) -> str:
    return _sha(p.read_bytes()) if p.exists() else ""


def _hash_files(paths: list[Path]) -> str:
    """Mirror beta_shadow_loader._hash_files so the loader's recomputed hash matches the manifest."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def build(target: Path) -> dict[str, Any]:
    target.mkdir(parents=True, exist_ok=True)
    src_hashes = {"machine": _file_sha(M10_DIR / "machine_checkable_case_specs_m10.jsonl"),
                  "list": _file_sha(M10_DIR / "list_rule_structured_specs_m10.jsonl"),
                  "review": _file_sha(M10_DIR / "review_required_packets_m10.jsonl"),
                  "external": _file_sha(M10_DIR / "external_source_work_orders_m10.jsonl"),
                  "residual": _file_sha(M10_DIR / "residual_authority_inventory_m10.json"),
                  "m7": _file_sha(M7), "m8": _file_sha(M8), "m9": _file_sha(M9),
                  "registry": _file_sha(REGISTRY)}

    # ---- machine + list specs: copy verbatim (already minimal runtime spec rows) ----
    machine = _rjsonl(M10_DIR / "machine_checkable_case_specs_m10.jsonl")
    lists = _rjsonl(M10_DIR / "list_rule_structured_specs_m10.jsonl")
    _wjsonl(target / "machine_checkable_case_specs_m10.jsonl", machine)
    _wjsonl(target / "list_rule_structured_specs_m10.jsonl", lists)

    # ---- review / external: keep ONLY the runtime keys (question_id, point_id) ----
    review = [{"question_id": r["question_id"], "point_id": r["point_id"]}
              for r in _rjsonl(M10_DIR / "review_required_packets_m10.jsonl")]
    external = [{"question_id": r["question_id"], "point_id": r["point_id"]}
                for r in _rjsonl(M10_DIR / "external_source_work_orders_m10.jsonl")]
    _wjsonl(target / "review_required_packets_m10.jsonl", review)
    _wjsonl(target / "external_source_work_orders_m10.jsonl", external)

    # ---- residual inventory: keep ONLY textbook_verbatim_auto_candidate points (runtime auto source) ----
    inv = json.loads((M10_DIR / "residual_authority_inventory_m10.json").read_text("utf-8"))
    auto_pts = [{"question_id": p["question_id"], "point_id": p["point_id"],
                 "authority_bucket": p["authority_bucket"]}
                for p in (inv.get("points") or []) if p.get("authority_bucket") == "textbook_verbatim_auto_candidate"]
    (target / "residual_authority_inventory_m10.json").write_text(
        json.dumps({"points": auto_pts, "minimized": True,
                    "note": "textbook_verbatim_auto_candidate points only (runtime auto source set)"},
                   ensure_ascii=False, indent=2), "utf-8")

    # ---- source-backed points: merge M7/M8/M9 verified (keys + verified textbook terms) ----
    sb: dict[tuple[str, str], list[str]] = {}
    for f in (M8, M9):
        for r in _rjsonl(f):
            key = (r["question_id"], r["point_id"])
            sb.setdefault(key, [])
            ref = r.get("verified_source_ref") or {}
            for cand in (ref.get("term"), ref.get("variant"), ref.get("parent_term")):
                if cand and str(cand).strip() and str(cand).strip() not in sb[key]:
                    sb[key].append(str(cand).strip())
    for a in _rjsonl(M7):
        for s in a.get("scoring_points", []):
            if s.get("auto_certifiable"):
                sb.setdefault((a["question_id"], s["point_id"]), [])
    source_rows = [{"question_id": q, "point_id": p, "source_terms": terms} for (q, p), terms in sorted(sb.items())]
    _wjsonl(target / "source_backed_points.jsonl", source_rows)

    # ---- golden typed-policy: MINIMAL {case_id, point_id, typed_policy} only (drop stem /
    # official_answer / student_answer / analysis — review material, never a runtime source) ----
    tp_rows: list[dict[str, Any]] = []
    seen_tp: set[tuple[str, str]] = set()
    for pk_path in (TYPED_POLICY, TYPED_POLICY_2):  # union, first wins (mirrors the original loader)
        if not pk_path.exists():
            continue
        pk = json.loads(pk_path.read_text("utf-8"))
        for t in pk.get("tasks", []):
            for sp in t.get("scoring_points", []):
                key = (t["case_id"], sp["point_id"])
                if key in seen_tp or not sp.get("typed_policy"):
                    continue
                seen_tp.add(key)
                tp_rows.append({"case_id": t["case_id"], "point_id": sp["point_id"], "typed_policy": sp["typed_policy"]})
    _wjsonl(target / "golden_typed_policy.jsonl", tp_rows)
    src_hashes["typed_policy"] = _file_sha(TYPED_POLICY)
    src_hashes["typed_policy_2"] = _file_sha(TYPED_POLICY_2)

    # ---- registry: copy verbatim (already signed: content_hash + rollback_pointer + status) ----
    (target / "registry_v1_release_candidate.json").write_text(REGISTRY.read_text("utf-8"), "utf-8")

    # ---- manifest: version + status + hashes (loader recomputes content_hash and verifies) ----
    supply_files = [target / n for n in ("machine_checkable_case_specs_m10.jsonl",
                    "list_rule_structured_specs_m10.jsonl", "review_required_packets_m10.jsonl",
                    "external_source_work_orders_m10.jsonl", "residual_authority_inventory_m10.json")]
    content_hash = _hash_files(supply_files)  # matches beta_shadow_loader._hash_files
    source_backed_hash = _file_sha(target / "source_backed_points.jsonl")
    typed_policy_hash = _file_sha(target / "golden_typed_policy.jsonl")
    registry_hash = json.loads((target / "registry_v1_release_candidate.json").read_text("utf-8")).get("registry_content_hash")
    manifest = {
        "schema_version": "luban_runtime_supply_bundle.v1",
        "version": "v1_limited_default", "status": "limited_default_candidate",
        "content_hash": content_hash, "source_backed_hash": source_backed_hash,
        "typed_policy_hash": typed_policy_hash, "registry_hash": registry_hash,
        "generated_from_artifact_hashes": src_hashes,
        "included_files": [p.name for p in supply_files] + ["source_backed_points.jsonl",
                          "golden_typed_policy.jsonl", "registry_v1_release_candidate.json",
                          "runtime_supply_manifest.json"],
        "counts": {"machine_specs": len(machine), "list_specs": len(lists), "review_points": len(review),
                   "external_points": len(external), "residual_auto_points": len(auto_pts),
                   "source_backed_points": len(source_rows), "golden_typed_policy_points": len(tp_rows)},
        "excluded_review_artifact_categories": EXCLUDED_REVIEW_CATEGORIES,
        "rollback_pointer": "legacy (drop request flag / env kill / registry unavailable -> fail-closed)",
        "runtime_authority": "deterministic textbook/spec/list matcher only; official_answer/model_vote/council_vote NEVER a source",
        "production_default": "off",
    }
    (target / "runtime_supply_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=str(DEFAULT_BUNDLE))
    args = ap.parse_args()
    m = build(Path(args.target))
    print(json.dumps({"target": args.target, "content_hash": m["content_hash"][:16],
                      "counts": m["counts"], "files": len(m["included_files"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
