"""Embedding-signature helpers for RAG index version selection."""

from __future__ import annotations

import logging
from typing import Any

from deeptutor.services.rag.index_versioning import EmbeddingSignature

logger = logging.getLogger(__name__)


def signature_from_config(config: Any) -> EmbeddingSignature:
    return EmbeddingSignature(
        binding=(getattr(config, "binding", "") or "").strip().lower(),
        model=(getattr(config, "model", "") or "").strip(),
        dimension=int(getattr(config, "dim", 0) or 0),
        base_url=(
            getattr(config, "effective_url", None) or getattr(config, "base_url", None) or ""
        ).strip(),
        api_version=(getattr(config, "api_version", "") or "").strip(),
    )


def signature_from_embedding_config() -> EmbeddingSignature | None:
    try:
        from deeptutor.services.embedding import get_embedding_config
    except Exception:
        return None

    try:
        return signature_from_config(get_embedding_config())
    except Exception as exc:
        logger.debug("Cannot resolve embedding signature: %s", exc)
        return None
