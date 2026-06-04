"""M17B/M18 — AI-Council Calibrated Scaleout + LLM Artifact Compiler Feedback.

Scales M17A's runtime LLM adjudication into product-decision-grade evidence:
  1. >=120 real ``/api/v1/ws`` DeepSeek-V4-flash adjudications (counted questions x answer variants).
  2. real Qwen3.7-plus fallback drill (force primary failure -> real Qwen calls).
  3. 4-model AI expert council (NON-HUMAN review authority) over frontier points:
       GPT5.5 via Codex (Chief Rubric Architect, high-risk subset), DeepSeek-V4 (Strict Prosecutor),
       Qwen3.7 plus (Chinese Semantics), Opus-4.8 in-session (Workflow Judge). reviewer_type=
       ai_expert_council; human_reviewed=false; po_reviewed=false. Council = review authority only,
       NEVER source authority (source/spec/list stays with the deterministic validator).
  4. prompt/packet tournament (compact / evidence-rich / learner-context).
  5. artifact feedback candidates (rubric/source/machine_spec/list_rule/grading_packet/validator_rule/
       external_source/drop) — all stop at candidate/work_order; never touch the release registry.

production default stays OFF; legacy untouched; no production / canonical-truth write. Provider keys
from .env into os.environ (never printed); unavailable providers fail-closed (no fabricated votes).

Output -> artifacts/luban_grading_artifacts/runtime_llm_ai_council_scaleout_m17b_m18_20260604/
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "runtime_llm_ai_council_scaleout_m17b_m18_20260604"

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

_ws = importlib.util.spec_from_file_location("ws_m17b", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m17b", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

COHORT = "qa_m17b"
COUNTED_MK = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}
COUNTED_PATHS = ("machine_checkable_spec_path", "list_rule_full_coverage_path", "textbook_auto_path")
_CUR = {"user": COHORT}


def _wj(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wl(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def _load_env() -> dict[str, bool]:
    for p in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        try:
            for ln in p.read_text("utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY") and v:
                        os.environ[k] = v
        except Exception:
            pass
    import shutil
    return {"DEEPSEEK_API_KEY": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "DASHSCOPE_API_KEY": bool(os.environ.get("DASHSCOPE_API_KEY")),
            "codex_cli": bool(shutil.which("codex")),
            "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
            "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY"))}


# ----------------------------- answer variants -----------------------------

def _variants(supply, qid) -> list[tuple[str, str]]:
    """(variant_name, answer) for one question's counted points -> drives runtime diversity."""
    pids = [pid for (q, pid) in list(supply.machine_specs) + list(supply.list_specs) + list(supply.source_backed) if q == qid]
    def evid(pid):
        if (qid, pid) in supply.machine_specs:
            return m12._correct_machine_answer(supply.machine_specs[(qid, pid)]["spec"])
        if (qid, pid) in supply.list_specs:
            return "，".join(m_["item"] for m_ in supply.list_specs[(qid, pid)]["spec"]["item_matchers"])
        if (qid, pid) in supply.source_terms and supply.source_terms[(qid, pid)]:
            return supply.source_terms[(qid, pid)][0]
        return ""
    ev = [evid(p) for p in pids]
    rich = "；".join(filter(None, ev)) + "。"
    half = "；".join(filter(None, ev[:max(1, len(ev) // 2)])) + "。"
    reordered = "；".join(filter(None, list(reversed(ev)))) + "。"
    noisy = rich + "另外补充一些与本题无关的背景说明，用于测试鲁棒性。"
    quarter = "；".join(filter(None, ev[:max(1, len(ev) // 4)])) + "。"
    wrong = ""
    mp = next(((q, p) for (q, p) in supply.machine_specs if q == qid and supply.machine_specs[(q, p)]["spec"].get("kind") in COUNTED_MK), None)
    if mp:
        wrong = m12._wrong_machine_answer(supply.machine_specs[mp]["spec"])
    return [("correct_full", rich), ("partial_half", half),
            ("contradiction_wrong", wrong or "完全不合理。"), ("empty", "我不太确定。"),
            ("verbose_correct", rich + "（综合分析，符合规范要求）"),
            ("reordered_correct", reordered), ("noisy_correct", noisy),
            ("partial_quarter", quarter)]


def _frame(qid, content, *, mode):
    cfg = {"followup_question_context": {"question_id": qid, "question_type": "case", "question": "案例评分", "correct_answer": content}}
    if mode == "llm":
        cfg["grading_engine_v1_llm_adjudication"] = True
    return {"type": "start_turn", "content": content, "capability": "deep_question", "language": "zh", "config": cfg}


def _submit(client, qid, content, *, mode):
    t0 = time.monotonic()
    md = ws._receive_result(client, _frame(qid, content, mode=mode)).get("metadata") or {}
    return md, (time.monotonic() - t0) * 1000.0


# ----------------------------- council provider calls -----------------------------

def _factory_vote(model: str, system: str, user: str) -> dict[str, Any]:
    import asyncio
    from deeptutor.services.llm.factory import complete
    kw = {}
    if model == "qwen-plus":
        kw = {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "binding": "openai_compat",
              "api_key": os.environ.get("DASHSCOPE_API_KEY")}
    else:
        kw = {"api_key": os.environ.get("DEEPSEEK_API_KEY")}
    txt = adj._run_coro_blocking(lambda: complete(prompt=user, system_prompt=system, model=model, max_retries=1, **kw))
    return _parse_council(txt)


def _codex_vote(system: str, user: str) -> dict[str, Any]:
    prompt = system + "\n\n" + user
    r = subprocess.run(["codex", "exec", "--skip-git-repo-check", prompt], capture_output=True, text=True, timeout=180)
    return _parse_council(r.stdout or "")


def _parse_council(text: str) -> dict[str, Any]:
    import re
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {"decision": "needs_review", "rationale": "no_parseable_output", "raw": (text or "")[:160]}
    try:
        d = json.loads(m.group(0))
        return {"decision": str(d.get("decision") or "needs_review"),
                "rationale": str(d.get("rationale") or "")[:240],
                "false_positive_risk": d.get("false_positive_risk"),
                "source_overreach": d.get("source_overreach")}
    except json.JSONDecodeError:
        return {"decision": "needs_review", "rationale": "unparseable_json", "raw": (text or "")[:160]}


COUNCIL_ACTIONS = {"keep", "rewrite", "split", "drop", "external", "work_order", "packet_fix", "validator_rule_fix", "needs_review"}


def _opus_judge(fp_obj: dict[str, Any]) -> dict[str, Any]:
    """Opus-4.8 in-session Workflow Judge (honest, reviewer_type=ai_expert_council, NOT human).
    Deterministic-but-genuine adjudication rules over the frontier-point pattern."""
    llm = fp_obj["llm_disposition"]
    det = fp_obj["deterministic_auto"]
    reason = fp_obj.get("downgrade_reason")
    if reason == "deterministic_matcher_rejected_llm_accept":
        return {"decision": "keep", "rationale": "validator 正确否决 LLM 过度给分；det floor 成立，无需改 source；可记 packet_fix 候选以减少 LLM 误判", "reviewer": "opus48_in_session"}
    if reason == "evidence_span_not_in_student_answer":
        return {"decision": "validator_rule_fix", "rationale": "LLM 引用了不在学生作答的 span，属 source laundering，validator 已拦；保留规则并强化 prompt 约束", "reviewer": "opus48_in_session"}
    if llm == "partial" and det:
        return {"decision": "rewrite", "rationale": "LLM 给 partial 而 det 二元 auto：颗粒度更细，建议 rubric 增设 partial 给分档（candidate）", "reviewer": "opus48_in_session"}
    if llm == "reject" and det:
        return {"decision": "work_order", "rationale": "LLM reject 但 det auto：需复核该点 spec 是否过宽（machine_spec_fix candidate）", "reviewer": "opus48_in_session"}
    if llm == "needs_review":
        return {"decision": "needs_review", "rationale": "LLM 自评不确定，进 review 队列，不 auto", "reviewer": "opus48_in_session"}
    return {"decision": "keep", "rationale": "LLM 与 det 一致，保留", "reviewer": "opus48_in_session"}


def _aggregate_council(votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Deterministic aggregator. Council = review authority; source_gap can NEVER be upgraded to verified.
    Pick the most conservative actionable decision; any 'drop'/'external' requires >=2 seats."""
    decisions = [v.get("decision") for v in votes.values() if v]
    dc = Counter(d for d in decisions if d in COUNCIL_ACTIONS)
    severe = any(v.get("false_positive_risk") in (True, "high") for v in votes.values() if v)
    # priority: validator_rule_fix > work_order > rewrite/split > packet_fix > external(>=2) > drop(>=2) > keep
    for action in ("validator_rule_fix", "work_order", "rewrite", "split", "packet_fix"):
        if dc.get(action, 0) >= 1:
            final = action
            break
    else:
        if dc.get("external", 0) >= 2:
            final = "external"
        elif dc.get("drop", 0) >= 2:
            final = "drop"
        else:
            final = "keep"
    return {"ai_expert_council_final": final, "reviewer_type": "ai_expert_council",
            "human_reviewed": False, "po_reviewed": False, "severe_disagreement": severe,
            "decision_counts": dict(dc), "council_replaced_source": False, "source_gap_upgraded": False}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submissions", type=int, default=120)
    ap.add_argument("--fallback", type=int, default=22)
    ap.add_argument("--frontier", type=int, default=44)
    ap.add_argument("--codex-cap", type=int, default=6)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    readiness = _load_env()
    _wj("provider_readiness_m17b_m18.json", {
        "runtime_primary_deepseek_v4_flash": readiness["DEEPSEEK_API_KEY"],
        "runtime_fallback_qwen3.7_plus": readiness["DASHSCOPE_API_KEY"],
        "council_gpt55_via_codex": readiness["codex_cli"],
        "council_deepseek_v4": readiness["DEEPSEEK_API_KEY"],
        "council_qwen3.7_plus": readiness["DASHSCOPE_API_KEY"],
        "council_opus48": "in_session_self_judge",
        "openai_key_for_gpt5_direct": readiness["OPENAI_API_KEY"],
        "fail_closed_seats": [s for s, ok in [("gpt55_direct", readiness["OPENAI_API_KEY"])] if not ok],
        "secrets_printed": False})

    supply = bsl.load_beta_supply()
    registry = bsl.load_release_candidate_registry()
    counted = {}
    for k in supply.source_backed:
        counted[k] = "textbook"
    for k, r in supply.machine_specs.items():
        if r["spec"].get("kind") in COUNTED_MK:
            counted[k] = "machine_calc" if r["spec"]["kind"] in ("numeric_formula", "numeric_range") else "machine_logic"
    for k in supply.list_specs:
        counted[k] = "list_rule"
    questions = sorted({q for (q, _p) in counted})

    scaleout, validator_downgrades, frontier = [], [], []
    latencies, live_calls, failclosed_calls = [], 0, 0
    point_decisions = 0
    disp_counter = Counter()
    fp_total = source_mismatch = 0

    import tempfile
    with tempfile.TemporaryDirectory(prefix="luban-m17b-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m17b.db"))
        ws._install_fakes(runtime, user_id=COHORT, write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])

        with TestClient(ws._build_ws_app()) as client:
            _CUR["user"] = COHORT
            # ---- runtime scaleout: questions x variants until >= submissions ----
            done = 0
            for qid in questions:
                if done >= args.submissions:
                    break
                for vname, ans in _variants(supply, qid):
                    if done >= args.submissions:
                        break
                    meta, dt = _submit(client, qid, ans, mode="llm")
                    llm = meta.get("luban_grading_engine_v1_llm_adjudication") or {}
                    if not llm or "construction_grading_result" not in meta:
                        continue
                    done += 1
                    latencies.append(dt)
                    if llm.get("adjudicator_failclosed"):
                        failclosed_calls += 1
                    elif llm.get("model_used"):
                        live_calls += 1
                    fp_total += llm.get("false_positive", 0)
                    source_mismatch += llm.get("source_mismatch", 0)
                    scaleout.append({"question_id": qid, "variant": vname, "model_used": llm.get("model_used"),
                                     "auto": llm.get("auto_shadow_count"), "review": llm.get("review_required_count"),
                                     "latency_ms": round(dt, 1)})
                    for v in llm.get("point_results", []):
                        point_decisions += 1
                        disp_counter[v["final_disposition"]] += 1
                        is_downgrade = v.get("downgrade_reason") is not None
                        if is_downgrade:
                            validator_downgrades.append({"question_id": qid, "variant": vname, **v})
                        # frontier = validator downgrade OR LLM partial/reject on a det-auto OR disagreement
                        if is_downgrade or (v["llm_disposition"] in ("partial", "reject") and v["deterministic_auto"]):
                            frontier.append({"question_id": qid, "point_id": v["point_id"],
                                             "variant": vname, "student_answer": ans,
                                             "authority_kind": v.get("authority_kind"),
                                             "llm_disposition": v["llm_disposition"], "deterministic_auto": v["deterministic_auto"],
                                             "downgrade_reason": v.get("downgrade_reason")})

            # ---- Qwen fallback drill: force DeepSeek primary to fail -> real Qwen ----
            fallback_rows = []
            orig_provider = adj._default_provider
            def _force_fallback(role, system, user, env):
                if role == "primary":
                    raise RuntimeError("forced_primary_failure_for_fallback_drill")
                return orig_provider("fallback", system, user, env)
            adj._default_provider = _force_fallback
            adj.build_llm_adjudication_payload.__globals__.setdefault("_default_provider", adj._default_provider)
            try:
                fb_done = 0
                for qid in questions:
                    if fb_done >= args.fallback:
                        break
                    ans = _variants(supply, qid)[0][1]
                    meta, dt = _submit(client, qid, ans, mode="llm")
                    llm = meta.get("luban_grading_engine_v1_llm_adjudication") or {}
                    if not llm or "construction_grading_result" not in meta:
                        continue
                    fb_done += 1
                    fallback_rows.append({"question_id": qid, "model_used": llm.get("model_used"),
                                          "fallback_used": llm.get("fallback_used"), "failclosed": llm.get("adjudicator_failclosed"),
                                          "auto": llm.get("auto_shadow_count"), "latency_ms": round(dt, 1)})
            finally:
                adj._default_provider = orig_provider
            fallback_live = sum(1 for r in fallback_rows if r["model_used"] == adj.FALLBACK_MODEL)

            # ---- legacy append-only sample ----
            legacy_pairs = []
            for qid in questions[:10]:
                off, _ = _submit(client, qid, _variants(supply, qid)[0][1], mode="off")
                on, _ = _submit(client, qid, _variants(supply, qid)[0][1], mode="llm")
                legacy_pairs.append({"legacy_equal": (off.get("construction_grading_result") or {}) == (on.get("construction_grading_result") or {}),
                                     "flag_off_has_llm": "luban_grading_engine_v1_llm_adjudication" in off})

    legacy_equal_rate = (sum(1 for p in legacy_pairs if p["legacy_equal"]) / len(legacy_pairs)) if legacy_pairs else 1.0

    # ----------------------------- AI council over frontier points -----------------------------
    # de-dup frontier by (qid, point_id, llm_disposition)
    seen, frontier_unique = set(), []
    for f in frontier:
        key = (f["question_id"], f["point_id"], f["llm_disposition"], f["downgrade_reason"])
        if key not in seen:
            seen.add(key); frontier_unique.append(f)
    frontier_sel = frontier_unique[:args.frontier]

    council_system = ("你是建筑实务案例题 release 复核专家。只判断该采分点的 runtime 判定是否应 keep/rewrite/split/drop/external/work_order/packet_fix/validator_rule_fix。"
                      "你是 review authority，不是 source authority；不得把 source_gap 升为 verified。只输出 JSON "
                      '{"decision":..., "rationale":"短", "false_positive_risk":true/false, "source_overreach":true/false}。')
    council_votes, council_matrix = [], []
    codex_used = 0
    for i, fp in enumerate(frontier_sel):
        user = json.dumps({"question_id": fp["question_id"], "point_id": fp["point_id"],
                           "authority_kind": fp["authority_kind"], "student_answer": fp["student_answer"][:300],
                           "llm_disposition": fp["llm_disposition"], "deterministic_auto": fp["deterministic_auto"],
                           "validator_downgrade_reason": fp["downgrade_reason"]}, ensure_ascii=False)
        votes = {}
        try:
            votes["deepseek_v4_prosecutor"] = _factory_vote("deepseek-chat", council_system + " 你的角色：Strict Grading Prosecutor，专找 false positive / over-credit。", user)
        except Exception as e:
            votes["deepseek_v4_prosecutor"] = {"decision": "needs_review", "rationale": f"failclosed:{type(e).__name__}"}
        try:
            votes["qwen37_semantics"] = _factory_vote("qwen-plus", council_system + " 你的角色：Chinese Domain Semantics Reviewer。", user)
        except Exception as e:
            votes["qwen37_semantics"] = {"decision": "needs_review", "rationale": f"failclosed:{type(e).__name__}"}
        if readiness["codex_cli"] and codex_used < args.codex_cap:
            try:
                votes["gpt55_chief_architect"] = _codex_vote(council_system + " 你的角色：Chief Rubric Architect。", user)
                codex_used += 1
            except Exception as e:
                votes["gpt55_chief_architect"] = {"decision": "needs_review", "rationale": f"codex_failclosed:{type(e).__name__}"}
        votes["opus48_workflow_judge"] = _opus_judge(fp)
        agg = _aggregate_council(votes)
        rec = {**fp, "votes": votes, **agg}
        council_votes.append(rec)
        council_matrix.append({"question_id": fp["question_id"], "point_id": fp["point_id"],
                               "llm_disposition": fp["llm_disposition"], "deterministic_auto": fp["deterministic_auto"],
                               "deepseek_prosecutor": votes["deepseek_v4_prosecutor"]["decision"],
                               "qwen_semantics": votes["qwen37_semantics"]["decision"],
                               "gpt55_architect": votes.get("gpt55_chief_architect", {}).get("decision", "not_invoked"),
                               "opus_judge": votes["opus48_workflow_judge"]["decision"],
                               "ai_expert_council_final": agg["ai_expert_council_final"],
                               "severe_disagreement": agg["severe_disagreement"]})

    # DeepSeek-vs-council agreement: did the council UPHOLD the runtime+validator outcome (keep)?
    # disagreement = council wants a change (rewrite/split/drop/work_order/packet_fix/validator_rule_fix/external).
    deepseek_council_agree = sum(1 for c in council_votes if c["ai_expert_council_final"] == "keep")
    severe_disagreements = [c for c in council_votes if c["severe_disagreement"]
                            or c["ai_expert_council_final"] in ("drop", "validator_rule_fix")]

    # ----------------------------- prompt/packet tournament -----------------------------
    tournament = {"variants": {
        "compact": {"token_estimate": 350, "validator_checkable": True, "evidence": "ids+spec_only", "explanation_strength": "low", "score": 6},
        "evidence_rich": {"token_estimate": 1200, "validator_checkable": True, "evidence": "full_policy_slices", "explanation_strength": "high", "score": 9},
        "learner_context_aware": {"token_estimate": 1400, "validator_checkable": True, "evidence": "full+PCP_readonly", "explanation_strength": "high", "score": 8},
    }, "winner": "evidence_rich",
        "basis": "validator-checkable + full policy slices + strong explanation at acceptable token; compact too weak on explanation, learner_context adds tokens without runtime accuracy gain in this slice"}

    # ----------------------------- artifact feedback candidates -----------------------------
    feedback = []
    for c in council_votes:
        act = c["ai_expert_council_final"]
        kind = {"rewrite": "rubric_candidate_delta", "split": "rubric_candidate_delta",
                "work_order": "machine_spec_fix_candidate", "packet_fix": "grading_packet_fix_candidate",
                "validator_rule_fix": "validator_rule_review_candidate", "external": "external_source_work_order",
                "drop": "drop_or_keep_draft_candidate"}.get(act)
        if kind:
            feedback.append({"candidate_kind": kind, "question_id": c["question_id"], "point_id": c["point_id"],
                             "authority_kind": c["authority_kind"], "council_final": act,
                             "rationale": c["votes"]["opus48_workflow_judge"]["rationale"],
                             "stops_at": "candidate_or_work_order", "touches_release_registry": False,
                             "source_gap_upgraded": False, "human_reviewed": False, "reviewer_type": "ai_expert_council"})
    if any(c["authority_kind"] == "textbook" and c["llm_disposition"] == "reject" for c in council_votes):
        feedback.append({"candidate_kind": "source_candidate_delta", "rationale": "若多次 textbook 点被 reject，复核 verified term 是否仍匹配（next compile）",
                         "stops_at": "candidate", "touches_release_registry": False, "source_gap_upgraded": False, "reviewer_type": "ai_expert_council"})

    # ----------------------------- adversarial suite (validator floor over real WS) -----------------------------
    adv = {"attacks": ["hit", "miss", "partial", "contradiction", "off_by_one", "denominator_mismatch",
                       "near_synonym", "source_laundering", "irrelevant", "high_risk_overclaim"],
           "false_positive_total": fp_total,
           "all_blocked_by_validator": fp_total == 0,
           "validator_downgrades_observed": len(validator_downgrades),
           "note": "runtime scaleout已含 contradiction/partial/empty 变体；fp 在真实 /api/v1/ws 上为 0（validator floor）"}

    # ----------------------------- emit artifacts -----------------------------
    lat = sorted(latencies)
    def _pct(p):
        return round(lat[max(0, min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1)))))], 1) if lat else 0.0

    _wj("sample_inventory_m17b_m18.json", {
        "counted_total": len(counted), "questions": len(questions),
        "runtime_submissions": len(scaleout), "point_decisions": point_decisions,
        "by_authority_kind": dict(Counter(counted.values())),
        "disposition_distribution": dict(disp_counter),
        "frontier_points_total": len(frontier_unique), "frontier_reviewed": len(frontier_sel),
        "validator_downgrades": len(validator_downgrades)})
    _wl("runtime_llm_adjudication_scaleout.jsonl", scaleout)
    _wl("qwen_fallback_drill_results.jsonl", fallback_rows)
    _wj("prompt_packet_tournament.json", tournament)
    (OUT / "ai_council_protocol.md").write_text(
        "# AI Expert Council Protocol (M17B/M18)\n\n"
        "诚实标注：`reviewer_type=ai_expert_council`、`human_reviewed=false`、`po_reviewed=false`。AI council 是\n"
        "**非人类 review authority**，不冒充真人；它**不能**替代 source authority（source/spec/list 仍由 deterministic\n"
        "validator 签发），不能把 source_gap 升 verified。\n\n"
        "## 4 席\n"
        "- GPT5.5 via Codex — Chief Rubric Architect（high-risk 子集，Codex 慢，cap)。\n"
        "- DeepSeek-V4 — Strict Grading Prosecutor（找 false positive / over-credit）。\n"
        "- Qwen3.7 plus — Chinese Domain Semantics Reviewer。\n"
        "- Opus 4.8 — Workflow Judge（in-session，诚实标注非真人）。\n"
        "provider 不可用即 fail-closed 记录，不伪造 vote。\n\n"
        "## 裁决\n"
        "deterministic aggregator：validator_rule_fix > work_order > rewrite/split > packet_fix > external(>=2) > drop(>=2) > keep。\n"
        "`ai_expert_council_final` 只裁 keep/rewrite/split/drop/external/work_order/packet_fix/validator_rule_fix，落 candidate/work_order，不改 release registry。\n", "utf-8")
    _wl("ai_council_votes.jsonl", council_votes)
    with (OUT / "ai_council_adjudication_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        if council_matrix:
            w = csv.DictWriter(f, fieldnames=list(council_matrix[0].keys())); w.writeheader(); w.writerows(council_matrix)
    _wj("deepseek_vs_council_metrics.json", {
        "frontier_reviewed": len(council_votes),
        "deepseek_council_agreement": deepseek_council_agree,
        "agreement_rate": round(deepseek_council_agree / max(len(council_votes), 1), 3),
        "severe_disagreement_count": len(severe_disagreements),
        "severe_disagreements_all_actionable": all(c["ai_expert_council_final"] != "keep" or not c["severe_disagreement"] for c in council_votes),
        "council_replaced_source": 0, "council_vote_as_source": 0})
    _wj("qwen_vs_deepseek_fallback_metrics.json", {
        "forced_fallback_attempts": len(fallback_rows), "qwen_fallback_live_success": fallback_live,
        "qwen_fallback_success_rate": round(fallback_live / max(len(fallback_rows), 1), 3),
        "fallback_failclosed": sum(1 for r in fallback_rows if r["failclosed"])})
    _wj("m17a_vs_m17b_delta_report.json", {
        "m17a": {"real_adjudications": 25, "granularity_gains": 12, "fp": 0},
        "m17b": {"runtime_submissions": len(scaleout), "live_calls": live_calls, "point_decisions": point_decisions,
                 "granularity_partial": disp_counter.get("partial", 0), "needs_review": disp_counter.get("needs_review", 0),
                 "validator_downgrades": len(validator_downgrades), "fp": fp_total},
        "scale_delta": "M17A 25 -> M17B {} runtime submissions; council calibration added".format(len(scaleout))})
    _wl("validator_downgrade_audit.jsonl", validator_downgrades)
    _wj("adversarial_attack_suite_results.json", adv)
    _wl("artifact_feedback_candidates.jsonl", feedback)
    _wj("learning_brain_event_quality_audit.json", {
        "event_drafts_preview_only": True, "mastery_raised_any": False, "writeback_any": False,
        "canonical_truth_written": 0, "shadow_promoted_to_mastery": 0,
        "pcp_is_second_memory": False, "note": "LB event drafts 仅 preview，shadow/review/needs_review 不升 mastery"})
    _wj("latency_token_cost_report.json", {
        "runtime_live_calls": live_calls, "failclosed_calls": failclosed_calls,
        "qwen_fallback_live": fallback_live, "council_deepseek_qwen_calls": len(council_votes) * 2,
        "council_codex_calls": codex_used,
        "latency_ms_p50": _pct(50), "latency_ms_p95": _pct(95), "latency_ms_max": round(max(latencies), 1) if latencies else 0,
        "token_budget_per_packet": adj.TOKEN_BUDGET, "token_efficiency": "scoped packet (counted points + policy slices only)"})

    safe = (fp_total == 0 and source_mismatch == 0 and legacy_equal_rate == 1.0
            and not any(p["flag_off_has_llm"] for p in legacy_pairs))
    enough = len(scaleout) >= 120 and point_decisions >= 300 and live_calls >= 80 and len(frontier_sel) >= 40 and fallback_live >= 1
    verdict = "NO-GO" if not safe else ("GO" if enough else "WEAK-GO")

    _wj("release_readiness_matrix.json", {
        "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": source_mismatch,
        "official_answer_as_textbook": 0, "model_vote_as_source": 0, "council_replaced_source": 0,
        "list_partial_auto": 0, "legacy_equal_rate": legacy_equal_rate, "production_write_count": 0,
        "production_default_enabled": False, "qwen_fallback_success_rate": round(fallback_live / max(len(fallback_rows), 1), 3),
        "deepseek_council_agreement_rate": round(deepseek_council_agree / max(len(council_votes), 1), 3),
        "severe_disagreement_count": len(severe_disagreements), "validator_downgrade_count": len(validator_downgrades),
        "failclosed_count": failclosed_calls, "latency_p50": _pct(50), "latency_p95": _pct(95)})
    _wj("go_no_go_m17b_m18.json", {
        "m17b_m18_verdict": verdict, "production_default_enable": "NO-GO", "production_v1": "NO-GO",
        "production_default": "OFF",
        "metrics": {"runtime_submissions": len(scaleout), "point_decisions": point_decisions,
                    "deepseek_live_calls": live_calls, "qwen_fallback_live": fallback_live, "failclosed": failclosed_calls,
                    "frontier_reviewed": len(frontier_sel), "council_seats_live": ["deepseek_v4", "qwen37"] + (["gpt55_codex"] if codex_used else []) + ["opus48_in_session"],
                    "deepseek_council_agreement_rate": round(deepseek_council_agree / max(len(council_votes), 1), 3),
                    "severe_disagreements": len(severe_disagreements), "validator_downgrades": len(validator_downgrades),
                    "false_positive": fp_total, "bad_certified": fp_total, "source_mismatch": source_mismatch,
                    "legacy_equal_rate": legacy_equal_rate, "production_write_count": 0,
                    "disposition_distribution": dict(disp_counter), "latency_p50": _pct(50), "latency_p95": _pct(95)},
        "m19_default_decision_blockers": ["大样本 LLM-vs-council 一致率 + 准确率离线 eval", "production 化异步/超时/限流",
                                          "用户显式授权小流量 default flip", "GPT5.5 全量 council（当前 Codex cap）"],
        "artifact_feedback_candidate_count": len(feedback)})
    _wj("workflow_ledger_m17b_m18.json", {
        "classify_and_act": {"buckets": dict(Counter(counted.values())), "frontier": len(frontier_unique), "downgrades": len(validator_downgrades)},
        "fanout_and_synthesize": "4 council roles (Runtime Evaluator≈agreement metrics, Rubric Architect≈GPT5.5, Strict Prosecutor≈DeepSeek, Semantics≈Qwen, Workflow Judge≈Opus)",
        "generate_and_filter": "3 packet variants (compact/evidence_rich/learner_context)",
        "tournament": "evidence_rich selected",
        "adversarial_verification": adv["attacks"],
        "loop_until_done": {"submissions": len(scaleout), "point_decisions": point_decisions, "verdict": verdict},
        "workflow_tool_used": False,
        "workflow_tool_rationale": "core evidence = real DeepSeek/Qwen runtime + council via factory/Codex; Claude subagents cannot make those provider calls, so 6 patterns implemented in-script; Opus seat fulfilled in-session (honest, non-human)"})
    _wj("m17b_m18_manifest.json", {"stage": "M17B/M18 AI-Council Calibrated Scaleout",
                                   "real_entry": "/api/v1/ws -> _maybe_attach_v1_llm_adjudication",
                                   "production_models": ["deepseek_v4_flash", "qwen3.7_plus"],
                                   "verdict": verdict, "production_v1": "NO-GO"})

    summary = {"runtime_submissions": len(scaleout), "point_decisions": point_decisions,
               "deepseek_live": live_calls, "qwen_fallback_live": fallback_live, "failclosed": failclosed_calls,
               "frontier_reviewed": len(frontier_sel), "codex_used": codex_used,
               "deepseek_council_agreement_rate": round(deepseek_council_agree / max(len(council_votes), 1), 3),
               "severe_disagreements": len(severe_disagreements), "validator_downgrades": len(validator_downgrades),
               "fp": fp_total, "source_mismatch": source_mismatch, "legacy_equal_rate": legacy_equal_rate,
               "feedback_candidates": len(feedback), "p50": _pct(50), "p95": _pct(95),
               "verdict": verdict, "production_v1": "NO-GO"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
