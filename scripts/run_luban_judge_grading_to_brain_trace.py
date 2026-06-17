#!/usr/bin/env python3
"""Phase 2 闭环 trace：artifact_first_llm_judge 真实判分结果 → Grading-to-Brain 链。

链路（全部复用既有 authority，不建第二套 memory/schema）：
  judge result -> to_rubric_grading_event -> rubric_grader_v1.to_learning_evidence
  -> LearnerStateEvent(memory_kind=learning_evidence, dedupe_key 含 user/session/attempt/qid/artifact_version)
  -> learning_synthesis（release-eligibility 读过滤）
  -> LearnerClaim projection -> training intent -> PersonalizationContextPack -> NextBestAction
  -> retest condition

两个臂：
- shadow_blocked 臂：quality.writeback_eligible=False 的 judge 证据必须被 synthesis 拒之门外
  （claims/PCP 为空）—— 这是 contract 的安全反证。
- eligible 臂：同一证据以 hermetic QA fixture 资格（writeback_eligible=True，authority 标
  hermetic_qa_fixture，非 release truth）走通全链，并用第二次同错因 attempt 证明 repeat 信号。

安全不变量：只写 artifacts 输出目录；canonical_truth_written=False；不触 DB/远端/registry。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.services.construction_grading.artifact_first_llm_judge import (  # noqa: E402
    to_rubric_grading_event,
)
from deeptutor.services.construction_grading.rubric_grader_v1 import to_learning_evidence  # noqa: E402
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth  # noqa: E402
from deeptutor.services.learner_state.next_best_action import build_next_best_actions  # noqa: E402
from deeptutor.services.learner_state.personalization_context import (  # noqa: E402
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.service import LearnerStateEvent  # noqa: E402
from deeptutor.services.learner_state.training_intent import (  # noqa: E402
    build_learning_training_intent,
)

DEFAULT_PER_ROW = (
    ROOT
    / "artifacts/luban_grading_artifacts/four_arm_ab_20260611"
    / "live_full_162_v5_patched_gold/per_row.jsonl"
)
DEFAULT_MANIFEST = ROOT / "tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a/manifest.json"
USER = "qa_judge_loop"
BOT = "construction-exam"
NODE_CODE_RE = re.compile(r"(1A\d{6})")


def _sha(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _node_code_for(question: dict[str, Any]) -> str:
    """从题目 source chunk id（如 EXAM_1A433000_P0011_01）确定性提取教材 taxonomy 码；
    不发明新 taxonomy，仅复用 chunk id 内嵌的教材章节码，provenance 记录于 trace。"""
    for ref in list(question.get("source_refs") or []):
        m = NODE_CODE_RE.search(str(ref.get("chunk_id") or ""))
        if m:
            return m.group(1)
    return ""


def _pick_judge_row(per_row: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        r for r in per_row
        if r.get("arm") == "artifact_first_llm_judge"
        and any(m.get("status") == "miss" for m in (r.get("point_matches") or []))
        and any(m.get("status") in ("hit", "partial") for m in (r.get("point_matches") or []))
        and not r.get("high_risk_review")
    ]
    if not candidates:
        raise SystemExit("no judge row with mixed hit/miss found")
    return candidates[0]


def _event(event_id: str, payload: dict[str, Any], *, dedupe_key: str, created_at: str) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id, user_id=USER, source_feature="construction_grading",
        source_id=f"turn:{event_id}", source_bot_id=BOT, memory_kind="learning_evidence",
        dedupe_key=dedupe_key, created_at=created_at, payload_json=payload,
    )


def run_trace(*, out_dir: str, per_row_path: Path = DEFAULT_PER_ROW,
              manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    per_row = [json.loads(l) for l in per_row_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    questions = {str(q.get("question_id")): q
                 for q in json.loads(manifest_path.read_text(encoding="utf-8")).get("questions") or []}

    row = _pick_judge_row(per_row)
    qid = str(row["question_id"])
    question = questions[qid]
    node_code = _node_code_for(question)
    artifact_version = "luban_m35_fastapi_case_subquestions_20q_100a.v1"

    judge_result = {
        "question_id": qid, "student_id": str(row["student_id"]),
        "artifact_version": artifact_version,
        "awarded_score": row["predicted_score"],
        "max_score": sum(float(m.get("max_score") or 0) for m in row["point_matches"]),
        "high_risk_review": bool(row.get("high_risk_review")),
        "point_matches": row["point_matches"],
    }

    # 1. GradingEvent（schema 见 to_rubric_grading_event）
    grading_event = to_rubric_grading_event(judge_result)
    (out / "grading_event.json").write_text(json.dumps(grading_event, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. learning_evidence payload（既有 projection，append-only）
    evidence = to_learning_evidence(grading_event, node_code=node_code)

    attempt_id = f"attempt_{qid}_{row['student_id']}_1"
    session_id = "judge_loop_session_1"
    dedupe_key = f"judge:{USER}:{session_id}:{attempt_id}:{qid}:{artifact_version}"

    # 3a. shadow_blocked 臂：writeback_eligible=False 必须被 release-eligibility 读过滤拒绝
    shadow_payload = dict(evidence)
    shadow_payload["quality"] = {**dict(evidence.get("quality") or {}),
                                 "writeback_eligible": False,
                                 "authority": "artifact_first_llm_judge_shadow"}
    shadow_event = _event("judge_evt_shadow", shadow_payload,
                          dedupe_key=dedupe_key + ":shadow", created_at="2026-06-11T10:00:00+08:00")
    shadow_projection = synthesize_learning_truth([shadow_event])
    shadow_claims = (list(shadow_projection.get("observed_candidates") or [])
                     + list(shadow_projection.get("weak_points") or []))

    # 3b. eligible 臂：hermetic QA fixture 资格（非 release truth）走通全链
    eligible_payload = dict(evidence)
    eligible_payload["quality"] = {**dict(evidence.get("quality") or {}),
                                    "writeback_eligible": True,
                                    "authority": "hermetic_qa_fixture"}
    e1 = _event("judge_evt_1", eligible_payload, dedupe_key=dedupe_key,
                created_at="2026-06-11T10:05:00+08:00")
    # 第二次同错因 attempt（repeat 信号；dedupe_key 含 attempt 边界所以是新事件）
    attempt2 = f"attempt_{qid}_{row['student_id']}_2"
    e2 = _event("judge_evt_2", eligible_payload,
                dedupe_key=f"judge:{USER}:{session_id}:{attempt2}:{qid}:{artifact_version}",
                created_at="2026-06-11T11:00:00+08:00")
    projection = synthesize_learning_truth([e1, e2])
    claims = (list(projection.get("observed_candidates") or [])
              + list(projection.get("weak_points") or []))
    (out / "learner_claim_projection.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in claims) + ("\n" if claims else ""),
        encoding="utf-8")

    # 4. training intent + PCP + NBA（既有 authority）
    miss_points = [m for m in row["point_matches"] if m.get("status") == "miss"]
    first_miss = miss_points[0]
    intent = build_learning_training_intent(
        user_id=USER, concept_id=node_code or str(first_miss.get("point_id")),
        concept_label=str(first_miss.get("criterion") or ""),
        error_code="E02", error_label=str(first_miss.get("mistake_type") or "omitted"),
        evidence_refs=["judge_evt_1", "judge_evt_2"], training_mode="mixed_review",
    )
    learning_brain = {"compiled_objects": list((projection.get("compiled_objects") or {}).values())}
    pcp = build_personalization_context_pack(
        user_id=USER, learning_brain=learning_brain, active_training_intent=intent,
        recent_events=[{"event_id": "judge_evt_1"}, {"event_id": "judge_evt_2"}],
    )
    (out / "personalization_context_pack.json").write_text(
        json.dumps(pcp, ensure_ascii=False, indent=2), encoding="utf-8")
    candidates = pcp.get("next_best_action_candidates") or build_next_best_actions(
        user_id=USER, training_intents=[intent], max_actions=1)
    next_action = candidates[0] if candidates else {}
    (out / "next_best_action.json").write_text(
        json.dumps(next_action, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. retest condition（引用 artifact_version + point + 成功条件；不自证掌握）
    retest_condition = {
        "target_point_id": first_miss.get("point_id"),
        "must_reference_artifact_version": artifact_version,
        "success_condition": "同一 point_id 在新 attempt 中 status=hit 且 evidence_span 原文验证通过",
        "promotion_note": "通过也只是 candidate 证据；mastery promotion 仍需 governed retest/trusted adjudication 门",
    }

    trace = {
        "schema_version": "luban_judge_grading_to_brain_trace.v1",
        "mode": "hermetic_local_real_services",
        "chain": {
            "artifact_version": artifact_version,
            "question_id": qid,
            "node_code": node_code,
            "node_code_provenance": "source_chunk_id_embedded_taxonomy_code",
            "point_matches": [m.get("point_id") for m in row["point_matches"]],
            "grading_event_hash": _sha(grading_event),
            "learning_evidence_hash": _sha(evidence),
            "learner_memory_event_ids": ["judge_evt_1", "judge_evt_2"],
            "dedupe_keys": [dedupe_key, f"judge:{USER}:{session_id}:{attempt2}:{qid}:{artifact_version}"],
            "claim_count": len(claims),
            "pcp_hash": _sha(pcp),
            "next_action_id": next_action.get("action_id") or next_action.get("intent_id") or "",
            "retest_condition": retest_condition,
        },
        "shadow_gate_proof": {
            "shadow_event_writeback_eligible": False,
            "shadow_claims_count": len(shadow_claims),
            "shadow_blocked": len(shadow_claims) == 0,
        },
        "eligible_arm": {
            "authority": "hermetic_qa_fixture",
            "is_release_truth": False,
            "claims_count": len(claims),
            "pcp_top_claims_count": len(pcp.get("top_claims") or []),
            "next_action_present": bool(next_action),
        },
        "safety": {
            "canonical_truth_written": False,
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "published_registry_written": False,
        },
    }
    (out / "loop_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-row", default=str(DEFAULT_PER_ROW))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir",
                        default=str(ROOT / "artifacts/luban_grading_artifacts/judge_grading_to_brain_trace_20260611"))
    args = parser.parse_args()
    trace = run_trace(out_dir=args.output_dir, per_row_path=Path(args.per_row),
                      manifest_path=Path(args.manifest))
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
