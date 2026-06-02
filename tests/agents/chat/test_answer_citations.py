import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline, ToolTrace
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


@pytest.mark.asyncio
async def test_chat_emit_sources_and_result_appends_paper_style_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ANSWER_CITATIONS_ENABLED", "true")
    stream = StreamBus()
    pipeline = AgenticChatPipeline(language="zh")
    trace = ToolTrace(
        name="rag",
        arguments={"query": "屋面防水等级"},
        result="context",
        success=True,
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_001",
                    "source_span": {"chapter": "1", "section": "1.4"},
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        metadata={},
    )

    await pipeline._emit_sources_and_result(
        stream=stream,
        responding_trace={},
        tool_traces=[trace],
        final_response="屋面防水等级应根据工程重要性确定。",
        observation="",
    )

    result = next(event for event in stream._history if event.type == StreamEventType.RESULT)
    response = result.metadata["response"]
    assert response == "屋面防水等级应根据工程重要性确定。"
    assert "〔1〕" not in response
    assert "依据" not in response
    assert result.metadata["citation_bundle"]["footer_text"].startswith("依据\n〔1〕2026 建筑实务教材")
    assert result.metadata["citation_bundle"]["citation_state"] in {"supported", "partial"}
    content = "".join(
        str(event.content or "")
        for event in stream._history
        if event.type == StreamEventType.CONTENT
    )
    assert content == response


@pytest.mark.asyncio
async def test_chat_emit_sources_shadow_candidate_without_changing_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_ANSWER_CITATIONS_ENABLED", raising=False)
    stream = StreamBus()
    pipeline = AgenticChatPipeline(language="zh")
    trace = ToolTrace(
        name="rag",
        arguments={"query": "屋面防水等级"},
        result="context",
        success=True,
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_001",
                    "source_span": {"chapter": "1", "section": "1.4"},
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        metadata={},
    )

    await pipeline._emit_sources_and_result(
        stream=stream,
        responding_trace={},
        tool_traces=[trace],
        final_response="屋面防水等级应根据工程重要性确定。",
        observation="",
    )

    result = next(event for event in stream._history if event.type == StreamEventType.RESULT)
    assert result.metadata["response"] == "屋面防水等级应根据工程重要性确定。"
    assert "citation_bundle" not in result.metadata
    assert result.metadata["citation_bundle_candidate"]["citation_state"] in {"supported", "partial"}
    assert result.metadata["citation_metrics"]["public_ref_count"] == 1
    assert result.metadata["citation_metrics"]["citation_ref_count"] == 1
    assert result.metadata["citation_metrics"]["citation_source_types"] == ["textbook"]
    assert result.metadata["citation_metrics"]["citation_quality"]["hidden_leak_detected"] is False
    assert result.metadata["citation_metrics"]["citation_quality"]["orphan_marker_count"] == 0
    assert result.metadata["citation_metrics"]["citation_quality"]["footer_marker_mismatch"] is False
