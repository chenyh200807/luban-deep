from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.source_compiler.lecture_compiler import compile_lecture_card
from deeptutor.services.source_compiler.question_compiler import _coerce_answer_list, compile_question_capsule
from deeptutor.services.source_compiler.question_join_resolver import resolve_question_capsule_joins
from deeptutor.services.source_compiler.rubric_compiler import compile_option_reasoning_backfill
from deeptutor.services.source_compiler.standard_compiler import compile_standard_clause, normalize_standard_code
from deeptutor.services.source_compiler.taxonomy_loader import TaxonomyIndex, build_taxonomy_index


def test_standard_stable_id_ignores_content_but_content_hash_changes() -> None:
    base = {
        "source_record_id": "STD_1",
        "source_context": {"standard_code": "GB／T 51366-2019"},
        "article_code": "1.0.1",
        "content": "old content",
    }
    changed = dict(base, content="new content")

    first = compile_standard_clause(base, run_id="r", source_path="标准/a.json", compiled_at="now")
    second = compile_standard_clause(changed, run_id="r", source_path="标准/a.json", compiled_at="now")

    assert first["stable_clause_id"] == second["stable_clause_id"]
    assert first["content_hash"] != second["content_hash"]
    assert first["normalized_standard_code"] == "GB/T51366-2019"


def test_standard_code_normalization_is_idempotent() -> None:
    value = "GB／T 51366-2019"
    assert normalize_standard_code(normalize_standard_code(value)) == normalize_standard_code(value)


def test_question_answer_coercion_and_stable_id_split() -> None:
    assert _coerce_answer_list(["B", "A", "A", None]) == ["A", "B"]

    base = {
        "source_chunk_id": "chunk1",
        "original_id": "orig1",
        "question_type": "single_choice",
        "node_code": "1A",
        "stem": "old stem",
        "options": {"A": "a"},
        "correct_answer": "A",
    }
    changed = dict(base, stem="new stem")

    first = compile_question_capsule(base, run_id="r", source_path="题库/a.json", compiled_at="now")
    second = compile_question_capsule(changed, run_id="r", source_path="题库/a.json", compiled_at="now")

    assert first["stable_question_source_id"] == second["stable_question_source_id"]
    assert first["content_hash"] != second["content_hash"]
    assert first["correct_answer"] == ["A"]


def test_taxonomy_lookup_and_duplicate_name_ambiguity() -> None:
    rows = build_taxonomy_index(
        [
            {"node_code": "1A", "name": "防水", "path_names": ["建筑", "防水"]},
            {"node_code": "1B", "name": "防水", "path_names": ["市政", "防水"]},
        ],
        run_id="r",
        source_path="taxonomy/t.json",
        compiled_at="now",
    )
    index = TaxonomyIndex(rows)

    assert index.lookup_node_by_code("1A")["name"] == "防水"
    assert index.lookup_node_by_path(["建筑", "防水"])["node_code"] == "1A"
    with pytest.raises(ValueError, match="ambiguous"):
        index.lookup_node_by_name("防水")


def test_question_join_resolver_emits_matched_and_unmatched() -> None:
    capsules = [
        {"stable_question_source_id": "q1", "original_id": "orig", "source_chunk_id": "missing", "node_code": "1A"},
        {
            "stable_question_source_id": "q2",
            "original_id": "none",
            "source_chunk_id": "none",
            "semantic_signature": "sig",
            "node_code": "1A",
        },
    ]
    bank_rows = [
        {"id": 10, "original_id": "orig", "source_chunk_id": "x", "node_code": "1A"},
        {"id": 11, "original_id": "other", "source_chunk_id": "y", "semantic_signature": "sig", "node_code": "1A"},
        {"id": 12, "original_id": "other2", "source_chunk_id": "z", "semantic_signature": "sig", "node_code": "1A"},
    ]

    matched, unmatched = resolve_question_capsule_joins(capsules, bank_rows)

    assert matched[0]["candidate_questions_bank_id"] == 10
    assert unmatched[0]["reason"] == "ambiguous_match"


def test_option_reasoning_preserves_existing_non_empty_policy() -> None:
    row = compile_option_reasoning_backfill(
        {
            "stable_question_source_id": "q1",
            "candidate_questions_bank_id": 10,
            "question_type": "single_choice",
            "option_reasoning": {"A": "because"},
        },
        existing_option_reasoning={"A": "curated"},
        run_id="r",
        source_path="题库/a.json",
        compiled_at="now",
    )

    assert row["writeback_policy"] == "skip_if_non_empty"


def test_lecture_card_has_figures_tables_and_content_hash_split() -> None:
    base = {"node_code": "1A", "title": "title", "content_markdown": "old", "figures": [{"id": "f"}]}
    changed = dict(base, content_markdown="new")

    first = compile_lecture_card(base, run_id="r", source_path="讲义/bundle.json", compiled_at="now")
    second = compile_lecture_card(changed, run_id="r", source_path="讲义/bundle.json", compiled_at="now")

    assert first["stable_lecture_card_id"] == second["stable_lecture_card_id"]
    assert first["content_hash"] != second["content_hash"]
    assert first["figures"] == [{"id": "f"}]
    assert first["tables"] == []
