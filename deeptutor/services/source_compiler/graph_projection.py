from __future__ import annotations

from .metadata import COMPILER_VERSION


def _edge(
    *,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relation: str,
    source_record_id: str,
    run_id: str,
) -> dict:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "target_type": target_type,
        "target_id": target_id,
        "relation": relation,
        "source_record_id": source_record_id,
        "compiler_version": COMPILER_VERSION,
        "run_id": run_id,
        "confidence": "projection",
    }


def edge_question_tests_node(question: dict, *, run_id: str) -> dict:
    qid = question["stable_question_source_id"]
    return _edge(
        source_type="question",
        source_id=qid,
        target_type="syllabus_node",
        target_id=question["node_code"],
        relation="tests",
        source_record_id=qid,
        run_id=run_id,
    )


def edge_question_cites_standard(question: dict, standard_ref: str, *, run_id: str) -> dict:
    qid = question["stable_question_source_id"]
    return _edge(
        source_type="question",
        source_id=qid,
        target_type="standard_article",
        target_id=standard_ref,
        relation="cites",
        source_record_id=qid,
        run_id=run_id,
    )


def edge_kb_chunk_cites_standard(kb_ref: dict, standard_ref: str, *, run_id: str) -> dict:
    chunk_id = kb_ref["chunk_id"]
    return _edge(
        source_type="kb_chunk",
        source_id=chunk_id,
        target_type="standard_article",
        target_id=standard_ref,
        relation="cites",
        source_record_id=chunk_id,
        run_id=run_id,
    )


def edge_standard_covers_node(standard: dict, node_code: str, *, run_id: str) -> dict:
    sid = standard["stable_clause_id"]
    return _edge(
        source_type="standard_article",
        source_id=sid,
        target_type="syllabus_node",
        target_id=node_code,
        relation="covers",
        source_record_id=sid,
        run_id=run_id,
    )


def edge_question_sourced_from_chunk(question: dict, chunk_id: str, *, run_id: str) -> dict:
    qid = question["stable_question_source_id"]
    return _edge(
        source_type="question",
        source_id=qid,
        target_type="kb_chunk",
        target_id=chunk_id,
        relation="sourced_from",
        source_record_id=qid,
        run_id=run_id,
    )


def edge_lecture_teaches_node(lecture_card: dict, node_code: str, *, run_id: str) -> dict:
    lid = lecture_card["stable_lecture_card_id"]
    return _edge(
        source_type="lecture_card",
        source_id=lid,
        target_type="syllabus_node",
        target_id=node_code,
        relation="teaches",
        source_record_id=lid,
        run_id=run_id,
    )


def project_graph_edges(
    *,
    questions: list[dict],
    standard_clauses: list[dict],
    lecture_cards: list[dict],
    kb_standard_refs: list[dict],
    run_id: str,
) -> list[dict]:
    edges: list[dict] = []
    for question in questions:
        if question.get("node_code"):
            edges.append(edge_question_tests_node(question, run_id=run_id))
        for standard_ref in question.get("candidate_standard_refs") or []:
            edges.append(edge_question_cites_standard(question, standard_ref, run_id=run_id))
        if question.get("source_chunk_id"):
            edges.append(edge_question_sourced_from_chunk(question, question["source_chunk_id"], run_id=run_id))
    for kb_ref in kb_standard_refs:
        if kb_ref.get("chunk_id") and kb_ref.get("standard_ref"):
            edges.append(edge_kb_chunk_cites_standard(kb_ref, kb_ref["standard_ref"], run_id=run_id))
    for standard in standard_clauses:
        for node_code in standard.get("taxonomy_node_codes") or []:
            edges.append(edge_standard_covers_node(standard, node_code, run_id=run_id))
    for lecture in lecture_cards:
        if lecture.get("node_code"):
            edges.append(edge_lecture_teaches_node(lecture, lecture["node_code"], run_id=run_id))
    return edges

