from __future__ import annotations

from deeptutor.services.rag.pipelines.supabase import SupabasePipeline, SupabaseSearchConfig
from deeptutor.services.rag.retrieval_plan import build_retrieval_plan


def _config() -> SupabaseSearchConfig:
    return SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=[],
        include_questions=True,
        top_k=3,
        fetch_count=6,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={"compiled_learning_truth": 1.0},
        question_weights={"question_exact_text": 3.0, "questions_bank": 1.5},
        max_per_document=2,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=False,
        second_pass_max_queries=0,
        second_pass_min_hits=0,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=False,
        rerank_window=3,
        rerank_timeout_s=2.0,
        exact_question_enabled=True,
        exact_question_text_first=True,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
    )


def test_compiled_truth_plan_materializes_only_when_retrieval_plan_allows_it() -> None:
    pipeline = SupabasePipeline()
    plan = build_retrieval_plan(
        "我老是案例题采分点漏写怎么办",
        routing_metadata={"compiled_learning_truth_available": True},
    )

    compiled_plan = pipeline._compiled_truth_plan(
        retrieval_plan=plan,
        compiled_learning_truth={
            "compiled_objects": {
                "error:1A432000:E02": {
                    "current_truth": "该学员反复漏写专家论证。",
                    "evidence_level": "L2_confirmed",
                    "supporting_event_ids": ["evt1", "evt2"],
                }
            }
        },
    )

    assert compiled_plan[0]["group_name"] == "compiled_learning_truth"
    assert compiled_plan[0]["results"][0]["source_type"] == "compiled_learning_truth"


def test_fuse_plan_results_keeps_exact_question_ahead_of_compiled_truth() -> None:
    pipeline = SupabasePipeline()
    fused = pipeline._fuse_plan_results(
        [
            {
                "phase": "primary",
                "group_name": "compiled_learning_truth",
                "query": "屋面防水等级",
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "chunk_id": "compiled-truth:concept:1A432000",
                        "source_type": "compiled_learning_truth",
                        "evidence_level": "L2_confirmed",
                        "rag_content": "学习事实",
                    }
                ],
            },
            {
                "phase": "primary",
                "group_name": "question_exact_text",
                "query": "屋面防水等级",
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "chunk_id": "q1",
                        "source_type": "questions_bank",
                        "rag_content": "题库精确命中",
                    }
                ],
            },
        ],
        query="屋面防水等级",
        question_like=True,
        config=_config(),
    )

    assert [item["chunk_id"] for item in fused[:2]] == ["q1", "compiled-truth:concept:1A432000"]
