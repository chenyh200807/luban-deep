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


# ---------------------------------------------------------------- dual judge


def _verdicts(verdict: str, coverage: float, *, status: str = "completed") -> dict:
    if status != "completed":
        return {"judge_status": status, "verdict": None, "point_hits": None, "point_coverage": None}
    return {"judge_status": "completed", "verdict": verdict, "point_hits": [True], "point_coverage": coverage}


def test_merge_dual_judgments_agreement_keeps_verdict_and_means_coverage():
    merged = mod.merge_dual_judgments(
        {mod.ARM_DEPLOYED: _verdicts("partial", 0.5)},
        {mod.ARM_DEPLOYED: _verdicts("partial", 0.75)},
    )
    entry = merged[mod.ARM_DEPLOYED]
    assert entry["judge_status"] == "completed"
    assert entry["verdict"] == "partial"
    assert entry["judge_disagreement"] is False
    assert entry["verdict_score"] == 0.5
    assert entry["point_coverage"] == 0.625


def test_merge_dual_judgments_disagreement_means_scores_and_flags():
    merged = mod.merge_dual_judgments(
        {mod.ARM_DEPLOYED: _verdicts("correct", 1.0)},
        {mod.ARM_DEPLOYED: _verdicts("wrong", 0.0)},
    )
    entry = merged[mod.ARM_DEPLOYED]
    assert entry["judge_disagreement"] is True
    assert entry["verdict"] == "correct"  # primary pass verdict retained for rate metrics
    assert entry["verdict_swapped"] == "wrong"
    assert entry["verdict_score"] == 0.5  # mean of 1.0 and 0.0
    assert entry["point_coverage"] == 0.5


def test_merge_dual_judgments_single_pass_failure_degrades_to_surviving_pass():
    merged = mod.merge_dual_judgments(
        {mod.ARM_DEPLOYED: _verdicts("correct", 1.0)},
        {mod.ARM_DEPLOYED: _verdicts("", 0.0, status="judge_failed")},
    )
    entry = merged[mod.ARM_DEPLOYED]
    assert entry["judge_status"] == "completed"
    assert entry["verdict"] == "correct"
    assert entry["verdict_score"] == 1.0
    assert entry["judge_disagreement"] is None  # cannot compare with a failed pass
    # both passes failed -> failed
    both = mod.merge_dual_judgments(
        {mod.ARM_DEPLOYED: _verdicts("", 0.0, status="judge_failed")},
        {mod.ARM_DEPLOYED: _verdicts("", 0.0, status="judge_failed")},
    )
    assert both[mod.ARM_DEPLOYED]["judge_status"] == "judge_failed"


def test_arm_summary_uses_verdict_score_and_reports_disagreement_rate():
    row_a = _judged_row(mod.ARM_DEPLOYED, "2023:a", "correct", 0.5)
    row_a.update({"verdict_score": 0.5, "judge_disagreement": True})
    row_b = _judged_row(mod.ARM_DEPLOYED, "2023:b", "partial", 0.5)
    row_b.update({"verdict_score": 0.5, "judge_disagreement": False})
    summary = mod.arm_summary(mod.ARM_DEPLOYED, [row_a, row_b])
    assert summary["semantic_score"] == 0.5  # mean of verdict_score, not raw verdict
    assert summary["judge_disagreement_rate"] == 0.5


def test_arm_summary_without_dual_judge_has_none_disagreement_rate():
    summary = mod.arm_summary(mod.ARM_DEPLOYED, [_judged_row(mod.ARM_DEPLOYED, "2023:a", "correct", 1.0)])
    assert summary["judge_disagreement_rate"] is None
    assert summary["semantic_score"] == 1.0


def test_run_eval_dual_judge_two_judge_calls_with_swapped_order():
    case = {
        "case_id": "2023:a",
        "year": 2023,
        "background": "背景",
        "sub_questions": [
            {"sub_id": "2023:a:q1.0", "sub_no": "1", "text": "问？", "gold_answer": "金", "gold_analysis": "", "score": 5.0, "node_code": ""}
        ],
    }
    calls = {"answer": 0, "judge": []}

    def provider(messages, *, max_tokens=800, **kwargs):
        import json as _json

        payload = _json.loads(messages[-1]["content"])
        if "candidates" in payload:  # judge call
            calls["judge"].append(payload)
            verdict = "correct" if len(calls["judge"]) == 1 else "partial"
            content = _json.dumps(
                {
                    "scoring_points": ["点一", "点二"],
                    "candidates": {k: {"verdict": verdict, "point_hits": [True, False]} for k in payload["candidates"]},
                }
            )
        else:
            calls["answer"] += 1
            content = _json.dumps({"answer": "答案", "citations": []})
        return {"model": "m", "content": content, "prompt_tokens": 10, "completion_tokens": 5, "latency_ms": 1.0}

    report = mod.run_eval(
        cases=[case],
        provider_call=provider,
        retriever=None,
        rich_resolver=None,
        model="m",
        seed=1,
        token_budget=10_000,
        dual_judge=True,
    )
    assert calls["answer"] == 2
    assert len(calls["judge"]) == 2
    judge_passes = [r.get("pass") for r in report["judge_rows"]]
    assert judge_passes == ["primary", "swapped"]
    rows = [r for r in report["rows"] if r.get("judge_status") == "completed"]
    assert rows and all(r["judge_disagreement"] is True for r in rows)
    assert all(r["verdict_score"] == 0.75 for r in rows)  # mean(correct=1.0, partial=0.5)
    assert report["dual_judge"]["enabled"] is True
    assert report["dual_judge"]["disagreement_rate"] == 1.0
    # the swapped pass must present candidates in reversed arm order
    first_map = report["judge_rows"][0]["mapping"]
    second_map = report["judge_rows"][1]["mapping"]
    assert list(first_map.values()) == list(reversed(list(second_map.values())))


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


def test_classify_citations_textbook_point_label_maps_to_rich_block():
    audit = mod.classify_citations(
        ["【教材要点 L1】", "教材要点 L2", "教材要点 L9"],
        chunk_ids=["CET_1"],
        rich_leaf_ids=["1A431000-C1", "1A432000-C2"],
    )
    # L1/L2 resolve to existing rich blocks; L9 is out of range -> unknown
    assert audit["counts"] == {"retrieval_chunk": 0, "rich_block": 2, "unknown": 1}


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


# ---------------------------------------------------------------- v3 pack-sourced rich supply


def _fake_pack() -> dict:
    def unit(unit_id: str, leaf_id: str, name_path: str) -> dict:
        return {
            "unit_id": unit_id,
            "leaf_id": leaf_id,
            "leaf_name_path": name_path,
            "compiled_context": {
                "concepts": ["概念A"],
                "rules": [],
                "exam_patterns": [],
                "teaching_cards": [],
                "scoring_points": [
                    {
                        "statement": f"采分点甲-{leaf_id}",
                        "required_terms": ["术语1"],
                        "provenance": {"chunk_id": "CK_1A_0001"},
                    }
                ],
            },
            "confidence": "high",
            "source_lane": "source_truth",
            "source_ref": {"chunk_id": "CK_1A_0001"},
            "relative_path": "p.json",
        }

    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "version": "v3.2_test",
        "safety": {
            "official_score_allowed": False,
            "canonical_truth_written": False,
            "release_truth_claimed": False,
        },
        "quarantine": {"quarantine_candidate_unit_ids": ["u_quarantined"]},
        "runtime_token_pack_units": [
            unit("u_keep", "1A411011-B054", "建筑设计 > 屋面卷材防水层施工"),
            unit("u_quarantined", "1A999999-X001", "隔离 > 不得供给"),
        ],
    }


def test_pack_rich_index_validates_and_excludes_quarantine(tmp_path):
    import json as _json

    path = tmp_path / "pack.json"
    path.write_text(_json.dumps(_fake_pack(), ensure_ascii=False), encoding="utf-8")
    index = mod._pack_rich_index(path)
    assert "1A411011-B054" in index
    assert "1A999999-X001" not in index  # quarantined units must never be supplied
    assert index["1A411011-B054"]["compiled_context"]["scoring_points"]


def test_rich_resolver_pack_grading_renders_scoring_points_first(tmp_path, monkeypatch):
    import json as _json

    import deeptutor.services.compiled_knowledge.general_knowledge as gk
    import deeptutor.services.construction_grading.rich_leaf_runtime as rr

    path = tmp_path / "pack.json"
    path.write_text(_json.dumps(_fake_pack(), ensure_ascii=False), encoding="utf-8")
    # register original loader so monkeypatch restores it after the resolver overrides it
    monkeypatch.setattr(rr, "_load_index", rr._load_index)
    monkeypatch.setattr(
        gk,
        "build_general_knowledge_query_plan",
        lambda text: {"candidates": [{"node_code": "1A411011-B054"}], "query_terms": ["卷材"]},
    )
    resolve = mod._rich_resolver(pack_path=path, grading=True)
    rich = resolve("背景：屋面工程。", "指出屋面卷材防水的不妥之处？")
    assert rich["leaf_ids"] == ["1A411011-B054"]
    grounding = rich["grounding"]
    assert "【教材要点 L1】" in grounding
    assert "[采分点] 采分点甲-1A411011-B054" in grounding
    assert "必含术语：术语1" in grounding
    assert "〔源:CK_1A_0001〕" in grounding
    # grading render puts the scoring-point family ahead of the concept family
    assert grounding.index("[采分点]") < grounding.index("[概念]")
    assert rich["supply_source"] == str(path)


def test_rich_resolver_default_supply_has_no_pack_override():
    resolve = mod._rich_resolver()
    assert getattr(resolve, "supply_info", None) == {
        "source": "tracked_runtime_supply_v_rich_leaf_context",
        "grading_render": False,
    }
