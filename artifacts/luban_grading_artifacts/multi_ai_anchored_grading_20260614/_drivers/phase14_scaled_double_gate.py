"""Phase 14 — scaled Stage-4 DOUBLE gate (MAE + over-credit), new vs legacy vs scaled gold.

Uses the verified 20-case identity remap (strong full-content match; shared-source pairs legitimate;
4 ambiguous cases Q4/Q8/Q10/Q19 EXCLUDED — not run on uncertain chunks). Runs legacy (minimally
replicated: deepseek judge required_terms → Σ hit scores) on the non-ambiguous cases' pairs, and
scores both arms against the non-circular scaled gold (gate verdict EXCLUDES production deepseek).

  gate = MAE(new) ≤ MAE(legacy)  AND  over_credit(new) ≤ over_credit(legacy)   — both halves.

Honest: legacy uses deepseek (production family); new uses deepseek coverage — both vs gold(¬deepseek)
is non-circular; comparison isolates arithmetic (coverage vs sum-minted). Synthetic student answers.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location(
    "deep_runner", REPO / "scripts/run_luban_rich_leaf_llm_deep_compile_runner.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)

M = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
SG = M / "scaled_gold"
GOLD_V1 = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
LEGACY_BANK = REPO / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"

JUDGE_SYS = ("你是一级建造师建筑实务案例题判分员(旧rubric口径)。给采分点(含required_terms关键词与判定标准)和学生作答,"
             "判断是否命中:命中required_terms体现的规范要点即命中(近义可接受除非exact_required须一字不差)。"
             "只输出JSON:{\"hit\":true|false}")


def _cr(v):
    return 1.0 if v == "hit" else (0.5 if v == "partial" else 0.0)


def _legacy_points():
    raw = json.loads(LEGACY_BANK.read_text("utf-8"))
    items = raw if isinstance(raw, list) else next((v for v in raw.values() if isinstance(v, list)), [])
    by = defaultdict(list)
    for p in items:
        m = re.match(r"(EXAM_\w+?_P\d+_\d+|EXAM_XW\d+_CASE_\d+)", str(p.get("qid") or ""))
        if m:
            by[m.group(1)].append(p)
    return by


def main() -> int:
    remap = {r["po_case"]: r for r in json.loads((SG / "identity_remap_20_verified.json").read_text("utf-8"))}
    usable = {cid: r for cid, r in remap.items() if r["in_legacy"] and not r["ambiguous"]}
    gv = json.loads(GOLD_V1.read_text("utf-8"))
    cases = {c["case_id"]: c for c in gv["cases"]}
    legacy_by = _legacy_points()
    gold = json.loads((SG / "scaled_gold.json").read_text("utf-8"))["gold"]
    gold_by = defaultdict(list)
    for g in gold:
        gold_by[(g["case_id"], g["student_id"])].append(g)

    call = RUN._openai_compat_provider(provider="deepseek", model=None, timeout_s=90, max_tokens=120)
    if call is None:
        raise SystemExit("deepseek key missing")

    def judge(p, ans):
        try:
            o = json.loads(call("j", [{"role": "system", "content": JUDGE_SYS},
                                       {"role": "user", "content": json.dumps(
                                           {"采分点": p.get("text"), "required_terms": p.get("required_terms"),
                                            "学生作答": ans}, ensure_ascii=False)}])["content"])
            return bool(o.get("hit"))
        except Exception:  # noqa: BLE001
            return False

    tasks = []
    for cid, r in usable.items():
        c = cases.get(cid)
        chunk = re.match(r"(EXAM_\w+?_P\d+_\d+|EXAM_XW\d+_CASE_\d+)", str(r["real_chunk"]))
        chunk = chunk.group(1) if chunk else r["real_chunk"]
        lpts = legacy_by.get(chunk, [])
        for s in c.get("eval_samples") or []:
            key = (cid, s["student_id"])
            if key in gold_by:
                tasks.append({"key": key, "lpts": lpts, "ans": s.get("answer_text", ""),
                              "official_total": float(c.get("max_score") or 0)})

    def grade_legacy(t):
        aw = sum(float(p.get("score") or 0) for p in t["lpts"] if judge(p, t["ans"]))
        return t["key"], round(aw, 3)

    legacy_aw = {}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for key, aw in ex.map(grade_legacy, tasks):
            legacy_aw[key] = aw

    recs = []
    for t in tasks:
        key = t["key"]
        gs = gold_by[key]
        tot = len(gs)
        oc = t["official_total"]
        new_aw = oc * sum(_cr(g["votes"]["deepseek"]) for g in gs) / tot
        gold_aw = oc * sum(_cr(g["gate_verdict_excl_production"]) for g in gs) / tot
        recs.append({"case": key[0], "student": key[1], "official_total": oc,
                     "new": round(new_aw, 3), "legacy": legacy_aw[key], "gold": round(gold_aw, 3)})

    def mae(a):
        return round(statistics.mean(abs(r[a] - r["gold"]) for r in recs), 4)

    mean_oc = statistics.mean(r["official_total"] for r in recs)
    new_mae, legacy_mae = mae("new"), mae("legacy")
    new_over = sum(1 for r in recs if r["new"] - r["gold"] > 1.0)
    legacy_over = sum(1 for r in recs if r["legacy"] - r["gold"] > 1.0)
    summary = {
        "schema": "luban_scaled_double_gate.v1", "generated_at_date": "2026-06-14",
        "gold": "non-circular scaled gold (excl production deepseek)", "n_pairs": len(recs),
        "cases_used": len(usable), "cases_excluded_ambiguous": [c for c in remap if remap[c]["ambiguous"]],
        "mean_official_total": round(mean_oc, 2),
        "MAE_new": new_mae, "MAE_legacy": legacy_mae,
        "as_pct": {"new": round(100 * new_mae / mean_oc, 1), "legacy": round(100 * legacy_mae / mean_oc, 1)},
        "over_credit": {"new": new_over, "legacy": legacy_over},
        "gate_MAE_new_le_legacy": new_mae <= legacy_mae,
        "gate_overcredit_new_le_legacy": new_over <= legacy_over,
        "double_gate_pass": (new_mae <= legacy_mae) and (new_over <= legacy_over),
        "honest_boundary": "16 non-ambiguous cases / ~80 pairs; legacy minimally replicated; synthetic student answers;"
                           " not production sign-off (needs PO stratified human spot-check).",
    }
    (SG / "scaled_double_gate.json").write_text(
        json.dumps({"summary": summary, "records": recs}, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
