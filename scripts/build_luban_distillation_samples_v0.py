#!/usr/bin/env python3
"""鲁班 Best-Quality -> DeepSeek 蒸馏样本准备 v0（artifacts only / 不训练 / 不接生产）。

把 Best-Quality 4-model 裁决（best_quality_for_golden 对 *缓存* 485 真实四模预测的
adjudication 输出）+ question_grading_artifact 的题目级评分包，抽取成可用于后续
prompt / fine-tune / eval 的蒸馏样本 JSONL。

红线（与 Stream E 停止条件一致）：
- 不调用训练、不接 production runtime、不写真实用户库 / 生产库。
- 不重跑 485-QWK-consensus：只读已缓存的四模型预测（best_quality_for_golden 内部消费）。
- 未确认 high_risk / unsupported 的采分点 **绝不** 被标成 gold 正确答案
  （is_gold_label=False, label_status='pending_review'）。teacher-final 才是写入
  Learning Brain 的 authority；这里产出的是离线蒸馏候选，不是 mastery 来源。
- 不新建表、不动 CaseGradingSkillKernel、不让 RAG 进评分 authority。

每条样本（一个采分点）含：
  question(stem/official_answer) + scoring_artifact(policy_type/required_terms/max_score)
  + student_answer + best_quality adjudicated point_result(hit/score)
  + evidence_span + rationale + high_risk reason + model_votes。

输出：
  artifacts/luban_consensus_gold/distillation_samples_v0_20260604/distillation_samples.jsonl
  + manifest.json（计数、policy_type 分布、exact_required 纪律案例 vs list_rule partial 案例标注）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.best_quality_ai_draft import (  # noqa: E402
    BestQualityUnavailable,
    best_quality_for_golden,
)
from deeptutor.services.construction_grading.question_grading_artifacts import (  # noqa: E402
    _cases,
    build_question_grading_artifact,
)

VERSION_ID = "distillation_samples_v0_20260604"
SCHEMA_VERSION = "luban_distillation_sample.v0"
OUT_DIR = REPO / "artifacts/luban_consensus_gold" / VERSION_ID


def _artifact_points_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {sp["point_id"]: sp for sp in (artifact.get("scoring_points") or [])}


def _eval_sample(question: dict[str, Any], student_id: str) -> dict[str, Any]:
    for es in question.get("eval_samples") or []:
        if es.get("student_id") == student_id:
            return es
    return {}


def _case_tag(policy_type: str | None, hit: str) -> str:
    """Label which discipline a point exercises.

    - exact_required hit/partial -> 踩字纪律案例 (近义/半术语不给分)
    - list_rule partial          -> 事实覆盖部分给分案例 (非机械 substring)
    - otherwise                  -> generic
    """
    if policy_type == "exact_required" and hit in ("hit", "partial"):
        return "exact_required_discipline"
    if policy_type == "list_rule" and hit == "partial":
        return "list_rule_partial"
    return "generic"


def build_sample(
    question: dict[str, Any],
    student_id: str,
    draft: dict[str, Any],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    """Project one adjudicated draft + artifact into per-point distillation samples.

    A point is only a gold label (is_gold_label=True) when Best-Quality
    auto_certified it (not high_risk, not unsupported). Unconfirmed high_risk /
    unsupported points are kept as training context but explicitly marked
    pending_review so they are never consumed as a correct answer.
    """
    art_points = _artifact_points_by_id(artifact)
    es = _eval_sample(question, student_id)
    student_answer = es.get("answer_text", "")
    samples: list[dict[str, Any]] = []

    for pr in draft.get("point_results") or []:
        point_id = pr.get("point_id")
        art_sp = art_points.get(point_id, {})
        policy_type = pr.get("policy_type") or art_sp.get("policy_type")
        hit = str(pr.get("hit") or "miss")

        high_risk = bool(pr.get("high_risk_review"))
        unsupported = bool(pr.get("unsupported"))
        auto_certified = bool(pr.get("auto_certified"))
        # A gold label requires Best-Quality auto-certification: not high_risk,
        # not unsupported. This is the hard gate against distilling unconfirmed
        # high_risk points as correct answers.
        is_gold_label = auto_certified and not high_risk and not unsupported
        if unsupported:
            label_status = "unsupported"
        elif high_risk:
            label_status = "pending_review"
        else:
            label_status = "best_quality_certified"

        samples.append({
            "schema_version": SCHEMA_VERSION,
            "question_id": draft.get("question_id") or question.get("case_id"),
            "stem": question.get("stem", ""),
            "official_answer": question.get("official_answer", ""),
            "student_id": student_id,
            "student_answer": student_answer,
            "point_id": point_id,
            "scoring_artifact": {
                "policy_type": policy_type,
                "required_terms": list(art_sp.get("required_terms") or []),
                "max_score": art_sp.get("max_score", pr.get("max_score")),
                "list_rule": art_sp.get("list_rule"),
                "label": art_sp.get("label") or pr.get("expected_point_label"),
            },
            "point_result": {
                "hit": hit,
                "score": pr.get("score"),
                "max_score": pr.get("max_score"),
            },
            "evidence_span": pr.get("evidence_span", ""),
            "rationale": pr.get("rationale"),
            "model_votes": pr.get("model_votes") or {},
            "disagreement_summary": pr.get("disagreement_summary"),
            "adjudication_reason": pr.get("adjudication_reason"),
            "high_risk": high_risk,
            "high_risk_reason": pr.get("review_reason") if high_risk else None,
            "unsupported": unsupported,
            "is_gold_label": is_gold_label,
            "label_status": label_status,
            "case_tag": _case_tag(policy_type, hit),
            "best_quality_source": draft.get("prediction_source"),
            "model_set": list(draft.get("model_set") or []),
            "authority": draft.get("authority"),
            "candidate_only": True,
            "not_production_grade": True,
        })
    return samples


def build_distillation_samples() -> list[dict[str, Any]]:
    """Adjudicate every golden (case, student) sample that has >=3 cached jurors.

    Deterministic: iterates the golden fixture in order, consumes only cached
    4-model predictions (no live provider, no clock, no randomness). Samples
    where Best-Quality is unavailable (insufficient jurors) are skipped, not
    fabricated.
    """
    cases = _cases()
    samples: list[dict[str, Any]] = []
    for case_id, question in cases.items():
        artifact = build_question_grading_artifact(case_id)
        if artifact.get("artifact_missing"):
            continue
        for es in question.get("eval_samples") or []:
            student_id = es.get("student_id")
            if not student_id:
                continue
            try:
                draft = best_quality_for_golden(question, student_id)
            except BestQualityUnavailable:
                continue
            samples.extend(build_sample(question, student_id, draft, artifact))
    return samples


def build_manifest(samples: list[dict[str, Any]]) -> dict[str, Any]:
    policy_dist: dict[str, int] = {}
    for s in samples:
        pt = s["scoring_artifact"].get("policy_type") or "unknown"
        policy_dist[pt] = policy_dist.get(pt, 0) + 1
    case_tag_dist: dict[str, int] = {}
    for s in samples:
        case_tag_dist[s["case_tag"]] = case_tag_dist.get(s["case_tag"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "version_id": VERSION_ID,
        "sample_count": len(samples),
        "question_count": len({s["question_id"] for s in samples}),
        "student_sample_count": len({(s["question_id"], s["student_id"]) for s in samples}),
        "policy_type_distribution": policy_dist,
        "case_tag_distribution": case_tag_dist,
        "gold_label_count": sum(1 for s in samples if s["is_gold_label"]),
        "high_risk_count": sum(1 for s in samples if s["high_risk"]),
        "unsupported_count": sum(1 for s in samples if s["unsupported"]),
        "pending_review_count": sum(1 for s in samples if s["label_status"] == "pending_review"),
        "exact_required_discipline_count": case_tag_dist.get("exact_required_discipline", 0),
        "list_rule_partial_count": case_tag_dist.get("list_rule_partial", 0),
        "provenance": {
            "best_quality": "best_quality_for_golden over cached 4-model 485 predictions",
            "scoring_artifact": "build_question_grading_artifact (golden v1 + typed_policy)",
            "trains_model": False,
            "touches_production": False,
            "unconfirmed_high_risk_as_gold": False,
        },
        "notes": (
            "Offline distillation candidates only. is_gold_label=True iff "
            "Best-Quality auto_certified (not high_risk, not unsupported). "
            "Unconfirmed high_risk/unsupported points are kept with "
            "label_status pending_review/unsupported and is_gold_label=False — "
            "they are NEVER a correct answer. teacher-final remains the only "
            "Learning Brain write authority."
        ),
    }


def write_outputs(out_dir: Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = build_distillation_samples()
    manifest = build_manifest(samples)

    jsonl_path = out_dir / "distillation_samples.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"jsonl_path": str(jsonl_path), "manifest_path": str(manifest_path), "manifest": manifest}


def main() -> None:
    result = write_outputs()
    print(json.dumps(result["manifest"], ensure_ascii=False, indent=2))
    print(f"\nwrote: {result['jsonl_path']}")
    print(f"wrote: {result['manifest_path']}")


if __name__ == "__main__":
    main()
