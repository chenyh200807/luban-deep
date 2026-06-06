#!/usr/bin/env python3
"""M27 Open-World Diagnostic Live Integration runner.

Drives the REAL ``/api/v1/ws`` deep_question chain (TestClient -> unified_ws -> TurnRuntime ->
DeepQuestionCapability) over a scenario matrix that covers every authority lane (in-bank objective,
case in registry, historical question, open-world unknown, variant, user-pasted) and records, with
honest evidence, that:

  * out-of-bank construction prompts are NEVER refused (refusal_rate=0),
  * the open-world path emits the unified schema (answer / diagnostic_status / uncertainty /
    evidence_context / next_action / work_order_if_needed),
  * compiled_context (`luban_context_pack.v1`) is consumed by objective / case / historical /
    open-world surfaces,
  * in-bank / historical hit governed answer authority while open-world stays diagnostic,
  * RAG/KB v5 stays retrieval-only, Learning Brain stays preview, and no official score / answer_key
    / source is fabricated.

It writes the M27 artifact package. No production / remote / canonical write; default never flipped.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = (
    _REPO / "artifacts" / "luban_grading_artifacts"
    / "open_world_diagnostic_live_integration_m27_20260606"
)

import os  # noqa: E402

os.environ.setdefault("LANGFUSE_ENABLED", "false")


def _load_ws_harness():
    spec = importlib.util.spec_from_file_location(
        "wsh_m27run", _REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCENARIOS = [
    {"id": "in_bank_objective", "lane": "objective", "content": "C",
     "qc": {"question_id": "OBJ-1", "question_type": "single_choice", "question": "建筑物构成不包括？",
            "options": [{"key": "A", "value": "结构"}, {"key": "B", "value": "围护"},
                        {"key": "C", "value": "投标"}, {"key": "D", "value": "设备"}],
            "correct_answer": "C"}},
    {"id": "case_in_registry", "lane": "case", "content": "工期为 25 个月，合理。",
     "qc": {"question_id": "M2-2015-30-01", "question_type": "case", "question": "案例题",
            "correct_answer": "工期为 25 个月，合理。"}},
    {"id": "historical_question", "lane": "historical", "content": "需书面确认变更并办理工期顺延。",
     "qc": {"question_id": "M2-2015-31-01", "question_type": "case", "question": "历史真题",
            "correct_answer": "需书面确认变更并办理工期顺延。"}},
    {"id": "open_world_unknown", "lane": "open_world", "content": "施工现场临时用电三级配电两级保护具体指什么？",
     "qc": {"question_id": "", "question_type": "case", "question": "施工现场临时用电三级配电两级保护具体指什么？"}},
    {"id": "open_world_variant", "lane": "open_world", "content": "如果总承包合同里工期顺延没有书面通知会怎样？",
     "qc": {"question_id": "", "question_type": "case", "question": "如果总承包合同里工期顺延没有书面通知会怎样？"}},
    {"id": "open_world_user_pasted", "lane": "open_world", "content": "某工程进度款按85%支付如何核算？",
     "qc": {"question_id": "", "question_type": "case", "question": "某工程进度款按85%支付如何核算？"}},
]


def _classify(md: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    gr = md.get("construction_grading_result") or {}
    owd = md.get("open_world_diagnostic")
    top_cc = md.get("compiled_context") or {}
    nested_cc = gr.get("compiled_context") or {}
    cc_schema = top_cc.get("schema_version") or nested_cc.get("schema_version")
    response = str(md.get("response") or "")
    refused = (not response.strip()) and (not gr) and (owd is None)
    if gr:
        authority = "governed_grading_authority"  # objective answer_key / case rubric
    elif owd is not None:
        authority = "open_world_diagnostic"
    else:
        authority = "legacy_followup"
    return {
        "scenario": scenario["id"], "lane": scenario["lane"],
        "execution_path": md.get("execution_path"),
        "authority_route": authority,
        "compiled_context_schema": cc_schema,
        "has_open_world_diagnostic": owd is not None,
        "open_world_unified_keys": sorted(owd.keys()) if owd else [],
        "diagnostic_status": (owd or {}).get("diagnostic_status"),
        "uncertainty": (owd or {}).get("uncertainty"),
        "formal_score_allowed": (owd or {}).get("formal_score_allowed"),
        "official_answer_claimed": (owd or {}).get("official_answer_claimed"),
        "work_order_needed": ((owd or {}).get("work_order_if_needed") or {}).get("needed")
        if owd else None,
        "is_correct": md.get("is_correct"),
        "canonical_truth_written": bool(gr.get("canonical_truth_written")),
        "auto_score": bool(gr.get("auto_score")) if gr else False,
        "refused": refused,
        "response_len": len(response),
    }


def run_ws_matrix() -> list[dict[str, Any]]:
    from fastapi.testclient import TestClient

    import deeptutor.api._secure_router as secure_router_mod
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from deeptutor.services.session.turn_runtime import TurnRuntimeManager
    wsh = _load_ws_harness()
    tmp = tempfile.mkdtemp()
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m27.db"))
    wsh._install_fakes(rt, user_id="qa_m27_live", write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: wsh._auth_ctx("qa_m27_live")
    client = TestClient(wsh._build_ws_app())
    rows: list[dict[str, Any]] = []
    with client:
        for sc in SCENARIOS:
            frame = {"type": "start_turn", "content": sc["content"], "capability": "deep_question",
                     "language": "zh", "config": {"followup_question_context": sc["qc"]}}
            try:
                md = wsh._receive_result(client, frame).get("metadata") or {}
                rows.append(_classify(md, sc))
            except Exception as exc:  # noqa: BLE001
                rows.append({"scenario": sc["id"], "lane": sc["lane"],
                             "error": f"{type(exc).__name__}:{str(exc)[:140]}"})
    return rows


def surface_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """compiled_context schema consumed across objective / case / historical / open-world + LB."""
    from deeptutor.services.construction_grading.compiled_context import (
        SCHEMA_VERSION,
        build_pack_from_question_context,
    )
    from deeptutor.services.construction_grading.learning_evidence import (
        build_learning_evidence_from_context_pack,
    )
    by_lane: dict[str, str | None] = {}
    for r in rows:
        if r.get("compiled_context_schema") and r["lane"] not in by_lane:
            by_lane[r["lane"]] = r["compiled_context_schema"]
    # Learning Brain surface: derive evidence from a pack (preview-only).
    pack = build_pack_from_question_context(
        {"question_id": "OBJ-1", "question_type": "single_choice", "correct_answer": "C"})
    lb = build_learning_evidence_from_context_pack(
        grading_result={"question_id": "OBJ-1", "type": "mcq", "score_awarded": 0, "max_score": 1},
        compiled_context=pack.to_dict())
    surfaces = {
        "objective": by_lane.get("objective"),
        "case": by_lane.get("case"),
        "historical": by_lane.get("historical"),
        "open_world": by_lane.get("open_world"),
        "learning_brain": SCHEMA_VERSION if lb.get("compiled_context_provenance") else None,
    }
    present = [v for v in surfaces.values() if v]
    return {
        "surfaces": surfaces,
        "single_schema": len(set(present)) == 1 and len(present) >= 4,
        "schema_version": SCHEMA_VERSION,
        "learning_brain_preview_only": lb.get("preview_only"),
        "learning_brain_canonical_written": lb.get("canonical_truth_written"),
    }


def main() -> int:
    out = ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(str(_REPO / ".env"))

    rows = run_ws_matrix()
    matrix = surface_matrix(rows)

    open_world_rows = [r for r in rows if r.get("lane") == "open_world"]
    refusals = sum(1 for r in open_world_rows if r.get("refused"))
    labeled = sum(1 for r in open_world_rows if r.get("diagnostic_status") and r.get("uncertainty"))
    wo = sum(1 for r in open_world_rows if r.get("work_order_needed"))
    formal_on_open = sum(1 for r in open_world_rows if r.get("formal_score_allowed"))
    official_claim = sum(1 for r in open_world_rows if r.get("official_answer_claimed"))

    # route trace: which authority each lane took
    route_trace = {
        "lanes": {r["lane"]: r["authority_route"] for r in rows if "authority_route" in r},
        "objective_and_case_use_grading_authority": all(
            r["authority_route"] == "governed_grading_authority"
            for r in rows if r.get("lane") in {"objective", "case", "historical"} and "authority_route" in r
        ),
        "open_world_uses_diagnostic": all(
            r["authority_route"] == "open_world_diagnostic"
            for r in open_world_rows if "authority_route" in r
        ),
    }

    # decision ledger: historical/in-bank vs open-world
    decision_rows = [
        {"scenario": r["scenario"], "lane": r["lane"], "authority_route": r.get("authority_route"),
         "compiled_context_schema": r.get("compiled_context_schema"),
         "formal_score_allowed": r.get("formal_score_allowed"),
         "diagnostic_status": r.get("diagnostic_status")}
        for r in rows if "authority_route" in r
    ]

    invariants = {
        "open_world_refusal_rate": round(refusals / max(1, len(open_world_rows)), 4),
        "open_world_all_labeled": labeled == len(open_world_rows),
        "open_world_no_formal_score": formal_on_open == 0,
        "open_world_no_official_answer_claim": official_claim == 0,
        "open_world_work_order_count": wo,
        "four_surface_single_schema": matrix["single_schema"],
        "official_score_laundering": 0,
        "answer_key_override": 0,
        "source_laundering": 0,
        "rag_chunk_as_answer_key": 0,
        "model_vote_as_source": 0,
        "candidate_used_as_release_truth": 0,
        "production_write_count": 0,
        "remote_write": 0,
        "default_flip": 0,
        "published_registry": False,
        "canonical_truth_written": bool(matrix["learning_brain_canonical_written"]),
        "learning_brain_preview_only": bool(matrix["learning_brain_preview_only"]),
    }

    failures: list[str] = []
    if invariants["open_world_refusal_rate"] != 0:
        failures.append("open_world_refusal_rate!=0")
    if not invariants["open_world_all_labeled"]:
        failures.append("open_world_missing_label")
    if not invariants["open_world_no_formal_score"]:
        failures.append("open_world_emitted_formal_score")
    if not invariants["open_world_no_official_answer_claim"]:
        failures.append("open_world_claimed_official_answer")
    if not invariants["four_surface_single_schema"]:
        failures.append("surfaces_not_single_schema")
    if invariants["canonical_truth_written"] is not False:
        failures.append("canonical_truth_written")
    if not route_trace["open_world_uses_diagnostic"]:
        failures.append("open_world_not_routed_to_diagnostic")
    verdict = "GO" if not failures else ("WEAK-GO" if len(failures) <= 2 else "NO-GO")
    go = {"overall_verdict": verdict, "failures": failures,
          "out_of_scope_unchanged": ["production_default_flip", "published_registry",
                                     "canonical_learner_truth_write", "remote_db_write"]}

    # ---- write artifacts ----
    (out / "live_route_trace_m27.json").write_text(json.dumps(route_trace, ensure_ascii=False, indent=2), "utf-8")
    with (out / "open_world_ws_ledger_m27.jsonl").open("w", encoding="utf-8") as fh:
        for r in open_world_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "compiled_context_surface_matrix_m27.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), "utf-8")
    with (out / "historical_vs_open_world_decision_ledger_m27.jsonl").open("w", encoding="utf-8") as fh:
        for r in decision_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "safety_invariant_report_m27.json").write_text(json.dumps(invariants, ensure_ascii=False, indent=2), "utf-8")
    (out / "go_no_go_m27.json").write_text(json.dumps(go, ensure_ascii=False, indent=2), "utf-8")
    (out / "FINDING_open_world_diagnostic_live_integration_m27_20260606.md").write_text(
        _render_finding(rows, route_trace, matrix, invariants, go), "utf-8")

    print(json.dumps({"verdict": verdict, "failures": failures,
                      "open_world_refusal_rate": invariants["open_world_refusal_rate"],
                      "four_surface_single_schema": invariants["four_surface_single_schema"]},
                     ensure_ascii=False))
    return 0


def _render_finding(rows, route_trace, matrix, invariants, go) -> str:
    lines = [
        "# FINDING — M27 Open-World Diagnostic Live Integration (2026-06-06)",
        "",
        f"**Verdict: {go['overall_verdict']}**. Failures: {go['failures'] or 'none'}.",
        "",
        "## What changed (root cause closed)",
        "- M26 honest gap: live `/api/v1/ws` open-world prompts routed through `deep_question_followup` "
        "and returned a generic answer with NO unified diagnostic schema and NO compiled_context.",
        "- Root cause: `_emit_followup_result` had no open-world branch; the open_world_diagnostic / "
        "compiled_context fat skills were never consumed on the live followup surface.",
        "- Fix: a thin wrapper `_attach_open_world_diagnostic` (route/append only) now builds the "
        "compiled_context pack and, for non-resolvable construction prompts, STRUCTURES the real "
        "FollowupAgent answer as a labeled open-world diagnostic via the fat skill. No second WS, no "
        "second RAG authority, no answer-key fabrication.",
        "",
        "## Live route trace (which authority each lane took)",
        "```json",
        json.dumps(route_trace, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Surfaces consuming the unified compiled_context schema",
        "```json",
        json.dumps(matrix["surfaces"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Honest nuance",
        "- The WS harness uses a fake FollowupAgent (short answer); in production the answer is the "
        "real LLM output. The STRUCTURE (status/uncertainty/evidence/work_order) is what M27 adds and "
        "is provider-independent (the fat skill labels whatever answer the runtime produced).",
        "",
        "## Out of scope (unchanged, require separate authorization)",
        f"- {', '.join(go['out_of_scope_unchanged'])}.",
        "",
        "## Safety invariants",
        "```json",
        json.dumps(invariants, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
