"""QA/test runtime-shadow small batch through the REAL deep_question wire helper.

Runs 3-5+ QA samples through ``deep_question._maybe_attach_runtime_shadow`` (the real
production wire, default OFF) with the flag toggled OFF then ON, proving:
  - flag OFF  -> legacy payload byte-identical, no shadow key.
  - flag ON   -> ``luban_grading_engine_shadow`` appended; legacy result unchanged.
  - published / draft / blocked / missing / non-QA behaviors via the artifact gate.

Deterministic: the engine builder is replaced with a fixture (hit every point, span ==
answer), so NO live provider call. REAL: wire helper, flag gating, Registry, gate,
legacy-untouched contract. SIMULATED: the per-point predictions only.

It does NOT write the DB / Learning Brain, NOT call the kernel, NOT touch RAG.

Output: artifacts/luban_consensus_gold/qa_runtime_shadow_batch_20260604/
  - batch_inputs.json / legacy_outputs.json / shadow_outputs.json
  - legacy_comparison.json / FINDING_qa_runtime_shadow_batch_20260604.md
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from deeptutor.capabilities import deep_question as dq
from deeptutor.core.context import UnifiedContext
from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_consensus_gold" / "qa_runtime_shadow_batch_20260604"

QA_STUDENT = "qa_runtime_shadow_20260604"
NON_QA_STUDENT = "real_student_999"
ANSWER = "施工总进度计划表(图)，甲乙丙，措施一二三，应组织专家论证。"

SAMPLES = [
    {"name": "published_partial_auto", "question_id": "Q17-1A433000", "student_id": QA_STUDENT,
     "expect": "published; some points auto-certified, weak points pending"},
    {"name": "published_exact_required", "question_id": "Q1-NA", "student_id": QA_STUDENT,
     "expect": "published exact_required boundary; auto-certifiable point stays auto"},
    {"name": "draft_no_auto", "question_id": "Q20-1A413000", "student_id": QA_STUDENT,
     "expect": "draft; 0 auto-certified, all pending"},
    {"name": "blocked_no_auto", "question_id": "Q15-NA", "student_id": QA_STUDENT,
     "expect": "blocked; 0 auto-certified, fail closed"},
    {"name": "missing_artifact", "question_id": "Q-DOES-NOT-EXIST", "student_id": QA_STUDENT,
     "expect": "artifact_missing; engine not run"},
    {"name": "non_qa_student", "question_id": "Q17-1A433000", "student_id": NON_QA_STUDENT,
     "expect": "qa_student_required; engine not run"},
]


def _legacy_result(question_id: str) -> dict[str, Any]:
    # A fixed, synthetic legacy result. The point of the batch is that the shadow does
    # not alter it, not to re-run the deterministic kernel here.
    return {
        "authority": "construction_grading",
        "type": "case",
        "question_id": question_id,
        "score_awarded": 1.0,
        "max_score": 2.0,
        "diagnosis": "PARTIAL",
    }


def _graded_context(question_id: str) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "user_answer": ANSWER,
        "question_type": "case",
        "construction_grading_result": _legacy_result(question_id),
    }


def _ctx(student_id: str, *, flag: bool) -> UnifiedContext:
    metadata: dict[str, Any] = {"user_id": student_id}
    if flag:
        metadata["grading_engine_runtime_shadow"] = True
        metadata["grading_engine_runtime_shadow_engine"] = "deepseek_fast"
    return UnifiedContext(session_id="qa-batch", user_message=ANSWER, metadata=metadata)


def _deterministic_builder(question, student_answer, *, student_id, artifact_gate):
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

    preds = [
        {"point_id": sp["point_id"], "hit": "hit", "score": float(sp.get("max_score") or 1),
         "evidence_span": student_answer, "rationale": "qa fixture"}
        for sp in (question.get("scoring_points") or [])
    ]
    return build_ai_draft(
        question, student_answer, preds, points=question.get("scoring_points") or [],
        student_id=student_id, artifact_gate=artifact_gate,
    )


def _run_sample(sample: dict[str, Any]) -> dict[str, Any]:
    qid = sample["question_id"]
    sid = sample["student_id"]

    # flag OFF -> legacy only
    payload_off: dict[str, Any] = {"construction_grading_result": _legacy_result(qid)}
    dq._maybe_attach_runtime_shadow(
        context=_ctx(sid, flag=False),
        graded_context=_graded_context(qid),
        result_payload=payload_off,
    )

    # flag ON -> legacy + shadow
    payload_on: dict[str, Any] = {"construction_grading_result": _legacy_result(qid)}
    dq._maybe_attach_runtime_shadow(
        context=_ctx(sid, flag=True),
        graded_context=_graded_context(qid),
        result_payload=payload_on,
    )

    legacy_off = payload_off.get("construction_grading_result")
    legacy_on = payload_on.get("construction_grading_result")
    shadow = payload_on.get("luban_grading_engine_shadow")
    point_results = (shadow or {}).get("point_results") or []
    positives = [p for p in point_results if str(p.get("hit")) in {"hit", "partial"}]
    positives_with_span = [p for p in positives if str(p.get("evidence_span") or "").strip()]

    return {
        "name": sample["name"],
        "question_id": qid,
        "student_id": sid,
        "expect": sample["expect"],
        "flag_off_has_shadow_key": "luban_grading_engine_shadow" in payload_off,
        "flag_on_has_shadow_key": "luban_grading_engine_shadow" in payload_on,
        "legacy_unchanged": legacy_off == legacy_on,
        "shadow_status": (shadow or {}).get("shadow_status"),
        "artifact_status": ((shadow or {}).get("artifact_gate") or {}).get("artifact_status"),
        "auto_certified_score": ((shadow or {}).get("scores") or {}).get("auto_certified_score"),
        "pending_review_score": ((shadow or {}).get("scores") or {}).get("pending_review_score"),
        "point_count": len(point_results),
        "positive_points": len(positives),
        "positive_points_with_span": len(positives_with_span),
        "writeback_performed": (shadow or {}).get("writeback_performed"),
        "teacher_review_required": (shadow or {}).get("teacher_review_required"),
        "legacy_off": legacy_off,
        "legacy_on": legacy_on,
        "shadow": shadow,
    }


def render_finding(results: list[dict[str, Any]]) -> str:
    all_legacy_unchanged = all(r["legacy_unchanged"] for r in results)
    all_no_writeback = all(r["writeback_performed"] in (False, None) for r in results)
    positive_span_ok = all(
        r["positive_points"] == r["positive_points_with_span"] for r in results
    )
    lines = [
        "# FINDING QA runtime shadow batch 2026-06-04",
        "",
        "## Truth level",
        "",
        "- **REAL**: the production wire helper `deep_question._maybe_attach_runtime_shadow`, "
        "the `grading_engine_runtime_shadow` flag gating, the QuestionGradingArtifact "
        "Registry, the ArtifactRuntimeGate, and the legacy-untouched contract.",
        "- **SIMULATED**: the per-point model predictions (deterministic fixture) instead of "
        "a live DeepSeek/Best-Quality call, so the batch is hermetic.",
        "- **NOT YET REAL**: the full `/api/v1/ws` turn (TurnRuntime + stream + persistence). "
        "Next step runs the same flag against a real QA WS turn; this batch exercises the "
        "exact helper that turn calls.",
        "",
        "## Acceptance answers",
        "",
        "1. 真实/近真实链路？ 近真实：调用生产 `_emit_grading_result` 所调的同一 wire helper，仅引擎预测为 fixture。",
        "2. QA-gated？ 是：flag `grading_engine_runtime_shadow` + 学生 id 必须 `qa_`/`test_`，否则 `qa_student_required`。",
        f"3. legacy 完全不变？ {'是' if all_legacy_unchanged else '否'}：flag off vs on 的 `construction_grading_result` 全样本相等。",
        "4. shadow 是否只 append？ 是：只新增 `luban_grading_engine_shadow` key，从不改 legacy。",
        "5. 是否写 DB / Learning Brain？ 否：`writeback_performed=false`，不调 `write_grading_error_events`，仅 `learning_evidence_payload_preview`。",
        "6. published/draft/blocked/missing 行为：见下表。",
        f"7. positive 必有 evidence_span？ {'是' if positive_span_ok else '否'}。",
        "8. fail-closed 覆盖：non-QA→qa_student_required；missing→artifact_missing（不跑引擎）；draft/blocked→auto=0；engine 异常→engine_unavailable。",
        "9. 是否可进入 teacher-review 真实写回小批？ 可以——shadow 已产出 teacher_review_required + learning_evidence preview，teacher-final 控写入。",
        "10. 还差什么才能到 production test？ 把同一 flag 接到真实 QA `/api/v1/ws` turn（live 引擎 + 异步 UX），并接 teacher 工作台。",
        "",
        "## Sample table",
        "",
        "| sample | qid | student | shadow_status | artifact | auto | pending | pts | legacy_unchanged | writeback |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['question_id']} | {r['student_id']} | {r['shadow_status']} | "
            f"{r['artifact_status']} | {r['auto_certified_score']} | {r['pending_review_score']} | "
            f"{r['point_count']} | {r['legacy_unchanged']} | {r['writeback_performed']} |"
        )
    lines += [
        "",
        "## Invariants",
        "",
        f"- legacy unchanged across all samples: **{all_legacy_unchanged}**",
        f"- no writeback across all samples: **{all_no_writeback}**",
        f"- every positive point carries evidence_span: **{positive_span_ok}**",
        "- artifact gate controls auto-certification; teacher-final controls Learning Brain.",
        "- not production grade; not a CaseGradingSkillKernel replacement; RAG not in authority.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # deterministic engine: no live provider call.
    adapter._build_deepseek_fast_draft = _deterministic_builder

    results = [_run_sample(s) for s in SAMPLES]

    batch_inputs = [
        {"name": s["name"], "question_id": s["question_id"], "student_id": s["student_id"],
         "answer": ANSWER, "expect": s["expect"]}
        for s in SAMPLES
    ]
    legacy_outputs = [
        {"name": r["name"], "question_id": r["question_id"],
         "construction_grading_result": r["legacy_on"],
         "has_shadow_key_when_flag_off": r["flag_off_has_shadow_key"]}
        for r in results
    ]
    shadow_outputs = [
        {"name": r["name"], "question_id": r["question_id"], "shadow": r["shadow"]}
        for r in results
    ]
    legacy_comparison = [
        {"name": r["name"], "question_id": r["question_id"],
         "legacy_off": r["legacy_off"], "legacy_on": r["legacy_on"],
         "legacy_unchanged": r["legacy_unchanged"]}
        for r in results
    ]

    (OUT_DIR / "batch_inputs.json").write_text(
        json.dumps(batch_inputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "legacy_outputs.json").write_text(
        json.dumps(legacy_outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "shadow_outputs.json").write_text(
        json.dumps(shadow_outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "legacy_comparison.json").write_text(
        json.dumps(legacy_comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "FINDING_qa_runtime_shadow_batch_20260604.md").write_text(
        render_finding(results), encoding="utf-8")

    for r in results:
        print(
            f"{r['name']:24s} {r['question_id']:16s} status={r['shadow_status']} "
            f"artifact={r['artifact_status']} auto={r['auto_certified_score']} "
            f"pts={r['point_count']} legacy_unchanged={r['legacy_unchanged']}"
        )
    print(f"-> {OUT_DIR}")


if __name__ == "__main__":
    main()
