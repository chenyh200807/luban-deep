"""Focused tests for the rich-leaf frozen-v1 real-world three-arm eval runner."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "run_luban_rich_leaf_real_world_three_arm_eval.py"
spec = importlib.util.spec_from_file_location("real_world_three_arm_eval", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["real_world_three_arm_eval"] = mod
spec.loader.exec_module(mod)


def _question(qid: str = "2024:EXAM_1A411001_P0001_01:0", qtype: str = "single_choice") -> dict:
    return {
        "question_id": qid,
        "year": 2024,
        "node_code": "1A411001",
        "qtype": qtype,
        "stem": "历史建筑的建筑高度应按建筑室外设计地坪至建构筑物（　）计算。A.檐口顶点 B.屋脊 C.墙顶点 D.最高点",
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
            "concepts": ["概念1 建筑高度计算", "概念2 历史建筑高度", "概念3 多余"],
            "rules": ["规则1", "规则2", "规则3"],
            "exam_patterns": ["考点1", "考点2"],
            "teaching_cards": ["卡1"],
        },
        "source_ref": {
            "chunk_id": "1A411011_002_0005",
            "source_lane": "textbook",
            "source_path": "book.json",
            "record_id": "book.json#chunk:1A411011_002_0005",
            "span_hash": "abc",
        },
    }


def _exam_payload() -> dict:
    chunks = []
    for i in range(50):
        chunks.append(
            {
                "chunk_id": f"EXAM_1A41100{i % 9}_P{i:04d}_01",
                "taxonomy": {"node_code": f"1A41100{i % 9}"},
                "exercises": [
                    {
                        "type": "single_choice" if i % 3 else "case_study",
                        "question_data": {
                            "stem": f"题干{i}",
                            "options": [{"key": "A", "value": "x"}],
                            "correct_answer": "A" if i % 3 else "要点答案",
                            "analysis": f"解析{i}",
                            "score": 1.0,
                        },
                    }
                ],
            }
        )
    return {"meta": {}, "stats": {}, "chunks": chunks}


# ---------------------------------------------------------------- sampling


def test_sample_questions_deterministic_and_mix() -> None:
    questions = mod.extract_questions(_exam_payload(), year=2024)
    assert all(q["gold_answer"] and q["stem"] for q in questions)
    s1 = mod.sample_questions(questions, seed=20260613, objective_count=8, subjective_count=4)
    s2 = mod.sample_questions(questions, seed=20260613, objective_count=8, subjective_count=4)
    assert [q["question_id"] for q in s1] == [q["question_id"] for q in s2]
    assert sum(1 for q in s1 if q["qtype"] in mod.OBJECTIVE_TYPES) == 8
    assert sum(1 for q in s1 if q["qtype"] not in mod.OBJECTIVE_TYPES) == 4
    s3 = mod.sample_questions(questions, seed=99, objective_count=8, subjective_count=4)
    assert [q["question_id"] for q in s1] != [q["question_id"] for q in s3]


# ---------------------------------------------------------------- leaf resolution


def test_resolve_leaf_exact_prefix_then_keyword_fallback() -> None:
    units = [_unit("1A411011-B054"), _unit("1A413020-B001")]
    units[1]["leaf_name_path"] = "其他 > 不相关"
    question = _question()
    question["node_code"] = "1A411011"
    unit, mode = mod.resolve_leaf(question, units)
    assert unit["leaf_id"] == "1A411011-B054"
    assert mode == "node_code_exact"

    question["node_code"] = "1A411003"  # only 6-char prefix family match
    unit, mode = mod.resolve_leaf(question, units)
    assert unit["leaf_id"] == "1A411011-B054"
    assert mode == "node_code_family"

    question["node_code"] = "1A999999"
    unit, mode = mod.resolve_leaf(question, units)
    assert mode == "keyword_fallback"
    assert unit["leaf_id"] == "1A411011-B054"  # keyword overlap on 建筑高度


# ---------------------------------------------------------------- arm contexts


def test_arm_context_shapes() -> None:
    unit = _unit()
    chunks = [
        {"chunk_id": "c1", "doc_type": "textbook", "score_final": 0.6, "content": "全文内容一" * 50},
        {"chunk_id": "c2", "doc_type": "standard", "score_final": 0.5, "content": "全文内容二"},
    ]
    ctx_a = mod.arm_context(mod.ARM_KBV5, question=_question(), kbv5_chunks=chunks, unit=unit)
    assert ctx_a["mode"] == mod.ARM_KBV5
    assert len(ctx_a["retrieved_chunks"]) == 2
    assert ctx_a["retrieved_chunks"][0]["content"] == "全文内容一" * 50  # full chunk, no truncation

    ctx_b = mod.arm_context(mod.ARM_RICH_FULL, question=_question(), kbv5_chunks=[], unit=unit)
    assert ctx_b["leaf_id"] == unit["leaf_id"]
    assert all(len(v) <= 2 for v in ctx_b["compiled_context"].values())
    assert len(ctx_b["compiled_context"]["concepts"]) == 2

    ctx_c = mod.arm_context(mod.ARM_RICH_GUARD, question=_question(), kbv5_chunks=[], unit=unit)
    assert all(len(v) <= 1 for v in ctx_c["compiled_context"].values())
    assert ctx_c["guardrails"]
    assert "source_ref" in ctx_c


def test_answer_messages_require_option_letters_for_mcq() -> None:
    messages = mod.answer_messages(mod.ARM_RICH_FULL, question=_question(), context={"mode": "x"})
    assert messages[0]["role"] == "system"
    assert "option letter" in messages[0]["content"] or "选项字母" in messages[0]["content"]
    assert _question()["stem"][:10] in messages[1]["content"]


# ---------------------------------------------------------------- objective scoring


def test_objective_exact_match_normalization() -> None:
    assert mod.objective_exact_match("D", "D") is True
    assert mod.objective_exact_match("A,B,D", "ABD") is True
    assert mod.objective_exact_match("bda", "ABD") is True
    assert mod.objective_exact_match("A、B", "ABD") is False
    assert mod.objective_exact_match("", "ABD") is False


# ---------------------------------------------------------------- judge ordinals


def test_judge_messages_use_short_ordinals() -> None:
    arm_rows = [
        {"arm": mod.ARM_KBV5, "answer": "D", "explanation": "x", "citations": ["c1"], "context_digest": "d1"},
        {"arm": mod.ARM_RICH_FULL, "answer": "C", "explanation": "y", "citations": [], "context_digest": "d2"},
        {"arm": mod.ARM_RICH_GUARD, "answer": "D", "explanation": "z", "citations": ["s1"], "context_digest": "d3"},
    ]
    messages, mapping = mod.judge_messages(_question(), arm_rows)
    assert mapping == {"1": mod.ARM_KBV5, "2": mod.ARM_RICH_FULL, "3": mod.ARM_RICH_GUARD}
    body = messages[1]["content"]
    assert '"1"' in body and '"2"' in body and '"3"' in body
    assert mod.ARM_KBV5 not in body  # judge sees ordinals, not arm names


def test_judge_non_coverage_degrades_missing_keys() -> None:
    mapping = {"1": mod.ARM_KBV5, "2": mod.ARM_RICH_FULL, "3": mod.ARM_RICH_GUARD}
    parsed = {
        "1": {"verdict": "correct", "explanation_quality": 4, "citation_grounded": True},
        "3": {"verdict": "wrong", "explanation_quality": 2, "citation_grounded": False},
    }
    verdicts = mod.apply_judge_verdicts(parsed, mapping)
    assert verdicts[mod.ARM_KBV5]["judge_status"] == "completed"
    assert verdicts[mod.ARM_KBV5]["verdict"] == "correct"
    assert verdicts[mod.ARM_RICH_FULL]["judge_status"] == "judge_failed"
    assert verdicts[mod.ARM_RICH_FULL]["verdict"] is None
    assert verdicts[mod.ARM_RICH_GUARD]["verdict"] == "wrong"
    bad = mod.apply_judge_verdicts({"1": {"verdict": "great"}}, mapping)
    assert bad[mod.ARM_KBV5]["judge_status"] == "judge_failed"  # invalid verdict degrades


# ---------------------------------------------------------------- summary + report


def _row(arm: str, *, verdict: str | None = "correct", status: str = "completed") -> dict:
    return {
        "arm": arm,
        "question_id": "q1",
        "qtype": "single_choice",
        "status": status,
        "verdict": verdict,
        "judge_status": "completed" if verdict else "judge_failed",
        "explanation_quality": 4 if verdict else None,
        "citation_grounded": bool(verdict == "correct"),
        "exact_match": verdict == "correct",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 1000.0,
    }


def test_arm_summary_metrics() -> None:
    rows = [
        _row(mod.ARM_KBV5),
        _row(mod.ARM_KBV5, verdict="partial"),
        _row(mod.ARM_KBV5, verdict=None, status="failed"),
    ]
    summary = mod.arm_summary(mod.ARM_KBV5, rows)
    assert summary["sample_count"] == 3
    assert summary["judged_count"] == 2
    assert summary["correct_rate"] == 0.5
    assert summary["semantic_score"] == 0.75  # correct=1, partial=0.5
    assert summary["fail_rate"] == round(1 / 3, 4)
    assert summary["mean_total_tokens"] == 150.0


def test_build_report_review_only_invariants() -> None:
    report = mod.build_report(
        questions=[_question()],
        rows=[_row(mod.ARM_KBV5)],
        judge_rows=[],
        model="deepseek-chat",
        seed=20260613,
        provider_configured=False,
        kbv5_status={"channel": "kb_v5_direct", "degraded": False},
    )
    assert report["schema"] == mod.SCHEMA
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["review_only"] is True
    assert report["classification"]["production_default"] is False
    assert report["safety"]["canonical_truth_written"] is False
    assert report["safety"]["production_write_count"] == 0
    assert "provider_call_not_configured" in report["blockers"]
