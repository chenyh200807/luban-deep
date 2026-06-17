"""Phase 11 — the LEGACY arm: complete the Stage-4 directional gate MAE(new) ≤ MAE(legacy).

Unblocked by the identity remap (the po_slice human gold dropped specific question-id, keeping only
chapter node — and mis-noded 3/12; content-matching official_answer recovers the real chunk_id, and
all 12 ARE in the legacy bank). So we can finally run the migration plan's actual flip gate on the
ONE non-circular human gold (po_slice 131 labels):

  legacy_awarded = Σ legacy minted per-point score over HIT points (the old `grade_with_rubric` arithmetic),
                   each point LLM-judged (DeepSeek, same family as production legacy) on required_terms.
  new_uniform    = official_total × AI_consensus_credited/total  (from Phase 10).
  human_awarded  = Σ human per-point score                       (non-circular gold).

  gate (directional): MAE(new vs human) ≤ MAE(legacy vs human).

Honest boundary unchanged: 12 cases / 24 pairs, small + directional; not a production sign-off.
Legacy is REPLICATED minimally (judge required_terms → sum hit scores) to avoid the production
bank's content_hash/verify fragility — faithful to the legacy arithmetic the plan describes.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import re
import statistics
import sys
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location(
    "deep_runner", REPO / "scripts/run_luban_rich_leaf_llm_deep_compile_runner.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)

M = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
FACDIR = M / "phase5_factory"
PK = REPO / "artifacts/luban_human_validation_v1/po_slice_20260601/po_review_packet.json"
LEGACY_BANK = REPO / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"

JUDGE_SYS = (
    "你是一级建造师建筑实务案例题判分员(旧 rubric 口径)。给你一个采分点(含 required_terms 关键词与判定标准)"
    "和学生作答。判断学生是否命中该点:命中 required_terms 体现的规范要点即算命中(近义可接受,除非标 exact_required"
    "须一字不差)。只输出 JSON:{\"hit\":true|false}"
)


def _legacy_points_by_chunk():
    raw = json.loads(LEGACY_BANK.read_text("utf-8"))
    items = raw if isinstance(raw, list) else next((v for v in raw.values() if isinstance(v, list)), [])
    by = {}
    for p in items:
        qid = str(p.get("qid") or "")
        m = re.match(r"(EXAM_\w+?_P\d+_\d+|EXAM_XW\d+_CASE_\d+)", qid)
        base = m.group(1) if m else qid
        by.setdefault(base, []).append(p)
    return by


def main() -> int:
    remap = {r["po_case"]: r for r in json.loads((FACDIR / "po_slice_identity_remap.json").read_text("utf-8"))}
    pk = json.loads(PK.read_text("utf-8"))
    legacy_by_chunk = _legacy_points_by_chunk()
    ph10 = {(r["case"], r["student"]): r
            for r in json.loads((FACDIR / "offline_human_gold_regression.json").read_text("utf-8"))["records"]}

    call = RUN._openai_compat_provider(provider="deepseek", model=None, timeout_s=90, max_tokens=120)
    if call is None:
        raise SystemExit("deepseek key missing")

    def judge(point, answer):
        payload = {"采分点": point.get("text"), "required_terms": point.get("required_terms"),
                   "policy": point.get("policy"), "学生作答": answer}
        try:
            o = json.loads(call("judge", [{"role": "system", "content": JUDGE_SYS},
                                           {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])["content"])
            return bool(o.get("hit"))
        except Exception:  # noqa: BLE001
            return False

    tasks = []
    for c in pk["cases"]:
        rm = remap.get(c["case_id"])
        if not rm:
            continue
        chunk = re.match(r"(EXAM_\w+?_P\d+_\d+|EXAM_XW\d+_CASE_\d+)", str(rm["real_chunk"]) or "")
        chunk = chunk.group(1) if chunk else rm["real_chunk"]
        pts = legacy_by_chunk.get(chunk, [])
        for s in c.get("samples") or []:
            key = (c["case_id"], s["student_id"])
            if key in ph10:
                tasks.append({"key": key, "points": pts, "answer": s.get("answer_text", "")})

    def grade(t):
        awarded = 0.0
        for p in t["points"]:
            if judge(p, t["answer"]):
                awarded += float(p.get("score") or 0)
        return t["key"], round(awarded, 3), len(t["points"])

    recs = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for key, legacy_awarded, npts in ex.map(grade, tasks):
            r10 = ph10[key]
            recs.append({"case": key[0], "student": key[1], "n_legacy_points": npts,
                         "legacy_awarded": legacy_awarded,
                         "new_uniform": r10["new_uniform"], "human_awarded": r10["human_awarded"],
                         "official_total": r10["official_total"]})

    def mae(a, b):
        return round(statistics.mean(abs(r[a] - r[b]) for r in recs), 4)

    mean_total = statistics.mean(r["official_total"] for r in recs)
    new_mae = mae("new_uniform", "human_awarded")
    legacy_mae = mae("legacy_awarded", "human_awarded")
    # over-credit: awarded materially exceeds human (>1pt over)
    new_over = sum(1 for r in recs if r["new_uniform"] - r["human_awarded"] > 1.0)
    legacy_over = sum(1 for r in recs if r["legacy_awarded"] - r["human_awarded"] > 1.0)
    summary = {
        "schema": "luban_legacy_arm_regression.v1", "generated_at_date": "2026-06-14",
        "gold": "po_slice 131 HUMAN labels (non-circular)", "n_pairs": len(recs),
        "mean_official_total": round(mean_total, 2),
        "MAE_new_vs_human": new_mae, "MAE_legacy_vs_human": legacy_mae,
        "as_pct": {"new": round(100 * new_mae / mean_total, 1), "legacy": round(100 * legacy_mae / mean_total, 1)},
        "over_credit_pairs": {"new": new_over, "legacy": legacy_over},
        "gate_MAE_new_le_legacy": new_mae <= legacy_mae,
        "verdict": ("new ≤ legacy ✓(directional pass)" if new_mae <= legacy_mae
                    else "new > legacy ✗(new worse — investigate)"),
        "honest_boundary": "12 cases/24 pairs directional; legacy minimally replicated (judge required_terms→sum hit scores);"
                           " not production sign-off (needs scaled human gold).",
    }
    (FACDIR / "legacy_arm_regression.json").write_text(
        json.dumps({"summary": summary, "records": recs}, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
