"""Phase 12 — scaled non-circular gold, STAGE A (cross-family blind propose + stratify).

Scales the gold from po_slice's 24 pairs to golden_v1's 100 (case,student) pairs — using its
STUDENT ANSWERS only (eval_samples), NOT its AI-constructed ground_truth_ledger (which its own
redline says is non-human / circular). Produces a FRESH gold per the non-circular design
(MULTI_AI_NONCIRCULAR_GOLD_DESIGN.md): anchored to the external official answer + 踩字, by an
ensemble whose verdict-for-the-gate excludes the production grader's model.

Production grader uses deepseek-chat (rubric_grader_v1.py:595). So the gate-time gold verdict must
exclude DeepSeek. We still RECORD every model's vote (DeepSeek + Qwen cheap full-run here; Opus
arbitrates disagreements in Stage B) so the gate can take the independent-of-production subset.

Stratified confidence:
  * both agree  → high-confidence (gold-ready)
  * disagree    → Stage-B Opus arbiter queue (medium if resolved, contested if not)

Calibration already validated (Phase 1 + Opus calib): any production-excluded 2-model subset
matches the 131 human labels ≥94.7%; 3-model majority 96.2%. REVIEW-ONLY / candidate.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location(
    "deep_runner", REPO / "scripts/run_luban_rich_leaf_llm_deep_compile_runner.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)

GOLD_V1 = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
OUT = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/scaled_gold"
GRADERS = [("deepseek", "盲标A_生产lane(门时排除)"), ("dashscope", "盲标B_跨家族独立")]

VERDICT_SYS = (
    "你是一级建造师建筑实务案例题盲标判分员。对给定的一个采分点,判断学生作答是否命中。"
    "判断必须严格锚定官方依据 official_basis 与该点的踩字/列举规则——这是唯一权威,不是你的主观印象。"
    "踩字铁律:必须命中规范术语原文,近义/错位不算(如要求'反铲挖掘机',学生只写'挖掘机'=未命中)。"
    "列举型按规则逐项。命中必须能 cite 学生作答里的逐字依据。"
    "只输出 JSON:{\"verdict\":\"hit|partial|miss\",\"student_span\":\"<支撑判断的学生逐字片段,miss则空>\"}"
)


def _grade(call, point, answer, stem):
    payload = {"采分点": point.get("label"), "official_basis": point.get("official_basis"),
               "list_rule": point.get("list_rule"), "max_score": point.get("max_score"),
               "题干背景": (stem or "")[:400], "学生作答": answer}
    try:
        o = json.loads(call("grade", [{"role": "system", "content": VERDICT_SYS},
                                       {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])["content"])
        v = str(o.get("verdict") or "error").lower()
        return v if v in ("hit", "partial", "miss") else "error"
    except Exception:  # noqa: BLE001
        return "error"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gv = json.loads(GOLD_V1.read_text("utf-8"))
    calls = {}
    for prov, _ in GRADERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=90, max_tokens=300)
        if c is None:
            raise SystemExit(f"{prov} key missing")
        calls[prov] = c

    tasks = []
    for c in gv["cases"]:
        for s in c.get("eval_samples") or []:
            for p in c.get("gold_scoring_points") or []:
                tasks.append({"case_id": c["case_id"], "student_id": s["student_id"],
                              "point_id": p["point_id"], "point": p, "stem": c.get("stem"),
                              "answer": s.get("answer_text", "")})

    def work(t):
        out = {"case_id": t["case_id"], "student_id": t["student_id"], "point_id": t["point_id"],
               "max_score": t["point"].get("max_score")}
        for prov, _ in GRADERS:
            out[prov] = _grade(calls[prov], t["point"], t["answer"], t["stem"])
        out["agree"] = out["deepseek"] == out["dashscope"] and out["deepseek"] != "error"
        return out

    rows = []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(work, tasks):
            rows.append(r)

    n = len(rows)
    agree = sum(1 for r in rows if r["agree"])
    errs = sum(1 for r in rows if r["deepseek"] == "error" or r["dashscope"] == "error")
    disagree = [r for r in rows if not r["agree"] and r["deepseek"] != "error" and r["dashscope"] != "error"]
    summary = {
        "schema": "luban_scaled_gold_propose.v1", "generated_at_date": "2026-06-14",
        "source_student_answers": "golden_v1 eval_samples (NOT its AI ground_truth_ledger)",
        "n_point_judgments": n, "n_pairs": len({(r["case_id"], r["student_id"]) for r in rows}),
        "cross_family_agree": f"{agree}/{n}", "agree_rate": round(agree / n, 4) if n else 0,
        "errors": errs, "to_opus_arbiter": len(disagree),
        "non_circular_note": "gate-time gold verdict excludes production model (deepseek-chat); both votes recorded.",
    }
    (OUT / "stageA_propose.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")
    (OUT / "stageA_disagreements.json").write_text(json.dumps(disagree, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
