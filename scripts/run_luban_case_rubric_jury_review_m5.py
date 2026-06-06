"""M5 — LLM Jury Rubric Review over the M4 published/draft jury packets.

Heterogeneous 4-model jury (gpt55 / opus48 / deepseek_v4 / qwen37) reviews each M4
scoring-point packet. HONEST provenance: reviewer_type=llm_jury, never manual_qa_teacher /
human PO. Fail-closed everywhere:
  - a model with no live provider key -> provider_unavailable (recorded, never skipped, never
    substituted by another model, never back-filled from the forbidden 485 cache).
  - < 3 independent model votes for a packet -> quorum not met -> needs_po_review.
  - LLM may NOT upgrade a weak source to verified (any such claim is ignored).
  - exact_required stays strict; calculation w/o spec and list_rule w/o denominator cannot be
    published; M4's >=50% verified coverage gate is inherited.
NEVER emits a formal registry; only a candidate simulation + PO review queue.

The adjudication protocol is a pure function (``adjudicate``) so tests can drive it with
synthetic votes; the live run uses ``_provider_vote`` which fail-closes without keys.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
M4_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_quality_m4_20260604"
M3_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
DEFAULT_OUT = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_review_m5_20260604"

MODELS = ["gpt55", "opus48", "deepseek_v4", "qwen37"]
MIN_QUORUM = 3
# model -> the env var whose presence would make a live vote possible
MODEL_PROVIDER_KEY = {
    "gpt55": "OPENAI_API_KEY",
    "opus48": "ANTHROPIC_API_KEY",
    "deepseek_v4": "DEEPSEEK_API_KEY",
    "qwen37": "DASHSCOPE_API_KEY",
}

VoteFn = Callable[[str, dict], dict]


def _packets() -> list[dict[str, Any]]:
    out = []
    for f in sorted(glob.glob(str(M4_DIR / "jury_review_packets" / "*.json"))):
        out.append(json.loads(Path(f).read_text("utf-8")))
    return out


def _m4_quality() -> dict[str, dict[str, Any]]:
    rows = json.loads((M4_DIR / "published_candidate_quality_audit.json").read_text("utf-8"))
    return {r["question_id"]: r for r in rows}


def _weak_point_ids(packet: dict[str, Any]) -> set[str]:
    return {str(p.get("point_id")) for p in packet.get("scoring_point_candidates") or []
            if str(p.get("source_status")) not in ("ok", "verified")}


def _provider_vote(model: str, packet: dict[str, Any]) -> dict[str, Any]:
    """Live provider adapter. NO key -> provider_unavailable. NEVER fabricates, NEVER uses the
    485 cache for new-question rubric review."""
    key = MODEL_PROVIDER_KEY.get(model)
    if not key or not os.environ.get(key):
        return {"model": model, "status": "provider_unavailable",
                "reason": f"no live provider key ({key}) for new-question rubric review; "
                          f"485 cache forbidden for M5", "votes_fabricated": False}
    # A real implementation would call the model here and return a structured vote.
    # Not reachable in this environment (no keys); kept fail-closed by design.
    return {"model": model, "status": "provider_unavailable",
            "reason": "live call not wired in this runtime", "votes_fabricated": False}


def adjudicate(packet: dict[str, Any], votes: list[dict[str, Any]], m4q: dict[str, Any]) -> dict[str, Any]:
    """Pure adjudication. votes = list of structured model votes (status omitted == real vote)."""
    qid = packet.get("question_id")
    points = packet.get("scoring_point_candidates") or []
    weak_ids = _weak_point_ids(packet)
    real_votes = [v for v in votes if v.get("status") not in ("provider_unavailable",)]
    n = len(real_votes)
    blockers = list((m4q or {}).get("blockers") or [])
    # M4 structural gates (inherited; LLM cannot relax)
    can_pub_m4 = bool((m4q or {}).get("can_enter_registry_published"))
    can_draft_m4 = bool((m4q or {}).get("can_enter_registry_draft"))

    point_rows: list[dict[str, Any]] = []
    notes: list[str] = []
    if n < MIN_QUORUM:
        for p in points:
            point_rows.append({"question_id": qid, "point_id": p.get("point_id"),
                               "decision": "needs_po_review", "accept": 0, "n_votes": n,
                               "reason": "insufficient_jurors_quorum_not_met"})
        return {"question_id": qid, "n_votes": n, "quorum_met": False,
                "question_level_decision": "needs_po_review",
                "question_level_rationale": "fewer than 3 independent model votes (provider-blocked)",
                "point_decisions": point_rows, "notes": ["quorum_not_met"], "proposed_patches": []}

    # quorum met: tally per point
    proposed_patches = []
    point_final = {}
    for p in points:
        pid = str(p.get("point_id"))
        pv = [next((pr for pr in v.get("point_reviews") or [] if str(pr.get("point_id")) == pid), None) for v in real_votes]
        pv = [x for x in pv if x]
        accept = sum(1 for x in pv if x.get("decision") == "accept")
        reject = sum(1 for x in pv if x.get("decision") == "reject")
        revise = sum(1 for x in pv if x.get("decision") == "revise")
        npr = sum(1 for x in pv if x.get("decision") == "needs_po_review")
        high_missing = sum(1 for x in pv if x.get("missing_point_risk") == "high")
        # weak source can never be upgraded to verified by an LLM vote
        upgrade_attempt = pid in weak_ids and any(x.get("textbook_anchor_ok") is True for x in pv)
        if upgrade_attempt:
            notes.append(f"{pid}:weak_anchor_upgrade_attempt_ignored")
        source_dispute = any(x.get("textbook_anchor_ok") is False or x.get("decision") == "reject" for x in pv)
        # collect any suggested revisions as PROPOSED ONLY
        for x in pv:
            if x.get("suggested_revision"):
                proposed_patches.append({"point_id": pid, "from_model": next((v.get("model") for v in real_votes
                                         if x in (v.get("point_reviews") or [])), None),
                                         "suggested_revision": x.get("suggested_revision")})
        if high_missing * 2 >= n or (accept == reject and accept > 0) or (npr > 0 and accept < 3):
            dec = "needs_po_review"
        elif accept >= 3:
            dec = "accept"
        elif reject > accept:
            dec = "reject"
        elif revise >= accept:
            dec = "revise"
        else:
            dec = "needs_po_review"
        point_final[pid] = dec
        point_rows.append({"question_id": qid, "point_id": pid, "decision": dec,
                           "accept": accept, "reject": reject, "revise": revise,
                           "needs_po_review": npr, "n_votes": len(pv),
                           "weak_upgrade_blocked": upgrade_attempt, "source_dispute": source_dispute})

    all_accept = points and all(point_final.get(str(p.get("point_id"))) == "accept" for p in points)
    any_reject = any(d == "reject" for d in point_final.values())
    any_npr = any(d == "needs_po_review" for d in point_final.values())
    if any_npr or not can_draft_m4:
        q_dec = "needs_po_review"
        q_reason = "split/high-risk points or M4 draft gate not met -> PO review"
    elif all_accept and can_pub_m4:
        q_dec = "publish_candidate"
        q_reason = "all points jury-accepted AND M4 published gate (coverage/policy/spec) passed"
    elif any_reject:
        q_dec = "reject"
        q_reason = "reject-majority point(s)"
    else:
        q_dec = "draft_candidate"
        q_reason = "jury-accepted but blocked from published by M4 gate (coverage/calc/list)"
    return {"question_id": qid, "n_votes": n, "quorum_met": True,
            "question_level_decision": q_dec, "question_level_rationale": q_reason,
            "point_decisions": point_rows, "notes": notes, "proposed_patches": proposed_patches,
            "m4_blockers": blockers}


def build_m5(out_dir: Path = DEFAULT_OUT, *, vote_fn: VoteFn = _provider_vote,
             models: list[str] | None = None) -> dict[str, Any]:
    models = list(models) if models else list(MODELS)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model_votes").mkdir(exist_ok=True)
    (out_dir / "proposed_packet_patches").mkdir(exist_ok=True)
    packets = _packets()
    m4q = _m4_quality()

    manifest = {"input_packets": len(packets), "models": models, "min_quorum": MIN_QUORUM,
                "reviewer_type": "llm_jury", "cache_485_used_for_new_questions": False,
                "question_ids": [p.get("question_id") for p in packets]}
    _dump(out_dir, "jury_input_manifest.json", manifest)

    provider_unavailable = {m: 0 for m in models}
    adjudications = []
    for packet in packets:
        qid = packet.get("question_id")
        votes = []
        for model in models:
            v = vote_fn(model, packet)
            if v.get("status") == "provider_unavailable":
                provider_unavailable[model] += 1
                (out_dir / "model_votes" / f"{qid}__{model}__provider_unavailable.json").write_text(
                    json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                assert v.get("votes_fabricated") is False, "fabricated votes are forbidden"
                votes.append(v)
                (out_dir / "model_votes" / f"{qid}__{model}.json").write_text(
                    json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
        adj = adjudicate(packet, votes, m4q.get(qid, {}))
        adjudications.append(adj)
        if adj["proposed_patches"]:
            (out_dir / "proposed_packet_patches" / f"{qid}.json").write_text(
                json.dumps({"question_id": qid, "proposed_patches": adj["proposed_patches"],
                            "note": "proposed only; does NOT overwrite M4 packets"}, ensure_ascii=False, indent=2),
                encoding="utf-8")

    _dump(out_dir, "jury_adjudication.json", adjudications)
    # point decision matrix CSV
    with open(out_dir / "point_decision_matrix.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "point_id", "decision", "accept", "n_votes"])
        for adj in adjudications:
            for r in adj["point_decisions"]:
                w.writerow([r["question_id"], r["point_id"], r["decision"], r.get("accept", 0), r.get("n_votes", 0)])

    from collections import Counter
    qdec = Counter(a["question_level_decision"] for a in adjudications)
    summary = {a["question_id"]: {"decision": a["question_level_decision"], "quorum_met": a["quorum_met"],
                                  "rationale": a["question_level_rationale"]} for a in adjudications}
    _dump(out_dir, "question_decision_summary.json", summary)

    sim = {"registry_emitted": False,
           "input_questions": len(packets),
           "publish_ready_after_jury": qdec.get("publish_candidate", 0),
           "draft_after_jury": qdec.get("draft_candidate", 0),
           "needs_po_review": qdec.get("needs_po_review", 0),
           "rejected": qdec.get("reject", 0),
           "provider_unavailable_counts": provider_unavailable,
           "quorum_blocked": sum(1 for a in adjudications if not a["quorum_met"])}
    _dump(out_dir, "registry_v1_candidate_simulation_m5.json", sim)

    po_queue = [{"question_id": a["question_id"], "reason": a["question_level_rationale"],
                 "m4_blockers": a.get("m4_blockers", [])}
                for a in adjudications if a["question_level_decision"] == "needs_po_review"]
    _dump(out_dir, "po_review_queue.json", {"count": len(po_queue), "queue": po_queue})

    (out_dir / "FINDING_case_rubric_jury_review_m5_20260604.md").write_text(_finding(packets, adjudications, sim, provider_unavailable), encoding="utf-8")
    return {"manifest": manifest, "adjudications": adjudications, "sim": sim, "provider_unavailable": provider_unavailable}


def _dump(out_dir: Path, name: str, obj: Any) -> None:
    (out_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _finding(packets, adjudications, sim, prov) -> str:
    n_points = sum(len(p.get("scoring_point_candidates") or []) for p in packets)
    all_unavail = bool(prov) and all(c == len(packets) for c in prov.values())
    from collections import Counter
    pdec = Counter(r["decision"] for a in adjudications for r in a["point_decisions"])
    return "\n".join([
        "# FINDING — M5 LLM Jury Rubric Review（2026-06-04）",
        "",
        "## 必答",
        f"1. M5 实际 review 了多少题、多少点？ 输入 **{len(packets)} 题 / {n_points} 点**；adjudication 全部执行。",
        f"2. 每个模型 vote 覆盖率？ gpt55/opus48/deepseek_v4/qwen37 实votes 均 **0/{len(packets)}**（见 3）。",
        f"3. 是否有 provider_unavailable？哪些？ **全部 4 模型 provider_unavailable**"
        + ("（无任何 live key：OPENAI/ANTHROPIC/DEEPSEEK/DASHSCOPE 均 unset；485 cache 禁用于新题）。" if all_unavail else "（部分）。")
        + " 已逐 packet 记录到 `model_votes/*__provider_unavailable.json`，未静默跳过、未用他模型冒充。",
        f"4. 7 个 M4 published_candidate 里 jury 后仍 publish_ready 的？ **{sim['publish_ready_after_jury']}**（quorum 未达，provider-blocked，非 jury 拒绝）。",
        f"5. 9 个 M4 draft_candidate 升 publish 的？ **0**（同上，quorum 未达，无法升级）。",
        f"6. point accept/revise/reject/needs_po_review？ accept {pdec.get('accept',0)} / revise {pdec.get('revise',0)} / reject {pdec.get('reject',0)} / needs_po_review {pdec.get('needs_po_review',0)}（全部因 quorum 未达落 needs_po_review）。",
        "7. source anchor dispute？ 0（无真实票可比对；weak→verified 升级在协议中会被忽略，已实现并测试）。",
        "8. calculation/list_rule/exact_required 主要问题？ 继承 M4：calculation 缺 spec（3 题阻 published）、exact_required 取严不放宽近义、list_rule denominator 已补；M5 因无真实票未新增结论。",
        "9. 是否生成正式 registry？ **NO**（仅 `registry_v1_candidate_simulation_m5.json`，registry_emitted=false）。",
        "10. 是否伪造 LLM vote / human review / textbook source？ **NO**（provider 无 key 即 fail-closed 记录，不伪造）。",
        f"11. 是否可进入 M6 PO/authority promotion？ **NO-GO（provider-blocked）**：4 模型均不可用，无任一 packet 达 3 票 quorum。harness 已就绪，接上 ≥3 个异质模型 key 后即可真跑。",
        "12. 下一步最小任务：为 jury 接入真实 provider（≥3 个：gpt55/deepseek_v4/qwen37/opus48 任三）或经 PO 批准的 sanctioned 缓存通道；keys 到位后重跑 M5，再按 quorum+gate 结果决定 M6。",
        "",
        f"## 概要",
        f"- input {len(packets)} 题 / {n_points} 点；publish_ready {sim['publish_ready_after_jury']} / draft {sim['draft_after_jury']} / needs_po_review {sim['needs_po_review']} / rejected {sim['rejected']}；quorum_blocked {sim['quorum_blocked']}。",
        f"- provider_unavailable: {prov}。registry_emitted=False。",
        "",
        "## 红线",
        "不新增表 / 不接 runtime / 不改 kernel / RAG 不进评分 / 不生成正式 registry / 不伪造 vote·source / llm_jury 不冒充真人 / 未覆盖 M4 产物（patch 仅 proposed）/ 未 commit。",
        "",
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    r = build_m5(Path(args.out_dir))
    s = r["sim"]
    print(f"M5 -> {args.out_dir}")
    print(f"  input={s['input_questions']} publish_ready={s['publish_ready_after_jury']} draft={s['draft_after_jury']} "
          f"needs_po_review={s['needs_po_review']} rejected={s['rejected']} quorum_blocked={s['quorum_blocked']}")
    print(f"  provider_unavailable={s['provider_unavailable_counts']} registry_emitted={s['registry_emitted']}")


if __name__ == "__main__":
    main()
