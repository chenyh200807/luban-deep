from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import json
from typing import Any

import pytest


class _FakeObservability:
    @contextmanager
    def start_observation(self, **_: Any):
        yield object()

    def update_observation(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_kbv5_pipeline_projects_readonly_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.rag.pipelines import kbv5

    captured: dict[str, Any] = {}

    def _fake_retrieve_chunks(query: str, **kwargs: Any) -> kbv5._RetrievalResult:
        captured["query"] = query
        captured.update(kwargs)
        return kbv5._RetrievalResult(
            query=query,
            chunks=[
                kbv5._RetrievedChunk(
                    chunk_id="CET_1A411011_P002",
                    doc_id="doc-1",
                    doc_type="textbook",
                    authority={"weight": Decimal("2.0")},
                    loc={
                        "page": Decimal("2"),
                        "chapter": "建筑物分类与构成",
                        "section": "建筑物构成",
                        "source_path": "2026教材/book.json",
                    },
                    content="建筑物由结构体系、围护体系和设备体系组成。",
                    score_vector=Decimal("0.7"),
                    score_lexical=Decimal("0.4"),
                    score_final=Decimal("0.9"),
                )
            ],
            latency_ms=12.3,
            embed_dim=1024,
            doc_types=("textbook",),
        )

    monkeypatch.setattr(kbv5, "observability", _FakeObservability())
    monkeypatch.setattr(kbv5, "_retrieve_chunks", _fake_retrieve_chunks)

    pipeline = kbv5.KbV5Pipeline()
    result = await pipeline.search(
        "建筑构造是什么？",
        kb_name="construction-exam",
        top_k=1,
        doc_types=("textbook",),
        data_version=2026,
    )

    assert captured["query"] == "建筑构造是什么？"
    assert captured["top_k"] == 1
    assert captured["doc_types"] == ("textbook",)
    assert result["provider"] == "kbv5"
    assert result["retrieval_status"] == "ok"
    assert result["sources"][0]["source_table"] == "kb_v5.chunks"
    assert result["sources"][0]["source_span"] == "p.2 建筑物构成"
    assert result["sources"][0]["score"] == 0.9
    assert "结构体系、围护体系和设备体系" in result["content"]
    assert result["evidence_bundle"]["provider"] == "kbv5"
    assert result["evidence_bundle"]["transport"] == "direct_postgres_readonly"
    json.dumps(result, ensure_ascii=False)


def test_env_supabase_aliases_prefer_kbv5_when_direct_url_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.config.knowledge_base_config import get_env_defined_kbs

    monkeypatch.setenv("SUPABASE_RAG_ENABLED", "false")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_RAG_DEFAULT_KB_NAME", "supabase-main")
    monkeypatch.setenv("KBV5_DB_URL", "postgresql://user:pass@example/db")

    entries, _defaults = get_env_defined_kbs()

    assert entries["supabase-main"]["rag_provider"] == "kbv5"
    assert entries["construction-exam"]["rag_provider"] == "kbv5"
    assert entries["construction-exam"]["remote_read_only"] is True
