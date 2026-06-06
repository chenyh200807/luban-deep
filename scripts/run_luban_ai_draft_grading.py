#!/usr/bin/env python3
"""鲁班 AI-Draft 测试评分工作流（test-env / shadow / candidate_only）。

把已离线验证的 DeepSeek Arm2 semantic protocol + span guard + exact_required
rationale fallback + selective-abstention(model-observable proxy) 串成一个可对
真实/模拟学生答案产出 "AI Draft" 的离线封装。

边界（红线）：
- 不是 production grading authority；绝不替换 CaseGradingSkillKernel，也不并入 submission_grader_agent。
- 输出固定标 authority=ai_draft_shadow / candidate_only=true / not_production_grade=true。
- evidence_span 必须逐字出现在 student_answer，否则 unsupported=true（fail-closed）。
- high_risk_review 仅表示"不自动认证"，不等于正确；high_risk 点不提升 mastery。
- 默认 dry_run：只构 learning_evidence payload preview，不写 learner_memory_events。
- 写回（writeback）只复用现有 write_grading_error_events / build_learning_evidence_payload，不新建表、不新建第二套 memory。
- 不接 RAG 进评分。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.build_luban_list_rule_semantic_model_bakeoff import ARM_PROMPTS  # noqa: E402
# single source of truth for the shadow assembler + guards lives in the service module
from deeptutor.services.construction_grading.ai_draft_shadow import (  # noqa: E402
    DRAFT_MARKERS,
    _as_text,
    apply_guards,
    build_ai_draft,
)

PROTOCOL = ARM_PROMPTS["list_rule_semantic_protocol"]
GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
OUT = REPO / "artifacts/luban_consensus_gold/ai_draft_test_20260604"


def ai_draft_grade(question: dict, student_answer: str, *, predictions: list[dict] | None = None,
                   client=None, abstain_tau: float = 0.6, build_preview: bool = True,
                   student_id: str | None = None) -> dict:
    """Thin wrapper: resolve golden scoring points, run DeepSeek if needed, delegate
    assembly to the service module (single source of truth)."""
    points = question.get("scoring_points") or _golden_points(question)
    if predictions is None:
        predictions = _run_deepseek(client, question, student_answer, points)
    return build_ai_draft(question, student_answer, predictions, points=points,
                          abstain_tau=abstain_tau, build_preview=build_preview, student_id=student_id)


def _golden_points(question):
    return [{"point_id": sp["point_id"], "label": sp.get("label"), "max_score": sp.get("max_score"),
             "typed_policy": _golden_typed_policy(question["case_id"], sp["point_id"])}
            for sp in (question.get("gold_scoring_points") or [])]


_TP_CACHE = {}


_TP_BUNDLE = REPO / "deeptutor/services/construction_grading/runtime_supply/v1_limited_default/golden_typed_policy.jsonl"


def _golden_typed_policy(case_id, point_id):
    if not _TP_CACHE:
        # DEFAULT: tracked minimal typed-policy bundle (clean-checkout safe). The gitignored review
        # packets are a dev/test fallback only.
        if _TP_BUNDLE.exists():
            for ln in _TP_BUNDLE.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if ln:
                    r = json.loads(ln)
                    _TP_CACHE.setdefault((r["case_id"], r["point_id"]), r.get("typed_policy"))
        else:
            for pk in ("artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_typed_policy_packet.json",
                       "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_typed_policy_packet.json"):
                p = REPO / pk
                if p.exists():
                    for t in json.loads(p.read_text(encoding="utf-8"))["tasks"]:
                        for sp in t["scoring_points"]:
                            _TP_CACHE.setdefault((t["case_id"], sp["point_id"]), sp.get("typed_policy"))
    return _TP_CACHE.get((case_id, point_id)) or {}


def _run_deepseek(client, question, student_answer, points):
    if client is None:
        client = _client()
    ctx = {"case_id": question.get("case_id"), "official_answer": question.get("official_answer", ""),
           "penalty_rule": question.get("penalty_rule", ""),
           "scoring_points": points, "student_answer": student_answer}
    prompt = PROTOCOL + "\n任务(JSON):\n" + json.dumps(ctx, ensure_ascii=False)
    n = len(points)
    for _ in range(2):
        try:
            r = client.chat.completions.create(model="deepseek-v4-flash", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=4000)
            preds = _parse(r.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001
            print("  err", str(exc)[:80], flush=True); preds = []
        if len(preds) == n:
            return preds
    return preds


def _client():
    from openai import OpenAI
    env = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
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


def build_run_summary(drafts: list[dict], selection_keys: set, available_samples: int) -> dict:
    """run_summary 口径：selected = 本次按 filter 选中的样本；completion_rate 按 selected 算，
    不按 available 算（避免把 100/100 显示成 51%）。available 仅作诊断。"""
    lats_sorted = sorted(d["latency_s"] for d in drafts if "latency_s" in d)

    def pct(p):
        return lats_sorted[min(len(lats_sorted) - 1, int(p * (len(lats_sorted) - 1)))] if lats_sorted else 0
    selected = len(selection_keys)
    completed = sum(1 for d in drafts if (d.get("question_id"), d.get("student_id")) in selection_keys)
    return {
        "dry_run": True, "writeback": False,
        "available_samples": available_samples,
        "selected_samples": selected,
        "completed_selected_samples": completed,
        "selected_completion_rate": round(completed / (selected or 1), 4),
        "total_points": sum(d["point_count"] for d in drafts),
        "parse_failures": sum(1 for d in drafts if d.get("parse_status") != "ok"),
        "unsupported_points": sum(d["unsupported_count"] for d in drafts),
        "high_risk_points": sum(d["high_risk_review_count"] for d in drafts),
        "auto_certified_points": sum(d["auto_certified_count"] for d in drafts),
        "latency_p50": pct(0.50), "latency_p95": pct(0.95), "latency_max": (lats_sorted[-1] if lats_sorted else 0),
    }


def _sample_set(cases, *, all_samples, case_id, limit, offset):
    samples = []
    for c in cases:
        if case_id and c.get("case_id") != case_id:
            continue
        evals = c.get("eval_samples") or [{}]
        if not all_samples:
            evals = evals[:1]
        for es in evals:
            samples.append((c, es))
    samples = samples[offset:]
    if limit:
        samples = samples[:limit]
    return samples


def _cached_preds(cache_dir: Path, case_id, student_id):
    f = cache_dir / f"{case_id}__{student_id}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("predictions")
        except Exception:  # noqa: BLE001
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=int, default=0, help="legacy: run N golden cases (first eval_sample)")
    ap.add_argument("--all-samples", action="store_true", help="run all 20 cases x 5 eval_samples = 100")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--case-id", default="")
    ap.add_argument("--resume", action="store_true", help="skip samples already in results (avoid duplicate real calls)")
    ap.add_argument("--cache-dir", default="")
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = out / "raw_model_outputs"
    raw_dir.mkdir(exist_ok=True)
    cache_dir = Path(args.cache_dir) if args.cache_dir else raw_dir
    results_path = out / "ai_draft_results.json"
    jsonl_path = out / "ai_draft_results.jsonl"
    failures_path = out / "failures.jsonl"

    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    if args.smoke:  # legacy compat
        samples = _sample_set(cases[: args.smoke], all_samples=False, case_id=args.case_id, limit=0, offset=0)
    else:
        samples = _sample_set(cases, all_samples=args.all_samples, case_id=args.case_id, limit=args.limit, offset=args.offset)

    existing = []
    done = set()
    if args.resume and results_path.exists():
        existing = json.loads(results_path.read_text(encoding="utf-8")).get("drafts", [])
        done = {(d.get("question_id"), d.get("student_id")) for d in existing}

    client = _client()
    drafts = list(existing)
    for c, es in samples:
        key = (c.get("case_id"), es.get("student_id"))
        if key in done:
            continue
        t0 = time.time()
        preds = _cached_preds(cache_dir, key[0], key[1]) if (args.resume or args.cache_dir) else None
        from_cache = preds is not None
        if preds is None:
            points = _golden_points(c)
            preds = _run_deepseek(client, c, es.get("answer_text", ""), points)
            (raw_dir / f"{key[0]}__{key[1]}.json").write_text(
                json.dumps({"case_id": key[0], "student_id": key[1], "predictions": preds}, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            d = ai_draft_grade(c, es.get("answer_text", ""), predictions=preds, student_id=key[1])
            d["latency_s"] = round(time.time() - t0, 2)
            d["from_cache"] = from_cache
            drafts.append(d)
            if d["parse_status"] != "ok":
                with failures_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"case_id": key[0], "student_id": key[1], "parse_status": d["parse_status"],
                                        "got": d["point_count"], "expected": d["expected_point_count"]}, ensure_ascii=False) + "\n")
            print(f"{key[0]}/{key[1]}: parse={d['parse_status']} auto={d['auto_certified_count']}/{d['point_count']} "
                  f"hr={d['high_risk_review_count']} unsup={d['unsupported_count']} model={d['model_draft_score']} "
                  f"cert={d['auto_certified_score']} pending={d['pending_review_score']} ({d['latency_s']}s){' [cache]' if from_cache else ''}", flush=True)
        except Exception as exc:  # noqa: BLE001
            with failures_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": key[0], "student_id": key[1], "error": str(exc)[:300]}, ensure_ascii=False) + "\n")
            print(f"{key[0]}/{key[1]}: ERROR {str(exc)[:80]}", flush=True)
            continue
        # checkpoint each sample
        results_path.write_text(json.dumps({"dry_run": True, "writeback": False, "count": len(drafts), "drafts": drafts}, ensure_ascii=False, indent=2), encoding="utf-8")

    with jsonl_path.open("w", encoding="utf-8") as f:
        for d in drafts:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    selection_keys = {(c.get("case_id"), es.get("student_id")) for c, es in samples}
    available_samples = sum(len(c.get("eval_samples") or [{}]) for c in cases)
    summary = build_run_summary(drafts, selection_keys, available_samples)
    pts = summary["total_points"]
    (out / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DRY-RUN (no writeback). completed {len(drafts)} drafts, {pts} points -> {out}")
    print(f"summary: {json.dumps(summary, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
