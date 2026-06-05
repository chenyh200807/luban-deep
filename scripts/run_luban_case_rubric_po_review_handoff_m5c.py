"""M5C — PO review hand-off. Consolidates the live M5B jury verdicts (11
published_candidate, 33/33 real votes) with the M5B PO review packets (30 questions)
into a single PO-ready queue + enriched packets.

The LLM jury is review evidence only — it never published anything, never minted a
textbook source. PO is the human authority that decides approve/keep_draft/rewrite/
require_external_source/reject. No registry emitted, no new table, no fabrication.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
M5B = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_review_m5b_20260604"
LIVE = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_live_m5b_20260604"
OUT_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_po_review_m5c_20260604"


def _recommend(m5a_status: str, jury: dict[str, Any] | None) -> tuple[str, int]:
    if jury:
        jv = jury["question_decision"]
        if jury.get("any_source_unsupported"):
            return "rewrite_point_or_require_external_source", 1  # jury disputes a verified anchor
        if jv == "publish_candidate":
            return "approve_publish_candidate", 2
        if jv == "draft_candidate":
            return "keep_draft", 3
        return "po_decide", 2
    # not jury-reviewed (carry M5A)
    if m5a_status == "needs_po_review":
        return "rewrite_point_or_require_external_source", 4
    return "keep_draft", 5


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "po_review_packets_enriched").mkdir(exist_ok=True)

    queue = json.loads((M5B / "po_review_queue.json").read_text("utf-8"))
    jury = {a["question_id"]: a for a in json.loads((LIVE / "jury_adjudication_live.json").read_text("utf-8"))}
    manifest = {m["question_id"]: m for m in json.loads((M5B / "jury_input_manifest.json").read_text("utf-8"))}

    final = []
    for q in queue:
        qid = q["question_id"]
        jv = jury.get(qid)
        action, prio = _recommend(q["m5a_status"], jv)
        final.append({
            "question_id": qid, "m5a_status": q["m5a_status"],
            "jury_reviewed": bool(jv), "jury_verdict": jv["question_decision"] if jv else None,
            "jury_publish_votes": jv["publish_votes"] if jv else None,
            "source_anchor_dispute": bool(jv and jv.get("any_source_unsupported")),
            "verified_coverage": q.get("verified_coverage"),
            "recommended_po_action": action, "po_priority": prio, "po_status": "pending_po",
        })
        # enrich the PO packet with the jury verdict (copy the M5B packet + append)
        src = M5B / "po_review_packets" / f"{qid}.md"
        if src.exists():
            body = src.read_text("utf-8")
            extra = ["", "## LLM jury verdict (live, 3 jurors: codex-GPT / DeepSeek / Qwen)", ""]
            if jv:
                extra += [f"- jury decision: **{jv['question_decision']}** (publish_votes {jv['publish_votes']}/3)",
                          f"- source_anchor_dispute: **{bool(jv.get('any_source_unsupported'))}** "
                          "(jury says a verbatim textbook anchor does NOT actually support the point)" if jv.get("any_source_unsupported") else
                          "- source_anchor_dispute: False",
                          "- point decisions:"]
                for pr in jv["point_decisions"]:
                    extra.append(f"  - {pr['point_id']} ({pr['policy_type']}): votes {pr['votes']} -> {pr['final']}")
            else:
                extra.append("- not jury-reviewed this round (M5A status carried; lower priority than published_candidate).")
            extra += ["", f"## Final recommended PO action: **{action}**", ""]
            (OUT_DIR / "po_review_packets_enriched" / f"{qid}.md").write_text(body + "\n".join(extra), encoding="utf-8")

    final.sort(key=lambda x: (x["po_priority"], x["question_id"]))
    from collections import Counter
    summary = {
        "total_questions": len(final),
        "jury_reviewed": sum(1 for x in final if x["jury_reviewed"]),
        "jury_verdicts": dict(Counter(x["jury_verdict"] for x in final if x["jury_reviewed"])),
        "source_anchor_disputes": sum(1 for x in final if x["source_anchor_dispute"]),
        "by_recommended_action": dict(Counter(x["recommended_po_action"] for x in final)),
        "publish_ready": 0,
        "formal_registry_emitted": False,
        "po_authority": "human PO decides; jury + deterministic anchors are evidence only",
    }
    _dump("po_review_queue_final.json", final)
    _dump("po_review_summary_m5c.json", summary)
    _write_finding(summary, final)
    print(f"M5C PO hand-off: questions={summary['total_questions']} jury_reviewed={summary['jury_reviewed']} "
          f"disputes={summary['source_anchor_disputes']} actions={summary['by_recommended_action']}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_finding(summary, final):
    top = [x for x in final if x["po_priority"] == 1][:12]
    lines = [
        "# FINDING — PO review hand-off M5C (2026-06-04)", "",
        "## 状态", "",
        f"- 总题数：**{summary['total_questions']}**（M5B 30 题 PO 队列）。",
        f"- 真实 jury 已复核：**{summary['jury_reviewed']}**（11 个 M5A published_candidate，3 juror，33/33 real votes）。",
        f"- jury 裁决分布：{summary['jury_verdicts']}（**publish_ready=0**）。",
        f"- **source_anchor_dispute：{summary['source_anchor_disputes']}**（jury 判定 verbatim 教材锚不支撑该点——M5A 短/句段锚的过度给分风险被坐实）。",
        f"- PO 行动分布：{summary['by_recommended_action']}。",
        "",
        "## 关键结论", "",
        "真实 3-juror jury 把**全部 11 个 M5A published_candidate 下调**（9 needs_po_review / 2 draft），其中 9 个存在 source-anchor dispute。",
        "→ **Registry v1 的真瓶颈是 PO 复核 + 数据返工（采分点重写 / 补真实教材锚），不是再跑 jury 或再挖锚点。**",
        "",
        "## PO 优先队列（priority 1 = jury 争议锚，最高）", "",
    ]
    for x in top:
        lines.append(f"- {x['question_id']}: jury={x['jury_verdict']}, dispute={x['source_anchor_dispute']} -> **{x['recommended_po_action']}**")
    lines += ["", "## 交付物", "",
              "- `po_review_queue_final.json`：30 题统一 PO 队列（含 jury 裁决 + 推荐动作 + 优先级）。",
              "- `po_review_packets_enriched/*.md`：每题 PO 包（M5B 包 + LLM jury 裁决段 + 最终推荐动作）。",
              "- 证据来源：M5B 离线包 + `case_rubric_jury_live_m5b_20260604/`（真实 jury votes）。",
              "",
              "## 红线",
              "jury 仅复核证据非 textbook source / 未发布任何题 / 未生成正式 registry / 未伪造 vote·source / PO 是人类终裁 authority / 未新增表 / 未接 runtime / 未改 kernel·RAG / 未 commit。",
              ""]
    (OUT_DIR / "FINDING_po_review_handoff_m5c_20260604.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
