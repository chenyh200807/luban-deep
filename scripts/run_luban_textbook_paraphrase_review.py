#!/usr/bin/env python3
"""Living LLM Artifact Compiler — open the verified_paraphrase review channel for the synthesis backlog.

The full textbook compile (run_luban_textbook_knowledge_compile.py) signs 1303 verbatim cards and routes
a small ``synthesis`` backlog (cards that faithfully paraphrase/summarize their block but are not literal
substrings) to a work-order list. This runner OPENS a review channel for that backlog:

  * joins each synthesis work-order item back to its source card + block content_markdown,
  * builds a self-contained review packet (claim + source + deterministic triage + faithfulness question),
  * stages them as compiler_feedback candidates (separate namespace, promote_to_release=False),
  * writes an append-only review queue to artifacts. NOTHING is auto-signed — verdicts stay unfilled
    until a GOVERNED reviewer (human / governed council) answers, which is a separately authorized pass.

Only a governed ``faithful`` verdict (+ grounded numbers) can later sign a packet into the SEPARATE
weaker class ``textbook_paraphrase_review`` (teaching context, never verbatim authority). NO remote /
production / canonical / publish write — all local + read-only.

Usage:
  python scripts/run_luban_textbook_paraphrase_review.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
COMPILE_OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "textbook_knowledge_full_20260606"
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "textbook_paraphrase_review_20260606"
BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")

from deeptutor.services.construction_grading import compiler_feedback as CF  # noqa: E402
from deeptutor.services.construction_grading import textbook_paraphrase_review as PR  # noqa: E402


def _load_backlog() -> list[dict[str, Any]]:
    """The synthesis work-order backlog emitted by the last full textbook compile."""
    path = COMPILE_OUT / "work_order_backlog.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _load_cards_and_sources() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Read-only: rebuild {point_id -> card} and {chunk_id -> content_markdown} from the 2026 教材."""
    cards_by_point: dict[str, dict[str, Any]] = {}
    source_by_chunk: dict[str, str] = {}
    if not BOOK_DIR.exists():
        return cards_by_point, source_by_chunk
    for f in sorted(BOOK_DIR.glob("FINAL_CLEANED_BOOK2026*fixed.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for b in doc.get("content_blocks") or []:
            if not isinstance(b, dict):
                continue
            cid = str(b.get("chunk_id") or "")
            cm = str(b.get("content_markdown") or "")
            if not cid or not cm.strip():
                continue
            source_by_chunk[cid] = cm
            node = str((b.get("taxonomy") or {}).get("node_code") or "")
            for idx, card in enumerate(b.get("knowledge_cards") or []):
                if not isinstance(card, dict):
                    continue
                pid = f"{cid}::C{idx}"
                cards_by_point[pid] = {**card, "chunk_id": cid, "node_code": node}
    return cards_by_point, source_by_chunk


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    backlog = _load_backlog()
    cards_by_point, source_by_chunk = _load_cards_and_sources()
    queue = PR.build_review_queue(backlog, cards_by_point, source_by_chunk)
    packets = queue["packets"]
    candidates = PR.make_paraphrase_candidates(packets)
    ledger = CF.build_ledger(candidates)

    # Dry-run proof: with NO verdicts filled, the signer signs nothing and routes all back to backlog.
    dry = PR.sign_verified_paraphrase_release_candidate(packets)

    with (OUT / "paraphrase_review_queue.jsonl").open("w", encoding="utf-8") as fh:
        for p in packets:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    (OUT / "candidate_ledger.json").write_text(json.dumps(
        {"summary": ledger, "entries": candidates}, ensure_ascii=False, indent=2), "utf-8")

    report = {
        "backlog_items": len(backlog),
        "channel_open_count": queue["open_count"],
        "unjoinable": queue["unjoinable"],
        "candidate_namespace": CF.NAMESPACE,
        "target_signed_namespace": PR.PARAPHRASE_NAMESPACE,
        "all_candidates_promote_to_release": any(c.get("promote_to_release") for c in candidates),
        "dry_run_signed_with_no_verdict": dry["manifest"]["signed_count"],  # must be 0 (fail-closed)
        "dry_run_routed_back": dry["manifest"]["work_order_count"],
        "note": "channel OPEN; verdicts unfilled. Only a governed 'faithful' verdict (+ grounded "
                "numbers) can sign into textbook_paraphrase_review (teaching context, never verbatim).",
    }
    gates = {
        "channel_opened": queue["open_count"] > 0,
        "candidates_separate_namespace": ledger["all_separate_from_release"],
        "no_candidate_promoted": ledger["candidate_used_as_release_truth"] == 0,
        "fail_closed_without_verdict": dry["manifest"]["signed_count"] == 0,
        "zero_verbatim_authority_minted": dry["manifest"]["verbatim_authority_records"] == 0,
    }
    report["verdict"] = "GO" if all(gates.values()) else "NO-GO"
    report["hard_gates"] = gates
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "FINDING_textbook_paraphrase_review.md").write_text(_finding(report, packets), "utf-8")
    return report


def _finding(report: dict[str, Any], packets: list[dict[str, Any]]) -> str:
    lines = [
        "# FINDING — verified_paraphrase 复核通道（synthesis backlog）",
        "",
        f"**verdict={report['verdict']}** — 仅开通道，不自动签署。NO publish / production / canonical / remote。",
        "",
        "## 通道状态",
        f"- synthesis backlog: **{report['backlog_items']}** 张；开通道: **{report['channel_open_count']}** 张。",
        f"- 候选暂存 namespace: `{report['candidate_namespace']}`（与 release 完全隔离）。",
        f"- 复核通过后签入 namespace: `{report['target_signed_namespace']}`（弱于逐字，教学上下文）。",
        f"- 空裁定 dry-run 签署数: **{report['dry_run_signed_with_no_verdict']}**（必须为 0，fail-closed）。",
        f"- 任何候选被提升为 release: {report['all_candidates_promote_to_release']}（必须为 False）。",
        "",
        "## 待复核卡片（claim ↔ source，含确定性 triage 信号）",
    ]
    for p in packets:
        t = p["triage"]
        lines += [
            f"### `{p['point_id']}` · node `{p['node_code']}`",
            f"- 标题: {p['claim_title']}",
            f"- 论断: {p['claim_content'][:120]}",
            f"- triage: 子句覆盖 {t['clauses_verbatim_in_source']}/{t['clause_count']} "
            f"({t['clause_coverage']}), 数字全部溯源={t['key_numbers_all_grounded']}",
        ]
    lines += [
        "",
        "## 门禁（硬约束）",
        "```json", json.dumps(report["hard_gates"], ensure_ascii=False, indent=2), "```",
        "",
        "## 范围外（需单独授权）",
        "governed 复核裁定 · 签入 textbook_paraphrase_review · publish · production · canonical · remote。",
    ]
    return "\n".join(lines)


def main() -> int:
    rep = run()
    print(json.dumps({"verdict": rep["verdict"], "channel_open": rep["channel_open_count"],
                      "backlog": rep["backlog_items"],
                      "dry_run_signed": rep["dry_run_signed_with_no_verdict"]}, ensure_ascii=False))
    return 0 if rep["verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
