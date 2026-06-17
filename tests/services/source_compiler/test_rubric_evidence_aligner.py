from __future__ import annotations

from deeptutor.services.source_compiler.rubric_evidence_aligner import (
    align_candidate_to_evidence,
    build_quality_report,
    build_review_rows,
    iter_evidence_records,
)


def test_iter_evidence_records_normalizes_book_and_standard_shapes() -> None:
    payload = {
        "content_blocks": [
            {
                "chunk_id": "c1",
                "content_markdown": "大体积混凝土温控指标包括温升值、里表温差、降温速率。",
                "taxonomy": {"node_code": "1A432000", "topic": "混凝土"},
            }
        ]
    }

    records = iter_evidence_records(payload, source_path="2026教材/a.json", source_class="book")

    assert records[0]["source_class"] == "book"
    assert records[0]["node_code"] == "1A432000"
    assert "温升值" in records[0]["content"]


def test_align_candidate_to_evidence_marks_publishable_candidate() -> None:
    candidate = {
        "stable_rubric_candidate_id": "rub1",
        "node_code": "1A432000",
        "overall_confidence": "A-",
        "warnings": [],
        "scoring_points": [
            {
                "point_id": "p1",
                "ordinal": 1,
                "label": "混凝土浇筑体的温升值",
                "expected_answer": "混凝土浇筑体的温升值",
                "max_score": 1.0,
                "confidence": "A-",
                "evidence_refs": [],
            }
        ],
    }
    evidence = [
        {
            "source_class": "book",
            "source_path": "book.json",
            "source_record_id": "c1",
            "node_code": "1A432000",
            "title": "大体积混凝土",
            "content": "大体积混凝土温控指标包括温升值、里表温差、降温速率。",
            "content_preview": "大体积混凝土温控指标包括温升值、里表温差、降温速率。",
        }
    ]

    aligned = align_candidate_to_evidence(candidate, evidence)
    review_rows = build_review_rows([aligned])
    report = build_quality_report([aligned], evidence_count=len(evidence))

    assert aligned["evidence_alignment_summary"]["aligned_points"] == 1
    assert aligned["publishability"]["gate"] == "publishable_candidate"
    assert review_rows[0]["evidence_aligned"] is True
    assert report["point_alignment_rate"] == 1.0


def test_missing_scores_block_publishability_even_with_evidence() -> None:
    candidate = {
        "stable_rubric_candidate_id": "rub1",
        "node_code": "1A432000",
        "overall_confidence": "B",
        "warnings": ["point_score_missing"],
        "scoring_points": [
            {
                "point_id": "p1",
                "ordinal": 1,
                "label": "三检制：自检、互检、工序交接检查",
                "expected_answer": "三检制：自检、互检、工序交接检查",
                "max_score": None,
                "confidence": "B",
                "evidence_refs": [],
            }
        ],
    }
    evidence = [
        {
            "source_class": "lecture_bundle",
            "source_path": "lecture.json",
            "source_record_id": "c1",
            "node_code": "1A432000",
            "title": "质量管理",
            "content": "施工质量管理包括三检制，自检、互检、工序交接检查。",
            "content_preview": "施工质量管理包括三检制，自检、互检、工序交接检查。",
        }
    ]

    aligned = align_candidate_to_evidence(candidate, evidence)

    assert aligned["publishability"]["gate"] == "blocked"
    assert "missing_score" in aligned["publishability"]["reasons"]
