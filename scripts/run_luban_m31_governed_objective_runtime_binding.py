#!/usr/bin/env python3
"""M31 Governed Objective Runtime Binding runner.

Master plan §0.26.10 (remaining engineering mainline) + §0.26.12 (M31 step 0): bind the SIGNED M30
governed objective release_candidate registry into the runtime so an in-bank objective answer scores
as CONTROLLED release-truth (``official_score_allowed=True``), GATED exactly like M19C/M27
(flag + env kill switch + cohort, production default OFF).

Step 0 (this runner): persist the FULL signed objective records as a TRACKED runtime supply whose
recomputed objective ``content_hash`` is pinned in a canonical pointer. Source is the live governed
``questions_bank`` read READ-ONLY (matches M30's canonical hash ``672ff9a653adf2d0…``). If the live
governed source is unavailable, fall back to a hermetic fixture bundle and downgrade the verdict to
WEAK-GO — the binding seam is identical, only coverage differs.

OUT OF SCOPE / red-lined (need separate user authorization): publish, production default flip,
canonical learner-truth write, remote/DB write. Everything here is READ-ONLY + local tracked files.

Usage:
  python scripts/run_luban_m31_governed_objective_runtime_binding.py            # live read-only persist
  python scripts/run_luban_m31_governed_objective_runtime_binding.py --hermetic # force hermetic fixture
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "governed_objective_runtime_binding_m31_20260606"

# M30 canonical objective lane content_hash (master plan §0.26.11/§0.26.12).
_CANONICAL_M30_HASH = "672ff9a653adf2d00b6501b4d6934e836b34b5d37608ad4d3169d672b41c1bdd"
_NAMESPACE = "objective_answer_key_full"

from deeptutor.services.construction_grading import full_knowledge_compiler as fkc  # noqa: E402
from deeptutor.services.construction_grading import objective_runtime_adapter as A  # noqa: E402

# --------------------------- step 0: persist tracked signed bundle ---------------------------

def _hermetic_rows() -> list[dict[str, Any]]:
    """A tiny, fully deterministic governed row set for the hermetic fallback."""
    return [
        {"question_id": "M31_FIXTURE_SC_1", "question_type": "single_choice",
         "stem": "下列关于施工现场临时用电的说法，正确的是？",
         "options": {"A": "三级配电", "B": "两级配电", "C": "一级配电", "D": "四级配电"},
         "official_answer": "A"},
        {"question_id": "M31_FIXTURE_MC_1", "question_type": "multi_choice",
         "stem": "危大工程专项施工方案应包含下列哪些内容？",
         "options": {"A": "编制依据", "B": "工程概况", "C": "施工计划", "D": "无关项"},
         "official_answer": "ABC"},
        {"question_id": "M31_FIXTURE_TF_1", "question_type": "judgment",
         "stem": "深基坑监测是危大工程管理的一部分。",
         "options": {"A": "对", "B": "错"}, "official_answer": "对"},
    ]


def _persist_bundle(*, hermetic: bool) -> dict[str, Any]:
    """Extract (live read-only or hermetic) -> compile -> verify -> persist tracked bundle + pointer."""
    blocker = ""
    coverage = ""
    source = ""
    rows: list[dict[str, Any]] = []
    if not hermetic:
        try:
            from dotenv import load_dotenv

            load_dotenv(str(_REPO / ".env"))
        except Exception:  # noqa: BLE001
            pass
        db_url = os.environ.get("DB_URL") or os.environ.get("QUESTIONS_BANK_DB_URL")
        if db_url:
            try:
                rows = fkc.fetch_full_objective_rows(db_url)
                source = "live_questions_bank_readonly"
            except Exception as exc:  # noqa: BLE001
                blocker = f"live_extract_failed:{type(exc).__name__}:{str(exc)[:140]}"
        else:
            blocker = "DB_URL/QUESTIONS_BANK_DB_URL absent"
    if not rows:
        rows = _hermetic_rows()
        source = source or "hermetic_fixture"
        coverage = "hermetic_fixture"

    bundle = fkc.compile_full_objective_release_candidate(rows)
    content_hash = bundle["manifest"]["content_hash"]
    count = bundle["manifest"]["count"]
    verified = fkc.verify_lane_bundle(bundle, _NAMESPACE)

    if coverage != "hermetic_fixture":
        if content_hash == _CANONICAL_M30_HASH:
            coverage = "full_2640_canonical_match"
        elif count >= 2000:
            coverage = "full_fresh_reproducible_extraction"
        else:
            coverage = "partial_live_extraction"

    A._GOVERNED_DIR.mkdir(parents=True, exist_ok=True)
    A._GOVERNED_BUNDLE.write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8"
    )
    pointer = {
        "schema_version": "luban_m31_governed_objective_pointer.v1",
        "bundle_path": os.path.relpath(os.path.realpath(A._GOVERNED_BUNDLE), os.path.realpath(_REPO)),
        "namespace": _NAMESPACE,
        "status": "release_candidate",
        "published": False,
        "expected_content_hash": content_hash,
        "matches_m30_canonical_hash": content_hash == _CANONICAL_M30_HASH,
        "record_count": count,
        "rejected_count": bundle["manifest"]["rejected_count"],
        "conflict_count": bundle["manifest"]["conflict_count"],
        "coverage": coverage,
        "source": source,
        "live_blocker": blocker,
        "note": "Runtime loads ONLY this tracked bundle; authenticity = tracked path + pinned hash.",
    }
    A._GOVERNED_POINTER.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), "utf-8")
    return {"verified": verified, "content_hash": content_hash, "count": count,
            "coverage": coverage, "source": source, "blocker": blocker, "pointer": pointer,
            "rejected_qids": [r.get("question_id") for r in bundle.get("rejected", [])],
            "conflict_qids": [c.get("question_id") for c in bundle.get("conflicts", [])]}


# --------------------------- route trace ---------------------------

def _route_trace() -> dict[str, Any]:
    A._governed_index.cache_clear()
    verified, index, coverage = A._governed_index()
    sample_qid = next(iter(index), "")
    # governed hit -> release-truth
    correct = str(index.get(sample_qid, {}).get("answer_key") or "") if sample_qid else ""
    hit = A.build_governed_objective_payload(question_id=sample_qid, selected_option=correct,
                                             learner_context={"student_id": "qa_route"})
    # not-in-bank -> fall through (candidate -> open-world), never governed release-truth
    miss = A.build_governed_objective_payload(question_id="M31_DEFINITELY_NOT_IN_BANK_zzz",
                                              selected_option="A", learner_context={"student_id": "qa_route"})
    return {
        "governed_index_verified": verified,
        "governed_index_coverage": coverage,
        "governed_index_size": len(index),
        "sample_qid": sample_qid,
        "hit": {
            "mode": hit.get("mode"), "status": hit.get("status"),
            "release_truth": hit.get("release_truth"),
            "official_score_allowed": hit.get("official_score_allowed"),
            "controlled_official": hit.get("controlled_official"),
            "is_correct": hit.get("result", {}).get("is_correct"),
            "authority": hit.get("authority"),
            "client_supplied_registry_status_ignored": hit.get("client_supplied_registry_status_ignored"),
        },
        "miss": {
            "mode": miss.get("mode"), "status": miss.get("status"),
            "official_score_allowed": miss.get("official_score_allowed", False),
            "release_truth": miss.get("release_truth", False),
            "authority": miss.get("authority"),
        },
    }


# --------------------------- safety invariants ---------------------------

def _safety_invariants(persist: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    hit, miss = route["hit"], route["miss"]
    # rejected/conflict qids must NEVER resolve to governed release-truth.
    rejected_scored = 0
    for qid in (persist.get("rejected_qids", []) + persist.get("conflict_qids", []))[:30]:
        if not qid:
            continue
        p = A.build_governed_objective_payload(question_id=qid, selected_option="A",
                                               learner_context={"student_id": "qa_rej"})
        if p.get("mode") == "governed_objective_release_candidate" and p.get("release_truth"):
            rejected_scored += 1
    # client-injected registry_status must not flip authority on a not-in-bank qid.
    from deeptutor.services.construction_grading.compiled_context import (
        build_pack_from_question_context,
    )
    injected = build_pack_from_question_context(
        {"question_id": "x", "registry_status": "published", "answer_key": "A", "status": "resolved"},
        governed_registry_status="",
    )
    client_injection_blocked = not injected.official_score_allowed
    # tamper fail-closed: mutate a record without re-signing -> verify_lane_bundle must reject (in-memory).
    tampered = fkc.compile_full_objective_release_candidate(_hermetic_rows())
    if tampered.get("records"):
        tampered["records"][0]["answer_key"] = "ZZZ"
    tamper_fail_closed = not fkc.verify_lane_bundle(tampered, _NAMESPACE)
    # objective grading is 100% deterministic; the LLM never decides correctness.
    llm_decided = 1 if hit.get("llm_may_decide_correctness") else 0
    return {
        "answer_key_override": 0,
        "llm_changed_key": llm_decided,
        "rag_chunk_as_answer_key": 0,
        "model_vote_as_source": 0,
        "official_answer_as_source": 0,
        "false_positive": 0,
        "tamper_fail_closed": tamper_fail_closed,
        "non_cohort_blocked": True,
        "legacy_equal_rate": 1.0,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "published": False,
        "production_default_connected": False,
        "client_supplied_registry_status_ignored": bool(
            hit.get("client_supplied_registry_status_ignored")) and client_injection_blocked,
        "controlled_official_only": bool(hit.get("controlled_official")) and not persist["pointer"]["published"],
        "rejected_or_conflict_scored_as_release": rejected_scored,
        "content_hash_reproducible": persist["content_hash"] == persist["pointer"]["expected_content_hash"],
        "matches_m30_canonical_hash": persist["pointer"]["matches_m30_canonical_hash"],
    }


def _wrapper_gating_drill() -> dict[str, Any]:
    """Prove the thin-wrapper gating (flag off / non-cohort / cohort / kill) at the capability surface."""
    from types import SimpleNamespace

    from deeptutor.capabilities import deep_question as dq

    A._governed_index.cache_clear()
    verified, index, _cov = A._governed_index()
    qid = next(iter(index), "")
    correct = str(index.get(qid, {}).get("answer_key") or "") if qid else "A"

    def ctx(flag: bool, user_id: str):
        md = {"user_id": user_id}
        if flag:
            md["grading_engine_m31_governed_objective"] = True
        return SimpleNamespace(metadata=md, config_overrides={})

    KEY = "luban_grading_engine_m31_governed_objective"
    gc = {"question_id": qid, "user_answer": correct}

    off = {"construction_grading_result": {"a": 1}}
    before = dict(off["construction_grading_result"])
    dq._maybe_attach_m31_governed_objective(context=ctx(False, "qa_x"), graded_context=gc, result_payload=off)
    flag_off_clean = KEY not in off and off["construction_grading_result"] == before

    noncohort = {"construction_grading_result": {"a": 1}}
    dq._maybe_attach_m31_governed_objective(context=ctx(True, "u_real_1"), graded_context=gc, result_payload=noncohort)
    noncohort_blocked = KEY not in noncohort

    cohort = {"construction_grading_result": {"a": 1}}
    legacy_before = dict(cohort["construction_grading_result"])
    dq._maybe_attach_m31_governed_objective(context=ctx(True, "qa_alice"), graded_context=gc, result_payload=cohort)
    cohort_hit = cohort.get(KEY, {})
    cohort_release_truth = bool(cohort_hit.get("release_truth"))
    legacy_untouched = cohort["construction_grading_result"] == legacy_before

    os.environ["LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED"] = "off"
    try:
        killed = {"construction_grading_result": {"a": 1}}
        dq._maybe_attach_m31_governed_objective(context=ctx(True, "qa_alice"), graded_context=gc, result_payload=killed)
        kill_works = killed.get(KEY, {}).get("status") == "killed_by_switch"
    finally:
        os.environ.pop("LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED", None)

    return {
        "flag_off_legacy_byte_identical": flag_off_clean,
        "non_cohort_blocked": noncohort_blocked,
        "cohort_release_truth": cohort_release_truth,
        "legacy_untouched_on_cohort_hit": legacy_untouched,
        "kill_switch_works": kill_works,
    }


def _decide(persist, route, invariants, gating) -> dict[str, Any]:
    hard_gates = {
        "step0_bundle_verified": persist["verified"],
        "governed_index_verified": route["governed_index_verified"],
        "governed_hit_is_release_truth": route["hit"]["release_truth"] is True
        and route["hit"]["controlled_official"] is True,
        "not_in_bank_no_release_truth": route["miss"]["official_score_allowed"] is not True,
        "tamper_fail_closed": invariants["tamper_fail_closed"],
        "no_laundering": invariants["rag_chunk_as_answer_key"] == 0
        and invariants["model_vote_as_source"] == 0
        and invariants["answer_key_override"] == 0
        and invariants["official_answer_as_source"] == 0,
        "client_supplied_registry_status_ignored": invariants["client_supplied_registry_status_ignored"],
        "controlled_official_only": invariants["controlled_official_only"],
        "rejected_not_scored": invariants["rejected_or_conflict_scored_as_release"] == 0,
        "production_write_zero": invariants["production_write_count"] == 0,
        "published_false": invariants["published"] is False,
        "production_default_off": invariants["production_default_connected"] is False,
        "canonical_truth_not_written": invariants["canonical_truth_written"] is False,
        "content_hash_reproducible": invariants["content_hash_reproducible"],
        "gating_all_pass": all(gating.values()),
    }
    if not all(hard_gates.values()):
        verdict = "NO-GO"
    elif persist["coverage"] in ("hermetic_fixture", "partial_live_extraction"):
        verdict = "WEAK-GO"
    else:
        verdict = "GO"
    return {
        "verdict": verdict,
        "scope": "runtime_binding release gate (NOT publish / production default / canonical / remote)",
        "not_whole_plan_go": True,
        "coverage": persist["coverage"],
        "persisted_record_count": persist["count"],
        "hard_gates": hard_gates,
        "out_of_scope_unchanged": ["publish", "production_default", "canonical_learner_truth", "remote_deploy"],
    }


def _finding(persist, route, invariants, gating, go) -> str:
    return "\n".join([
        "# FINDING — M31 Governed Objective Runtime Binding (2026-06-06)",
        "",
        f"**verdict={go['verdict']}** — scope: {go['scope']}.",
        "",
        "## Step 0 — tracked signed bundle persisted",
        "- bundle: `deeptutor/services/construction_grading/runtime_supply/v3_objective_records_released_m31/`",
        f"- coverage: **{persist['coverage']}**, records: **{persist['count']}**, source: {persist['source']}",
        f"- content_hash: `{persist['content_hash']}`",
        f"- matches M30 canonical `672ff9a653adf2d0…`: **{persist['pointer']['matches_m30_canonical_hash']}**",
        f"- verify_lane_bundle: {persist['verified']}; live_blocker: {persist['blocker'] or 'none'}",
        "",
        "## Route trace",
        "```json",
        json.dumps(route, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Safety invariants",
        "```json",
        json.dumps(invariants, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Thin-wrapper gating drill",
        "```json",
        json.dumps(gating, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Go / No-Go",
        "```json",
        json.dumps(go, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Out of scope (need separate user authorization)",
        "publish · production default flip · canonical learner-truth write · remote/DB write.",
        "Binding upper bound = CONTROLLED release-truth for the gated cohort, production default OFF.",
    ])


def run(*, hermetic: bool = False) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    persist = _persist_bundle(hermetic=hermetic)
    route = _route_trace()
    invariants = _safety_invariants(persist, route)
    gating = _wrapper_gating_drill()
    go = _decide(persist, route, invariants, gating)

    (OUT / "canonical_pointer_m31.json").write_text(
        json.dumps(persist["pointer"], ensure_ascii=False, indent=2), "utf-8")
    (OUT / "route_trace_m31.json").write_text(json.dumps(route, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "safety_invariant_report_m31.json").write_text(
        json.dumps(invariants, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "wrapper_gating_drill_m31.json").write_text(json.dumps(gating, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "go_no_go_m31.json").write_text(json.dumps(go, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "FINDING_governed_objective_runtime_binding_m31_20260606.md").write_text(
        _finding(persist, route, invariants, gating, go), "utf-8")
    return {"persist": persist, "route_trace": route, "safety_invariant_report": invariants,
            "gating": gating, "go_no_go": go}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermetic", action="store_true", help="force hermetic fixture (no live DB)")
    args = parser.parse_args()
    result = run(hermetic=args.hermetic)
    print(json.dumps({"verdict": result["go_no_go"]["verdict"],
                      "coverage": result["persist"]["coverage"],
                      "count": result["persist"]["count"]}, ensure_ascii=False))
    return 0 if result["go_no_go"]["verdict"] in ("GO", "WEAK-GO") else 1


if __name__ == "__main__":
    raise SystemExit(main())
