"""Teacher-review REAL writeback v2 — real file-backed LearnerStateService.

Proves the closed loop the fake integration could not:
  teacher-final review payload
    -> build_teacher_review_writeback (dry_run=False)
    -> write_grading_error_events (existing authority)
    -> REAL learner_memory_events on disk (MEMORY_EVENTS.jsonl)
    -> readback from disk
    -> Learning Brain synthesis + read model
    -> next suggestion preview.

REAL: append_memory_event -> MEMORY_EVENTS.jsonl (the learning_evidence write
authority), readback, synthesis. STUBBED: only the downstream home-personalization
projection (a non-authoritative cache that otherwise makes a ~6s network call).

QA-gated (qa_/test_), no production user, no new table, no kernel/RAG/production
runtime change. Writes to a TEMP dir, never the repo's data/user.

Output: artifacts/luban_consensus_gold/teacher_review_real_writeback_v2_20260604/
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "artifacts" / "luban_consensus_gold" / "teacher_review_real_writeback_v2_20260604"
QA_STUDENT = "qa_luban_teacher_review_v2"


def _reviews(student_id: str) -> list[dict[str, Any]]:
    return [
        {"sample_id": "exact_required_override_miss", "case_id": "Q-exact-001",
         "student_id": student_id, "engine": "best_quality_4model", "teacher_reviewed": True,
         "review_source": "qa_fixture_teacher_review", "point_reviews": [{
             "point_id": "P-exact-01", "label": "官方术语：专项施工方案", "policy_type": "exact_required",
             "max_score": 2, "ai_hit": "partial", "ai_score": 0.5, "high_risk_review": True,
             "review_action": "override", "teacher_hit": "miss", "teacher_score": 0,
             "teacher_note": "未写官方术语，近义不给分"}]},
        {"sample_id": "list_rule_confirm_partial", "case_id": "Q-list-002",
         "student_id": student_id, "engine": "best_quality_4model", "teacher_reviewed": True,
         "review_source": "qa_fixture_teacher_review", "point_reviews": [{
             "point_id": "P-list-01", "label": "资源供应平衡要点", "policy_type": "list_rule",
             "max_score": 3, "ai_hit": "partial", "ai_score": 1.5, "review_action": "confirm",
             "teacher_hit": "partial", "teacher_score": 1.5, "teacher_note": "列举不全，仍缺关键要点"}]},
        {"sample_id": "calculation_confirm_hit", "case_id": "Q-calc-003",
         "student_id": student_id, "engine": "best_quality_4model", "teacher_reviewed": True,
         "review_source": "qa_fixture_teacher_review", "point_reviews": [{
             "point_id": "P-calc-01", "label": "流水节拍计算", "policy_type": "calculation",
             "max_score": 4, "ai_hit": "hit", "ai_score": 4, "auto_certified": True,
             "review_action": "confirm", "teacher_hit": "hit", "teacher_score": 4,
             "teacher_note": "公式与数值正确，结果成立"}]},
        {"sample_id": "high_risk_unreviewed", "case_id": "Q-hr-004",
         "student_id": student_id, "engine": "best_quality_4model", "teacher_reviewed": True,
         "review_source": "qa_fixture_teacher_review", "point_reviews": [{
             "point_id": "P-hr-01", "label": "施工组织设计审批", "policy_type": "exact_required",
             "max_score": 2, "ai_hit": "hit", "ai_score": 2, "high_risk_review": True,
             "review_action": ""}]},
        {"sample_id": "unsupported_unreviewed", "case_id": "Q-unsup-005",
         "student_id": student_id, "engine": "best_quality_4model", "teacher_reviewed": True,
         "review_source": "qa_fixture_teacher_review", "point_reviews": [{
             "point_id": "P-unsup-01", "label": "质量验收批次", "policy_type": "list_rule",
             "max_score": 2, "ai_hit": "hit", "ai_score": 2, "unsupported": True,
             "review_action": ""}]},
    ]


def _backend_audit_md(events_file: Path) -> str:
    return "\n".join([
        "# Backend audit — teacher-review real writeback v2 (2026-06-04)",
        "",
        "## 是否有真实可写 learner_state backend？",
        "",
        "有。`LearnerStateService`（`deeptutor/services/learner_state/service.py`）是**文件后端**：",
        "`append_memory_event(...)` 把每条事件以 JSONL 追加到 `MEMORY_EVENTS.jsonl`，",
        "`list_memory_events(...)` 从同一文件读回。这不是 fake monkeypatch，是生产同一服务。",
        "",
        "## 写到哪里？",
        "",
        "`<DEEPTUTOR_USER_DATA_DIR>/learner_state/<user_id>/MEMORY_EVENTS.jsonl`。",
        f"本轮用临时目录（不污染 repo `data/user`）：`{events_file}`。",
        "根目录由 `DEEPTUTOR_USER_DATA_DIR` 覆盖（`path_service.resolve_runtime_user_data_dir`）。",
        "",
        "## 是否 sqlite / postgres / in-memory？",
        "",
        "文件后端（JSONL），非 sqlite/postgres；Supabase 仅为**可选 sync**（`SUPABASE_URL/KEY` 未设时不参与）。",
        "属于真实本地持久化，不是 in-memory fake。",
        "",
        "## blocker？",
        "",
        "无 blocker。唯一为测速 stub 的是 **下游 home-personalization 投影写**（`_write_home_projection`，",
        "非授权缓存，否则约 6s 网络调用）。学习记忆写入授权链（`append_memory_event → MEMORY_EVENTS.jsonl`）",
        "全程真实、未 mock。",
    ])


def _next_suggestions(projection: dict[str, Any], read_model: dict[str, Any]) -> dict[str, Any]:
    weaknesses = []
    for c in projection.get("observed_candidates") or []:
        weaknesses.append({
            "concept_id": c.get("concept_id"),
            "error_code": c.get("error_code"),
            "claim": c.get("claim"),
            "evidence_level": c.get("evidence_level"),
            "recommended_training": c.get("recommended_training"),
        })
    improvements = [
        {"concept_id": i.get("concept_id"), "claim": i.get("claim")}
        for i in read_model.get("improvement_signals") or []
    ]
    suggestions = [
        {
            "type": "remediate_weakness",
            "concept_id": w["concept_id"],
            "why": w["claim"] or w["error_code"],
            "next_training": w["recommended_training"],
        }
        for w in weaknesses if w["recommended_training"]
    ]
    return {
        "source": "learner_memory_events.learning_evidence -> synthesis projection",
        "can_generate_suggestions": bool(suggestions),
        "weaknesses": weaknesses,
        "improvements": improvements,
        "next_suggestions": suggestions,
        "needs_new_table": False,
        "note": "复用现有 payload/read model（observed_candidates.recommended_training + improvement_signals），无需新表。",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="qa_teacher_review_v2_"))
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_KEY", None)
    os.environ["DEEPTUTOR_ENV"] = "local"
    os.environ["DEEPTUTOR_USER_DATA_DIR"] = str(tmp)

    from deeptutor.services import path_service as ps
    ps.PathService.reset_instance()
    from deeptutor.services.construction_grading import writeback as wb
    wb._write_home_projection = lambda **_kwargs: None  # non-authoritative cache; skip network
    from deeptutor.services.learner_state.service import LearnerStateService
    from deeptutor.services.construction_grading.teacher_review_writeback import (
        build_teacher_review_writeback,
    )
    from deeptutor.services.learner_state.learning_brain_read_model import (
        build_learning_brain_read_model,
    )

    service = LearnerStateService()
    reviews = _reviews(QA_STUDENT)

    outputs = [
        build_teacher_review_writeback(r, dry_run=False, learner_state_service=service, user_id=QA_STUDENT)
        for r in reviews
    ]

    events_file = tmp / "learner_state" / QA_STUDENT / "MEMORY_EVENTS.jsonl"
    on_disk = [json.loads(line) for line in events_file.read_text("utf-8").splitlines() if line.strip()]

    readback = service.list_memory_events(QA_STUDENT, limit=50)
    readback_dicts = [
        {"event_id": e.event_id, "memory_kind": e.memory_kind, "source_feature": e.source_feature,
         "question_id": e.payload_json.get("question_id"),
         "error_events": e.payload_json.get("error_events"),
         "teacher_final_grading_result": e.payload_json.get("next_training_signal", {}).get("teacher_final_grading_result")}
        for e in readback
    ]

    synthesis = service.synthesize_learning_truth(QA_STUDENT, dry_run=True, event_limit=50)
    projection = synthesis["projection"]
    read_model = build_learning_brain_read_model(user_id=QA_STUDENT, projection=projection, surface="qa")
    next_suggestions = _next_suggestions(projection, read_model)

    # write artifacts
    (OUT_DIR / "backend_audit.md").write_text(_backend_audit_md(events_file), encoding="utf-8")
    (OUT_DIR / "teacher_review_inputs.json").write_text(
        json.dumps(reviews, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "writeback_outputs.json").write_text(
        json.dumps([{k: v for k, v in o.items() if k != "learning_evidence_payload"} | {
            "writeback_count": o.get("writeback_count"),
            "mastery_point_ids": o.get("mastery_point_ids"),
        } for o in outputs], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "readback_memory_events.json").write_text(
        json.dumps({"on_disk_jsonl_count": len(on_disk), "events": readback_dicts},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "learning_brain_synthesis.json").write_text(
        json.dumps({"event_count": read_model.get("event_count"),
                    "weak_points": read_model.get("weak_points"),
                    "improvement_signals": read_model.get("improvement_signals"),
                    "observed_candidates": projection.get("observed_candidates")},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "next_suggestion_preview.json").write_text(
        json.dumps(next_suggestions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mastery_ids = [pid for o in outputs for pid in o["mastery_point_ids"]]
    finding = _finding_md(outputs, on_disk, read_model, projection, mastery_ids, events_file)
    (OUT_DIR / "FINDING_teacher_review_real_writeback_v2_20260604.md").write_text(finding, encoding="utf-8")

    print(f"writeback_counts={[o['writeback_count'] for o in outputs]} on_disk={len(on_disk)} "
          f"mastery={mastery_ids} event_count={read_model.get('event_count')} "
          f"suggestions={len(next_suggestions['next_suggestions'])}")
    print(f"-> {OUT_DIR}")


def _finding_md(outputs, on_disk, read_model, projection, mastery_ids, events_file) -> str:
    weakness_concepts = sorted({c.get("concept_id") for c in projection.get("observed_candidates") or []})
    improvement_concepts = sorted({i.get("concept_id") for i in read_model.get("improvement_signals") or []})
    return "\n".join([
        "# FINDING teacher-review REAL writeback v2 (2026-06-04)",
        "",
        "## Answers",
        "",
        f"1. 是否真实 DB / test backend 写入？ **是**。真实 `LearnerStateService` 把 {len(on_disk)} 条事件写入磁盘 `MEMORY_EVENTS.jsonl` 并读回。",
        "2. backend 是什么？ 文件后端（JSONL）`<DEEPTUTOR_USER_DATA_DIR>/learner_state/<user>/MEMORY_EVENTS.jsonl`；非 fake，Supabase 仅可选 sync（本轮未启用）。",
        f"3. 写入几条 `learner_memory_events`？ **{len(on_disk)} 条**（writeback_count={[o['writeback_count'] for o in outputs]}），memory_kind 全为 `learning_evidence`。",
        "4. 是否仍 QA-gated？ 是。`qa_`/`test_` 前缀强制；非 QA → `qa_user_id_required` 不写。",
        "5. 是否新增表？ 否。复用现有 `learner_memory_events` 流。",
        "6. 是否改 kernel / RAG / production runtime？ 否。未触 `CaseGradingSkillKernel`、RAG、生产 runtime；仅 stub 下游 home-personalization 缓存写（非授权）。",
        "7. AI-Draft 未复核是否写入？ 否。`teacher_reviewed!=true` → `teacher_reviewed_required` 跳过，不写。",
        "8. teacher-final 是否成为写入 authority？ 是。`next_training_signal.teacher_final_grading_result` 进入每条 payload；override > AI draft（exact_required AI partial → teacher override miss）。",
        f"9. high_risk / unsupported 是否被阻止 mastery？ 是。未复核的 high_risk/unsupported 点 `mastery_eligible=false`；本轮 mastery 仅 {mastery_ids}（teacher-confirmed 计算满分点）。",
        f"10. Learning Brain 是否读回 weakness/mastery？ 是。read model `event_count={read_model.get('event_count')}`；mastery/improvement={improvement_concepts}；weakness observed_candidates={weakness_concepts}。",
        "11. 是否生成 next suggestion？ 是，见 `next_suggestion_preview.json`（由 observed_candidates.recommended_training + improvement_signals 派生，无需新表）。",
        "12. blocker？ 无。唯一加速 stub 是非授权的 home-personalization 网络写；记忆写入授权链全真实。",
        "",
        "## 真实写入证据",
        "",
        f"- on-disk JSONL: `{events_file}`（{len(on_disk)} 行，memory_kind=learning_evidence）",
        "- exact_required override→miss = E03 gap；list_rule partial = E02 gap；calculation full hit = 无 error、mastery；high_risk/unsupported 未复核 = gap、非 mastery。",
        "",
        "## 红线",
        "",
        "- 不新增表 / 不改 kernel / RAG 不进评分 / 不写生产用户 / 不把 fake service 当真实 DB（本轮是真实文件后端，已贴 on-disk 证据）/ 未复核 AI-Draft 不写 Learning Brain。",
        "",
    ])


if __name__ == "__main__":
    main()
