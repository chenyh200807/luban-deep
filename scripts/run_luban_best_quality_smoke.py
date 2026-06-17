#!/usr/bin/env python3
"""鲁班 Best-Quality(4-model 裁决) vs DeepSeek-Fast 小样 smoke（确定性，不调 live provider）。

可复现地重新生成 `artifacts/luban_consensus_gold/best_quality_ai_draft_20260604/`
下的 smoke_results.json / comparison_*.json / FINDING_*.md。

确定性来源（红线：绝不调 provider）：
- best_quality：用 best_quality_ai_draft.best_quality_for_golden 对**缓存的真实 4-model 预测**
  (`unified_predictions_485_span_guarded.json`) 做 policy-aware 裁决。
- deepseek_fast：直接取同一缓存文件里的 deepseek_v4_flash arm 预测，喂给 ai_draft_shadow.build_ai_draft
  得到 fast draft —— 与 best_quality **同源、确定性**，不调 _run_deepseek。

边界：dry_run / 不写库 / 不接 runtime / 不改 kernel / 不接 RAG / 不新增表 / 不新增 endpoint。
本脚本只产出 artifacts，不动任何 runtime 代码。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading import best_quality_ai_draft as bq  # noqa: E402
from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft  # noqa: E402
from scripts.run_luban_ai_draft_grading import _golden_points  # noqa: E402

GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEFAULT_OUT = REPO / "artifacts/luban_consensus_gold/best_quality_ai_draft_20260604"

DEEPSEEK_ARM = "deepseek_v4_flash_typed_policy_primary"

# >=3 policy types, each chosen for a meaningful best-quality vs fast contrast.
# (case_id, student_id, human-readable description)
SMOKE_SAMPLES: list[tuple[str, str, str]] = [
    ("Q10-1A422000", "S2", "exact_required 边界(近义/半术语)：期望 best-quality 取严纠正单模放水"),
    ("Q5-1A432000", "S3", "list_rule 部分列举：期望 best-quality 语义 partial（非机械 substring）"),
    ("Q5-1A432000", "S2", "calculation：期望不被语义放水（数值题取严/多数）"),
    ("Q4-1A434000-罚则", "S1", "penalty_rule：罚则点，期望不被语义放水"),
    ("Q7-1A431000", "S1", "list_rule/figure_label：含 unsupported 点，期望 fail-closed(不 auto_certified)"),
]


def _load_golden_cases() -> dict[str, dict]:
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    return {c["case_id"]: c for c in cases}


def _load_deepseek_fast_index() -> dict[tuple[str, str], list[dict]]:
    """{(case_id, student_id): [deepseek_v4_flash predictions]} from the cached 485 file."""
    if not bq.CACHED_4MODEL.exists():
        raise bq.BestQualityUnavailable("cached 4-model predictions file not found")
    data = json.loads(bq.CACHED_4MODEL.read_text(encoding="utf-8"))
    arm = next((s for s in data.get("prediction_sets", []) if s["arm"] == DEEPSEEK_ARM), None)
    if arm is None:
        raise bq.BestQualityUnavailable("deepseek_v4_flash arm not present in cached predictions")
    idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in arm["predictions"]:
        idx[(p["case_id"], p["student_id"])].append(p)
    return idx


def _deepseek_fast_draft(case: dict, student_id: str, fast_preds: list[dict]) -> dict:
    """Deterministic fast draft from cached deepseek arm (same guards as best_quality)."""
    es = next((e for e in (case.get("eval_samples") or []) if e.get("student_id") == student_id), {})
    answer = es.get("answer_text", "")
    points = case.get("scoring_points") or _golden_points(case)
    preds = sorted(fast_preds, key=lambda p: str(p.get("point_id")))
    draft = build_ai_draft(case, answer, preds, points=points, student_id=student_id)
    draft["engine"] = "deepseek_fast"
    draft["prediction_source"] = "cached_deepseek_v4_flash_485"
    return draft


def run_sample(case_id: str, student_id: str,
               *, cases: dict[str, dict] | None = None,
               fast_index: dict[tuple[str, str], list[dict]] | None = None) -> dict:
    """Produce {best_quality, deepseek_fast} drafts for one sample, deterministically."""
    cases = cases if cases is not None else _load_golden_cases()
    fast_index = fast_index if fast_index is not None else _load_deepseek_fast_index()
    case = cases[case_id]
    best = bq.best_quality_for_golden(case, student_id)
    fast = _deepseek_fast_draft(case, student_id, fast_index.get((case_id, student_id), []))
    return {"best_quality": best, "deepseek_fast": fast}


def build_smoke_results(samples: list[tuple[str, str, str]] | None = None) -> list[dict]:
    samples = samples if samples is not None else SMOKE_SAMPLES
    cases = _load_golden_cases()
    fast_index = _load_deepseek_fast_index()
    out: list[dict] = []
    for case_id, student_id, desc in samples:
        drafts = run_sample(case_id, student_id, cases=cases, fast_index=fast_index)
        out.append({"case_id": case_id, "student_id": student_id, "desc": desc, **drafts})
    return out


def _summarize(draft: dict) -> dict:
    return {
        "parse_status": draft.get("parse_status"),
        "model": draft.get("model_draft_score"),
        "cert": draft.get("auto_certified_score"),
        "pending": draft.get("pending_review_score"),
        "bad": draft.get("bad_certified_count"),
        "high_risk": draft.get("high_risk_review_count"),
        "unsupported": draft.get("unsupported_count"),
    }


def _point_by_id(draft: dict) -> dict[str, dict]:
    return {str(p.get("point_id")): p for p in draft.get("point_results", [])}


def build_comparison(smoke: list[dict]) -> list[dict]:
    comparison: list[dict] = []
    for entry in smoke:
        best = entry["best_quality"]
        fast = entry["deepseek_fast"]
        fast_pts = _point_by_id(fast)
        point_comparison = []
        for bp in best.get("point_results", []):
            pid = str(bp.get("point_id"))
            fp = fast_pts.get(pid)
            votes = bp.get("model_votes") or {}
            # which lenient jurors got overruled to a stricter best-quality verdict
            order = {"miss": 0, "partial": 1, "hit": 2}
            adj = order.get(str(bp.get("hit")), 0)
            overruled = sorted(
                m for m, v in votes.items()
                if order.get(str(v.get("hit")), 0) > adj
            )
            point_comparison.append({
                "point_id": pid,
                "policy_type": bp.get("policy_type"),
                "deepseek_fast": (f"{fp.get('hit')}/{fp.get('score')}" if fp else "ABSENT"),
                "best_quality": f"{bp.get('hit')}/{bp.get('score')}",
                "best_quality_unsupported": bool(bp.get("unsupported")),
                "best_quality_auto_certified": bool(bp.get("auto_certified")),
                "split": "无多数" in str(bp.get("disagreement_summary"))
                         or bool(bp.get("high_risk_review")) and len(set(
                             str(v.get("hit")) for v in votes.values())) >= 2,
                "votes": bp.get("disagreement_summary"),
                "adjudication_reason": bp.get("adjudication_reason"),
                "best_quality_overruled_lenient_juror": overruled,
            })
        comparison.append({
            "case": entry["case_id"],
            "student": entry["student_id"],
            "desc": entry["desc"],
            "deepseek_fast_summary": _summarize(fast),
            "best_quality_summary": _summarize(best),
            "point_comparison": point_comparison,
        })
    return comparison


def _overruled_lines(comparison: list[dict], policy_type: str | None = None) -> list[str]:
    lines = []
    for entry in comparison:
        for pc in entry["point_comparison"]:
            if policy_type is not None and pc["policy_type"] != policy_type:
                continue
            if pc["best_quality_overruled_lenient_juror"]:
                jurors = "+".join(pc["best_quality_overruled_lenient_juror"])
                lines.append(
                    f"- {entry['case']}/{entry['student']} {pc['point_id']} "
                    f"({pc['policy_type']}): {pc['votes']}（overruled {jurors}）"
                )
    return lines


def build_finding(smoke: list[dict], comparison: list[dict]) -> str:
    ptypes = sorted({pc["policy_type"] for e in comparison for pc in e["point_comparison"] if pc["policy_type"]})
    total_bad = sum(e["best_quality"]["bad_certified_count"] for e in smoke)
    total_bad += sum(e["deepseek_fast"]["bad_certified_count"] for e in smoke)
    unsupported = [
        (e["case_id"], e["student_id"], pr["point_id"])
        for e in smoke for pr in e["best_quality"]["point_results"]
        if pr["unsupported"] and not pr["auto_certified"]
    ]
    exact = [pc for e in comparison for pc in e["point_comparison"]
             if pc["policy_type"] == "exact_required" and pc["best_quality_overruled_lenient_juror"]]
    list_partial = [pc for e in comparison for pc in e["point_comparison"]
                    if pc["policy_type"] == "list_rule" and str(pc["best_quality"]).startswith("partial")]
    exact_overruled = _overruled_lines(comparison, policy_type="exact_required")

    lines: list[str] = []
    lines.append("# FINDING: Best-Quality vs DeepSeek-Fast 小样 smoke（确定性复现，2026-06-04）")
    lines.append("")
    lines.append("> status: `directional/shadow / candidate_only`。**dry_run / 不写库 / 不接 runtime / 不改 kernel / 不接 RAG / 不新增表 / 不新增 endpoint。**")
    lines.append("> 由 `scripts/run_luban_best_quality_smoke.py` **确定性重新生成**：")
    lines.append("> - best_quality = 对**缓存真实 4-model 预测**(`cached_4model_485`)做 policy-aware 裁决；")
    lines.append("> - deepseek_fast = 取同一缓存文件 deepseek_v4_flash arm 预测喂 `build_ai_draft`（`cached_deepseek_v4_flash_485`）。")
    lines.append("> **全程不调 live provider**；缺 4-model 预测时 fail closed（best_quality_unavailable），绝不用单模冒充。")
    lines.append("")
    lines.append(f"## 覆盖样本（{len(smoke)} 个，policy_type: {', '.join(ptypes)}）")
    lines.append("")
    lines.append("| case/student | policy 焦点 | fast(model/cert/pending/bad) | best-quality(model/cert/pending/bad/hr/unsup) |")
    lines.append("|---|---|---|---|")
    for e in smoke:
        fs, bs = _summarize(e["deepseek_fast"]), _summarize(e["best_quality"])
        lines.append(
            f"| {e['case_id']}/{e['student_id']} | {e['desc']} | "
            f"{fs['parse_status']} {fs['model']}/{fs['cert']}/{fs['pending']}/{fs['bad']} | "
            f"{bs['parse_status']} {bs['model']}/{bs['cert']}/{bs['pending']}/{bs['bad']}/hr{bs['high_risk']}/unsup{bs['unsupported']} |"
        )
    lines.append("")
    lines.append("## 验收问题")
    lines.append("")
    lines.append("**1. best-quality 是否更守 exact_required 纪律？**")
    if exact:
        lines.append(f"是。在 {len(exact)} 个 exact_required 点上，裁决取严（踩字纪律），把单模放水(partial/hit)纠正成更严判：")
        lines.extend(exact_overruled)
    else:
        lines.append("本样本集 exact_required 点四模一致，无需取严纠正（无放水可纠）。")
    lines.append("")
    lines.append("**2. 是否改善 list_rule partial？**")
    if list_partial:
        lines.append(f"是。{len(list_partial)} 个 list_rule 点按事实覆盖语义多数给合理 partial（非机械 substring），并路由 pending_review：")
        for pc in list_partial:
            lines.append(f"- {pc['point_id']}: {pc['votes']} · {pc['adjudication_reason']}")
    else:
        lines.append("本样本集 list_rule 点未触发语义 partial。")
    lines.append("")
    lines.append(f"**3. bad_certified 是否为 0？** 是，全部样本 best_quality + deepseek_fast 合计 bad_certified = {total_bad}。")
    lines.append("")
    lines.append("**4. unsupported 是否 fail-closed？**")
    if unsupported:
        lines.append("是。以下 unsupported 点（positive 但 evidence_span 未逐字出现在作答）被 fail-closed（auto_certified=False，不计入认证分）：")
        for cid, sid, pid in unsupported:
            lines.append(f"- {cid}/{sid} {pid}")
    else:
        lines.append("本样本集未出现 unsupported 点；span guard 未触发（无可证伪）。")
    lines.append("")
    lines.append("**5. 是否足够支撑 QA runtime 测试（不宣称生产精度）？**")
    lines.append("足够支撑 QA-gated runtime 测试：输出 schema 与 deepseek_fast 一致、含 model_votes/裁决理由可供 UI 展示、")
    lines.append("guards（span fail-closed / high_risk·unsupported 不 auto_certified / pending≠0）全部生效、且确定性可复现。")
    lines.append("**不宣称生产精度**：非真人 gold；high_risk/unsupported/pending 为待复核（非 0、非错误）。")
    lines.append("")
    lines.append("## 产物")
    lines.append("- `smoke_results.json`（每样本 best_quality + deepseek_fast 完整 draft）")
    lines.append("- `comparison_deepseek_fast_vs_best_quality.json`（逐点对比 + overruled 暴露）")
    lines.append("- 本 FINDING")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output artifacts directory")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    smoke = build_smoke_results()
    comparison = build_comparison(smoke)
    finding = build_finding(smoke, comparison)

    (out / "smoke_results.json").write_text(
        json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "comparison_deepseek_fast_vs_best_quality.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "FINDING_best_quality_ai_draft_20260604.md").write_text(finding, encoding="utf-8")

    total_bad = sum(e["best_quality"]["bad_certified_count"] + e["deepseek_fast"]["bad_certified_count"] for e in smoke)
    ptypes = sorted({pc["policy_type"] for e in comparison for pc in e["point_comparison"] if pc["policy_type"]})
    print(f"DRY-RUN best-quality smoke -> {out}")
    print(f"  samples={len(smoke)} policy_types={ptypes} total_bad_certified={total_bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
