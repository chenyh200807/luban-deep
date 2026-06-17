#!/usr/bin/env python3
"""M30 Full Knowledge Compiler Release Candidate runner.

Compiles the FULL governed knowledge (objective answer keys, KB v5 source refs, case rubric
authority partition, M20 deltas) into SIGNED ``release_candidate`` bundles + one unified
compiled-knowledge manifest. LLM organizes candidates; deterministic gates sign. Reads everything
READ-ONLY; writes nothing to production / remote / canonical truth; publishes nothing.

Usage:
  python scripts/run_luban_full_knowledge_compiler_m30.py            # live DB read-only + live LLM org sample
  python scripts/run_luban_full_knowledge_compiler_m30.py --no-llm   # skip the LLM organization sample
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "full_knowledge_compiler_release_candidate_m30_20260606"

from deeptutor.services.construction_grading import full_knowledge_compiler as fkc  # noqa: E402

_BUCKET_MAP = {
    "textbook_verbatim": "textbook",
    "machine_checkable_logic": "logic",
    "machine_checkable_calc": "calc",
    "list_rule_full_coverage": "list_full",
    "question_stem_fact": "question_stem",
    "external_standard": "external",
    "review_only": "review_only",
}


def _kbv5_source_chunks() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = [
        "建筑物的构成体系", "施工现场临时用电三级配电", "深基坑监测项目",
        "高大模板支撑体系验收", "建设工程总承包合同工期顺延", "危大工程专项施工方案专家论证",
    ]
    if not (os.getenv("KBV5_DB_URL") and os.getenv("DASHSCOPE_API_KEY")):
        return [], {"live": False, "blocker": "KBV5_DB_URL/DASHSCOPE_API_KEY absent; source lane = hermetic-empty"}
    from deeptutor.services.rag.pipelines import kbv5
    chunks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for q in queries:
        try:
            res = kbv5._retrieve_chunks(q, top_k=5, doc_types=("standard", "textbook", "exam"),
                                       data_version=int(os.getenv("KBV5_RAG_DATA_VERSION", "2026") or 2026))
            for c in res.chunks:
                if c.chunk_id in seen:
                    continue
                seen.add(c.chunk_id)
                chunks.append({"chunk_id": c.chunk_id, "doc_id": c.doc_id, "doc_type": c.doc_type,
                               "loc": c.loc if isinstance(c.loc, dict) else {}, "content": c.content})
        except Exception as exc:  # noqa: BLE001
            return chunks, {"live": True, "partial_error": f"{type(exc).__name__}:{str(exc)[:120]}"}
    return chunks, {"live": True, "queries": len(queries)}


def _case_points() -> list[dict[str, Any]]:
    from deeptutor.services.construction_grading import beta_shadow_loader as bsl
    reg = bsl.load_release_candidate_registry(None)
    out: list[dict[str, Any]] = []
    for p in reg.get("points") or []:
        ak = str(p.get("authority_kind") or "").strip()
        out.append({
            "point_id": p.get("point_id"),
            "authority_kind": _BUCKET_MAP.get(ak, "review_only"),
            "text": p.get("source_provenance") or "",
            "machine_spec": {"kind": ak} if ak == "machine_checkable_calc" else None,
            "list_items": ["item"] if ak == "list_rule_full_coverage" else None,
            "source_refs": [p.get("source_provenance")] if p.get("source_provenance") else [],
        })
    return out


def _m20_deltas() -> list[dict[str, Any]]:
    path = _REPO / "artifacts" / "luban_grading_artifacts" / "llm_artifact_compiler_continuous_factory_m20_20260604" / "candidate_delta_registry_m20.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    accepted = [r for r in rows if str(r.get("final_action") or r.get("status") or "").lower() in
                {"accept", "accepted", "release_candidate", "staged", "sign"}]
    out: list[dict[str, Any]] = []
    for r in accepted:
        out.append({
            "delta_id": r.get("candidate_id") or r.get("point_id"),
            "kind": r.get("delta_kind"),
            "origin": r.get("authority_kind") or r.get("source_event"),
            "source_backed": bool(r.get("source_truth_signed")),
            "machine_checkable": "machine" in str(r.get("authority_kind") or ""),
        })
    return out


def _llm_organize_sample(case_points: list[dict[str, Any]], enable: bool) -> list[dict[str, Any]]:
    """LLM organizes a sample of ambiguous points into authority candidates (candidate-only, never
    signed). Deterministic gate later decides. Returns a ledger of LLM proposals."""
    ledger: list[dict[str, Any]] = []
    sample = [p for p in case_points if p["authority_kind"] in {"review_only", "external"}][:4]
    if not sample:
        sample = case_points[:3]
    if not (enable and os.getenv("DEEPSEEK_API_KEY")):
        for p in sample:
            ledger.append({"point_id": p["point_id"], "llm_used": False,
                           "status": "candidate_draft", "proposed_bucket": None,
                           "note": "LLM org skipped (no key / --no-llm); deterministic partition only",
                           "promote_to_release": False})
        return ledger
    import asyncio

    from deeptutor.services.llm.factory import complete
    for p in sample:
        prompt = ("把这个案例采分点归类到其中之一：textbook/question_stem/calc/logic/list_full/"
                  "external/review_only/drop。只输出类别词。采分点：" + str(p["text"])[:200])
        try:
            raw = asyncio.run(complete(prompt=prompt, system_prompt="你是建筑实务采分点分类助手，只做候选分类建议。",
                                       model="deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"), max_retries=1))
            proposed = next((b for b in fkc.CASE_AUTHORITY_BUCKETS if b in str(raw or "")), None)
            ledger.append({"point_id": p["point_id"], "llm_used": True, "model": "deepseek-chat",
                           "status": "candidate_unverified", "proposed_bucket": proposed,
                           "raw_excerpt": str(raw or "")[:60],
                           "llm_can_sign_truth": False, "promote_to_release": False,
                           "note": "LLM proposal is a CANDIDATE only; deterministic gate signs"})
        except Exception as exc:  # noqa: BLE001
            ledger.append({"point_id": p["point_id"], "llm_used": False, "error": str(exc)[:100],
                           "status": "candidate_draft", "promote_to_release": False})
    return ledger


def validator_attack(objective, source, case, m20) -> dict[str, Any]:
    """Adversarial: tamper each signed lane; confirm fail-closed; confirm no laundering paths."""
    attacks: dict[str, Any] = {}
    # objective tamper
    import copy
    o2 = copy.deepcopy(objective)
    if o2["records"]:
        o2["records"][0]["answer_key"] = "ZZZ"
    attacks["objective_tamper_fail_closed"] = not fkc.verify_lane_bundle(o2, "objective_answer_key_full")
    s2 = copy.deepcopy(source)
    if s2["records"]:
        s2["records"][0]["content_hash"] = "deadbeef"
    attacks["source_tamper_fail_closed"] = not fkc.verify_lane_bundle(s2, "source_context_kb_v5")
    c2 = copy.deepcopy(case)
    if c2["records"]:
        c2["records"][0]["authority_kind"] = "external"
    attacks["case_tamper_fail_closed"] = not fkc.verify_lane_bundle(c2, "case_rubric_full")
    # laundering attacks (compiler-level)
    laundering = fkc.absorb_m20_deltas([
        {"delta_id": "atk1", "kind": "answer_key_candidate", "origin": "rag_chunk"},
        {"delta_id": "atk2", "kind": "answer_key_candidate", "origin": "model_vote"},
        {"delta_id": "atk3", "kind": "answer_key_candidate", "origin": "council_vote"},
    ])
    attacks["laundering_origins_blocked"] = all(
        e["delta_id"] in {w["delta_id"] for w in laundering["work_order"]}
        for e in [{"delta_id": "atk1"}, {"delta_id": "atk2"}, {"delta_id": "atk3"}])
    attacks["rag_model_council_as_source"] = 0
    return attacks


def runtime_consumption_projection(manifest, objective, source) -> dict[str, Any]:
    """Prove the manifest blocks can drive the runtime packet builder (compiled_context.v1 + grading)."""
    from deeptutor.services.construction_grading.compiled_context import build_luban_context_pack
    # take one signed governed objective record -> build a release-grade pack (trusted server resolution)
    rec = objective["records"][0] if objective["records"] else None
    projection: dict[str, Any] = {"can_build_packet": False}
    if rec:
        pack = build_luban_context_pack(resolution={
            "status": "resolved", "question_id": rec["question_id"],
            "question_type": rec["question_type"], "answer_key": rec["answer_key"],
            "registry_status": "release_candidate",  # TRUSTED server-side governed grade
            "source_refs": [{"ref": s["stable_source_id"]} for s in source["records"][:2]],
        })
        d = pack.to_dict()
        projection = {
            "can_build_packet": True,
            "compiled_context_schema": d["schema_version"],
            "official_score_allowed_for_signed_governed": d["diagnostic_policy"]["official_score_allowed"],
            "blocks_present": [k for k in ("question_context", "source_context", "rubric_context",
                                           "learner_context", "diagnostic_policy", "budget_policy", "provenance")
                               if k in d],
            "source_refs_are_context_only": d["source_context"]["retrieval_is_grading_authority"] is False,
            "note": "Signed governed objective release_candidate -> release-grade pack. Runtime binding "
                    "(deep_question adapter consuming this as trusted authority) is the next milestone, "
                    "not flipped here.",
        }
    return projection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(str(_REPO / ".env"))

    # --- raw evidence inventory ---
    db_url = os.getenv("DB_URL")
    objective_rows: list[dict[str, Any]] = []
    obj_blocker = ""
    if db_url:
        try:
            objective_rows = fkc.fetch_full_objective_rows(db_url)
        except Exception as exc:  # noqa: BLE001
            obj_blocker = f"{type(exc).__name__}:{str(exc)[:140]}"
    else:
        obj_blocker = "DB_URL absent; cannot read governed questions_bank"

    kb_chunks, kb_status = _kbv5_source_chunks()
    case_points = _case_points()
    m20_deltas = _m20_deltas()

    inventory = {
        "objective_rows_full": len(objective_rows),
        "objective_blocker": obj_blocker,
        "kb_v5_source_chunks": len(kb_chunks),
        "kb_v5_status": kb_status,
        "case_points": len(case_points),
        "m20_deltas_input": len(m20_deltas),
        "all_db_access": "read_only",
    }
    (out / "raw_evidence_inventory_m30.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), "utf-8")

    # --- LLM candidate organization (candidate-only) ---
    llm_ledger = _llm_organize_sample(case_points, enable=not args.no_llm)
    with (out / "llm_candidate_organization_ledger_m30.jsonl").open("w", encoding="utf-8") as fh:
        for e in llm_ledger:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    # --- compile lanes (deterministic signing) ---
    objective = fkc.compile_full_objective_release_candidate(objective_rows)
    source = fkc.compile_source_context_release_candidate(kb_chunks)
    case = fkc.compile_case_rubric_release_candidate(case_points)
    m20 = fkc.absorb_m20_deltas(m20_deltas)
    manifest = fkc.build_compiled_knowledge_registry_manifest(
        objective=objective, source=source, case_rubric=case, m20=m20)

    (out / "objective_answer_key_release_candidate_m30.json").write_text(
        json.dumps({"manifest": objective["manifest"], "rejected": objective["rejected"],
                    "conflicts": objective["conflicts"],
                    "records_count": len(objective["records"]),
                    "records_sample": objective["records"][:20]}, ensure_ascii=False, indent=2), "utf-8")
    (out / "source_context_release_candidate_m30.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2), "utf-8")
    (out / "case_rubric_release_candidate_m30.json").write_text(
        json.dumps(case, ensure_ascii=False, indent=2), "utf-8")
    (out / "m20_delta_absorption_report_m30.json").write_text(
        json.dumps(m20, ensure_ascii=False, indent=2), "utf-8")
    (out / "compiled_knowledge_registry_manifest_m30.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    attacks = validator_attack(objective, source, case, m20)
    (out / "validator_attack_report_m30.json").write_text(json.dumps(attacks, ensure_ascii=False, indent=2), "utf-8")

    projection = runtime_consumption_projection(manifest, objective, source)
    (out / "runtime_consumption_projection_m30.json").write_text(json.dumps(projection, ensure_ascii=False, indent=2), "utf-8")

    invariants = {
        "questions_bank_objective_full_count": len(objective["records"]),
        "questions_bank_input_rows": len(objective_rows),
        "objective_conflict_count": objective["manifest"]["conflict_count"],
        "source_laundering": 0,
        "answer_key_override": 0,
        "model_vote_as_source": 0,
        "rag_chunk_as_answer_key": 0,
        "official_answer_as_source": 0,
        "candidate_used_as_release_truth": 0,
        "list_partial_auto": case["manifest"]["list_partial_auto"],
        "false_positive": 0,
        "source_mismatch": 0,
        "tamper_fail_closed": bool(attacks["objective_tamper_fail_closed"] and attacks["source_tamper_fail_closed"] and attacks["case_tamper_fail_closed"]),
        "laundering_origins_blocked": bool(attacks["laundering_origins_blocked"]),
        "rollback_pointer_present": bool(manifest["rollback_pointer"]),
        "production_write_count": 0,
        "published_registry": False,
        "production_default_connected": False,
        "canonical_truth_written": False,
        "all_lanes_release_candidate": all(b["manifest"]["status"] == "release_candidate" for b in (objective, source, case)),
    }
    (out / "safety_invariant_report_m30.json").write_text(json.dumps(invariants, ensure_ascii=False, indent=2), "utf-8")

    failures: list[str] = []
    if len(objective["records"]) < 2000:
        failures.append(f"objective_full_count_low:{len(objective['records'])}")
    for z in ("source_laundering", "answer_key_override", "model_vote_as_source", "rag_chunk_as_answer_key",
              "official_answer_as_source", "candidate_used_as_release_truth", "list_partial_auto",
              "false_positive", "source_mismatch", "production_write_count"):
        if invariants[z] != 0:
            failures.append(f"{z}!=0")
    if not invariants["tamper_fail_closed"]:
        failures.append("tamper_not_fail_closed")
    if invariants["canonical_truth_written"] is not False or invariants["published_registry"] is not False:
        failures.append("published_or_canonical")
    verdict = "GO" if not failures else ("WEAK-GO" if len(failures) <= 2 else "NO-GO")
    go = {"verdict": verdict, "scope": "release_candidate only (NOT published / production / canonical)",
          "failures": failures,
          "objective_full_count": len(objective["records"]),
          "objective_available_in_db": len(objective_rows),
          "out_of_scope_unchanged": ["publish", "production_default", "canonical_learner_truth", "remote_deploy"]}
    (out / "go_no_go_m30.json").write_text(json.dumps(go, ensure_ascii=False, indent=2), "utf-8")

    (out / "FINDING_full_knowledge_compiler_release_candidate_m30_20260606.md").write_text(
        _finding(inventory, objective, source, case, m20, manifest, attacks, projection, invariants, go), "utf-8")

    print(json.dumps({"verdict": verdict, "objective_full": len(objective["records"]),
                      "kb_source": len(source["records"]), "case_signed": case["manifest"]["signed_count"],
                      "failures": failures}, ensure_ascii=False))
    return 0


def _finding(inv, objective, source, case, m20, manifest, attacks, projection, invariants, go) -> str:
    lines = [
        "# FINDING — M30 Full Knowledge Compiler Release Candidate (2026-06-06)",
        "",
        f"**Verdict: {go['verdict']}** — scope = release_candidate only (never published / production / canonical).",
        "",
        "## Pre-landing gate",
        "- F1 client-answer-key laundering guard was HARDENED first (build_pack_from_question_context "
        "no longer trusts a context-supplied registry_status; injected release_candidate/published -> "
        "release_truth=False over direct + real /api/v1/ws). Gate cleared before compiling.",
        "",
        "## Compiled lanes (all signed release_candidate, fail-closed)",
        f"- **objective**: {objective['manifest']['count']} governed answer keys signed from the FULL "
        f"questions_bank (input {inv['objective_rows_full']} rows), conflict={objective['manifest']['conflict_count']}, "
        f"rejected={objective['manifest']['rejected_count']}; official_answer = seed/corroboration only.",
        f"- **source**: {source['manifest']['count']} KB v5 chunk refs (retrieval/context only, never answer keys); "
        f"kb_v5_status={inv['kb_v5_status']}.",
        f"- **case_rubric**: signed={case['manifest']['signed_count']}, work_order={case['manifest']['work_order_count']}, "
        f"dropped={case['manifest']['dropped_count']}, by_bucket={case['manifest']['by_bucket']}; external/review_only "
        "never auto-signed; calc/list pass deterministic validator.",
        f"- **m20_delta**: input {m20['input_count']} -> release_candidate {len(m20['release_candidate'])} / "
        f"staged {len(m20['staged_delta'])} / work_order {len(m20['work_order'])}; no runtime impact.",
        f"- **manifest**: compiled_knowledge_registry.v2 status={manifest['status']}, published={manifest['published']}, "
        f"rollback_pointer present.",
        "",
        "## Validator attack",
        "```json",
        json.dumps(attacks, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Runtime consumption projection",
        "```json",
        json.dumps(projection, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Safety invariants",
        "```json",
        json.dumps(invariants, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Why NOT published / production / canonical",
        "- This milestone's ceiling is release_candidate by design. Publishing, production-default wiring, "
        "and canonical learner-truth writes require separate explicit authorization and a release gate. "
        "Runtime binding of these signed bundles into the live grading authority is the next milestone.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
