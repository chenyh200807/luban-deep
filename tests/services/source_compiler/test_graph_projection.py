from __future__ import annotations

import pytest

from deeptutor.services.source_compiler.graph_projection import (
    edge_kb_chunk_cites_standard,
    edge_lecture_teaches_node,
    edge_question_cites_standard,
    edge_question_sourced_from_chunk,
    edge_question_tests_node,
    edge_standard_covers_node,
    project_graph_edges,
)


def test_graph_emits_six_edge_families() -> None:
    edges = project_graph_edges(
        questions=[
            {
                "stable_question_source_id": "q1",
                "node_code": "1A",
                "candidate_standard_refs": ["GB50210-2018:1.0.1"],
                "source_chunk_id": "chunk1",
            }
        ],
        standard_clauses=[{"stable_clause_id": "std1", "taxonomy_node_codes": ["1A"]}],
        lecture_cards=[{"stable_lecture_card_id": "lect1", "node_code": "1A"}],
        kb_standard_refs=[{"chunk_id": "chunk1", "standard_ref": "GB50210-2018:1.0.1"}],
        run_id="r",
    )

    families = {(edge["source_type"], edge["target_type"], edge["relation"]) for edge in edges}
    assert ("question", "syllabus_node", "tests") in families
    assert ("question", "standard_article", "cites") in families
    assert ("kb_chunk", "standard_article", "cites") in families
    assert ("standard_article", "syllabus_node", "covers") in families
    assert ("question", "kb_chunk", "sourced_from") in families
    assert ("lecture_card", "syllabus_node", "teaches") in families


def test_graph_edges_include_metadata_and_do_not_override_authority() -> None:
    edge = edge_question_tests_node({"stable_question_source_id": "q1", "node_code": "1A"}, run_id="r")

    assert edge["source_record_id"] == "q1"
    assert edge["compiler_version"] == "2026-source-compiler-v0.2"
    assert edge["run_id"] == "r"
    assert edge["confidence"] == "projection"
    assert "correct_answer" not in edge


@pytest.mark.parametrize(
    "builder,args",
    [
        (edge_question_cites_standard, ({"stable_question_source_id": "q1"}, "GB50210-2018:1.0.1")),
        (edge_kb_chunk_cites_standard, ({"chunk_id": "chunk1"}, "GB50210-2018:1.0.1")),
        (edge_standard_covers_node, ({"stable_clause_id": "std1"}, "1A")),
        (edge_question_sourced_from_chunk, ({"stable_question_source_id": "q1"}, "chunk1")),
        (edge_lecture_teaches_node, ({"stable_lecture_card_id": "lect1"}, "1A")),
    ],
)
def test_edge_helpers(builder, args) -> None:
    edge = builder(*args, run_id="r")
    assert edge["run_id"] == "r"
    assert edge["confidence"] == "projection"
