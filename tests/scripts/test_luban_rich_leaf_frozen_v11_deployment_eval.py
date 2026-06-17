"""Focused tests for the rich-leaf frozen-v11 deployment-shape two-arm eval runner."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "run_luban_rich_leaf_frozen_v11_deployment_eval.py"
spec = importlib.util.spec_from_file_location("rich_leaf_frozen_v11_deployment_eval", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["rich_leaf_frozen_v11_deployment_eval"] = mod
spec.loader.exec_module(mod)


def _question(qid: str = "2024:EXAM_1A411001_P0001_01:0", qtype: str = "single_choice") -> dict:
    return {
        "question_id": qid,
        "year": 2024,
        "node_code": "1A411011",
        "qtype": qtype,
        "stem": "历史建筑的建筑高度应按建筑室外设计地坪至建构筑物（　）计算。",
        "options": [{"key": "D", "value": "最高点"}],
        "gold_answer": "D",
        "gold_analysis": "历史建筑高度按室外设计地坪至最高点计算。",
        "score": 1.0,
    }


def _unit(leaf_id: str = "1A411011-B054") -> dict:
    return {
        "unit_id": "rtpf1_x",
        "leaf_id": leaf_id,
        "leaf_name_path": "建筑工程技术 > 建筑设计 > 建筑高度计算",
        "compiled_context": {
            "concepts": ["建筑高度计算概念"],
            "rules": ["规则1"],
            "exam_patterns": ["考点1"],
            "teaching_cards": [],
        },
        "source_ref": {"chunk_id": "c", "source_lane": "textbook", "source_path": "b.json", "record_id": "r", "span_hash": "h"},
    }


_CHUNKS = [
    {"chunk_id": "k1", "doc_type": "textbook", "score_final": 0.7, "content": "正文一"},
    {"chunk_id": "k2", "doc_type": "standard", "score_final": 0.6, "content": "正文二"},
]


def _rich_block(count: int = 2) -> dict:
    return {
        "primary_leaf": "1A411011-B054",
        "leaf_resolution": "node_code_exact",
        "query_terms": ["建筑高度"],
        "rich_leaf_ids": [f"1A41101{i}-B05{i}" for i in range(count)],
        "rich_leaf_count": count,
        "rendered_lines": ["【富叶编译上下文 rich_leaf - 仅供讲解，非官方答案，不得作为官方判分依据】", "富叶知识点：x（y）", "- [概念] z"],
        "rendered_chars": 60,
    }


# ---------------------------------------------------------------- rich block resolution


def test_resolve_rich_block_uses_runtime_seam_and_renders() -> None:
    captured: dict = {}

    def fake_get_contexts(query_terms, leaf_codes, *, top_k=3):
        captured["query_terms"] = query_terms
        captured["leaf_codes"] = leaf_codes
        captured["top_k"] = top_k
        return [
            {"leaf_id": "1A411011-B054", "compiled_context": {"concepts": ["a"]}},
            {"leaf_id": "1A411012-B001", "compiled_context": {"concepts": ["b"]}},
        ]

    def fake_render(pack):
        assert len(pack["rich_leaf_contexts"]) == 2
        return ["L1", "L2"]

    block = mod.resolve_rich_block(_question(), [_unit()], get_contexts=fake_get_contexts, render=fake_render)
    assert captured["leaf_codes"] == ["1A411011-B054"]  # three-tier primary leaf feeds the seam
    assert captured["top_k"] == 3
    assert captured["query_terms"]  # production term extraction produced terms
    assert block["rich_leaf_count"] == 2
    assert block["rich_leaf_ids"] == ["1A411011-B054", "1A411012-B001"]
    assert block["rendered_lines"] == ["L1", "L2"]
    assert block["rendered_chars"] == sum(len(l) + 1 for l in ["L1", "L2"])


def test_resolve_rich_block_empty_contexts_fall_open() -> None:
    block = mod.resolve_rich_block(
        _question(), [_unit()], get_contexts=lambda *a, **k: [], render=lambda pack: ["should_not_render"]
    )
    assert block["rich_leaf_count"] == 0
    assert block["rendered_lines"] == []
    assert block["rendered_chars"] == 0


# ---------------------------------------------------------------- arm contexts


def test_arm_context_deploy_has_chunks_plus_rich_baseline_chunks_only() -> None:
    rich = _rich_block()
    ctx_d = mod.arm_context(mod.ARM_DEPLOY, kbv5_chunks=_CHUNKS, rich_block=rich)
    assert ctx_d["mode"] == mod.ARM_DEPLOY
    assert [c["chunk_id"] for c in ctx_d["retrieved_chunks"]] == ["k1", "k2"]
    assert ctx_d["rich_leaf_block"]["leaf_ids"] == rich["rich_leaf_ids"]
    assert "富叶编译上下文" in ctx_d["rich_leaf_block"]["rendered_text"]

    ctx_e = mod.arm_context(mod.ARM_BASELINE, kbv5_chunks=_CHUNKS, rich_block=rich)
    assert ctx_e["mode"] == mod.ARM_BASELINE
    assert "rich_leaf_block" not in ctx_e
    assert ctx_e["retrieved_chunks"] == ctx_d["retrieved_chunks"]  # shared retrieval, rich is the only delta


def test_answer_messages_allow_rich_leaf_citations() -> None:
    messages = mod.answer_messages(_question(), {"mode": "x"})
    assert messages[0]["role"] == "system"
    assert "option letter" in messages[0]["content"]
    assert "leaf_id" in messages[0]["content"]
    assert _question()["stem"][:8] in messages[1]["content"]


# ---------------------------------------------------------------- judge


def test_judge_messages_short_ordinals_and_citation_source_contract() -> None:
    arm_rows = [
        {
            "arm": mod.ARM_DEPLOY,
            "answer": "D",
            "explanation": "x",
            "citations": ["k1", "1A411011-B054"],
            "chunk_ids": ["k1", "k2"],
            "rich_leaf_ids": ["1A411011-B054"],
            "context_digest": "d1",
        },
        {
            "arm": mod.ARM_BASELINE,
            "answer": "C",
            "explanation": "y",
            "citations": ["k2"],
            "chunk_ids": ["k1", "k2"],
            "rich_leaf_ids": [],
            "context_digest": "d2",
        },
    ]
    messages, mapping = mod.judge_messages(_question(), arm_rows)
    assert mapping == {"1": mod.ARM_DEPLOY, "2": mod.ARM_BASELINE}
    body = messages[1]["content"]
    assert '"1"' in body and '"2"' in body
    assert mod.ARM_DEPLOY not in body  # judge sees ordinals, not arm names
    payload = json.loads(body)
    assert payload["candidates"]["1"]["evidence_inventory"]["rich_leaf_ids"] == ["1A411011-B054"]
    assert payload["required_json"]["1"]["citation_source"].startswith("retrieval_chunk |")
    assert "citation_source" in messages[0]["content"]


def test_apply_judge_verdicts_citation_source_validation() -> None:
    mapping = {"1": mod.ARM_DEPLOY, "2": mod.ARM_BASELINE}
    parsed = {
        "1": {"verdict": "correct", "explanation_quality": 5, "citation_grounded": True, "citation_source": "both"},
        "2": {"verdict": "partial", "explanation_quality": 3, "citation_grounded": True, "citation_source": "weird"},
    }
    verdicts = mod.apply_judge_verdicts(parsed, mapping)
    assert verdicts[mod.ARM_DEPLOY]["citation_source"] == "both"
    assert verdicts[mod.ARM_BASELINE]["judge_status"] == "completed"
    assert verdicts[mod.ARM_BASELINE]["citation_source"] is None  # invalid source degrades to None
    missing = mod.apply_judge_verdicts({}, mapping)
    assert missing[mod.ARM_DEPLOY]["judge_status"] == "judge_failed"
    assert missing[mod.ARM_DEPLOY]["citation_source"] is None


# ---------------------------------------------------------------- summaries + comparison


def _row(arm: str, *, qtype: str = "single_choice", verdict: str | None = "correct", source: str | None = "retrieval_chunk",
         rich_count: int = 0, tokens: int = 150) -> dict:
    return {
        "arm": arm,
        "question_id": "q1",
        "qtype": qtype,
        "status": "completed",
        "verdict": verdict,
        "judge_status": "completed" if verdict else "judge_failed",
        "explanation_quality": 4 if verdict else None,
        "citation_grounded": verdict == "correct",
        "citation_source": source,
        "exact_match": (verdict == "correct") if qtype in mod.OBJECTIVE_TYPES else None,
        "rich_leaf_count": rich_count,
        "prompt_tokens": tokens - 50,
        "completion_tokens": 50,
        "total_tokens": tokens,
        "latency_ms": 1000.0,
    }


def test_arm_summary_splits_question_groups_and_counts_sources() -> None:
    rows = [
        _row(mod.ARM_DEPLOY, qtype="single_choice", verdict="correct", source="retrieval_chunk", rich_count=1),
        _row(mod.ARM_DEPLOY, qtype="case_study", verdict="partial", source="rich_block", rich_count=3),
        _row(mod.ARM_DEPLOY, qtype="case_study", verdict="correct", source="both", rich_count=2),
    ]
    summary = mod.arm_summary(mod.ARM_DEPLOY, rows)
    assert summary["sample_count"] == 3
    assert summary["semantic_score"] == round((1.0 + 0.5 + 1.0) / 3, 4)
    assert summary["citation_source_counts"] == {"both": 1, "retrieval_chunk": 1, "rich_block": 1}
    obj = summary["by_question_group"]["objective"]
    sub = summary["by_question_group"]["subjective_case"]
    assert obj["sample_count"] == 1 and obj["objective_exact_match_rate"] == 1.0
    assert sub["sample_count"] == 2
    assert sub["mean_rich_leaf_count"] == 2.5
    assert sub["multi_leaf_rate"] == 1.0
    assert sub["citation_source_counts"] == {"both": 1, "rich_block": 1}


def test_comparison_block_deltas_and_case_multi_leaf_readout() -> None:
    deploy_rows = [
        _row(mod.ARM_DEPLOY, qtype="single_choice", verdict="correct", rich_count=1, tokens=200),
        _row(mod.ARM_DEPLOY, qtype="case_study", verdict="correct", source="rich_block", rich_count=3, tokens=260),
    ]
    baseline_rows = [
        _row(mod.ARM_BASELINE, qtype="single_choice", verdict="correct", tokens=150),
        _row(mod.ARM_BASELINE, qtype="case_study", verdict="wrong", tokens=150),
    ]
    arms = [mod.arm_summary(mod.ARM_DEPLOY, deploy_rows), mod.arm_summary(mod.ARM_BASELINE, baseline_rows)]
    comparison = mod.comparison_block(arms)
    deltas = comparison["deltas_deploy_minus_baseline"]
    assert deltas["overall"]["semantic_score"] == 0.5
    assert deltas["overall"]["mean_total_tokens"] == 80.0
    assert deltas["subjective_case"]["semantic_score"] == 1.0
    assert comparison["deploy_subjective_multi_leaf"]["mean_rich_leaf_count"] == 3.0
    assert comparison["deploy_subjective_multi_leaf"]["multi_leaf_rate"] == 1.0
    assert comparison["deploy_subjective_multi_leaf"]["citation_source_counts"] == {"rich_block": 1}


# ---------------------------------------------------------------- previous-run reference


def test_previous_run_reference_verifies_question_set(tmp_path: Path) -> None:
    previous = {
        "seed": 20260613,
        "rows": [{"question_id": "q1", "arm": "real_kbv5_rag"}, {"question_id": "q2", "arm": "real_kbv5_rag"}],
        "arms": [{"arm": "real_kbv5_rag", "semantic_score": 0.825}],
    }
    path = tmp_path / "prev.json"
    path.write_text(json.dumps(previous), encoding="utf-8")
    ref = mod.previous_run_reference(path, ["q2", "q1"])
    assert ref["available"] is True
    assert ref["question_set_identical"] is True
    assert ref["reused_from"] == str(path)
    assert ref["previous_real_kbv5_rag_summary"]["semantic_score"] == 0.825
    mismatch = mod.previous_run_reference(path, ["q1", "qX"])
    assert mismatch["question_set_identical"] is False
    assert mod.previous_run_reference(tmp_path / "missing.json", ["q1"])["available"] is False


# ---------------------------------------------------------------- report invariants


def test_build_report_review_only_invariants() -> None:
    report = mod.build_report(
        questions=[_question()],
        rows=[_row(mod.ARM_DEPLOY)],
        judge_rows=[],
        model="deepseek-chat",
        seed=20260613,
        provider_configured=False,
        kbv5_status={"channel": "kb_v5.search_chunks_v2", "degraded": False},
        supply_manifest={"schema": "luban_rich_leaf_context_bundle.v1", "source_pack_version": "v3.1.1", "record_count": 1595, "content_hash": "x"},
        previous_reference={"available": False, "reason": "previous_results_missing"},
    )
    assert report["schema"] == mod.SCHEMA
    assert report["runtime_exercised"] is False
    assert "provider_call_not_configured" in report["blockers"]
    assert report["rich_leaf_supply"]["record_count"] == 1595
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["review_only"] is True
    assert report["classification"]["production_default"] is False
    assert report["safety"]["canonical_truth_written"] is False
    assert report["safety"]["official_score_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_resume_index_requires_schema_and_judged_rows() -> None:
    previous = {
        "schema": mod.SCHEMA,
        "rows": [
            {"question_id": "q1", "arm": mod.ARM_DEPLOY, "status": "completed", "judge_status": "completed"},
            {"question_id": "q1", "arm": mod.ARM_BASELINE, "status": "completed", "judge_status": "judge_failed"},
        ],
        "judge_rows": [{"question_id": "q1", "status": "completed"}],
    }
    answers, judges = mod._resume_index(previous)
    assert ("q1", mod.ARM_DEPLOY) in answers
    assert ("q1", mod.ARM_BASELINE) not in answers  # unjudged rows are re-run
    assert "q1" in judges
    assert mod._resume_index({"schema": "other.v1", "rows": previous["rows"]}) == ({}, {})
