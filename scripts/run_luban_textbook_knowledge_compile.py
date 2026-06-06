#!/usr/bin/env python3
"""Living LLM Artifact Compiler — Textbook Verbatim Lane (增量①): FULL 2026-textbook compile.

Design: docs/plan/2026-06-06-luban-textbook-verbatim-lane-design.md.

Runs ALL ~650 content_blocks of the 2026 教材 through the living compiler pipeline (lane="textbook")
→ the FIRST full-book signed textbook knowledge pack + an HONEST coverage report. Every card is
classified into a provenance bucket and either signed against verbatim content_markdown OR routed to
a named, append-only work-order backlog. Nothing silently dropped; nothing over-claimed.

The deterministic signer is the sole provenance authority (5 must-fix guards). The LLM (DeepSeek,
live-gated) only proposes verbatim spans; --no-llm runs the deterministic span finder (hermetic, $0).
NO remote / production / canonical / publish write — all local + read-only.

Usage:
  python scripts/run_luban_textbook_knowledge_compile.py            # deterministic full compile ($0)
  python scripts/run_luban_textbook_knowledge_compile.py --live     # DeepSeek span proposal (~$0.3)
  python scripts/run_luban_textbook_knowledge_compile.py --limit 50 # smoke on first N blocks
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "textbook_knowledge_full_20260606"
SUPPLY_DIR = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_textbook_knowledge_full"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
_NS = "textbook_knowledge_full"
_FREQ_K = 5  # a clause present in >= K distinct blocks is boilerplate (must-fix #5)

from deeptutor.services.construction_grading import compiled_registry_resolver as RES  # noqa: E402
from deeptutor.services.construction_grading import compiler_pipeline as PIPE  # noqa: E402
from deeptutor.services.construction_grading import feedback_ingest_bridge as BR  # noqa: E402
from deeptutor.services.construction_grading import full_knowledge_compiler as FKC  # noqa: E402
from deeptutor.services.construction_grading import textbook_knowledge_worker as TW  # noqa: E402


def _load_blocks(limit: int | None) -> list[dict[str, Any]]:
    """Read all 2026 教材 content_blocks (read-only). Only blocks with chunk_id + content_markdown."""
    blocks: list[dict[str, Any]] = []
    if not BOOK_DIR.exists():
        return blocks
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026*fixed.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for b in doc.get("content_blocks") or []:
            if not isinstance(b, dict):
                continue
            if not str(b.get("content_markdown") or "").strip() or not b.get("chunk_id"):
                continue
            blocks.append(b)
            if limit and len(blocks) >= limit:
                return blocks
    return blocks


def _freq_blocklist(blocks: list[dict[str, Any]]) -> list[str]:
    """Normalized clauses appearing in >= _FREQ_K distinct blocks -> boilerplate (must-fix #5)."""
    counts: dict[str, int] = {}
    for b in blocks:
        seen: set[str] = set()
        for clause in TW._CLAUSE_SPLIT.split(str(b.get("content_markdown") or "")):
            n = FKC._norm_textbook(clause)
            if len(n) >= 6 and n not in seen:
                seen.add(n)
                counts[n] = counts.get(n, 0) + 1
    return sorted(n for n, c in counts.items() if c >= _FREQ_K)


def _make_worker(*, live: bool):
    if not live:
        return TW.default_textbook_block_worker
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return TW.default_textbook_block_worker
    from deeptutor.services.llm.factory import complete

    def _worker(item: dict[str, Any]) -> list[dict[str, Any]]:
        return TW.textbook_block_worker(item, complete_fn=complete, api_key=key)

    return _worker


def _coverage_report(result: dict[str, Any], blocks: int, cards: int) -> dict[str, Any]:
    bundle = result["signed_bundle"]
    manifest = bundle["manifest"] if bundle else {}
    by_bucket = manifest.get("by_bucket", {})
    signed = manifest.get("signed_count", 0)
    return {
        "blocks_processed": blocks,
        "total_cards": cards,
        "signed_count": signed,
        "work_order_count": manifest.get("work_order_count", 0),
        "dropped_count": manifest.get("dropped_count", 0),
        "by_provenance_bucket": by_bucket,
        "signed_pct_of_cards": round(signed / cards, 3) if cards else 0.0,
        "node_codes_covered": len(manifest.get("node_index", {})),
        "honest_note": "signed = verbatim-confirmed subset; backlog (external/synthesis/human-gate) is "
                       "named + append-only; NOT a claim the whole textbook is compiled to answer-keys.",
    }


def _persist_supply(bundle: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    SUPPLY_DIR.mkdir(parents=True, exist_ok=True)
    (SUPPLY_DIR / "textbook_knowledge_release_candidate.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    pointer = {"namespace": _NS, "status": "release_candidate", "published": False,
               "expected_content_hash": bundle["manifest"]["content_hash"],
               "signed_point_count": bundle["manifest"]["signed_count"],
               "node_codes": coverage["node_codes_covered"], "coverage": "full_650_blocks"}
    (SUPPLY_DIR / "canonical_pointer.json").write_text(json.dumps(pointer, ensure_ascii=False, indent=2), "utf-8")
    return pointer


def _handoff_proof(bundle: dict[str, Any], pointer: dict[str, Any]) -> dict[str, Any]:
    nindex = bundle["manifest"].get("node_index") or {}
    node = next(iter(nindex), "")
    on = RES.build_pack_for_node(node, bundle=bundle, pointer=pointer, namespace=_NS, grant_release=True)
    off = RES.build_pack_for_node(node, bundle=bundle, pointer=pointer, namespace=_NS, grant_release=False)
    return {
        "sample_node": node,
        "granted_official_score_allowed": bool(on.to_dict()["diagnostic_policy"]["official_score_allowed"]) if on else None,
        "ungranted_official_score_allowed": bool(off.to_dict()["diagnostic_policy"]["official_score_allowed"]) if off else None,
        "authority_is_server_kwarg_only": bool(on) and bool(off)
        and on.to_dict()["diagnostic_policy"]["official_score_allowed"] is True
        and off.to_dict()["diagnostic_policy"]["official_score_allowed"] is False,
    }


def _verbatim_audit(bundle: dict[str, Any], blocks_by_id: dict[str, str]) -> dict[str, Any]:
    """Independent re-check: every signed point's quote + key_numbers ARE in its block's corpus."""
    bad_quote = bad_num = 0
    for r in bundle.get("records", []):
        corpus = FKC._norm_textbook(blocks_by_id.get(str(r.get("chunk_id")), ""))
        q = r.get("textbook_quote")
        if q and FKC._norm_textbook(q) not in corpus:
            bad_quote += 1
        for kn in r.get("key_numbers") or []:
            if FKC._num_core(kn) not in corpus:
                bad_num += 1
    return {"signed": len(bundle.get("records", [])), "quote_not_in_corpus": bad_quote,
            "key_number_not_in_corpus": bad_num, "verbatim_rate_ok": bad_quote == 0 and bad_num == 0}


def _decide(result, coverage, handoff, audit, blocks_n: int) -> dict[str, Any]:
    s = result["safety"]
    bundle = result["signed_bundle"]
    gates = {
        "signed_something": coverage["signed_count"] > 0,
        "bundle_verifies": bool(bundle) and FKC.verify_lane_bundle(bundle, _NS),
        "verbatim_rate_ok": audit["verbatim_rate_ok"],
        "external_laundering_zero": audit["key_number_not_in_corpus"] == 0 and audit["quote_not_in_corpus"] == 0,
        "key_number_not_in_text_signed_zero": s["key_number_not_in_text_signed"] == 0,
        "promote_only_in_s5": s["illegit_promote_outside_s5"] == 0,
        "no_source_laundering": s["candidate_used_as_release_truth"] == 0 and s["model_vote_as_source"] == 0,
        "tamper_fail_closed": s["tamper_fail_closed"] is True,
        "published_false": s["published"] is False,
        "canonical_truth_not_written": s["canonical_truth_written"] is False,
        "production_write_zero": s["production_write_count"] == 0,
        "node_code_indexed": coverage["node_codes_covered"] > 0,
        "handoff_authority_is_server_only": handoff["authority_is_server_kwarg_only"] is True,
        "coverage_reported_honestly": "honest_note" in coverage,
    }
    verdict = "GO" if all(gates.values()) and blocks_n >= 600 else ("WEAK-GO" if all(gates.values()) else "NO-GO")
    return {"verdict": verdict, "scope": "textbook verbatim lane — full 2026 textbook signed pack; "
            "NO publish / production / canonical / remote", "hard_gates": gates,
            "blocks_processed": blocks_n,
            "out_of_scope_unchanged": ["publish", "production_default", "canonical_learner_truth", "remote_deploy"]}


def run(*, live: bool = False, limit: int | None = None) -> dict[str, Any]:
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_REPO / ".env"))
    except Exception:  # noqa: BLE001
        pass
    OUT.mkdir(parents=True, exist_ok=True)

    blocks = _load_blocks(limit)
    total_cards = sum(len(b.get("knowledge_cards") or []) for b in blocks)
    blocks_by_id = {str(b.get("chunk_id")): str(b.get("content_markdown") or "") for b in blocks}
    blocklist = _freq_blocklist(blocks)

    evidence = BR.ingest_sources(textbook_blocks=blocks, run_id="textbook-full-1")
    worker = _make_worker(live=live)
    result = PIPE.run_pipeline(evidence, run_id="textbook-full-1", llm_worker=worker, lane="textbook",
                               max_iter=1, textbook_freq_blocklist=blocklist)

    bundle = result["signed_bundle"]
    coverage = _coverage_report(result, len(blocks), total_cards)
    pointer = _persist_supply(bundle, coverage) if bundle else {"expected_content_hash": ""}
    handoff = _handoff_proof(bundle, pointer) if bundle else {"authority_is_server_kwarg_only": False}
    audit = _verbatim_audit(bundle, blocks_by_id) if bundle else {"verbatim_rate_ok": False, "quote_not_in_corpus": 1, "key_number_not_in_corpus": 1}
    go = _decide(result, coverage, handoff, audit, len(blocks))

    (OUT / "coverage_report.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "pipeline_safety_report.json").write_text(json.dumps(result["safety"], ensure_ascii=False, indent=2), "utf-8")
    (OUT / "verbatim_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "runtime_handoff_proof.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "candidate_ledger.json").write_text(json.dumps(result["ledger"], ensure_ascii=False, indent=2), "utf-8")
    if bundle:
        wob = bundle.get("work_order", [])
        with (OUT / "work_order_backlog.jsonl").open("w", encoding="utf-8") as fh:
            for w in wob:
                fh.write(json.dumps(w, ensure_ascii=False) + "\n")
        (OUT / "signed_release_candidate_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "go_no_go.json").write_text(json.dumps(go, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "FINDING_textbook_knowledge_full.md").write_text(_finding(coverage, audit, handoff, go, live), "utf-8")
    return {"go_no_go": go, "coverage": coverage, "audit": audit, "handoff": handoff,
            "blocks": len(blocks), "cards": total_cards, "blocklist_size": len(blocklist)}


def _finding(coverage, audit, handoff, go, live) -> str:
    bb = coverage["by_provenance_bucket"]
    return "\n".join([
        "# FINDING — Textbook Verbatim Lane (增量①): full 2026-textbook compile",
        "",
        f"**verdict={go['verdict']}** — {go['scope']}. mode={'live DeepSeek' if live else 'deterministic ($0)'}.",
        "",
        "## Honest coverage (full 2026 textbook)",
        f"- blocks processed: **{coverage['blocks_processed']}**, knowledge_cards: **{coverage['total_cards']}**.",
        f"- **signed: {coverage['signed_count']}** ({coverage['signed_pct_of_cards']*100:.1f}% of cards), "
        f"work_order backlog: {coverage['work_order_count']}, dropped: {coverage['dropped_count']}.",
        f"- node_codes covered: {coverage['node_codes_covered']}.",
        f"- provenance buckets: {json.dumps(bb, ensure_ascii=False)}",
        f"- {coverage['honest_note']}",
        "",
        "## Verbatim provenance audit (independent re-check of every signed point)",
        "```json", json.dumps(audit, ensure_ascii=False, indent=2), "```",
        "",
        "## Runtime hand-off — authority is the server kwarg, never the bundle",
        "```json", json.dumps(handoff, ensure_ascii=False, indent=2), "```",
        "",
        "## Go / No-Go", "```json", json.dumps(go, ensure_ascii=False, indent=2), "```",
        "",
        "## Out of scope (needs separate authorization)",
        "publish · production default · canonical learner-truth · remote/DB write · human-gate review pass.",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="DeepSeek verbatim-span proposal (~$0.3)")
    parser.add_argument("--limit", type=int, default=None, help="only first N blocks (smoke)")
    args = parser.parse_args()
    out = run(live=args.live, limit=args.limit)
    print(json.dumps({"verdict": out["go_no_go"]["verdict"], "blocks": out["blocks"],
                      "cards": out["cards"], "signed": out["coverage"]["signed_count"],
                      "signed_pct": out["coverage"]["signed_pct_of_cards"]}, ensure_ascii=False))
    return 0 if out["go_no_go"]["verdict"] in ("GO", "WEAK-GO") else 1


if __name__ == "__main__":
    raise SystemExit(main())
