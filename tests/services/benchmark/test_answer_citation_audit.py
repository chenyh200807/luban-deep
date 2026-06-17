from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.benchmark.answer_citation_audit import audit_answer_citation_cases


def test_answer_citation_audit_fixture_passes_accuracy_checks() -> None:
    result = audit_answer_citation_cases(Path("tests/fixtures/answer_citation_eval_cases.json"))

    assert result["suite"] == "answer_citation_eval_v1"
    assert result["citation_accuracy"] == 1.0
    assert result["footer_coverage"] == 1.0
    assert result["hidden_leak_count"] == 0
    assert result["results"] == [
        {
            "case_id": "textbook_roof_waterproofing",
            "citation_supported": True,
            "footer_supported": True,
            "hidden_leaks": [],
            "failures": [],
        }
    ]


def test_answer_citation_audit_rejects_missing_structured_footer(tmp_path) -> None:
    fixture_path = tmp_path / "bad_answer_citations.json"
    fixture_path.write_text(
        json.dumps(
            {
                "suite": "answer_citation_eval_v1_negative",
                "cases": [
                    {
                        "case_id": "missing_structured_footer",
                        "answer": "屋面防水等级应根据工程重要性确定。",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "1", "section": "1.4"},
                                }
                            ],
                            "claims": [
                                {
                                    "claim_id": "claim_1",
                                    "text": "屋面防水等级应根据工程重要性确定。",
                                    "citation_ids": ["c1"],
                                }
                            ],
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "屋面防水等级应根据工程重要性确定。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "1", "section": "1.4"},
                            }
                        ],
                        "forbidden_terms": ["correct_answer"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = audit_answer_citation_cases(fixture_path)

    assert result["citation_accuracy"] == 1.0
    assert result["footer_coverage"] == 0.0
    assert result["hidden_leak_count"] == 0
    assert result["results"][0]["footer_supported"] is False
    assert result["results"][0]["failures"] == ["missing_footer"]


def test_answer_citation_audit_does_not_split_on_body_judgement_basis_heading(tmp_path) -> None:
    fixture_path = tmp_path / "body_heading_answer_citations.json"
    fixture_path.write_text(
        json.dumps(
            {
                "suite": "answer_citation_eval_v1_body_heading",
                "cases": [
                    {
                        "case_id": "body_has_judgement_basis_heading",
                        "answer": "## 判断依据\n屋面防水等级应根据工程重要性确定。",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "1", "section": "1.4"},
                                }
                            ],
                            "footer_text": "依据\n〔1〕2026 建筑实务教材，第 1 章 第 1.4 节。",
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "屋面防水等级应根据工程重要性确定。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "1", "section": "1.4"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = audit_answer_citation_cases(fixture_path)

    assert result["footer_coverage"] == 1.0
    assert result["citation_accuracy"] == 1.0
    assert result["results"][0]["failures"] == []


def test_answer_citation_audit_preserves_legal_document_numbers(tmp_path) -> None:
    fixture_path = tmp_path / "legal_doc_answer_citations.json"
    fixture_path.write_text(
        json.dumps(
            {
                "suite": "answer_citation_eval_v1_legal_doc",
                "cases": [
                    {
                        "case_id": "legal_document_number",
                        "answer": "防疫复工可参考建办质〔2020〕8号。\n\n依据：关键线路决定总工期。",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "2"},
                                }
                            ],
                            "footer_text": "依据\n〔1〕2026 建筑实务教材，第 2 章。",
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "关键线路决定总工期。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "2"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = audit_answer_citation_cases(fixture_path)

    assert result["footer_coverage"] == 1.0
    assert result["results"][0]["failures"] == []


def test_answer_citation_audit_reports_negative_cases(tmp_path) -> None:
    fixture_path = tmp_path / "bad_answer_citations.json"
    fixture_path.write_text(
        json.dumps(
            {
                "suite": "answer_citation_eval_v1_negative",
                "cases": [
                    {
                        "case_id": "missing_footer",
                        "answer": "屋面防水等级应根据工程重要性确定。〔1〕",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "1", "section": "1.4"},
                                }
                            ]
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "屋面防水等级应根据工程重要性确定。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "1", "section": "1.4"},
                            }
                        ],
                        "forbidden_terms": ["correct_answer"],
                    },
                    {
                        "case_id": "orphan_body_marker",
                        "answer": "屋面防水等级应根据工程重要性确定。〔2〕\n\n依据\n〔1〕2026 建筑实务教材，第 1 章 第 1.4 节，source_id=book_2026_001。",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "1", "section": "1.4"},
                                }
                            ]
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "屋面防水等级应根据工程重要性确定。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "1", "section": "1.4"},
                            }
                        ],
                        "forbidden_terms": ["correct_answer"],
                    },
                    {
                        "case_id": "forbidden_term",
                        "answer": "屋面防水等级应根据工程重要性确定。〔1〕\n\n依据\n〔1〕2026 建筑实务教材，第 1 章 第 1.4 节，source_id=book_2026_001。correct_answer",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "1", "section": "1.4"},
                                }
                            ]
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "屋面防水等级应根据工程重要性确定。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "1", "section": "1.4"},
                            }
                        ],
                        "forbidden_terms": ["correct_answer"],
                    },
                    {
                        "case_id": "expected_span_mismatch",
                        "answer": "屋面防水等级应根据工程重要性确定。〔1〕\n\n依据\n〔1〕2026 建筑实务教材，第 1 章 第 1.4 节，source_id=book_2026_001。",
                        "citation_bundle": {
                            "refs": [
                                {
                                    "citation_id": "c1",
                                    "marker": "〔1〕",
                                    "source_id": "book_2026_001",
                                    "source_span": {"chapter": "1", "section": "1.4"},
                                }
                            ]
                        },
                        "expected_claim_refs": [
                            {
                                "claim_text": "屋面防水等级应根据工程重要性确定。",
                                "expected_source_ids": ["book_2026_001"],
                                "expected_source_span": {"chapter": "2", "section": "2.1"},
                            }
                        ],
                        "forbidden_terms": ["correct_answer"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = audit_answer_citation_cases(fixture_path)
    by_case = {case["case_id"]: case for case in result["results"]}

    assert result["citation_accuracy"] == 0.75
    assert result["footer_coverage"] == 0.0
    assert result["hidden_leak_count"] == 1
    assert by_case["missing_footer"]["failures"] == ["answer_contains_inline_markers:〔1〕", "missing_footer"]
    assert by_case["orphan_body_marker"]["failures"] == [
        "answer_contains_inline_markers:〔2〕",
        "answer_contains_footer",
        "missing_footer",
    ]
    assert by_case["forbidden_term"]["failures"] == [
        "answer_contains_inline_markers:〔1〕",
        "answer_contains_footer",
        "missing_footer",
        "hidden_forbidden_terms",
    ]
    assert by_case["expected_span_mismatch"]["failures"] == [
        "answer_contains_inline_markers:〔1〕",
        "answer_contains_footer",
        "missing_footer",
        "unsupported_expected_claim_ref:屋面防水等级应根据工程重要性确定。"
    ]
