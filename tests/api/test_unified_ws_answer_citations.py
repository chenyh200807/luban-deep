from deeptutor.services.citations import CitationPolicy, assemble_cited_answer
from deeptutor.api.routers.unified_ws import _redact_event_for_public


def test_public_citation_bundle_does_not_include_hidden_grading_authority() -> None:
    cited = assemble_cited_answer(
        "这题考查屋面防水。",
        sources=[
            {"source_type": "questions_bank", "field": "correct_answer", "value": "A"},
            {"source_type": "questions_bank", "field": "knowledge_point", "value": "屋面防水"},
        ],
        policy=CitationPolicy(surface="student"),
    )

    payload = cited.bundle.to_public_dict()
    text = str(payload)
    assert "correct_answer" not in text
    assert "grading_key" not in text
    assert "屋面防水" in text


def test_unified_ws_public_boundary_redacts_hidden_fields_inside_citation_bundle() -> None:
    event = {
        "type": "result",
        "metadata": {
            "response": "这题考查屋面防水。",
            "citation_bundle": {
                "citation_state": "supported",
                "refs": [
                    {
                        "marker": "〔1〕",
                        "title": "题库",
                        "correct_answer": "A",
                        "official_answer": "A",
                        "source_fields": ["knowledge_point", "correct_answer"],
                    },
                    {
                        "field": "grading_key",
                        "value": {"correct_answer": "B"},
                    },
                ],
                "claims": [],
                "footer_text": "依据\n〔1〕题库",
            },
        },
    }

    redacted = _redact_event_for_public(event)
    text = str(redacted)

    assert "correct_answer" not in text
    assert "official_answer" not in text
    assert "grading_key" not in text
    assert "knowledge_point" in text


def test_public_citation_bundle_drops_internal_source_titles() -> None:
    event = {
        "type": "result",
        "metadata": {
            "response": "我会只用学生可见的话复盘。",
            "citation_bundle": {
                "citation_state": "supported",
                "refs": [
                    {
                        "marker": "〔1〕",
                        "title": "learner_summary",
                        "source": "learner_summary",
                    },
                    {
                        "marker": "〔2〕",
                        "title": "教材公开资料",
                        "source": "construction_grading",
                    },
                ],
                "claims": [],
                "footer_text": "依据\n〔1〕learner_summary\n〔2〕教材公开资料",
            },
        },
    }

    redacted = _redact_event_for_public(event)
    text = str(redacted)

    assert "learner_summary" not in text
    assert "教材公开资料" in text
