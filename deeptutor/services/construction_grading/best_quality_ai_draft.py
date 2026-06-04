"""Best-Quality 4-model adjudicated AI-Draft (test-env / shadow / candidate_only).

This is the HIGHEST-CAPABILITY research/test grading mode — it does NOT省 models:
it adjudicates the four heterogeneous jurors (GPT5.5 / Opus4.8 / DeepSeek-V4 /
Qwen3.7) per scoring point, with policy-aware adjudication:
  - exact_required disagreement -> take the STRICT side (踩字 discipline: 近义/半术语不给分)
  - list_rule disagreement      -> semantic majority / fact-coverage partial (not substring)
  - hard split (no clear majority) -> high_risk_review (genuine ambiguity to a human)

It is a fat skill: all voting / adjudication / disagreement logic lives here. The
guards (span fail-closed, high_risk/unsupported never auto_certified, pending_review
score != 0, learning_evidence payload preview) are REUSED from ai_draft_shadow.py —
NOT re-implemented. Output schema matches the DeepSeek fast draft so the UI barely changes.

NOT production authority. Does NOT touch CaseGradingSkillKernel, RAG, runtime, or any DB.
This round it adjudicates CACHED real 4-model predictions (source clearly labeled); if no
4-model predictions are available it fails closed (best_quality_unavailable) and NEVER
impersonates best-quality with a single DeepSeek pass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.ai_draft_shadow import _as_text, build_ai_draft

REPO = Path(__file__).resolve().parents[3]
CACHED_4MODEL = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/unified_predictions_485_span_guarded.json"

# arm -> short juror name
ARM_TO_MODEL = {
    "gpt55_primary": "gpt",
    "opus48_primary": "opus",
    "deepseek_v4_flash_typed_policy_primary": "deepseek",
    "qwen37_plus_nothink_primary": "qwen",
}
HIT_ORD = {"miss": 0, "partial": 1, "hit": 2}


class BestQualityUnavailable(Exception):
    """Raised when 4-model predictions are not available — fail closed, never impersonate."""


def load_cached_4model_predictions(case_id: str, student_id: str) -> dict[str, dict]:
    """{model: {point_id: pred}} from the cached 485 real 4-model run for one sample."""
    if not CACHED_4MODEL.exists():
        raise BestQualityUnavailable("cached 4-model predictions file not found")
    data = json.loads(CACHED_4MODEL.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for s in data.get("prediction_sets", []):
        model = ARM_TO_MODEL.get(s["arm"])
        if not model:
            continue
        out[model] = {p["point_id"]: p for p in s["predictions"]
                      if p.get("case_id") == case_id and p.get("student_id") == student_id}
    present = {m: v for m, v in out.items() if v}
    if len(present) < 3:  # need a real jury, not 1-2 models
        raise BestQualityUnavailable(f"only {len(present)} models have predictions for {case_id}/{student_id}")
    return out


def _adjudicate_point(point_id: str, policy_type: str | None, votes: dict[str, dict]) -> tuple[dict, dict]:
    """Return (adjudicated_prediction, extra_fields). votes: {model: pred}."""
    labels = {m: str(v.get("hit") or "miss") for m, v in votes.items()}
    n = len(labels)
    from collections import Counter
    tally = Counter(labels.values())
    top_label, top_n = tally.most_common(1)[0]
    distinct = len(tally)

    hard_split = (top_n * 2 <= n)  # no strict majority (e.g. 2-2 or 1-1-1-1 / 2-1-1)
    if distinct == 1:
        adj_label, reason = top_label, "四模一致"
    elif policy_type == "exact_required":
        # 踩字 discipline: take the STRICTER side on disagreement (lowest ordinal among votes)
        adj_label = min(labels.values(), key=lambda h: HIT_ORD.get(h, 0))
        reason = "exact_required 取严：踩字纪律，近义/半术语不给分"
    elif policy_type == "list_rule":
        # semantic: majority; tie -> partial (fact-coverage credit, not substring)
        adj_label = top_label if top_n * 2 > n else "partial"
        reason = "list_rule 语义裁决：按事实覆盖多数派 partial（非机械 substring）"
    else:
        adj_label = top_label if top_n * 2 > n else min(labels.values(), key=lambda h: HIT_ORD.get(h, 0))
        reason = "多数裁决" if top_n * 2 > n else "无多数，取严"

    # score = mean of models that gave the adjudicated label; miss -> 0
    agree_scores = [float(votes[m].get("score") or 0) for m in votes if labels[m] == adj_label]
    adj_score = 0.0 if adj_label == "miss" else round(sum(agree_scores) / len(agree_scores), 3) if agree_scores else 0.0
    # evidence_span: from a model with the adjudicated label + non-empty span (prefer opus, gpt)
    span = ""
    for m in ("opus", "gpt", "qwen", "deepseek"):
        if m in votes and labels.get(m) == adj_label and _as_text(votes[m].get("evidence_span")).strip():
            span = _as_text(votes[m].get("evidence_span"))
            break

    disagreement = " ".join(f"{m.upper()}:{labels[m]}" for m in ("gpt", "opus", "deepseek", "qwen") if m in labels)
    disagreement += f" → 裁决 {adj_label}"
    pred = {
        "point_id": point_id, "hit": adj_label, "score": adj_score,
        "evidence_span": span, "rationale": reason,
        # genuine ambiguity -> route to human review (quality feature, not a guard duplication)
        "high_risk": bool(hard_split and distinct >= 2),
    }
    extra = {
        "model_votes": {m: {"hit": labels[m], "score": votes[m].get("score")} for m in labels},
        "disagreement_summary": disagreement,
        "adjudication_reason": reason,
    }
    return pred, extra


def adjudicate(points: list[dict], model_outputs: dict[str, dict]) -> tuple[list[dict], dict]:
    adjudicated, extras = [], {}
    for sp in points:
        pid = sp["point_id"]
        policy_type = (sp.get("typed_policy") or {}).get("policy_type")
        votes = {m: outs[pid] for m, outs in model_outputs.items() if pid in outs}
        if len(votes) < 3:
            # not enough jurors for this point -> route to review, do not fabricate
            adjudicated.append({"point_id": pid, "hit": "miss", "score": 0, "evidence_span": "",
                                "rationale": "本点四模型预测不足，转复核", "high_risk": True})
            extras[pid] = {"model_votes": {m: {"hit": votes[m].get("hit")} for m in votes},
                           "disagreement_summary": "insufficient jurors", "adjudication_reason": "jurors<3 → review"}
            continue
        pred, extra = _adjudicate_point(pid, policy_type, votes)
        adjudicated.append(pred)
        extras[pid] = extra
    return adjudicated, extras


def best_quality_draft(question: dict, student_answer: str, model_outputs: dict[str, dict], *,
                       points: list[dict] | None = None, student_id: str | None = None,
                       source: str = "cached_4model_485", artifact_gate: Any = None) -> dict:
    """Adjudicate 4-model votes -> draft. Reuses ai_draft_shadow guards via build_ai_draft.

    Best-Quality is subject to the SAME QuestionGradingArtifact runtime gate as the
    fast path: it forwards ``artifact_gate`` to ``build_ai_draft`` (no duplicate gate
    logic). A missing/draft/blocked artifact downgrades every point here too.
    """
    points = points if points is not None else (question.get("scoring_points") or [])
    adjudicated, extras = adjudicate(points, model_outputs)
    draft = build_ai_draft(question, student_answer, adjudicated, points=points,
                           student_id=student_id, artifact_gate=artifact_gate)
    # re-mark authority/engine + source provenance (UI must show this is not a single-model draft)
    draft["authority"] = "best_quality_4model_shadow"
    draft["engine"] = "best_quality_4model"
    draft["model_set"] = ["gpt55", "opus48", "deepseek_v4", "qwen37"]
    draft["prediction_source"] = source
    draft["candidate_only"] = True
    draft["not_production_grade"] = True
    for p in draft["point_results"]:
        p.update(extras.get(p["point_id"], {}))
    return draft


def best_quality_for_golden(question: dict, student_id: str | None = None) -> dict:
    """Convenience: adjudicate cached real 4-model predictions for a golden case sample."""
    case_id = question.get("case_id") or question.get("id")
    eval_samples = question.get("eval_samples") or [{}]
    es = next((e for e in eval_samples if e.get("student_id") == student_id), eval_samples[0])
    sid = es.get("student_id")
    answer = es.get("answer_text", "")
    model_outputs = load_cached_4model_predictions(case_id, sid)
    # build scoring points (with typed_policy) the same way the fast path does
    from scripts.run_luban_ai_draft_grading import _golden_points  # thin reuse of golden->points
    points = question.get("scoring_points") or _golden_points(question)
    return best_quality_draft(question, answer, model_outputs, points=points, student_id=sid)
