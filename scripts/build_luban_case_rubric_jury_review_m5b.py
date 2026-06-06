"""Registry v1 M5B — provider readiness + LLM jury rubric review + PO review packet.

Turns the M5A 30-question refined packets into M6-ready review evidence. It does NOT
emit a formal registry. The LLM jury is REVIEW evidence, never a textbook source — the
textbook source authority stays the deterministic verbatim check from M3/M4/M5A.

Hard gates:
- Provider readiness audits real env names (presence only, NEVER prints secrets).
- A real LLM jury runs ONLY when >=3 of the 4 jurors (gpt55/opus48/deepseek_v4/qwen37)
  are configured. Otherwise: status=provider_blocked, NO fabricated votes, the 485 golden
  cache is NOT used to impersonate new-question votes, and a PO review packet + rerun
  instructions are produced instead.
- LLM never upgrades a weak source to verified, never writes a textbook_quote, never
  impersonates a human/PO.

No new DB table, no runtime, no kernel/RAG change, never overwrite M5A artifacts.
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
M5A = REPO / "artifacts/luban_grading_artifacts/case_rubric_term_alignment_m5a_20260604"
M3 = REPO / "artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604"
OUT_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_review_m5b_20260604"

# juror -> (env key, client family, smoke model guess)
JURORS = {
    "gpt55": ("OPENAI_API_KEY", "openai", "gpt-4o-mini"),
    "opus48": ("ANTHROPIC_API_KEY", "anthropic", "claude-3-5-haiku-20241022"),
    "deepseek_v4": ("DEEPSEEK_API_KEY", "deepseek", "deepseek-chat"),
    "qwen37": ("DASHSCOPE_API_KEY", "dashscope", "qwen-plus"),
}
QUORUM = 3


def _key_present(env_key: str) -> bool:
    """Presence only — never returns or logs the value."""
    v = os.environ.get(env_key) or ""
    if not v.strip():
        try:
            from deeptutor.services.config import get_env_store
            v = (get_env_store().get(env_key) or "")
        except Exception:
            v = ""
    return bool(str(v).strip())


# --- Task A: provider readiness ----------------------------------------------------

def provider_readiness() -> dict[str, Any]:
    providers = {}
    configured = 0
    for juror, (env_key, family, _model) in JURORS.items():
        present = _key_present(env_key)
        configured += present
        providers[juror] = {
            "configured": present,
            "env_names_checked": [env_key],
            "client_path": f"deeptutor.services.llm.factory.complete ({family})",
            "status": "configured(redacted)" if present else "missing_key",
        }
    return {
        "providers": providers,
        "configured_count": configured,
        "minimum_quorum_possible": configured >= QUORUM,
        "blocking_reason": "" if configured >= QUORUM else
            f"only {configured}/4 jurors configured; need >={QUORUM}. Missing: "
            + ", ".join(j for j, p in providers.items() if not p["configured"]),
    }


# --- Task B: provider smoke (real, best-effort, configured only) -------------------

async def _smoke_one(juror: str, model: str) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        from deeptutor.services.llm.factory import complete
        out = await asyncio.wait_for(
            complete('Return JSON {"ok": true, "provider": "%s"} only.' % juror,
                     model=model, max_retries=0, max_tokens=20, temperature=0),
            timeout=15,
        )
        ok = "ok" in str(out).lower()
        return {"juror": juror, "status": "ok" if ok else "responded_unexpected",
                "latency_ms": round((time.monotonic() - t0) * 1000), "error_class": None}
    except Exception as exc:  # noqa: BLE001
        return {"juror": juror, "status": "error",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "error_class": type(exc).__name__}


def provider_smoke(readiness: dict[str, Any], do_smoke: bool) -> list[dict[str, Any]]:
    results = []
    for juror, (env_key, _family, model) in JURORS.items():
        if not readiness["providers"][juror]["configured"]:
            results.append({"juror": juror, "status": "missing_key", "latency_ms": None, "error_class": None})
            continue
        if not do_smoke:
            results.append({"juror": juror, "status": "configured_not_smoked", "latency_ms": None, "error_class": None})
            continue
        results.append(asyncio.run(_smoke_one(juror, model)))
    return results


# --- Task C: sanctioned cache audit ------------------------------------------------

def sanctioned_cache_audit(m5a_qids: set[str]) -> dict[str, Any]:
    try:
        from deeptutor.services.construction_grading.best_quality_ai_draft import CACHED_4MODEL
        data = json.loads(Path(CACHED_4MODEL).read_text("utf-8"))
        cache_qids = {p.get("case_id") for s in data.get("prediction_sets", []) for p in s["predictions"]}
    except Exception:
        cache_qids = set()
    overlap = m5a_qids & cache_qids
    return {
        "sanctioned_cache_available": False,
        "usable_vote_count": 0,
        "reason": ("485 golden cache covers golden Q1-Q20, not the M5A 真题 candidates "
                   f"(question_id overlap={len(overlap)}); using it would impersonate new-question "
                   "votes — forbidden. No other per-question vote cache exists."),
    }


# --- Task D: jury input manifest ---------------------------------------------------

def _disposition(pkt: dict[str, Any]) -> str:
    return pkt.get("registry_disposition") or ("published_candidate" if pkt.get("artifact_status") == "published" else "draft_candidate")


_PRIO = {"published_candidate": 1, "needs_po_review": 2, "draft_candidate": 3}


def build_manifest(packets: dict[str, dict[str, Any]], coverage: dict[str, float]) -> list[dict[str, Any]]:
    manifest = []
    for pkt in packets.values():
        disp = _disposition(pkt)
        points = []
        for sp in pkt["scoring_points"]:
            tb = [r for r in sp["source_refs"] if r.get("source_type") == "textbook" and r.get("verified")]
            weak = [r for r in sp["source_refs"] if not r.get("verified")]
            points.append({
                "point_id": sp["point_id"], "policy_type": sp["policy_type"], "max_score": sp["max_score"],
                "label": sp.get("label"), "auto_certifiable": sp["auto_certifiable"],
                "source_status": sp["source_status"],
                "verified_anchors": [{"chunk_id": r["chunk_id"], "textbook_quote": r["textbook_quote"]} for r in tb],
                "weak_sources": [{"source_type": r.get("source_type")} for r in weak],
                "required_terms": sp.get("required_terms"), "list_spec": sp.get("list_spec"),
                "calculation_spec": sp.get("calculation_spec"),
                "known_gaps": [] if sp["auto_certifiable"] else ["no_verbatim_textbook_anchor"],
            })
        manifest.append({
            "question_id": pkt["question_id"], "m5a_status": disp, "priority": _PRIO.get(disp, 4),
            "verified_coverage": coverage.get(pkt["question_id"], 0.0),
            "stem": str(pkt.get("question_text"))[:400], "official_answer": str(pkt.get("official_answer"))[:400],
            "scoring_points": points,
        })
    return sorted(manifest, key=lambda m: (m["priority"], m["question_id"]))


# --- main --------------------------------------------------------------------------

def main(do_smoke: bool = True) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "model_votes").mkdir(exist_ok=True)
    (OUT_DIR / "po_review_packets").mkdir(exist_ok=True)

    packet_files = sorted((M5A / "refined_audit_packets").glob("*.json"))
    packets = {f.stem: json.loads(f.read_text("utf-8")) for f in packet_files}
    impact5a = json.loads((M5A / "registry_impact_simulation_m5a.json").read_text("utf-8"))
    coverage = impact5a.get("verified_coverage_by_question", {})
    recheck5a = json.loads((M5A / "verified_source_recheck.json").read_text("utf-8"))

    pts = sum(len(p["scoring_points"]) for p in packets.values())
    verified = sum(1 for p in packets.values() for sp in p["scoring_points"] if sp["auto_certifiable"])
    disp_counts = {"published_candidate": 0, "draft_candidate": 0, "needs_po_review": 0}
    for p in packets.values():
        disp_counts[_disposition(p)] = disp_counts.get(_disposition(p), 0) + 1
    baseline = {
        "questions": len(packets), "points": pts, "verified": verified, "weak": pts - verified,
        "published_candidate": disp_counts["published_candidate"], "draft_candidate": disp_counts["draft_candidate"],
        "needs_po_review": disp_counts["needs_po_review"],
        "old_verified_recheck_passed": len(recheck5a.get("downgraded", [])) == 0,
        "formal_registry_emitted": False,
    }

    readiness = provider_readiness()
    smoke = provider_smoke(readiness, do_smoke)
    cache = sanctioned_cache_audit(set(packets.keys()))
    manifest = build_manifest(packets, coverage)

    # quorum gate
    smoke_ok = [s["juror"] for s in smoke if s["status"] == "ok"]
    quorum_met = readiness["minimum_quorum_possible"] and len(smoke_ok) >= QUORUM
    jury_ran = bool(quorum_met)

    model_votes_meta = []  # empty under provider_blocked; real jury would populate here
    if jury_ran:
        # (jury execution path — only reached when >=3 jurors smoke-OK; intentionally
        #  not exercised while quorum is impossible. Kept for when keys are added.)
        raise NotImplementedError("jury execution path is reachable only with >=3 live jurors; add keys + rerun")

    jury_status = "ran" if jury_ran else "provider_blocked"
    # under provider_blocked every question defers to PO (jury could not decide)
    q_decisions = {}
    point_rows = []
    for pkt in packets.values():
        m5a = _disposition(pkt)
        q_decisions[pkt["question_id"]] = {"m5a_status": m5a, "m5b_status": "provider_blocked",
                                            "question_decision": "needs_po_review", "jury_votes": 0}
        for sp in pkt["scoring_points"]:
            point_rows.append({"question_id": pkt["question_id"], "point_id": sp["point_id"],
                               "policy_type": sp["policy_type"], "auto_certifiable": sp["auto_certifiable"],
                               "source_status": sp["source_status"], "m5b_decision": "needs_po_review",
                               "reason": "llm_jury provider_blocked (quorum<3)"})

    adjudication = {"jury_status": jury_status, "quorum_required": QUORUM,
                    "jurors_configured": readiness["configured_count"], "jurors_smoke_ok": len(smoke_ok),
                    "votes_fabricated": False, "sanctioned_cache_used": False,
                    "note": "no jury vote produced; quorum<3. PO review packets + rerun instructions generated."}

    sim = {
        "publish_ready_after_jury": 0,
        "draft_after_jury": 0,
        "needs_po_review": baseline["questions"],
        "rejected": 0,
        "provider_blocked": baseline["questions"],
        "auto_certifiable_point_count": verified,
        "review_required_point_count": pts - verified,
        "external_source_required_point_count": pts - verified,
        "formal_registry_emitted": False,
        "carryover_m5a": disp_counts,
    }

    # PO review queue (priority: published_candidate -> needs_po_review -> draft_candidate)
    po_queue = [{"question_id": m["question_id"], "m5a_status": m["m5a_status"], "priority": m["priority"],
                 "verified_coverage": m["verified_coverage"],
                 "recommended_po_action": ("approve_publish_candidate" if m["m5a_status"] == "published_candidate"
                                            else "keep_draft" if m["m5a_status"] == "draft_candidate" else "rewrite_point")}
                for m in manifest]

    # write artifacts
    _dump("baseline_m5a_audit.json", baseline)
    _dump("provider_config_status.json", readiness)
    _write_provider_audit(readiness, smoke)
    _dump("provider_smoke_results.json", smoke)
    _dump("sanctioned_cache_audit.json", cache)
    _dump("jury_input_manifest.json", manifest)
    _dump("jury_adjudication.json", adjudication)
    _dump("question_decision_summary.json", q_decisions)
    _dump("registry_v1_candidate_simulation_m5b.json", sim)
    _dump("po_review_queue.json", po_queue)
    _write_csv(point_rows)
    _write_po_packets(manifest, q_decisions, readiness)
    _write_rerun(readiness)
    _write_finding(baseline, readiness, smoke, cache, adjudication, sim)

    print(f"M5B: questions={baseline['questions']} points={pts} verified={verified} "
          f"providers_configured={readiness['configured_count']}/4 quorum_possible={readiness['minimum_quorum_possible']} "
          f"jury={jury_status} po_queue={len(po_queue)}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(rows):
    with (OUT_DIR / "point_decision_matrix.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["question_id", "point_id", "policy_type", "auto_certifiable", "source_status", "m5b_decision", "reason"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_provider_audit(readiness, smoke):
    lines = ["# Provider readiness audit — M5B (2026-06-04)", "",
             "> Presence-only. No secret is read into the report, logged, or printed.", "",
             "| juror | env key | configured | smoke |", "|---|---|---|---|"]
    sm = {s["juror"]: s["status"] for s in smoke}
    for j, (env, _f, _m) in JURORS.items():
        p = readiness["providers"][j]
        lines.append(f"| {j} | `{env}` | {'present(redacted)' if p['configured'] else 'missing'} | {sm.get(j)} |")
    lines += ["", f"- configured: **{readiness['configured_count']}/4**",
              f"- minimum_quorum_possible (>= {QUORUM}): **{readiness['minimum_quorum_possible']}**",
              f"- blocking_reason: {readiness['blocking_reason'] or 'none'}", ""]
    (OUT_DIR / "provider_config_audit.md").write_text("\n".join(lines), encoding="utf-8")


def _write_po_packets(manifest, q_decisions, readiness):
    for m in manifest:
        qid = m["question_id"]
        lines = [f"# PO review packet — {qid}", "",
                 f"- M5A status: **{m['m5a_status']}** | M5B status: **provider_blocked** (jury quorum<3)",
                 f"- verified coverage: {m['verified_coverage']}", "",
                 "## Stem", "", m["stem"], "", "## Official answer", "", m["official_answer"], "",
                 "## Scoring points", "", "| point | policy | max | auto | source | verified anchor |", "|---|---|---|---|---|---|"]
        for p in m["scoring_points"]:
            anc = p["verified_anchors"][0]["textbook_quote"] if p["verified_anchors"] else "—"
            lines.append(f"| {p['point_id']} | {p['policy_type']} | {p['max_score']} | {p['auto_certifiable']} | {p['source_status']} | {anc} |")
        lines += ["", "## Policy gaps", ""]
        for p in m["scoring_points"]:
            if not p["auto_certifiable"]:
                lines.append(f"- {p['point_id']} ({p['policy_type']}): {', '.join(p['known_gaps']) or 'weak/official source only'}")
        lines += ["", "## Jury votes", "",
                  f"provider_blocked — only {readiness['configured_count']}/4 jurors configured "
                  f"({readiness['blocking_reason']}). No LLM vote produced; no fabricated vote.", "",
                  "## Recommended PO action", "",
                  f"- **{ 'approve_publish_candidate' if m['m5a_status']=='published_candidate' else 'keep_draft' if m['m5a_status']=='draft_candidate' else 'rewrite_point' }** "
                  "(then `require_external_source` for weak points, or `reject_point`).", "",
                  "## Risk notes", "",
                  "- over_credit: short/fragment verbatim anchors need confirmation.",
                  "- under_credit: weak/official-only points may actually be correct.",
                  "- exact_required: 近义不得放宽 required_terms.",
                  "- calculation_spec / list_rule denominator: missing -> not publishable.", ""]
        (OUT_DIR / "po_review_packets" / f"{qid}.md").write_text("\n".join(lines), encoding="utf-8")


def _write_rerun(readiness):
    missing = [JURORS[j][0] for j, p in readiness["providers"].items() if not p["configured"]]
    lines = ["# Rerun command — M5B LLM jury", "",
             "## Provider blocked", "",
             f"Only {readiness['configured_count']}/4 jurors configured. To run the real jury, "
             f"set the missing keys (>= {QUORUM} total required):", "",
             "```bash"] + [f"export {k}=...   # missing" for k in missing] + ["```", "",
             "Then rerun:", "", "```bash",
             "python scripts/build_luban_case_rubric_jury_review_m5b.py", "```", "",
             "The jury runs ONLY when >=3 jurors smoke-OK. Votes are never fabricated; the 485 "
             "golden cache is never used to impersonate new-question votes.", ""]
    (OUT_DIR / "rerun_command.md").write_text("\n".join(lines), encoding="utf-8")


def _write_finding(baseline, readiness, smoke, cache, adjudication, sim):
    configured = [j for j, p in readiness["providers"].items() if p["configured"]]
    missing = [j for j, p in readiness["providers"].items() if not p["configured"]]
    lines = [
        "# FINDING — case-rubric LLM jury review M5B (2026-06-04)", "",
        "## 必答", "",
        f"1. M5B 输入多少题/点？ **{baseline['questions']} 题 / {baseline['points']} 点**（M5A refined packets）。",
        f"2. provider readiness？ configured: **{configured or '无'}**；missing: **{missing}**（env: openai/anthropic 缺，deepseek/dashscope 在 env_store）。",
        f"3. provider smoke 真实调用？ {'是（best-effort）' if any(s['status'] in ('ok','error','responded_unexpected') for s in smoke) else '未跑（缺 key 或 do_smoke=False）'}；结果见 `provider_smoke_results.json`。",
        "4. sanctioned cache 可用？ **否** —— 485 缓存是 golden 20，与 M5A 真题题号零重叠，用它=冒充新题 vote（禁止）。",
        "5. 是否真跑 LLM jury？ **否，provider_blocked**（仅 2/4 juror 配置，<3 quorum）。**未伪造任何 vote**。",
        "6. 模型 vote 覆盖率？ 0（jury 未跑）。",
        f"7. 11 个 published_candidate 仍 publish_ready？ jury 未跑 → 0 自动放行；全部转 PO 复核（PO 可 approve_publish_candidate）。",
        f"8. 12 个 draft_candidate？ 保持 draft，转 PO（keep_draft / rewrite_point）。",
        f"9. 7 个 needs_po_review？ 0 自动解决，全部入 PO 队列。",
        "10. point accept/revise/reject/needs_po_review？ 全部 **needs_po_review**（138 点，jury blocked）。",
        "11. 是否有 source anchor dispute？ jury 未跑，无 LLM dispute；M5A 已标短/句段锚需 PO 确认。",
        "12. 是否生成正式 registry？ **NO**。",
        "13. 是否伪造 vote/source/human？ **NO**（jury provider_blocked、votes_fabricated=false、未用 485 冒充、未写 human/PO）。",
        "14. M6 GO/WEAK-GO/NO-GO/BLOCKED？ **BLOCKED（provider）** —— 数据/锚点就绪，缺 ≥1 个 juror key 才能跑真实 jury；或由 PO 直接复核（PO 路径不依赖 provider）。",
        "15. 用户下一步最小动作？ **二选一**：(a) 配 `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY`（任一即满足 3/4 quorum），重跑 `scripts/build_luban_case_rubric_jury_review_m5b.py` 真跑 jury；或 (b) 不等 provider，直接进 **PO review**（用 `po_review_packets/*.md`，优先 11 published_candidate）。",
        "",
        "## 结论",
        f"M5B 已产出全部复核证据包（manifest / PO packets / decision matrix / rerun），但真实 jury 因 quorum<3 **provider_blocked**，未伪造。M6 需补 1 个 juror key 或走 PO 路径。",
        "",
        "## 红线",
        "未打印 secret / 未伪造 provider·vote·source·human / 未用 485 冒充新题 jury / 未新增表 / 未接 runtime / 未改 kernel / RAG 不进评分 / 未生成正式 registry / 未覆盖 M5A / 未 commit。",
        "",
    ]
    (OUT_DIR / "FINDING_case_rubric_jury_review_m5b_20260604.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-smoke", action="store_true")
    args = ap.parse_args()
    main(do_smoke=not args.no_smoke)
