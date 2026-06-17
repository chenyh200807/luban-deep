"""Phase 2 trace runner 验收（hermetic：真实服务链 + 本地 fixture，不打外网不写库）。"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_judge_grading_to_brain_trace import run_trace

PER_ROW = Path("artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162/per_row.jsonl")


def test_judge_grading_to_brain_trace_chain_and_gates(tmp_path):
    trace = run_trace(out_dir=str(tmp_path))

    # 链路：artifact_version -> point_matches -> evidence -> memory events -> claims -> PCP -> NBA -> retest
    chain = trace["chain"]
    assert chain["artifact_version"]
    assert chain["point_matches"]
    assert chain["grading_event_hash"].startswith("sha256:")
    assert chain["learning_evidence_hash"].startswith("sha256:")
    assert len(chain["learner_memory_event_ids"]) == 2
    # dedupe_key 必须含 user/session/attempt/question/artifact_version 五要素
    for key in chain["dedupe_keys"]:
        assert "qa_judge_loop" in key and "judge_loop_session_1" in key
        assert "attempt_" in key and chain["question_id"] in key and chain["artifact_version"] in key
    assert chain["claim_count"] > 0
    assert chain["retest_condition"]["must_reference_artifact_version"] == chain["artifact_version"]

    # 安全反证：shadow / writeback_eligible=False 不得进入 claims
    assert trace["shadow_gate_proof"]["shadow_blocked"] is True

    # 正证臂：hermetic QA fixture 资格走通全链，但绝不是 release truth
    assert trace["eligible_arm"]["claims_count"] > 0
    assert trace["eligible_arm"]["is_release_truth"] is False

    # 安全不变量
    safety = trace["safety"]
    assert safety["canonical_truth_written"] is False
    assert safety["db_write_count"] == 0 and safety["remote_write_count"] == 0

    # 产物文件齐全
    for name in ("grading_event.json", "learner_claim_projection.jsonl",
                 "personalization_context_pack.json", "next_best_action.json", "loop_trace.json"):
        assert (tmp_path / name).exists()
    pcp = json.loads((tmp_path / "personalization_context_pack.json").read_text(encoding="utf-8"))
    assert "top_claims" in pcp
