from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any

from scripts.run_luban_knowql_nexus_three_arm_ab import (
    ARM_NEXUS_V1_KNOWQL,
    ARM_NEXUS_V1_NO_KNOWQL,
    ARM_RAG_REF,
    semantic_understanding_score,
    run_three_arm_eval_for_cases,
)


def _tiny_case() -> dict[str, Any]:
    return {
        "case_id": "T-KNOWQL-1",
        "stem": "【问题】1. 施工总进度计划应补充哪些内容？",
        "official_answer": "应补充施工总进度计划表(图)。",
        "official_analysis": "标准口径为施工总进度计划表(图)。",
        "max_score": 1,
        "question_node": "1A420000",
        "gold_scoring_points": [
            {
                "point_id": "P1",
                "label": "必须写出'施工总进度计划表(图)'。",
                "max_score": 1,
                "official_basis": "施工总进度计划表(图)",
                "list_rule": "",
            }
        ],
        "eval_samples": [
            {
                "student_id": "S1",
                "archetype": "完整满分",
                "answer_text": "应补充施工总进度计划表(图)。",
                "ground_truth_ledger": {
                    "point_hits": [{"point_id": "P1", "hit": "hit"}],
                    "penalty_triggered": False,
                },
            }
        ],
    }


async def _fake_complete(**kwargs: Any) -> str:
    system_prompt = str(kwargs.get("system_prompt") or "")
    prompt = str(kwargs.get("prompt") or "")
    if "拆成采分点" in system_prompt or "参考答案" in prompt:
        return json.dumps(
            [
                {
                    "text": "施工总进度计划表(图)",
                    "score": 1,
                    "policy": "qualitative",
                    "required_terms": ["施工总进度计划表", "图"],
                }
            ],
            ensure_ascii=False,
        )
    indexes = [int(i) for i in re.findall(r'"idx":\s*(\d+)', prompt)]
    return json.dumps(
        [
            {
                "idx": idx,
                "status": "hit",
                "partial_ratio": 1,
                "evidence_span": "施工总进度计划表(图)",
                "mistake_type": "",
            }
            for idx in indexes
        ],
        ensure_ascii=False,
    )


def test_three_arm_report_uses_requested_arms_and_semantic_metric() -> None:
    report = run_three_arm_eval_for_cases(
        cases=[_tiny_case()],
        complete_fn=_fake_complete,
        api_key="test-key",  # pragma: allowlist secret
        model="fake-model",
        concurrency=1,
    )

    assert set(report["summary"]) == {
        ARM_RAG_REF,
        ARM_NEXUS_V1_NO_KNOWQL,
        ARM_NEXUS_V1_KNOWQL,
    }
    assert "semantic_understanding" in report["evaluation_criteria"]
    for arm_summary in report["summary"].values():
        assert "mean_semantic_understanding_score" in arm_summary

    rows_by_arm = {row["arm"]: row for row in report["rows"]}
    assert rows_by_arm[ARM_RAG_REF]["rag_ref_context_used"] is True
    assert rows_by_arm[ARM_RAG_REF]["score_authority"] == "legacy_rag_ref_kernel"

    assert rows_by_arm[ARM_NEXUS_V1_NO_KNOWQL]["compiled_rubric_used"] is False
    assert rows_by_arm[ARM_NEXUS_V1_NO_KNOWQL]["knowql_context_pack_attached"] is False
    assert rows_by_arm[ARM_NEXUS_V1_NO_KNOWQL]["score_authority"] == "rubric_grader_v1"
    assert rows_by_arm[ARM_NEXUS_V1_NO_KNOWQL]["point_recall"] == 1.0
    assert rows_by_arm[ARM_NEXUS_V1_NO_KNOWQL]["hallucination"] is False

    knowql = rows_by_arm[ARM_NEXUS_V1_KNOWQL]
    assert knowql["compiled_rubric_used"] is True
    assert knowql["knowql_context_pack_attached"] is True
    assert knowql["learner_evidence_attached"] is True
    assert knowql["score_authority"] == "rubric_grader_v1"
    assert knowql["token_proxy"] == knowql["llm_token_proxy"]
    assert knowql["context_token_proxy"] > 0
    assert knowql["cold_token_proxy"] >= knowql["llm_token_proxy"]
    assert knowql["semantic_understanding_score"] == 1.0

    assert report["safety"]["production_default_flip"] is False
    assert report["safety"]["canonical_learner_truth_written"] is False


def test_semantic_understanding_score_penalizes_overcredit_and_hallucination() -> None:
    perfect = semantic_understanding_score(
        pred_score=1,
        gold_score=1,
        max_score=1,
        point_precision=1,
        point_recall=1,
        hallucination=False,
    )
    over_credit = semantic_understanding_score(
        pred_score=1,
        gold_score=0,
        max_score=1,
        point_precision=0,
        point_recall=1,
        hallucination=False,
    )
    hallucinated = semantic_understanding_score(
        pred_score=1,
        gold_score=1,
        max_score=1,
        point_precision=1,
        point_recall=1,
        hallucination=True,
    )

    assert perfect == 1.0
    assert over_credit < perfect
    assert hallucinated < perfect


def test_three_arm_script_is_executable_as_file() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_luban_knowql_nexus_three_arm_ab.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "three-arm case-grading comparison" in result.stdout
