#!/usr/bin/env python3
"""list_rule semantic model bakeoff: can model-side protocol (not new deterministic
rules) move the 485 WEAK-GO toward STRONG-GO without hurting exact_required?

Arms (DeepSeek-V4-flash, same model, different protocol prompt):
  baseline                         : reuse the existing 485 predictions
  list_rule_semantic_protocol      : allow list_rule partial for fact-equivalent
                                     coverage WITH evidence_span + named items;
                                     exact_required stays verbatim-strict.
  list_rule_strict_then_semantic   : count k/n strictly first, then check fact-
                                     equivalent coverage, final score needs item evidence.

Also: frontier reviewer (Opus/GPT) handled separately; score_delta decomposition (Task D).
NO new deterministic list_rule scoring patch. directional/shadow, NOT runtime, NOT RAG,
does NOT touch consensus gold, DeepSeek never scores its own LOO gold.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SRC = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603"
OUT = REPO / "artifacts/luban_consensus_gold/list_rule_semantic_model_bakeoff_20260603"
PACKET = SRC / "unified_typed_policy_packet_485.json"
GOLD = SRC / "loo_gold_485_flat.json"
BASELINE = SRC / "unified_predictions_485_span_guarded.json"
DS_ARM = "deepseek_v4_flash_typed_policy_primary"

_COMMON = (
    "你是鲁班一级建造师《建筑实务》案例阅卷主阅卷员。只看题干、标准答案、采分点、typed_policy、学生答案逐点阅卷。"
    "硬规则:hit/partial 必须引用学生答案逐字 evidence_span,无 span 退 miss 或 unsupported=true;"
    "policy_type=exact_required 必须逐字写出官方/规范术语原文,近义/大白话/口号不给分(这条不受 list_rule 宽松影响);"
    "policy_type=calculation 无法重算标 high_risk;policy_type=penalty_rule 先判罚则再判基础点。"
)
_SCHEMA = ('只输出 JSON 数组,每个采分点一对象:'
           '{"point_id","hit"(hit|partial|miss),"score","confidence","evidence_span","rationale",'
           '"policy_type","high_risk","needs_policy_review","review_reason","unsupported"}')

ARM_PROMPTS = {
    "list_rule_semantic_protocol": _COMMON + (
        "对 policy_type=list_rule:**可以按学生事实覆盖的列举项给 partial**——只要学生用近义/大白话表达了某个标准列举项的事实含义,"
        "该项可计入命中;但必须 (a) 引用学生答案 evidence_span,(b) 在 rationale 里明确列出命中了哪些标准 item,(c) 按 k/n×max 给分。"
        "吃不准是否事实等价 → 输出 high_risk_review,不硬给分。**exact_required 仍必须逐字规范术语,不被 list_rule 语义宽松污染。**"
    ) + _SCHEMA,
    "list_rule_strict_then_semantic": _COMMON + (
        "对 policy_type=list_rule:先**严格逐字**数 k/n(只数逐字命中的标准术语);再判断学生是否对未逐字命中的项存在**事实等价覆盖**(近义/大白话表达了该项含义);"
        "最终给分必须在 rationale 里逐项说明 item-level evidence(哪项逐字命中、哪项事实等价、哪项未覆盖),按总命中 k/n×max 给分。"
        "事实等价吃不准 → high_risk_review。**exact_required 不走此语义放宽,仍逐字。**"
    ) + _SCHEMA,
}


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _as_text(s):
    if isinstance(s, list):
        return " ".join(_as_text(x) for x in s)
    return s if isinstance(s, str) else ("" if s is None else str(s))


def _ds_index(preds, arm=DS_ARM):
    for s in preds["prediction_sets"]:
        if s["arm"] == arm:
            return {(p["case_id"], p["student_id"], p["point_id"]): p for p in s["predictions"]}
    return {}


def _packet_index(packet):
    idx = {}
    for t in packet["tasks"]:
        for sp in t["scoring_points"]:
            tp = sp.get("typed_policy") or {}
            idx[(t["case_id"], t["student_id"], sp["point_id"])] = {
                "policy_type": tp.get("policy_type"), "list_spec": tp.get("list_spec") or {}, "max": sp.get("max_score")}
    return idx


# ---------- Task A: eval set ----------

def build_eval_set():
    packet, gold_list = _read(PACKET), _read(GOLD)
    gold = {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold_list}
    ds = _ds_index(_read(BASELINE))
    rows = []
    for t in packet["tasks"]:
        for sp in t["scoring_points"]:
            tp = sp.get("typed_policy") or {}
            if tp.get("policy_type") != "list_rule":
                continue
            k = (t["case_id"], t["student_id"], sp["point_id"])
            g = gold.get(k)
            p = ds.get(k)
            frontier = (g is None)
            disagree = bool(g and p and str(p.get("hit")) != str(g.get("gold_hit")))
            rows.append({
                "case_id": k[0], "student_id": k[1], "point_id": k[2], "max_score": sp.get("max_score"),
                "official_answer": (t.get("official_answer") or "")[:400], "point_label": sp.get("label"),
                "list_rule_items": (tp.get("list_spec") or {}).get("terms"),
                "denominator": (tp.get("list_spec") or {}).get("denominator"),
                "student_answer": t.get("student_answer"),
                "current_deepseek_pred": {"hit": p.get("hit"), "score": p.get("score"),
                                          "evidence_span": _as_text(p.get("evidence_span")), "rationale": p.get("rationale")} if p else None,
                "loo_gold": {"gold_hit": g.get("gold_hit"), "gold_score": g.get("gold_score"), "status": g.get("status")} if g else None,
                "layer": "list_rule_frontier" if (frontier or disagree) else "list_rule_all_consensus",
            })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "list_rule_eval_set.json").write_text(json.dumps({"total": len(rows), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    nf = sum(1 for r in rows if r["layer"] == "list_rule_frontier")
    print(f"eval set: {len(rows)} list_rule points | frontier/disagreement layer: {nf}")
    return rows


# ---------- Task B: run a protocol arm on DeepSeek-flash ----------

def _client():
    from openai import OpenAI
    env = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            kk, vv = line.strip().split("=", 1)
            env[kk] = vv.strip().strip('"').strip("'")
    return OpenAI(api_key=(env.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEYS", "")).split(",")[0].strip(),
                  base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))


def _parse(text):
    t = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", text.strip()).strip()).strip()
    a, b = t.find("["), t.rfind("]")
    if a < 0 or b < 0:
        return []
    try:
        return json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        try:
            return json.loads(re.sub(r",(\s*[}\]])", r"\1", t[a:b + 1]))
        except json.JSONDecodeError:
            return []


def run_arm(arm):
    instruct = ARM_PROMPTS[arm]
    packet = _read(PACKET)
    # only tasks containing >=1 list_rule point
    tasks = [t for t in packet["tasks"] if any((sp.get("typed_policy") or {}).get("policy_type") == "list_rule" for sp in t["scoring_points"])]
    out_path = OUT / "predictions_by_arm" / f"{arm}.json"
    preds = _ds_index(_read(out_path), arm) if out_path.exists() else {}
    client = _client()
    for t in tasks:
        n = len(t["scoring_points"])
        if sum(1 for sp in t["scoring_points"] if (t["case_id"], t["student_id"], sp["point_id"]) in preds) == n:
            continue
        ctx = {"case_id": t["case_id"], "official_answer": t.get("official_answer", ""), "penalty_rule": t.get("penalty_rule", ""),
               "scoring_points": t["scoring_points"], "student_answer": t["student_answer"]}
        prompt = instruct + "\n任务(JSON):\n" + json.dumps(ctx, ensure_ascii=False)
        p = []
        for _ in range(2):
            try:
                r = client.chat.completions.create(model="deepseek-v4-flash", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=4000)
                p = _parse(r.choices[0].message.content or "")
            except Exception as exc:  # noqa: BLE001
                print("  err", str(exc)[:70], flush=True)
            if len(p) == n:
                break
        for x in p:
            x["case_id"], x["student_id"] = t["case_id"], t["student_id"]
            x.setdefault("unsupported", False)
            preds[(x["case_id"], x["student_id"], x["point_id"])] = x
        out_path.write_text(json.dumps({"slice_id": "list-rule-bakeoff", "prediction_sets": [{"arm": arm, "predictions": list(preds.values())}]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{arm}] {t['case_id']}/{t['student_id']}: {len(p)}/{n}", flush=True)
    print(f"{arm}: {len(preds)} list_rule-task points")


# ---------- metrics + Task D decomposition ----------

def _arm_merged_index(arm):
    """baseline for all points, overridden by arm preds where present."""
    base = _ds_index(_read(BASELINE))
    if arm == "baseline":
        return base
    armp = _ds_index(_read(OUT / "predictions_by_arm" / f"{arm}.json"), arm)
    merged = dict(base)
    merged.update(armp)
    return merged


def compute_metrics():
    from scripts.build_luban_485_list_rule_policy import gate_metrics
    packet, gold_list = _read(PACKET), _read(GOLD)
    pidx = _packet_index(packet)
    gold = {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold_list}
    arms = ["baseline"] + list(ARM_PROMPTS)
    out = {}
    for arm in arms:
        ds = _arm_merged_index(arm)
        full = gate_metrics(ds, pidx, gold)
        # list_rule_all + frontier subset metrics
        lr = [k for k in gold if pidx.get(k, {}).get("policy_type") == "list_rule" and k in ds]
        def sub(keys):
            n = len(keys) or 1
            hit = sum(1 for k in keys if str(ds[k].get("hit")) == str(gold[k]["gold_hit"])) / n
            sd = sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) for k in keys) / n
            return {"points": len(keys), "hit_agreement": round(hit, 4), "score_delta": round(sd, 4)}
        ds_base = _ds_index(_read(BASELINE))
        frontier = [k for k in lr if str(ds_base.get(k, {}).get("hit")) != str(gold[k]["gold_hit"])]
        out[arm] = {"overall_485_gate": full, "list_rule_all": sub(lr), "list_rule_frontier": sub(frontier)}
        print(f"{arm}: overall gate={full['gate_verdict']} auto_hit={full['auto_hit']} sdelta={full['score_delta']} "
              f"exact_major={full['exact_major']} unsup={full['unsupported']} hrr={full['high_risk_review']} | lr_all hit={out[arm]['list_rule_all']['hit_agreement']}")
    (OUT / "arm_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def score_delta_decomposition():
    packet, gold_list = _read(PACKET), _read(GOLD)
    pidx = _packet_index(packet)
    gold = {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold_list}
    ds = _ds_index(_read(BASELINE))
    qtotal = {}
    for t in packet["tasks"]:
        qtotal[(t["case_id"], t["student_id"])] = sum((sp.get("max_score") or 0) for sp in t["scoring_points"])
    buckets = {"0-1": [], "1-2": [], "2-4": [], "4+": []}
    by_type = {}
    for k, g in gold.items():
        if k not in ds:
            continue
        mx = pidx.get(k, {}).get("max") or 0
        ad = abs(float(ds[k].get("score") or 0) - float(g["gold_score"] or 0))
        b = "0-1" if mx <= 1 else "1-2" if mx <= 2 else "2-4" if mx <= 4 else "4+"
        buckets[b].append((ad, ad / mx if mx else 0))
        pt = pidx.get(k, {}).get("policy_type")
        by_type.setdefault(pt, []).append((ad, ad / mx if mx else 0, ad / (qtotal[(k[0], k[1])] or 1)))
    def agg(items, i):
        return round(sum(x[i] for x in items) / len(items), 4) if items else 0
    decomp = {
        "by_max_score_bucket": {b: {"points": len(v), "raw_score_delta": agg(v, 0), "normalized_per_point_delta": agg(v, 1)} for b, v in buckets.items()},
        "by_policy_type": {str(pt): {"points": len(v), "raw_score_delta": agg(v, 0), "normalized_per_point_delta": agg(v, 1), "normalized_per_question_delta": agg(v, 2)} for pt, v in by_type.items()},
        "note": "normalized = abs_delta/max_score (per point) or /question_total. DIAGNOSTIC ONLY — does NOT replace the raw score_delta<=0.05 gate.",
    }
    (OUT / "score_delta_decomposition.json").write_text(json.dumps(decomp, ensure_ascii=False, indent=2), encoding="utf-8")
    print("score_delta by bucket:", {b: f"raw {d['raw_score_delta']} / norm {d['normalized_per_point_delta']}" for b, d in decomp["by_max_score_bucket"].items()})
    print("list_rule:", decomp["by_policy_type"].get("list_rule"))
    return decomp


def qwk_diagnostics(arm="list_rule_semantic_protocol"):
    """QWK + exact/adjacent agreement + normalized delta, overall / by policy_type / by max bucket.
    DIAGNOSTIC ONLY — does NOT replace the zero-tolerance hard gates."""
    from scripts.luban_grading_metrics import agreement_block, qwk_for_pairs
    packet, gold_list = _read(PACKET), _read(GOLD)
    pidx = _packet_index(packet)
    gold = {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold_list}
    qtotal = {(t["case_id"], t["student_id"]): sum((sp.get("max_score") or 0) for sp in t["scoring_points"]) for t in packet["tasks"]}
    out = {"arm": arm, "hard_gates_unchanged": ["exact_required_major_violation==0", "unsupported_positive==0", "penalty_major==0", "evidence_span traceable"],
           "note": "QWK/normalized are DIAGNOSTIC candidates (metric-v2), NOT a replacement for raw score_delta gate or the hard gates. See governance plan."}
    for name in ("baseline", arm):
        ds = _arm_merged_index(name)
        keys = [k for k in gold if k in ds]
        ph = [ds[k].get("hit") for k in keys]
        gh = [gold[k]["gold_hit"] for k in keys]
        raw = round(sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) for k in keys) / (len(keys) or 1), 4)
        npp = round(sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) / (pidx.get(k, {}).get("max") or 1) for k in keys) / (len(keys) or 1), 4)
        npq = round(sum(abs(float(ds[k].get("score") or 0) - float(gold[k]["gold_score"] or 0)) / (qtotal.get((k[0], k[1])) or 1) for k in keys) / (len(keys) or 1), 4)
        by_type = {}
        for pt in set(pidx.get(k, {}).get("policy_type") for k in keys):
            kk = [k for k in keys if pidx.get(k, {}).get("policy_type") == pt]
            by_type[str(pt)] = qwk_for_pairs([ds[k].get("hit") for k in kk], [gold[k]["gold_hit"] for k in kk])
        by_bucket = {}
        for b, lo, hi in (("0-1", 0, 1), ("1-2", 1, 2), ("2-4", 2, 4), ("4+", 4, 1e9)):
            kk = [k for k in keys if lo < (pidx.get(k, {}).get("max") or 0) <= hi or (b == "0-1" and (pidx.get(k, {}).get("max") or 0) <= 1)]
            by_bucket[b] = qwk_for_pairs([ds[k].get("hit") for k in kk], [gold[k]["gold_hit"] for k in kk])
        out[name] = {**agreement_block(ph, gh), "overall_qwk_alias": qwk_for_pairs(ph, gh),
                     "by_policy_type_qwk": by_type, "by_max_score_bucket_qwk": by_bucket,
                     "raw_score_delta": raw, "normalized_per_point_delta": npp, "normalized_per_question_delta": npq}
    (OUT / "qwk_metric_diagnostics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for name in ("baseline", arm):
        d = out[name]
        print(f"{name}: QWK={d['qwk']} exact_agr={d['exact_agreement']} adj_agr={d['adjacent_agreement']} | raw_delta={d['raw_score_delta']} norm/pt={d['normalized_per_point_delta']} norm/q={d['normalized_per_question_delta']} | list_rule QWK={d['by_policy_type_qwk'].get('list_rule')}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-eval-set", action="store_true")
    ap.add_argument("--run-arm")
    ap.add_argument("--metrics", action="store_true")
    ap.add_argument("--decompose", action="store_true")
    ap.add_argument("--qwk", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.qwk:
        qwk_diagnostics()
    if a.build_eval_set:
        build_eval_set()
    if a.run_arm:
        run_arm(a.run_arm)
    if a.decompose:
        score_delta_decomposition()
    if a.metrics:
        compute_metrics()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
