"""Phase 1 of the capability-matched multi-AI anchored grading team.

Roles this phase (the two production-lane blind graders, cross-family):
  * DeepSeek v4 flash  — 盲标判分员 A (fast, cheap, Chinese-strong, IS the prod grader)
  * Qwen 3.7 plus      — 盲标判分员 B (independent second grader, different family)

Each grades every (case, student, scoring-point) the humans labeled, ANCHORED to the
official basis + 踩字/list rule, and must cite the student span. We compare to the 131
human point-labels (the external gold — NOT AI-self-labeled, so not circular) to measure
the residual: does a cross-family blind-grader pair match human 踩字 judgment?

Non-circular by construction: gold = human labels (independent); judgment is anchored to
the official requirement (external), not the model's free opinion; cite-required so a hit
must point to real student text. This phase establishes the residual; Phase 2 adds the
Codex/Opus adversarial + anchor-verify layer.
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
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

ART = REPO / "artifacts/luban_human_validation_v1/po_slice_20260601"
OUT = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
PACKET = ART / "po_review_packet.json"
HUMAN = ART / "po_labels_filled.csv"

GRADERS = [("deepseek", "盲标判分员A"), ("dashscope", "盲标判分员B")]

VERDICT_SYS = (
    "你是一级建造师建筑实务案例题盲标判分员。对给定的一个采分点,判断学生作答是否命中。"
    "判断必须严格锚定到官方依据 official_basis 与该点的踩字/列举规则 list_rule——这是唯一权威,"
    "不是你的主观印象。踩字铁律:必须命中规范术语原文,近义/错位不算(如要求'反铲挖掘机',"
    "学生只写'挖掘机'=未命中该项)。列举型按规则逐项扣分。命中必须能 cite 学生作答里的逐字依据。"
    "只输出 JSON: {\"verdict\":\"hit|partial|miss\",\"score\":<0..max_score>,"
    "\"student_span\":\"<学生作答里支撑判断的逐字片段,miss则空>\",\"reason\":\"<对照official_basis的简短依据>\"}"
)


def _grade(call, point: dict, answer_text: str, case: dict) -> dict:
    payload = {
        "采分点": point.get("label"),
        "official_basis": point.get("official_basis"),
        "list_rule": point.get("list_rule"),
        "max_score": point.get("max_score"),
        "题干_背景": (case.get("stem") or "")[:400],
        "学生作答全文": answer_text,
    }
    messages = [
        {"role": "system", "content": VERDICT_SYS},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        result = call("grade", messages)
        obj = json.loads(result["content"])
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "error", "score": None, "student_span": "", "reason": str(exc)[:120]}
    return {
        "verdict": str(obj.get("verdict") or "error"),
        "score": obj.get("score"),
        "student_span": str(obj.get("student_span") or ""),
        "reason": str(obj.get("reason") or ""),
    }


def main() -> int:
    packet = json.loads(PACKET.read_text("utf-8"))
    cases = {c["case_id"]: c for c in packet["cases"]}
    # index points + student answers
    point_by = {}
    answer_by = {}
    for c in packet["cases"]:
        for p in c.get("gold_scoring_points") or []:
            point_by[(c["case_id"], p["point_id"])] = p
        for s in c.get("samples") or []:
            answer_by[(c["case_id"], s["student_id"])] = s["answer_text"]

    rows = list(csv.DictReader(HUMAN.open("r", encoding="utf-8")))
    calls = {}
    for prov, _ in GRADERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=90, max_tokens=600)
        if c is None:
            raise SystemExit(f"{prov} API key missing")
        calls[prov] = c

    def work(row):
        key_p = (row["case_id"], row["point_id"])
        key_a = (row["case_id"], row["student_id"])
        point = point_by.get(key_p)
        answer = answer_by.get(key_a)
        if point is None or answer is None:
            return None
        out = {
            "case_id": row["case_id"], "student_id": row["student_id"], "point_id": row["point_id"],
            "max_score": float(row["max_score"]),
            "human_hit": row["human_hit"], "human_score": float(row["human_score"] or 0),
            "human_note": row["human_note"],
        }
        for prov, _ in GRADERS:
            out[prov] = _grade(calls[prov], point, answer, cases[row["case_id"]])
        return out

    results = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(work, rows):
            if r:
                results.append(r)

    # metrics vs human (external gold)
    def norm_hit(v):  # collapse to binary hit-ish for agreement
        return "hit" if v in ("hit",) else ("partial" if v == "partial" else "miss")
    metrics = {}
    for prov, _ in GRADERS:
        agree = sum(1 for r in results if norm_hit(r[prov]["verdict"]) == norm_hit(r["human_hit"]))
        scored = [(r[prov]["score"], r["human_score"]) for r in results
                  if isinstance(r[prov]["score"], (int, float))]
        mae = sum(abs(a - b) for a, b in scored) / len(scored) if scored else None
        errs = sum(1 for r in results if r[prov]["verdict"] == "error")
        metrics[prov] = {"point_hit_agreement": round(agree / len(results), 4),
                         "score_mae": round(mae, 4) if mae is not None else None,
                         "error_rows": errs, "n": len(results)}
    # cross-model consensus (both agree with each other) coverage + its human agreement
    consensus = [r for r in results if norm_hit(r["deepseek"]["verdict"]) == norm_hit(r["dashscope"]["verdict"])]
    cons_human = sum(1 for r in consensus if norm_hit(r["deepseek"]["verdict"]) == norm_hit(r["human_hit"]))
    metrics["cross_model_consensus"] = {
        "consensus_rate": round(len(consensus) / len(results), 4),
        "consensus_human_agreement": round(cons_human / len(consensus), 4) if consensus else None,
        "note": "where DeepSeek and Qwen agree, how often does that agreed verdict match human gold",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase1_blind_grader_results.json").write_text(json.dumps({
        "schema": "luban_multi_ai_anchored_grading_phase1.v1", "generated_at_date": "2026-06-14",
        "classification": {"candidate_only": True, "review_only": True,
                           "gold_is_human_not_ai": True, "anchored_non_circular": True},
        "roles": {"deepseek": "盲标判分员A(生产lane)", "dashscope": "盲标判分员B(跨家族)"},
        "metrics": metrics, "rows": results,
    }, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
