from __future__ import annotations

import math

import pytest

from deeptutor.services.embedding.validation import validate_embedding_batch


def test_validate_embedding_batch_normalizes_numeric_vectors() -> None:
    assert validate_embedding_batch(
        [[1, 2.5], [3, 4]],
        expected_count=2,
        binding="test",
        model="embed",
    ) == [[1.0, 2.5], [3.0, 4.0]]


@pytest.mark.parametrize(
    ("vectors", "match"),
    [
        ([[0.1, None]], "dimension 1 is null"),
        ([[0.1], []], "vector is empty"),
        ([[0.1], [0.2, 0.3]], "inconsistent vector dimensions"),
        ([[math.inf]], "not finite"),
    ],
)
def test_validate_embedding_batch_rejects_invalid_vectors(vectors, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        validate_embedding_batch(vectors, expected_count=len(vectors), binding="test", model="bad")


def test_validate_embedding_batch_rejects_dropped_provider_results() -> None:
    with pytest.raises(ValueError, match="expected 2, got 1"):
        validate_embedding_batch([[0.1, 0.2]], expected_count=2)
