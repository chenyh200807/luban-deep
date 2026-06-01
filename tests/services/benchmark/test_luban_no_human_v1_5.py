from __future__ import annotations

from deeptutor.services.benchmark.luban_no_human_v1_5 import (
    anchor_required_terms,
    build_textbook_anchor_corpus,
    build_case_official_answer_corpus,
    build_no_human_labels_for_case,
    classify_residual_resolution,
    apply_resolution_merge_to_fixture,
    categorize_unanchored_term,
    judge_point_agent_a,
    judge_point_agent_b,
    numeric_terms_from_point,
    squeeze_required_terms,
)


def test_textbook_anchor_corpus_pins_exact_and_form_normalized_spans(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材"
    standard_dir = source_root / "标准文件"
    textbook_dir.mkdir(parents=True)
    standard_dir.mkdir(parents=True)
    (textbook_dir / "book.json").write_text(
        '{"content":"施工总进度计划表（图），资源需要量及供应平衡表。"}',
        encoding="utf-8",
    )
    (standard_dir / "gb.json").write_text('{"content":"设置防护栏杆。"}', encoding="utf-8")

    corpus = build_textbook_anchor_corpus(source_root)
    anchored = anchor_required_terms(["施工总进度计划表(图)", "资源需要量及供应平衡表", "不存在术语"], corpus)

    by_term = {item["term"]: item for item in anchored["terms"]}
    assert by_term["施工总进度计划表(图)"]["anchors"][0]["match_method"] == "form_normalized"
    assert by_term["资源需要量及供应平衡表"]["anchors"][0]["match_method"] == "exact"
    assert anchored["unanchored_terms"] == ["不存在术语"]


def test_blind_agents_apply_literal_term_matching_without_synonyms() -> None:
    terms = ["诚实信用", "防护栏杆"]
    answer = "应遵循诚信经营原则，并设置防护栏杆。"

    a = judge_point_agent_a(answer, terms, max_score=2.0)
    b = judge_point_agent_b(answer, terms, max_score=2.0)

    assert a["hit"] == "partial"
    assert b["hit"] == "partial"
    assert a["score"] == 1.0
    assert b["score"] == 1.0
    assert a["matched_terms"] == ["防护栏杆"]
    assert b["matched_terms"] == ["防护栏杆"]


def test_numeric_terms_from_point_extracts_units_for_calculation_validation() -> None:
    point = {
        "label": "计算水泥用量=275kg、砂=742kg。",
        "official_basis": "配合比计算结果为水泥275kg, 砂742kg。",
    }

    assert numeric_terms_from_point(point) == ["275kg", "742kg"]


def test_classify_residual_resolution_keeps_external_expert_as_last_resort() -> None:
    assert (
        classify_residual_resolution(
            residual_type="calculation",
            unanchored_terms=[],
            terms=["275kg"],
            matched_terms=["275kg"],
        )["resolution_class"]
        == "A"
    )
    assert (
        classify_residual_resolution(
            residual_type="boundary",
            unanchored_terms=["连续安全绳"],
            terms=["连续安全绳"],
            matched_terms=[],
        )["resolution_class"]
        == "B"
    )
    tier2 = classify_residual_resolution(
        residual_type="expert_discretion",
        unanchored_terms=["行业裁量项"],
        terms=[],
        matched_terms=[],
    )
    assert tier2["resolution_class"] == "C"
    assert "Tier-0" in tier2["exhaustion_proof"]
    assert "Tier-1" in tier2["exhaustion_proof"]


def test_squeeze_required_terms_repairs_slash_paraphrase_to_anchored_term(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "标准文件" / "gb.json").write_text('{"content":"临边应设置防护栏杆。"}', encoding="utf-8")
    corpus = build_textbook_anchor_corpus(source_root)

    result = squeeze_required_terms(["防护栏杆/防护", "黄色或红色标示"], corpus)

    assert result["terms"] == ["防护栏杆"]
    assert result["root_cause_counts"]["rubric_is_paraphrase"] == 1
    assert result["root_cause_counts"]["genuinely_absent"] == 1


def test_case_official_answer_is_valid_exact_anchor_when_textbook_index_misses(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text('{"content":"教材没有这个枚举。"}', encoding="utf-8")
    corpus = build_textbook_anchor_corpus(source_root)
    case_corpus = corpus + build_case_official_answer_corpus(
        {"case_id": "Q11", "official_answer": "①生活区；②办公区；③材料加工和存放区。"}
    )

    result = squeeze_required_terms(["生活区/办公区/材料加工和存放区"], case_corpus)
    anchored = anchor_required_terms(result["terms"], case_corpus)

    assert result["terms"] == ["生活区", "办公区", "材料加工和存放区"]
    assert {item["anchors"][0]["source_class"] for item in anchored["terms"]} == {"official_answer"}


def test_empty_anchor_point_is_unverifiable_class_b_not_certified_miss() -> None:
    case = {
        "case_id": "QX",
        "gold_scoring_points": [{"point_id": "P1", "label": "官方术语缺失点", "max_score": 2.0}],
        "eval_samples": [{"student_id": "S1", "answer_text": "学生其实写了官方答案。"}],
    }

    labels = build_no_human_labels_for_case(case=case, corpus=[], required_terms_by_point={"P1": []})
    label = labels["labels_by_sample"]["S1"][0]

    assert label["verifiable"] is False
    assert label["hit"] == "unverifiable"
    assert label["score"] is None
    assert label["is_deterministic"] is False
    assert label["resolution_class"] == "B"


def test_independent_triage_cannot_demote_unverifiable_empty_anchor_to_a() -> None:
    fixture = {
        "cases": [
            {
                "case_id": "Q1",
                "eval_samples": [
                    {
                        "student_id": "S1",
                        "no_human_v1_5_labels": [
                            {
                                "case_id": "Q1",
                                "sample_id": "S1",
                                "point_id": "P1",
                                "resolution_class": "B",
                                "verifiable": False,
                                "is_deterministic": False,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    merged = {"rows": [{"case_id": "Q1", "sample_id": "S1", "point_id": "P1", "resolution_class": "A"}]}

    updated = apply_resolution_merge_to_fixture(fixture, merged)
    label = updated["cases"][0]["eval_samples"][0]["no_human_v1_5_labels"][0]

    assert label["resolution_class"] == "B"
    assert label["is_deterministic"] is False


def test_squeeze_required_terms_drops_junk_non_terms_even_when_present_in_source(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text('{"content":"可选项 环境 气候 地形"}', encoding="utf-8")
    corpus = build_textbook_anchor_corpus(source_root)

    result = squeeze_required_terms(["可选项", "环境", "气候"], corpus)

    assert result["terms"] == ["环境", "气候"]


def test_categorize_unanchored_term_detects_numeric_and_normalization(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text('{"content":"施工总进度计划表（图）"}', encoding="utf-8")
    corpus = build_textbook_anchor_corpus(source_root)

    assert categorize_unanchored_term("275kg", corpus)["category"] == "is_numeric_not_term"
    assert categorize_unanchored_term("施工总进度计划表(图)", corpus)["category"] == "normalization_miss"


def test_apply_resolution_merge_to_fixture_rewrites_only_matching_labels() -> None:
    fixture = {
        "cases": [
            {
                "case_id": "Q1",
                "eval_samples": [
                    {
                        "student_id": "S1",
                        "no_human_v1_5_labels": [
                            {
                                "case_id": "Q1",
                                "sample_id": "S1",
                                "point_id": "P1",
                                "resolution_class": "B",
                                "is_deterministic": False,
                            },
                            {
                                "case_id": "Q1",
                                "sample_id": "S1",
                                "point_id": "P2",
                                "resolution_class": "B",
                                "is_deterministic": False,
                            },
                        ],
                    }
                ],
            }
        ]
    }
    merged = {
        "rows": [
            {"case_id": "Q1", "sample_id": "S1", "point_id": "P1", "resolution_class": "A"},
            {"case_id": "Q1", "sample_id": "S1", "point_id": "P2", "resolution_class": "B"},
        ]
    }

    updated = apply_resolution_merge_to_fixture(fixture, merged)
    labels = updated["cases"][0]["eval_samples"][0]["no_human_v1_5_labels"]

    assert labels[0]["resolution_class"] == "A"
    assert labels[0]["is_deterministic"] is True
    assert labels[0]["independent_triage_applied"] is True
    assert labels[1]["resolution_class"] == "B"
