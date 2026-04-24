"""Tests for OpenAI-compatible embedding response parsing."""

from deeptutor.services.embedding.adapters.openai_compatible import (
    OpenAICompatibleEmbeddingAdapter,
)


def _extract(data):
    return OpenAICompatibleEmbeddingAdapter._extract_embeddings_from_response(data)


def test_none_embedding_value_is_normalized_to_empty_list() -> None:
    data = {
        "data": [
            {"embedding": [0.1, 0.2]},
            {"embedding": None},
            {"embedding": [0.3, 0.4]},
        ]
    }

    assert _extract(data) == [[0.1, 0.2], [], [0.3, 0.4]]
