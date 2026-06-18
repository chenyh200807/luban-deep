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

    async def _fake_embed_query(query: str) -> list[float]:
        captured["embedded_query"] = query
        return [0.0] * kbv5.EMBED_DIM

    monkeypatch.setattr(kbv5, "_embed_query", _fake_embed_query)

    pipeline = kbv5.KbV5Pipeline()
    result = await pipeline.search(
        "建筑构造是什么？",
        kb_name="construction-exam",
        top_k=1,
        doc_types=("textbook",),
        data_version=2026,
    )

    assert captured["query"] == "建筑构造是什么？"
    assert captured["embedded_query"] == "建筑构造是什么？"
    assert captured["top_k"] == 1
    assert captured["doc_types"] == ("textbook",)
    assert len(captured["embedding"]) == kbv5.EMBED_DIM
    assert result["provider"] == "kbv5"
    assert result["retrieval_status"] == "ok"
    assert result["sources"][0]["source_table"] == "kb_v5.chunks"
    assert result["sources"][0]["source_span"] == "p.2 建筑物构成"
    assert result["sources"][0]["score"] == 0.9
    assert "结构体系、围护体系和设备体系" in result["content"]
    assert result["evidence_bundle"]["provider"] == "kbv5"
    # kbv5 lane diagnostics moved into the canonical bundle's ``trace`` bucket (consolidation)
    assert result["evidence_bundle"]["trace"]["transport"] == "direct_postgres_readonly"
    json.dumps(result, ensure_ascii=False)


class _FakeCursor:
    description = [
        ("chunk_id",), ("doc_id",), ("doc_type",), ("authority",), ("loc",),
        ("content",), ("score_vector",), ("score_lexical",), ("score_final",),
    ]

    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self._captured["sql"] = sql
        self._captured["params"] = params

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []

    def close(self) -> None:
        return None


class _FakeConnection:
    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def set_session(self, **kwargs: Any) -> None:
        self._captured["session"] = kwargs

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._captured)

    def close(self) -> None:
        self._captured["closed"] = True


# A query shaped like the production failure: case background containing a
# markdown table whose ruler row (|----|----|) drives Postgres
# websearch_to_tsquery into "tsquery stack too small".
_MARKDOWN_TABLE_QUERY = (
    "背景资料：新建住宅小区单位工程，总建筑面积12.5万m²。\n"
    "| 检测项目 | 检测参数 | 抽检频次 |\n"
    "|------|----------|------------------|\n"
    "| 混凝土性能 | 同条件转标养强度 | 每批次 |\n"
    "问题：写出《临时用电组织设计》内容与管理中不妥之处的正确做法。"
)


def test_lexical_query_text_strips_markdown_table_ruler() -> None:
    from deeptutor.services.rag.pipelines.kbv5 import lexical_query_text

    bounded = lexical_query_text(_MARKDOWN_TABLE_QUERY)

    assert "-" not in bounded
    assert "|" not in bounded
    assert "混凝土性能" in bounded
    assert "同条件转标养强度" in bounded


def test_lexical_query_text_keeps_plain_short_query_words() -> None:
    from deeptutor.services.rag.pipelines.kbv5 import lexical_query_text

    assert lexical_query_text("建筑构造是什么？") == "建筑构造是什么"


def test_lexical_query_text_dedupes_and_caps_terms() -> None:
    from deeptutor.services.rag.pipelines.kbv5 import lexical_query_text

    repeated = " ".join(["混凝土"] * 50)
    assert lexical_query_text(repeated) == "混凝土"

    many = " ".join(f"词{i:04d}" for i in range(300)) + " 超长判别词保留优先"
    bounded = lexical_query_text(many, max_terms=64)
    terms = bounded.split(" ")
    assert len(terms) == 64
    # longest (most discriminative) terms are preferred over short ones
    assert "超长判别词保留优先" in terms


def test_retrieve_chunks_sends_bounded_lexical_query_but_embeds_full_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import kbv5

    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        kbv5,
        "connect_for_fact",
        lambda fact, **kwargs: (
            captured.update({"fact": fact, "connect_kwargs": kwargs})
            or _FakeConnection(captured)
        ),
    )

    embedded: dict[str, str] = {}

    def _embedder(text: str) -> list[float]:
        embedded["text"] = text
        return [0.0] * kbv5.EMBED_DIM

    kbv5._retrieve_chunks(
        _MARKDOWN_TABLE_QUERY,
        top_k=3,
        doc_types=("textbook",),
        data_version=2026,
        embedder=_embedder,
        db_url="postgresql://user:pass@example/db",
    )

    # embedding channel keeps the full raw query
    assert embedded["text"] == _MARKDOWN_TABLE_QUERY
    # lexical channel (query_text param) is bounded/sanitized
    sent_query_text = captured["params"][0]
    assert sent_query_text == kbv5.lexical_query_text(_MARKDOWN_TABLE_QUERY)
    assert "-" not in sent_query_text
    assert captured["fact"] == "kb_v5_chunk_retrieval"
    assert captured["connect_kwargs"]["db_url"] == "postgresql://user:pass@example/db"
    assert captured["connect_kwargs"]["readonly"] is True
    assert captured["connect_kwargs"]["timeout_s"] == 20
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_kbv5_embedding_uses_embedding_client_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import kbv5

    captured: dict[str, Any] = {}

    class FakeEmbeddingClient:
        def __init__(self, config: Any) -> None:
            captured["config"] = config

        async def embed(self, texts: list[str]) -> list[list[float]]:
            captured["texts"] = texts
            return [[0.0] * kbv5.EMBED_DIM]

    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(kbv5, "EmbeddingClient", FakeEmbeddingClient)

    embedding = await kbv5._embed_query("建筑构造是什么？")

    config = captured["config"]
    assert captured["texts"] == ["建筑构造是什么？"]
    assert config.binding == "dashscope"
    assert config.model == kbv5.EMBED_MODEL_DEFAULT
    assert config.dim == kbv5.EMBED_DIM
    assert config.effective_url == kbv5.DASHSCOPE_EMBEDDING_BASE_URL
    assert len(embedding) == kbv5.EMBED_DIM


@pytest.mark.asyncio
async def test_kbv5_embedding_fails_closed_on_wrong_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import kbv5

    class WrongDimensionClient:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 4]

    with pytest.raises(kbv5._KbV5Unavailable, match="unexpected embedding dim"):
        await kbv5._embed_query("建筑构造是什么？", client=WrongDimensionClient())


def test_benchmark_adapter_shares_the_same_lexical_query_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types

    from deeptutor.services.benchmark import kb_v5_readonly_adapter as kb
    from deeptutor.services.rag.pipelines.kbv5 import lexical_query_text

    captured: dict[str, Any] = {}
    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.connect = lambda url, connect_timeout=20: _FakeConnection(captured)
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)

    kb.retrieve(
        _MARKDOWN_TABLE_QUERY,
        top_k=3,
        embedder=lambda text: [0.0] * 4,
        db_url="postgresql://user:pass@example/db",
    )

    assert captured["params"][0] == lexical_query_text(_MARKDOWN_TABLE_QUERY)


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
