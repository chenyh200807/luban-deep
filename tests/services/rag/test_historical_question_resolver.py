from __future__ import annotations

import json

import pytest


_UNDERGROUND_WALL_QUERY = (
    "关于地下连续墙施工要求，正确的有（    ）。\n"
    "A. 地下连续墙单元槽段长度宜为8～10m\n"
    "B. 导墙高度不应小于1.0m\n"
    "C. 应设置现浇钢筋混凝土导墙\n"
    "D. 水下混凝土应采用导管法连续浇筑\n"
    "E. 混凝土达到设计强度后方可进行墙底注浆\n"
    "我选ACDE，对吗？"
)


def _write_question_bank(root) -> None:
    payload = {
        "taxonomy": {"node_code": "1A413020", "node_name": "土石方工程施工"},
        "exercises": [
            {
                "type": "multi_choice",
                "question_data": {
                    "stem": "关于地下连续墙施工要求，正确的有（    ）。",
                    "options": [
                        {"key": "A", "value": "地下连续墙单元槽段长度宜为8～10m"},
                        {"key": "B", "value": "导墙高度不应小于1.0m"},
                        {"key": "C", "value": "应设置现浇钢筋混凝土导墙"},
                        {"key": "D", "value": "水下混凝土应采用导管法连续浇筑"},
                        {"key": "E", "value": "混凝土达到设计强度后方可进行墙底注浆"},
                    ],
                    "correct_answer": "CDE",
                    "analysis": "A选项错误，槽段长度宜为4～6m。B选项错误，导墙高度不应小于1.2m。",
                    "score": 2.0,
                    "difficulty": "hard",
                },
                "predicted_node": "1A413020",
            }
        ],
    }
    (root / "questions.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_roof_slope_question_bank(root) -> None:
    payload = {
        "taxonomy": {"node_code": "1A411010", "node_name": "建筑设计"},
        "exercises": [
            {
                "type": "single_choice",
                "question_data": {
                    "stem": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（　　）。",
                    "options": [
                        {"key": "A", "value": "1%"},
                        {"key": "B", "value": "2%"},
                        {"key": "C", "value": "3%"},
                        {"key": "D", "value": "5%"},
                    ],
                    "correct_answer": "D",
                    "analysis": "屋面最小坡度：压型金属板：5%。",
                    "score": 1.0,
                    "difficulty": "medium",
                },
                "predicted_node": "1A411010",
            }
        ],
    }
    (root / "roof.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_historical_question_resolver_matches_full_mcq_from_configured_bank(tmp_path) -> None:
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_question_bank(tmp_path)

    exact_question = resolve_historical_question(
        _UNDERGROUND_WALL_QUERY,
        question_bank_dir=str(tmp_path),
    )

    assert exact_question is not None
    assert exact_question["answer_kind"] == "mcq"
    assert exact_question["source_group"] == "historical_question_bank"
    assert exact_question["correct_answer"] == "CDE"
    assert exact_question["stem"] == "关于地下连续墙施工要求，正确的有（    ）。"
    assert exact_question["options"][1] == {"key": "B", "value": "导墙高度不应小于1.0m"}
    assert exact_question["metadata"]["node_code"] == "1A413020"
    assert "source_path" not in exact_question["metadata"]


def test_historical_question_resolver_remaps_answer_to_current_option_surface(tmp_path) -> None:
    from deeptutor.services.rag.exact_authority import build_exact_authority_response
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_roof_slope_question_bank(tmp_path)
    query = (
        "这题选项顺序我手抄乱了：某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（　　）。\n"
        "A. 5%\n"
        "B. 1%\n"
        "C. 2%\n"
        "D. 3%\n"
        "我选A，对吗？别展开，一句话。"
    )

    exact_question = resolve_historical_question(query, question_bank_dir=str(tmp_path))

    assert exact_question is not None
    assert exact_question["correct_answer"] == "A"
    assert exact_question["options"][0] == {"key": "A", "value": "5%"}
    response = build_exact_authority_response(exact_question, user_message=query)
    assert response == "对，标准答案是 A（A. 5%），题库解析依据是：屋面最小坡度：压型金属板：5%。"


def test_historical_question_resolver_matches_natural_stem_variant_with_option_surface(tmp_path) -> None:
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_roof_slope_question_bank(tmp_path)
    query = "压型金属板采用轻型屋面时，屋面最小坡度宜为多少？A. 5% B. 1% C. 2% D. 3%，我选A，对吗？"

    exact_question = resolve_historical_question(query, question_bank_dir=str(tmp_path))

    assert exact_question is not None
    assert exact_question["correct_answer"] == "A"
    assert exact_question["metadata"]["canonical_correct_answer"] == "D"
    assert exact_question["metadata"]["option_surface"] == "query"


def test_historical_question_resolver_trims_trailing_learner_comment_from_option_surface(
    tmp_path,
) -> None:
    from deeptutor.services.rag.exact_authority import build_exact_authority_response
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_roof_slope_question_bank(tmp_path)
    query = (
        "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。"
        "A.5% B.1% C.2% D.3%，我听别人说A，直接判"
    )

    exact_question = resolve_historical_question(query, question_bank_dir=str(tmp_path))

    assert exact_question is not None
    assert exact_question["correct_answer"] == "A"
    assert exact_question["options"][3] == {"key": "D", "value": "3%"}
    assert exact_question["metadata"]["option_surface"] == "query"
    response = build_exact_authority_response(exact_question, user_message=query)
    assert "标准答案：A（A. 5%）" in response
    assert "D. 3%" in response


def test_historical_question_resolver_matches_value_only_ordered_options(tmp_path) -> None:
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_question_bank(tmp_path)
    query = (
        "地下连续墙那个：槽段8-10m、导墙1.0m、现浇导墙、导管法、"
        "水下混凝土后注浆，我是不是选CDE？别让我重打选项。"
    )

    exact_question = resolve_historical_question(query, question_bank_dir=str(tmp_path))

    assert exact_question is not None
    assert exact_question["correct_answer"] == "CDE"
    assert exact_question["metadata"]["option_surface"] == "canonical_value_only_query"


def test_historical_question_resolver_matches_fuzzy_option_surface_with_stem_anchor(
    tmp_path,
) -> None:
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_question_bank(tmp_path)
    query = (
        "地下连续墙施工要求：A槽段8-10m B导墙高度≥1.0m "
        "C现浇钢筋混凝土导墙 D导管法连续浇筑 E达设计强度后墙底注浆。"
        "我选ACDE，对吗？"
    )

    exact_question = resolve_historical_question(query, question_bank_dir=str(tmp_path))

    assert exact_question is not None
    assert exact_question["correct_answer"] == "CDE"
    assert exact_question["metadata"].get("option_surface") is None


def test_historical_question_resolver_does_not_match_option_values_without_stem_anchor(tmp_path) -> None:
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    _write_roof_slope_question_bank(tmp_path)
    query = "A. 5% B. 1% C. 2% D. 3%，我选A，对吗？"

    assert resolve_historical_question(query, question_bank_dir=str(tmp_path)) is None


@pytest.mark.asyncio
async def test_rag_service_adds_historical_exact_question_when_pipeline_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.rag.service import RAGService
    from deeptutor.services.rag import service as rag_service_module

    _write_question_bank(tmp_path)
    monkeypatch.setenv("DEEPTUTOR_HISTORICAL_QUESTION_BANK_DIR", str(tmp_path))

    class _EmptyPipeline:
        async def search(self, **kwargs):
            return {
                "query": kwargs["query"],
                "answer": "No documents indexed. Please upload documents first.",
                "content": "No documents indexed. Please upload documents first.",
                "sources": [],
                "provider": "llamaindex",
            }

    monkeypatch.setattr(rag_service_module, "get_pipeline", lambda *args, **kwargs: _EmptyPipeline())
    service = RAGService(provider="llamaindex")
    monkeypatch.setattr(service, "_get_provider_for_kb", lambda kb_name: "llamaindex")

    result = await service.search(query=_UNDERGROUND_WALL_QUERY, kb_name="construction-exam")

    assert result["exact_question"]["correct_answer"] == "CDE"
    assert result["exact_question"]["source_group"] == "historical_question_bank"
    assert result["evidence_bundle"]["exact_question"]["correct_answer"] == "CDE"
    assert "题库原题" in result["content"]
    assert "标准答案：CDE" in result["content"]


@pytest.mark.asyncio
async def test_rag_service_returns_historical_exact_question_when_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.rag.exceptions import RAGSearchError
    from deeptutor.services.rag.service import RAGService
    from deeptutor.services.rag import service as rag_service_module

    _write_question_bank(tmp_path)
    monkeypatch.setenv("DEEPTUTOR_HISTORICAL_QUESTION_BANK_DIR", str(tmp_path))

    class _FailingPipeline:
        async def search(self, **kwargs):
            raise RAGSearchError(
                "supabase retrieval failed: Data API unavailable",
                provider="supabase",
                kb_name=kwargs["kb_name"],
                query=kwargs["query"],
                stage="pipeline.search",
                retryable=False,
            )

    monkeypatch.setattr(rag_service_module, "get_pipeline", lambda *args, **kwargs: _FailingPipeline())
    service = RAGService(provider="supabase")
    monkeypatch.setattr(service, "_get_provider_for_kb", lambda kb_name: "supabase")

    result = await service.search(query=_UNDERGROUND_WALL_QUERY, kb_name="construction-exam")

    assert result["exact_question"]["correct_answer"] == "CDE"
    assert result["canonical_question_context"]["answer_key"] == "CDE"
    assert result["retrieval_degraded"] is True
    assert result["retrieval_status"] == "provider_failed_exact_question_resolved"
    assert result["evidence_bundle"]["exact_question"]["correct_answer"] == "CDE"
    assert result["evidence_bundle"]["canonical_question_context"]["answer_key"] == "CDE"
    assert result["evidence_bundle"]["retrieval_degraded"] is True
    assert result["evidence_bundle"]["retrieval_status"] == "provider_failed_exact_question_resolved"
    assert "题库原题" in result["content"]
    assert "标准答案：CDE" in result["content"]
