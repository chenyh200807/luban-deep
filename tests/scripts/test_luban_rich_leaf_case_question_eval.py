"""Focused tests for the case-question two-arm eval runner (no live provider calls)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "run_luban_rich_leaf_case_question_eval",
    REPO / "scripts" / "run_luban_rich_leaf_case_question_eval.py",
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


# ---------------------------------------------------------------- stem split


def test_split_case_stem_colon_marker():
    bg, no, sub = mod.split_case_stem("背景甲乙丙。\n\n问题1：指出不妥之处，并写出正确做法。")
    assert bg == "背景甲乙丙。"
    assert no == "1"
    assert sub == "指出不妥之处，并写出正确做法。"


def test_split_case_stem_bracket_marker():
    bg, no, sub = mod.split_case_stem("背景资料若干。\n\n【问题】3. 常用高分子防水卷材有哪些？")
    assert (no, sub) == ("3", "常用高分子防水卷材有哪些？")
    assert bg == "背景资料若干。"


def test_split_case_stem_numbered_paragraph_fallback():
    stem = "背景：\n（1）条件一；\n（2）条件二。\n\n2.与绿色建造相关的信息技术还有哪些？"
    bg, no, sub = mod.split_case_stem(stem)
    assert no == "2"
    assert sub == "与绿色建造相关的信息技术还有哪些？"


def test_split_case_stem_drops_unsplittable():
    assert mod.split_case_stem("只有背景没有问题标记的文本（1）甲（2）乙") is None


# ---------------------------------------------------------------- grouping


def _exam_payload() -> dict:
    def ex(stem: str, gold: str) -> dict:
        return {
            "type": "case_study",
            "question_data": {"stem": stem, "correct_answer": gold, "analysis": "解析", "score": 5.0},
        }

    bg = "【背景资料】某新建工程，地下2层，地上12层，发生了若干管理事件。"
    bg_dup = "某新建工程，地下2层，地上12层，发生了若干管理事件。"  # same case, prefix stripped
    return {
        "chunks": [
            {
                "chunk_id": "EXAM_X_1",
                "taxonomy": {"node_code": "1A431000"},
                "exercises": [
                    ex(f"{bg}\n\n问题1：指出不妥之处？", "金标A"),
                    ex(f"{bg}\n\n问题2：列出验收程序有哪些？", "金标B"),
                ],
            },
            {
                "chunk_id": "EXAM_X_2",
                "taxonomy": {"node_code": "1A432000"},
                "exercises": [
                    ex(f"{bg_dup}\n\n问题2：列出验收程序有哪些？", "金标B更长版本内容"),
                    ex(f"{bg_dup}\n\n问题3：计算工期是多少天？", "金标C"),
                    {"type": "single_choice", "question_data": {"stem": "选择题", "correct_answer": "A"}},
                ],
            },
        ]
    }


def test_extract_case_groups_merges_prefix_variants_and_dedupes_subs():
    groups = mod.extract_case_groups(_exam_payload(), year=2023)
    assert len(groups) == 1
    case = groups[0]
    assert case["year"] == 2023
    subs = case["sub_questions"]
    assert [s["sub_no"] for s in subs] == ["1", "2", "3"]
    # dedupe keeps the longer gold for the duplicated sub-question 2
    assert subs[1]["gold_answer"] == "金标B更长版本内容"
    assert all(s["sub_id"].startswith("2023:") for s in subs)


def test_sample_cases_seed_deterministic_and_min_subs():
    cases = [
        {"case_id": f"2023:c{i}", "year": 2023, "background": "bg", "sub_questions": [{}] * n}
        for i, n in enumerate([1, 2, 3, 4, 5, 2, 3])
    ]
    picked_a = mod.sample_cases(cases, seed=7, count=3)
    picked_b = mod.sample_cases(cases, seed=7, count=3)
    assert picked_a == picked_b
    assert all(len(c["sub_questions"]) >= 2 for c in picked_a)
    assert [c["case_id"] for c in picked_a] == sorted(c["case_id"] for c in picked_a)


# ---------------------------------------------------------------- arm context


def test_arm_context_baseline_has_no_rich_block():
    chunks = [{"chunk_id": "CET_1", "doc_type": "textbook", "content": "x" * 999}]
    rich = {"grounding": "【富叶】内容", "leaf_ids": ["1A431000-C1"]}
    deployed = mod.arm_context(mod.ARM_DEPLOYED, kbv5_chunks=chunks, rich=rich)
    baseline = mod.arm_context(mod.ARM_BASELINE, kbv5_chunks=chunks, rich=rich)
    assert deployed["rich_leaf_grounding"] == "【富叶】内容"
    assert deployed["rich_leaf_ids"] == ["1A431000-C1"]
    assert "rich_leaf_grounding" not in baseline and "rich_leaf_ids" not in baseline
    assert len(deployed["retrieved_chunks"][0]["content"]) <= mod.CHUNK_CONTENT_CLIP


# ---------------------------------------------------------------- judge parsing


def test_apply_case_judge_happy_path():
    parsed = {
        "scoring_points": ["点一", "点二", "点三"],
        "candidates": {
            "1": {"verdict": "partial", "point_hits": [True, False, True]},
            "2": {"verdict": "wrong", "point_hits": [False, False, False]},
        },
    }
    points, verdicts = mod.apply_case_judge(parsed, {"1": mod.ARM_DEPLOYED, "2": mod.ARM_BASELINE})
    assert points == ["点一", "点二", "点三"]
    assert verdicts[mod.ARM_DEPLOYED]["point_coverage"] == 0.6667
    assert verdicts[mod.ARM_BASELINE]["verdict"] == "wrong"
    assert all(v["judge_status"] == "completed" for v in verdicts.values())


def test_apply_case_judge_length_mismatch_degrades_to_failed():
    parsed = {
        "scoring_points": ["点一", "点二"],
        "candidates": {
            "1": {"verdict": "correct", "point_hits": [True]},  # wrong length
            "2": {"verdict": "maybe", "point_hits": [True, False]},  # invalid verdict
        },
    }
    _, verdicts = mod.apply_case_judge(parsed, {"1": mod.ARM_DEPLOYED, "2": mod.ARM_BASELINE})
    assert all(v["judge_status"] == "judge_failed" for v in verdicts.values())
    assert all(v["point_coverage"] is None for v in verdicts.values())


def test_apply_case_judge_empty_points_degrades():
    parsed = {"scoring_points": [], "candidates": {"1": {"verdict": "correct", "point_hits": []}}}
    _, verdicts = mod.apply_case_judge(parsed, {"1": mod.ARM_DEPLOYED})
    assert verdicts[mod.ARM_DEPLOYED]["judge_status"] == "judge_failed"


# ---------------------------------------------------------------- citations


def test_classify_citations_three_way_split():
    audit = mod.classify_citations(
        ["CET_1A434000_P0066_002", "rich:1A431000-C1", "捏造的来源", ""],
        chunk_ids=["CET_1A434000_P0066_002", "CET_OTHER"],
        rich_leaf_ids=["1A431000-C1"],
    )
    assert audit["counts"] == {"retrieval_chunk": 1, "rich_block": 1, "unknown": 1}
    assert audit["total"] == 3
    assert audit["grounded_rate"] == 0.6667


def test_classify_citations_empty_is_none_rate():
    audit = mod.classify_citations([], chunk_ids=["C1"], rich_leaf_ids=[])
    assert audit["total"] == 0 and audit["grounded_rate"] is None


# ---------------------------------------------------------------- summaries / report


def _judged_row(arm: str, case_id: str, verdict: str, coverage: float, tokens: int = 1000) -> dict:
    return {
        "arm": arm,
        "case_id": case_id,
        "sub_id": f"{case_id}:q1.0",
        "status": "completed",
        "judge_status": "completed",
        "verdict": verdict,
        "point_coverage": coverage,
        "citation_audit": {"counts": {"retrieval_chunk": 1, "rich_block": 0, "unknown": 1}, "total": 2, "grounded_rate": 0.5},
        "prompt_tokens": tokens,
        "completion_tokens": 100,
        "total_tokens": tokens + 100,
        "latency_ms": 50.0,
    }


def test_arm_summary_metrics():
    rows = [
        _judged_row(mod.ARM_DEPLOYED, "2023:a", "correct", 1.0),
        _judged_row(mod.ARM_DEPLOYED, "2023:b", "partial", 0.5),
    ]
    summary = mod.arm_summary(mod.ARM_DEPLOYED, rows)
    assert summary["semantic_score"] == 0.75
    assert summary["scoring_point_coverage"] == 0.75
    assert summary["citation_grounded_rate"] == 0.5
    assert summary["citation_source_counts"]["unknown"] == 2
    assert summary["mean_total_tokens"] == 1100.0


def test_case_summaries_group_by_case():
    rows = [
        _judged_row(mod.ARM_DEPLOYED, "2023:a", "correct", 1.0),
        _judged_row(mod.ARM_BASELINE, "2023:a", "wrong", 0.0),
    ]
    summaries = mod.case_summaries(rows)
    assert len(summaries) == 1
    assert summaries[0][mod.ARM_DEPLOYED]["semantic_score"] == 1.0
    assert summaries[0][mod.ARM_BASELINE]["semantic_score"] == 0.0


def test_build_report_without_provider_is_not_exercised(tmp_path):
    report = mod.build_report(
        cases=[{"case_id": "2023:a", "year": 2023, "sub_questions": [{}]}],
        rows=[],
        judge_rows=[],
        model="deepseek-chat",
        seed=1,
        provider_configured=False,
        kbv5_status={"channel": "kb_v5.search_chunks_v2"},
    )
    assert report["runtime_exercised"] is False
    assert "provider_call_not_configured" in report["blockers"]
    assert report["safety"]["canonical_truth_written"] is False
    assert report["classification"]["candidate_only"] is True


def test_run_eval_no_provider_writes_checkpoint(tmp_path):
    out = tmp_path / "results.json"
    report = mod.run_eval(
        cases=[],
        provider_call=None,
        retriever=None,
        rich_resolver=None,
        model="deepseek-chat",
        seed=1,
        token_budget=1000,
        output_path=out,
    )
    assert out.exists()
    assert report["runtime_exercised"] is False


def test_run_eval_resume_skips_completed_sub(monkeypatch):
    case = {
        "case_id": "2023:a",
        "year": 2023,
        "background": "背景",
        "sub_questions": [
            {"sub_id": "2023:a:q1.0", "sub_no": "1", "text": "问？", "gold_answer": "金", "gold_analysis": "", "score": 5.0, "node_code": ""}
        ],
    }
    previous = {
        "rows": [
            {"sub_id": "2023:a:q1.0", "arm": arm, "status": "completed", "judge_status": "completed", "verdict": "correct"}
            for arm in mod.PLANNED_ARMS
        ],
        "judge_rows": [{"sub_id": "2023:a:q1.0", "status": "completed"}],
    }

    def boom(*args, **kwargs):  # provider must never be called when fully resumed
        raise AssertionError("provider called despite resume")

    report = mod.run_eval(
        cases=[case],
        provider_call=boom,
        retriever=None,
        rich_resolver=None,
        model="deepseek-chat",
        seed=1,
        token_budget=1000,
        previous=previous,
    )
    assert len(report["rows"]) == 2
    assert report["judge_rows"][0]["status"] == "completed"
