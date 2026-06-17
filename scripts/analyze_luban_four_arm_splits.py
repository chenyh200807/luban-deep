#!/usr/bin/env python3
"""四臂 A/B 同源循环拆表 + latency 分位 + residual 分类（读 per_row.jsonl，纯离线）。

拆三张表（用户 2026-06-11 指令）：
1. ai_governed_gold vs ai_council_directional；
2. cross_model_agreed（qwen-max 非 DeepSeek 独立支持 + 无争议 route）vs
   deepseek_dominant_or_disputed（DeepSeek 主导或 arbitration/unconfirmed 争议点）；
3. residual 抽样清单（供 Qwen/人工盲审）。
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162"
GOLD = ROOT / "artifacts/luban_grading_artifacts/m35_gold_labeling_full/student_answers.jsonl"

DISPUTED_ROUTES = {"arbitration", "arbitration_unresolved", "majority_review_unconfirmed"}


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    idx = min(len(data) - 1, max(0, int(round(q * (len(data) - 1)))))
    return round(data[idx], 2)


def row_bucket(gold_row: dict[str, Any]) -> str:
    points = list(gold_row.get("point_label_provenance") or [])
    if not points:
        return "deepseek_dominant_or_disputed"
    for p in points:
        if str(p.get("route") or "") in DISPUTED_ROUTES:
            return "deepseek_dominant_or_disputed"
        if "qwen-max" not in list(p.get("supporting_model_ids") or []):
            return "deepseek_dominant_or_disputed"
    return "cross_model_agreed"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"sample_count": 0}
    return {
        "sample_count": len(rows),
        "score_mae": round(st.mean([r["abs_score_delta"] for r in rows]), 4),
        "point_precision": round(st.mean([r["point_precision"] for r in rows]), 4),
        "point_recall": round(st.mean([r["point_recall"] for r in rows]), 4),
        "fail_open_rate": round(st.mean([1.0 if r["over_credit"] else 0.0 for r in rows]), 4),
        "evidence_span_rate": round(st.mean([r["evidence_span_rate"] for r in rows]), 4),
        "high_risk_review_rate": round(st.mean([1.0 if r.get("high_risk_review") else 0.0 for r in rows]), 4),
    }


def main() -> int:
    per_row = [json.loads(l) for l in (BASE / "per_row.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    gold_rows = {str(r.get("answer_id")): r for r in
                 (json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip())}
    by_key = {(str(r.get("question_id")), str(r.get("student_id"))): r for r in gold_rows.values()}

    arms: dict[str, list[dict[str, Any]]] = {}
    for r in per_row:
        arms.setdefault(r["arm"], []).append(r)

    out: dict[str, Any] = {"schema_version": "luban_four_arm_split_analysis.v1"}

    # 表 1：label authority 拆分
    table1: dict[str, Any] = {}
    for arm, rows in arms.items():
        table1[arm] = {
            label: summarize([r for r in rows if r.get("label_authority") == label])
            for label in ("ai_governed_gold", "ai_council_directional")
        }
    out["split_by_label_authority"] = table1

    # 表 2：同源循环拆分（按 gold provenance 路由/支持模型）
    buckets: dict[tuple[str, str], str] = {}
    for key, g in by_key.items():
        buckets[key] = row_bucket(g)
    table2: dict[str, Any] = {}
    bucket_counts = {"cross_model_agreed": 0, "deepseek_dominant_or_disputed": 0}
    for key, b in buckets.items():
        bucket_counts[b] += 1
    for arm, rows in arms.items():
        table2[arm] = {
            bucket: summarize([
                r for r in rows
                if buckets.get((str(r["question_id"]), str(r["student_id"]))) == bucket
            ])
            for bucket in ("cross_model_agreed", "deepseek_dominant_or_disputed")
        }
    out["split_by_provenance_bucket"] = {"row_bucket_counts": bucket_counts, "arms": table2}

    # latency 分位（judge 臂真实 latency；kernel 臂为本地微秒级无意义）
    judge_rows = arms.get("artifact_first_llm_judge") or []
    lat = [float(r["latency_ms"]) for r in judge_rows]
    out["judge_latency_ms"] = {"p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95),
                               "max": _percentile(lat, 1.0)}

    # 表 3：residual 抽样（judge 与 gold 分歧最大 + 部分一致样本作对照）
    ranked = sorted(judge_rows, key=lambda r: -float(r["abs_score_delta"]))
    disagree = ranked[:18]
    agree = [r for r in ranked if float(r["abs_score_delta"]) == 0.0][:8]
    sample = [
        {"question_id": r["question_id"], "student_id": r["student_id"],
         "abs_score_delta": r["abs_score_delta"], "predicted_score": r["predicted_score"],
         "gold_score": r["gold_score"], "over_credit": r["over_credit"],
         "high_risk_review": r.get("high_risk_review"),
         "bucket": buckets.get((str(r["question_id"]), str(r["student_id"]))),
         "label_authority": r.get("label_authority"),
         "kind": "disagree" if float(r["abs_score_delta"]) > 0 else "agree_control"}
        for r in disagree + agree
    ]
    out["residual_audit_sample"] = sample

    (BASE / "analysis_splits.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    compact = {
        "bucket_counts": bucket_counts,
        "judge_latency_ms": out["judge_latency_ms"],
        "judge_by_label": table1.get("artifact_first_llm_judge"),
        "judge_by_bucket": table2.get("artifact_first_llm_judge"),
        "legacy_by_bucket": table2.get("legacy"),
        "compiled_by_bucket": table2.get("artifact_first_compiled"),
        "residual_sample_count": len(sample),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
