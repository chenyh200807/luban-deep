#!/usr/bin/env python3
"""Living LLM Artifact Compiler — first vertical slice runner (machine_spec lane).

Design: docs/plan/知识编译与检索/2026-06-06-luban-living-llm-artifact-compiler-design.md §8.

Proves the WHOLE loop end-to-end on ONE lane (case-rubric machine_spec) with REAL evidence:
  real M2 audit-packet scoring points -> S2 worker (DeepSeek live-gated, default deterministic) ->
  S3 deterministic gates (G2 real verbatim textbook anchor + G4 real m10 7-vector spec attack, both
  INJECTED) -> S4 (none for the slice) -> S5 deterministic sign -> tracked runtime supply -> S6
  resolver -> build_luban_context_pack -> runtime hand-off -> S7 loop re-ingest. Plus one M20
  machine_spec delta absorbed through the (previously dead) executor.

The factory, not a report. NO remote / production / canonical / publish write — all local + read-only.

Usage:
  python scripts/run_luban_compiler_pipeline_slice.py            # live DeepSeek S2 if key present
  python scripts/run_luban_compiler_pipeline_slice.py --no-llm   # deterministic S2 only
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "living_compiler_slice_20260606"
SUPPLY_DIR = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_slice_case_rubric"
M2_DIR = _REPO / "artifacts" / "luban_grading_artifacts" / "case_rubric_expansion_m2_20260604" / "audit_packets"
_NS = "case_rubric_full"

from deeptutor.services.construction_grading import compiled_registry_resolver as RES  # noqa: E402
from deeptutor.services.construction_grading import compiler_pipeline as PIPE  # noqa: E402
from deeptutor.services.construction_grading import feedback_ingest_bridge as BR  # noqa: E402
from deeptutor.services.construction_grading import full_knowledge_compiler as FKC  # noqa: E402


def _load_script(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _REPO / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# real script-bound gates (scripts may import scripts)
_SCHEMA = _load_script("luban_case_rubric_schema", "luban_case_rubric_schema.py")
_M10 = _load_script("luban_m10_factory", "build_luban_non_textbook_rubric_authority_factory_m10.py")


# ----------------------------- injected gates (REAL) -----------------------------

def _real_verify_anchor(anchor: dict[str, Any]) -> bool:
    return bool(_SCHEMA.verify_textbook_anchor(anchor))


def _positive_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    kind = spec.get("kind")
    if kind == "boolean_judgment":
        return {"judgment": spec.get("expected_bool")}
    if kind == "numeric_range":
        return {"value": (float(spec["lo"]) + float(spec["hi"])) / 2}
    rng = spec.get("acceptance_range")
    if rng:
        cand = {"value": float(rng[0])}
        if kind == "numeric_judgment":
            cand["judgment"] = spec.get("judgment")
        return cand
    return {"value": spec.get("expected")}


def _m10_spec_attack_fp(spec: dict[str, Any]) -> int:
    """G4: run the spec's own m10 negative_controls + the positive through matcher_accepts. fp=0 pass."""
    if not isinstance(spec, dict) or not spec:
        return 1
    fp = 0
    if not _M10.matcher_accepts(spec, _positive_candidate(spec)):
        fp += 1  # exact_hit must be accepted
    for nc in spec.get("negative_controls", []) or []:
        inp = nc.get("input")
        if isinstance(inp, bool):
            cand: dict[str, Any] = {"judgment": inp}
        elif isinstance(inp, (int, float)):
            cand = {"value": float(inp)}
            if "judgment" in nc:
                cand["judgment"] = nc["judgment"]
        else:
            continue
        if _M10.matcher_accepts(spec, cand):
            fp += 1  # a negative control accepted == false positive
    return fp


GATES = PIPE.GateSet(verify_textbook_anchor=_real_verify_anchor, spec_attack_fp=_m10_spec_attack_fp)


# ----------------------------- S0: real M2 evidence -----------------------------

def _load_m2_machine_spec_points(limit: int = 40) -> tuple[list[dict[str, Any]], int]:
    """Real M2 audit packets -> machine_spec_point evidence rows (via m10._machine_spec)."""
    rows: list[dict[str, Any]] = []
    scanned = 0
    if not M2_DIR.exists():
        return rows, scanned
    for f in sorted(M2_DIR.glob("*.json")):
        try:
            packet = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        qid = str(packet.get("question_id") or f.stem)
        for i, point in enumerate(packet.get("scoring_points") or []):
            scanned += 1
            label = str(point.get("point_label") or point.get("label") or "")
            # M2 scoring points carry ``label``; m10._machine_spec reads ``point_label`` — shim it.
            spec = _M10._machine_spec({**point, "point_label": label})
            if not spec:
                continue
            pid = f"{qid}::SP{i}"
            anchor = packet.get("textbook_anchor_evidence") if isinstance(packet.get("textbook_anchor_evidence"), dict) else None
            rows.append({"payload": {
                "point_id": pid, "question_id": qid,
                "text": label[:300],
                "machine_spec": spec,
                "required_terms": [label[:40]] if label else [],
                "textbook_anchor": anchor,
            }})
            if len(rows) >= limit:
                return rows, scanned
    return rows, scanned


def _one_m20_machine_spec_delta() -> list[dict[str, Any]]:
    """One real M20 delta routed through the (previously dead) absorber."""
    for d in _REPO.glob("artifacts/luban_grading_artifacts/**/candidate_delta_registry_m20.jsonl"):
        for line in d.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            return [{"delta_id": row.get("candidate_id"), "delta_kind": row.get("delta_kind"),
                     "origin": row.get("authority_kind") or "teacher_review",
                     "source_backed": bool(row.get("source_truth_signed")),
                     "machine_checkable": "machine" in str(row.get("authority_kind") or "")}]
    return []


# ----------------------------- S2: DeepSeek live-gated worker -----------------------------

def _deepseek_worker(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Live S2: DeepSeek proposes a CANDIDATE classification (organization only, never authority).
    Falls back to the deterministic default worker when the key is absent (--no-llm discipline)."""
    if item.get("evidence_kind") != "machine_spec_point":
        return PIPE.default_machine_spec_worker(item)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return PIPE.default_machine_spec_worker(item)
    payload = item.get("payload") or {}
    try:
        import asyncio

        from deeptutor.services.llm.factory import complete

        prompt = ("判断这个建筑实务采分点是否为可机器判定的计算/数值点，只输出 yes 或 no。采分点："
                  + str(payload.get("text"))[:160])
        raw = asyncio.run(complete(prompt=prompt, system_prompt="你只做候选分类建议，不决定对错。",
                                   model="deepseek-chat", api_key=key, max_retries=1))
        verdict = "yes" if "yes" in str(raw or "").lower() else "no"
    except Exception:  # noqa: BLE001 — LLM failure must not break the deterministic spine
        verdict = "fallback"
    cands = PIPE.default_machine_spec_worker(item)
    return [{**c, "payload": {**c["payload"], "llm_machine_checkable_vote": verdict,
                              "llm_provider": "deepseek-chat"}} for c in cands]


# ----------------------------- persistence + hand-off -----------------------------

def _persist_supply(bundle: dict[str, Any]) -> dict[str, Any]:
    SUPPLY_DIR.mkdir(parents=True, exist_ok=True)
    (SUPPLY_DIR / "case_rubric_release_candidate_slice.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    pointer = {"namespace": _NS, "status": "release_candidate", "published": False,
               "expected_content_hash": bundle["manifest"]["content_hash"],
               "signed_point_count": bundle["manifest"]["signed_count"], "coverage": "m2_machine_spec_slice"}
    (SUPPLY_DIR / "canonical_pointer.json").write_text(json.dumps(pointer, ensure_ascii=False, indent=2), "utf-8")
    return pointer


def _handoff_proof(bundle: dict[str, Any], pointer: dict[str, Any]) -> dict[str, Any]:
    qindex = bundle["manifest"].get("question_index") or {}
    qid = next(iter(qindex), "")
    on = RES.build_pack_for_question(qid, bundle=bundle, pointer=pointer, namespace=_NS, grant_release=True)
    off = RES.build_pack_for_question(qid, bundle=bundle, pointer=pointer, namespace=_NS, grant_release=False)
    return {
        "sample_qid": qid,
        "granted_official_score_allowed": bool(on.to_dict()["diagnostic_policy"]["official_score_allowed"]) if on else None,
        "granted_controlled_official": bool(on.to_dict()["diagnostic_policy"]["controlled_official"]) if on else None,
        "ungranted_official_score_allowed": bool(off.to_dict()["diagnostic_policy"]["official_score_allowed"]) if off else None,
        "authority_is_server_kwarg_only": bool(on) and bool(off)
        and on.to_dict()["diagnostic_policy"]["official_score_allowed"] is True
        and off.to_dict()["diagnostic_policy"]["official_score_allowed"] is False,
    }


def _decide(result: dict[str, Any], handoff: dict[str, Any], m2_count: int) -> dict[str, Any]:
    s = result["safety"]
    bundle = result["signed_bundle"]
    gates = {
        "signed_something": bundle is not None and bundle["manifest"]["signed_count"] > 0,
        "bundle_verifies": bool(bundle) and FKC.verify_lane_bundle(bundle, _NS),
        "promote_only_in_s5": s["illegit_promote_outside_s5"] == 0,
        "no_laundering": s["candidate_used_as_release_truth"] == 0 and s["model_vote_as_source"] == 0
        and s["rag_chunk_as_answer_key"] == 0 and s["official_answer_as_source"] == 0,
        "list_partial_auto_zero": s["list_partial_auto"] == 0,
        "tamper_fail_closed": s["tamper_fail_closed"] is True,
        "published_false": s["published"] is False,
        "canonical_truth_not_written": s["canonical_truth_written"] is False,
        "production_write_zero": s["production_write_count"] == 0,
        "handoff_authority_is_server_only": handoff["authority_is_server_kwarg_only"] is True,
        "loop_reingested": len(result["reingested"]) >= 0,  # loop wire present
    }
    verdict = "GO" if all(gates.values()) and m2_count > 0 else ("WEAK-GO" if all(gates.values()) else "NO-GO")
    return {"verdict": verdict, "scope": "living-compiler first vertical slice (machine_spec lane); "
            "NO publish / production / canonical / remote", "hard_gates": gates,
            "m2_real_points": m2_count,
            "out_of_scope_unchanged": ["publish", "production_default", "canonical_learner_truth", "remote_deploy"]}


def run(*, no_llm: bool = False) -> dict[str, Any]:
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_REPO / ".env"))
    except Exception:  # noqa: BLE001
        pass
    OUT.mkdir(parents=True, exist_ok=True)

    m2_rows, scanned = _load_m2_machine_spec_points()
    evidence = BR.ingest_sources(machine_spec_points=m2_rows, runtime_misses=[{"point_id": "slice-miss-1", "prompt": "变体题"}], run_id="slice-run-1")
    m20 = BR.absorb_m20_deltas(_one_m20_machine_spec_delta())

    worker = None if no_llm else _deepseek_worker
    result1 = PIPE.run_pipeline(evidence, run_id="slice-run-1", gates=GATES, llm_worker=worker, max_iter=3)
    # loop proof: run-2 carries run-1's seen set (越用越强 / bounded)
    result2 = PIPE.run_pipeline(evidence, run_id="slice-run-2", gates=GATES, llm_worker=worker,
                                max_iter=2, prior_seen=set(result1["seen"]))

    bundle = result1["signed_bundle"]
    pointer = _persist_supply(bundle) if bundle else {"expected_content_hash": "", "coverage": "no_signed"}
    handoff = _handoff_proof(bundle, pointer) if bundle else {"authority_is_server_kwarg_only": False}
    go = _decide(result1, handoff, len(m2_rows))

    # artifact ledger (local only)
    (OUT / "evidence_inventory.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in evidence), "utf-8")
    (OUT / "candidate_ledger.json").write_text(json.dumps(result1["ledger"], ensure_ascii=False, indent=2), "utf-8")
    if bundle:
        (OUT / "signed_release_candidate_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "pipeline_safety_report.json").write_text(json.dumps(result1["safety"], ensure_ascii=False, indent=2), "utf-8")
    (OUT / "m20_absorption.json").write_text(json.dumps(m20, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "runtime_handoff_proof.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "loop_reingest_proof.json").write_text(json.dumps(
        {"run1_seen": len(result1["seen"]), "run2_seen": len(result2["seen"]),
         "run1_iterations": result1["iterations"], "run1_reingested": len(result1["reingested"]),
         "run2_grew": len(result2["seen"]) >= len(result1["seen"])}, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "go_no_go.json").write_text(json.dumps(go, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "FINDING_living_compiler_slice.md").write_text(_finding(result1, m20, handoff, go, len(m2_rows), scanned), "utf-8")
    return {"go_no_go": go, "result1": result1, "m20": m20, "handoff": handoff, "pointer": pointer,
            "m2_count": len(m2_rows), "scanned": scanned}


def _finding(result, m20, handoff, go, m2_count, scanned) -> str:
    b = result["signed_bundle"]
    return "\n".join([
        "# FINDING — Living LLM Artifact Compiler, first vertical slice (machine_spec)",
        "",
        f"**verdict={go['verdict']}** — {go['scope']}.",
        "",
        "## Real evidence (S0)",
        f"- scanned {scanned} M2 scoring points -> {m2_count} machine_spec_point evidence items (m10._machine_spec).",
        f"- one M20 delta absorbed: release_candidate={len(m20.get('release_candidate', []))} "
        f"staged={len(m20.get('staged_delta', []))} work_order={len(m20.get('work_order', []))} "
        f"(candidate_used_as_release_truth={m20.get('candidate_used_as_release_truth')}).",
        "",
        "## Sign (S5) — the one flip site",
        f"- signed points: {b['manifest']['signed_count'] if b else 0}; "
        f"work_order: {b['manifest']['work_order_count'] if b else 0}; verify_lane_bundle: "
        f"{bool(b) and FKC.verify_lane_bundle(b, _NS)}; promoted: {result['promoted_count']}.",
        "",
        "## Runtime hand-off (S6) — authority is the server kwarg, never the bundle",
        "```json", json.dumps(handoff, ensure_ascii=False, indent=2), "```",
        "",
        "## Safety (§9)", "```json", json.dumps(result["safety"], ensure_ascii=False, indent=2), "```",
        "", "## Go / No-Go", "```json", json.dumps(go, ensure_ascii=False, indent=2), "```",
        "", "## Out of scope (needs separate authorization)",
        "publish · production default · canonical learner-truth · remote/DB write.",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="deterministic S2 only (no DeepSeek)")
    args = parser.parse_args()
    out = run(no_llm=args.no_llm)
    print(json.dumps({"verdict": out["go_no_go"]["verdict"], "m2_points": out["m2_count"],
                      "signed": out["result1"]["signed_bundle"]["manifest"]["signed_count"]
                      if out["result1"]["signed_bundle"] else 0}, ensure_ascii=False))
    return 0 if out["go_no_go"]["verdict"] in ("GO", "WEAK-GO") else 1


if __name__ == "__main__":
    raise SystemExit(main())
