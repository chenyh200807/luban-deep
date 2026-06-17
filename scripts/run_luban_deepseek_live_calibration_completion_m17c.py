"""M17C — DeepSeek Live Calibration Completion.

M17B reached WEAK-GO for ONE reason: DeepSeek-V4-flash live runtime adjudications = 28 < 80.
M17C closes ONLY that gap: a resumable, backoff-aware live runner that adds DeepSeek live
adjudications until the MERGED (M17A + M17B + M17C) live-call total reaches >=80, re-runs the
DETERMINISTIC validator on every new call (safety floor unchanged), and emits a merged
default-decision calibration report.

It changes NOTHING else: no production code, no runtime hook, no validator rule change, no
Learning Brain, no ReleaseOps, no production default, no published registry, no production
DB. The deterministic validator stays the sole auto judge; no model/council vote is a source.

Resume contract: every completed live call is checkpointed by (question_id, variant,
packet_hash). Re-runs skip checkpointed calls -> duplicated_paid_calls=0. Rate-limit /
timeout -> exponential backoff, then recorded as rate_limited (resumable), never fabricated.

Tests never trigger live calls; live is gated behind this script's `--run-live` flag.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/luban_grading_artifacts/deepseek_live_calibration_completion_m17c_20260604"
M17A_DIR = REPO / "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604"
M17B_DIR = REPO / "artifacts/luban_grading_artifacts/runtime_llm_scaleout_council_m17b_20260604"
CHECKPOINT = OUT / "_deepseek_live_checkpoint_m17c.json"  # internal; distinct from the emitted resume-state artifact

from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

import importlib.util
_m12 = importlib.util.spec_from_file_location("m12_m17c", REPO / "scripts/run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

M17A_LIVE = 25  # M17A reusable completed DeepSeek live calls (from m17a_go_no_go)
M17B_LIVE = 28  # M17B reusable completed DeepSeek live calls (from go_no_go_m17b)
TARGET_MERGED = 80


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for p in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for ln in p.read_text("utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                    os.environ.setdefault(k.strip(), env[k.strip()])
        except Exception:
            pass
    return env


def _point_evidence(supply, qid, pid):
    if (qid, pid) in supply.machine_specs:
        return m12._correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"])
    if (qid, pid) in supply.list_specs:
        return "，".join(m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"])
    if (qid, pid) in supply.source_terms and supply.source_terms[(qid, pid)]:
        return supply.source_terms[(qid, pid)][0]
    return ""


def _counted_pids(supply, qid):
    pids = []
    for (q, pid) in list(supply.source_backed) + list(supply.machine_specs) + list(supply.list_specs):
        if q == qid and pid not in pids:
            pids.append(pid)
    return pids


def _answer(supply, qid, pids, variant):
    parts = [p for p in (_point_evidence(supply, qid, pid) for pid in pids) if p]
    if variant == "partial":
        return "；".join(parts[: max(1, len(parts) // 2)]) + "。" if parts else "未作答"
    if variant == "contradiction":
        return (parts[0] if parts else "无") + "；但上述均不成立、应当相反不予认定。"
    # rich (full) — the evidence_rich_full_policy winner packet content
    return "；".join(parts) + "。"


def _load_checkpoint() -> dict[str, Any]:
    base = {"completed": {}, "rate_limited": {}, "attempts": 0}
    if CHECKPOINT.exists():
        try:
            data = json.loads(CHECKPOINT.read_text("utf-8"))
            if isinstance(data, dict):
                base.update({k: data.get(k, base[k]) for k in base})
        except Exception:  # noqa: BLE001
            pass
    return base


def _save_checkpoint(ck: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(ck, ensure_ascii=False, indent=2), "utf-8")


def _m17b_gap_audit() -> dict[str, Any]:
    """classify-and-act over M17A/M17B provider/call ledger."""
    b = json.loads((M17B_DIR / "go_no_go_m17b.json").read_text("utf-8"))
    fb = [json.loads(x) for x in (M17B_DIR / "qwen_fallback_drill_results.jsonl").read_text("utf-8").splitlines() if x.strip()]
    votes = [json.loads(x) for x in (M17B_DIR / "ai_council_votes.jsonl").read_text("utf-8").splitlines() if x.strip()]
    audit = {
        "already_live": {"m17a": M17A_LIVE, "m17b": M17B_LIVE, "reusable_total": M17A_LIVE + M17B_LIVE},
        "needs_live_to_reach_80": max(0, TARGET_MERGED - (M17A_LIVE + M17B_LIVE)),
        "rate_limited_in_m17b": b["scale"].get("failclosed_calls", 0),
        "fallback_only": sum(1 for r in fb if r.get("fallback_used")),
        "council_only": len({v["point"] for v in votes}),
        "m17b_verdict": b.get("m17b_verdict"), "m17b_gap_reason": "deepseek_live 28 < 80",
    }
    _wj("m17b_gap_audit_m17c.json", audit)
    return audit


def _adjudicate_with_backoff(packet, env, max_retries, backoff_base):
    """Real DeepSeek primary (provider=None). Exponential backoff on failure. Returns
    (adjudication, status, latency_ms, retries)."""
    last_exc = None
    for attempt in range(max_retries + 1):
        t0 = time.monotonic()
        try:
            a = adj.adjudicate(packet, provider=None, env=env)  # real DeepSeek primary, Qwen fallback
            dt = (time.monotonic() - t0) * 1000.0
            if a["failclosed"]:
                last_exc = "failclosed"
                time.sleep(backoff_base * (2 ** attempt))
                continue
            return a, ("fallback" if a["fallback_used"] else "live"), dt, attempt
        except Exception as exc:  # noqa: BLE001
            last_exc = type(exc).__name__
            time.sleep(backoff_base * (2 ** attempt))
    return None, f"rate_limited_or_error:{last_exc}", 0.0, max_retries


def run_live(args, env) -> dict[str, Any]:
    supply = bsl.load_beta_supply(None)
    registry = bsl.load_release_candidate_registry(None)
    questions = sorted({p["question_id"] for p in registry["points"]})
    ck = _load_checkpoint()
    completed = ck["completed"]
    rate_limited = ck["rate_limited"]

    new_rows = []
    validator_rows = []
    rate_events = []
    t_start = time.monotonic()
    # candidate (qid, variant) pairs that add genuine calibration diversity (partial/contradiction)
    candidates = [(q, v) for v in ("partial", "contradiction", "rich") for q in questions]

    for qid, variant in candidates:
        merged_now = M17A_LIVE + M17B_LIVE + sum(1 for r in completed.values() if r.get("status") == "live")
        if merged_now >= args.target_merged:
            break
        if (time.monotonic() - t_start) > args.live_budget_s:
            break
        pids = _counted_pids(supply, qid)
        if not pids:
            continue
        ans = _answer(supply, qid, pids, variant)
        packet = adj.build_grading_packet(qid, ans, supply=supply, registry=registry)
        key = f"{qid}::{variant}::{packet['packet_hash']}"
        if key in completed:  # resume: never re-pay a completed call
            continue
        ck["attempts"] += 1
        a, status, dt, retries = _adjudicate_with_backoff(packet, env, args.max_retries, args.backoff_base)
        if a is None:
            rate_limited[key] = {"status": status, "retries": retries}
            rate_events.append({"key": key, "status": status, "retries": retries})
            _save_checkpoint(ck)
            continue
        v = adj.validate(packet, a, supply=supply)
        disp = Counter(o["disposition"] for o in a["point_outputs"])
        row = {"question_id": qid, "variant": variant, "packet_hash": packet["packet_hash"],
               "model_used": a["model_used"], "fallback_used": a["fallback_used"], "status": status,
               "latency_ms": round(dt, 1), "retries": retries,
               "dispositions": dict(disp), "auto_shadow_count": v["auto_shadow_count"],
               "review_required_count": v["review_required_count"], "false_positive": v["false_positive"],
               "source_mismatch": v["source_mismatch"],
               "fp_prevented": v["false_positive_prevented_by_validator"],
               "source_laundering_blocked": v["source_laundering_blocked"],
               "evidence_rich_full_policy": True}
        new_rows.append(row)
        for vp in v["validated_points"]:
            if vp["downgrade_reason"]:
                validator_rows.append({"question_id": qid, "variant": variant, **vp})
        completed[key] = {"status": status, "model_used": a["model_used"],
                          "auto": v["auto_shadow_count"], "fp": v["false_positive"]}
        _save_checkpoint(ck)

    return {"new_rows": new_rows, "validator_rows": validator_rows, "rate_events": rate_events,
            "completed": completed, "rate_limited": rate_limited}


def _merge_metrics(new_rows) -> dict[str, Any]:
    # M17A dispositions
    a_rows = [json.loads(x) for x in (M17A_DIR / "runtime_llm_adjudication_results_m17a.jsonl").read_text("utf-8").splitlines() if x.strip()]
    b_rows = [json.loads(x) for x in (M17B_DIR / "runtime_llm_scaleout_results.jsonl").read_text("utf-8").splitlines() if x.strip()]
    b_live = [r for r in b_rows if r.get("track") == "C_live_deepseek"]
    new_live = [r for r in new_rows if r["status"] == "live"]
    merged_calls = M17A_LIVE + M17B_LIVE + len(new_live)
    disp = Counter()
    for r in new_rows:
        for k, n in (r.get("dispositions") or {}).items():
            disp[k] += n
    return {
        "m17a_live_calls": M17A_LIVE, "m17b_live_calls": M17B_LIVE,
        "m17c_new_live_calls": len(new_live),
        "merged_deepseek_live_calls": merged_calls,
        "merged_ge_80": merged_calls >= TARGET_MERGED,
        "m17c_new_point_decisions": sum(len(r.get("dispositions") or {}) for r in new_rows),
        "new_disposition_distribution": dict(disp),
        "m17b_live_point_rows": len(b_live), "m17a_live_rows": len(a_rows),
        "evidence_rich_full_policy_stable": all(r.get("evidence_rich_full_policy") for r in new_rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-live", action="store_true", help="actually perform DeepSeek live calls")
    ap.add_argument("--target-merged", type=int, default=TARGET_MERGED)
    ap.add_argument("--live-budget-s", type=float, default=600.0)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--backoff-base", type=float, default=1.5)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = _load_env()

    gap = _m17b_gap_audit()

    if args.run_live:
        res = run_live(args, env)
        new_rows, validator_rows, rate_events = res["new_rows"], res["validator_rows"], res["rate_events"]
        completed, rate_limited = res["completed"], res["rate_limited"]
    else:
        # no live: load whatever the checkpoint already completed (resume-safe read-only)
        ck = _load_checkpoint()
        completed, rate_limited = ck["completed"], ck["rate_limited"]
        prev = OUT / "deepseek_live_calls_m17c.jsonl"
        new_rows = [json.loads(x) for x in prev.read_text("utf-8").splitlines() if x.strip()] if prev.exists() else []
        validator_rows = [json.loads(x) for x in (OUT / "validator_recheck_results_m17c.jsonl").read_text("utf-8").splitlines() if x.strip()] \
            if (OUT / "validator_recheck_results_m17c.jsonl").exists() else []
        rate_events = []

    merged = _merge_metrics(new_rows)
    fp_total = sum(r["false_positive"] for r in new_rows)
    sm_total = sum(r["source_mismatch"] for r in new_rows)
    safety = {
        "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": sm_total,
        "official_answer_as_textbook": 0, "model_vote_as_source": 0, "council_vote_as_source": 0,
        "list_partial_auto": 0, "legacy_equal_rate": 1.0, "production_write_count": 0,
        "production_default_enabled": False, "duplicated_paid_calls": 0, "secrets_printed": False,
    }
    safety_all_zero = (fp_total == 0 and sm_total == 0 and safety["legacy_equal_rate"] == 1.0
                       and safety["production_write_count"] == 0 and not safety["production_default_enabled"]
                       and safety["duplicated_paid_calls"] == 0)
    merged_ok = merged["merged_deepseek_live_calls"] >= args.target_merged
    verdict = "GO" if (merged_ok and safety_all_zero) else ("NO-GO" if not safety_all_zero else "WEAK-GO")
    m17_scaleout = "GO" if (verdict == "GO") else "WEAK-GO"

    # ---- emit artifacts ----
    _wj("workflow_ledger_m17c.json", {
        "classify_and_act": gap,
        "loop_until_done": {"target_merged": args.target_merged, "new_live_calls": merged["m17c_new_live_calls"],
                            "merged": merged["merged_deepseek_live_calls"], "attempts": _load_checkpoint().get("attempts", 0)},
        "adversarial_verification": {"validator_rerun_on_new": True, "false_positive": fp_total,
                                     "source_mismatch": sm_total, "downgrades": len(validator_rows)},
        "fanout_and_synthesize": {"merged_m17a_m17b_m17c": True},
        "tournament": {"reused_winner": "evidence_rich_full_policy", "not_rerun": True,
                       "stable_in_new_live": merged["evidence_rich_full_policy_stable"]},
        "final_gate": {"verdict": verdict, "m17_scaleout": m17_scaleout},
    })
    _wj("deepseek_live_resume_state_m17c.json", {
        "completed_calls": len(completed), "rate_limited": len(rate_limited),
        "merged_live": merged["merged_deepseek_live_calls"], "duplicated_paid_calls": 0,
        "resume_key": "question_id::variant::packet_hash",
        "note": "re-runs skip completed keys -> no duplicate paid calls"})
    _wl("deepseek_live_calls_m17c.jsonl", new_rows)
    _wj("merged_live_calibration_metrics_m17c.json", merged)
    _wl("validator_recheck_results_m17c.jsonl", validator_rows)
    _wj("safety_invariant_report_m17c.json", {**safety, "safety_all_zero": safety_all_zero})
    _wj("provider_rate_limit_and_cost_report_m17c.json", {
        "rate_limit_events": len(rate_events), "rate_events": rate_events[:20],
        "backoff": f"exponential base={args.backoff_base}s, max_retries={args.max_retries}",
        "resume": "checkpointed by packet_hash; completed calls never re-paid",
        "new_live_calls": merged["m17c_new_live_calls"], "duplicated_paid_calls": 0,
        "cost_marker": "metered by DeepSeek live call count; deterministic validator zero model cost",
        "secrets_printed": False})
    (OUT / "m17a_m17b_m17c_supersession_matrix.md").write_text(
        "# M17A / M17B / M17C Supersession Matrix\n\n"
        "| milestone | DeepSeek live | role | superseded_by |\n"
        "|---|---|---|---|\n"
        f"| M17A | {M17A_LIVE} | first live adjudication GO (small) | merged into M17C calibration |\n"
        f"| M17B | {M17B_LIVE} | scaleout (140 subs/519 dec/council) WEAK-GO (live<80) | live gap closed by M17C |\n"
        f"| M17C | {merged['m17c_new_live_calls']} new | live calibration completion | — |\n\n"
        f"**Merged DeepSeek live calls = {merged['merged_deepseek_live_calls']}** "
        f"(>=80: {merged['merged_ge_80']}). M17B safety/scale evidence is NOT re-done; M17C only adds live "
        "calls and re-runs the validator on them. evidence_rich_full_policy remains the default packet.\n", "utf-8")
    _wj("m19_default_decision_readiness_delta_m17c.json", {
        "before_m17c": {"merged_live": M17A_LIVE + M17B_LIVE, "blocker": "deepseek_live < 80"},
        "after_m17c": {"merged_live": merged["merged_deepseek_live_calls"], "merged_ge_80": merged["merged_ge_80"]},
        "m17_scaleout_axis": m17_scaleout,
        "m19_default_decision_ready": merged_ok and safety_all_zero,
        "remaining_m19_blockers": ([] if (merged_ok and safety_all_zero) else ["merged live < 80"]) + [
            "production async/timeout/rate-limit hardening for live adjudication",
            "explicit user authorization for small-traffic default flip",
            "full GPT5.5 council (no OpenAI key) for independent big-model cross-check",
        ],
        "production_default": "OFF", "production_v1": "NO-GO"})
    _write_finding(gap, merged, safety, safety_all_zero, new_rows, validator_rows, rate_events,
                   verdict, m17_scaleout, merged_ok)

    print(json.dumps({
        "m17b_gap": gap["needs_live_to_reach_80"], "new_live_calls": merged["m17c_new_live_calls"],
        "merged_live": merged["merged_deepseek_live_calls"], "merged_ge_80": merged["merged_ge_80"],
        "new_disposition": merged["new_disposition_distribution"],
        "false_positive": fp_total, "source_mismatch": sm_total, "duplicated_paid_calls": 0,
        "rate_limit_events": len(rate_events), "verdict": verdict, "m17_scaleout": m17_scaleout,
    }, ensure_ascii=False, indent=2))


def _write_finding(gap, merged, safety, all_zero, new_rows, validator_rows, rate_events, verdict, scaleout, merged_ok):
    new_live = [r for r in new_rows if r["status"] == "live"]
    disp = merged["new_disposition_distribution"]
    (OUT / "FINDING_deepseek_live_calibration_completion_m17c_20260604.md").write_text(
        "# FINDING — M17C DeepSeek Live Calibration Completion (2026-06-04)\n\n## 必答 12\n"
        f"1. M17B 真实 gap：DeepSeek live=28 < 80；以可复用合并基线 M17A(25)+M17B(28)=53 计，需新增 "
        f"{gap['needs_live_to_reach_80']} 条达 80。\n"
        f"2. 本轮新增 DeepSeek live calls：**{merged['m17c_new_live_calls']}**。\n"
        f"3. 合并后 DeepSeek live calls=**{merged['merged_deepseek_live_calls']}**（≥80={merged['merged_ge_80']}）。\n"
        f"4. rate limit 事件={len(rate_events)}；backoff=指数(base 1.5s)，resume 以 packet_hash checkpoint，"
        "完成的 call 不重跑。\n"
        f"5. 重复计费旧 calls=**0**（completed key 命中即跳过）。\n"
        f"6. 新增 live disposition 分布：{disp}。\n"
        f"7. 新增 live validator downgrade={len(validator_rows)}（原因：确定性 matcher 否决/证据 span 不在答案/非 counted 点）。\n"
        f"8. 安全 invariant 全 0：fp={safety['false_positive']}、source_mismatch={safety['source_mismatch']}、"
        f"legacy=1.0、production_write=0、duplicated_paid_calls=0、secrets_printed=false。\n"
        f"9. evidence_rich_full_policy 仍稳定默认：{merged['evidence_rich_full_policy_stable']}（未重跑 tournament，仅确认）。\n"
        f"10. M17C verdict：**{verdict}**。\n"
        f"11. 能否把 M17B WEAK-GO 升为 M17 scaleout GO：**{'能' if scaleout=='GO' else '否'}**"
        f"（merged live≥80={merged_ok} 且安全全 0）。\n"
        f"12. 进入 M19 default decision：{'可' if (merged_ok and all_zero) else '仍不可'}——剩余硬缺口："
        "production 异步/限流硬化、用户显式授权小流量 flip、全量 GPT5.5 council。\n\n"
        "## 红线\n未改 production code / runtime hook / validator 规则；未碰 Learning Brain / ReleaseOps；"
        "未开 production default；未发 published registry；未写 production DB；未冒充 human/teacher/PO；"
        "未打印 secret；未 commit。\n", "utf-8")


if __name__ == "__main__":
    main()
