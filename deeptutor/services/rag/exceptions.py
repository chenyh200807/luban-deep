"""Typed RAG provider errors."""

from __future__ import annotations


class RAGError(Exception):
    """Base typed error for RAG provider failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        kb_name: str | None = None,
        query: str | None = None,
        stage: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.kb_name = kb_name
        self.query = query
        self.stage = stage
        self.retryable = retryable


class RAGSearchError(RAGError):
    """RAG retrieval failed before a grounded payload could be produced."""


def wrap_rag_error(
    exc: Exception,
    *,
    provider: str,
    kb_name: str | None = None,
    query: str | None = None,
    stage: str | None = None,
    retryable: bool = False,
) -> RAGError:
    """Normalize arbitrary exceptions into the single typed RAG error contract."""
    if isinstance(exc, RAGError):
        return exc
    detail = str(exc).strip() or exc.__class__.__name__
    return RAGSearchError(
        f"{provider} retrieval failed: {detail}",
        provider=provider,
        kb_name=kb_name,
        query=query,
        stage=stage,
        retryable=retryable,
    )
