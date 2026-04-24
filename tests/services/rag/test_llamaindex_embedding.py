"""Tests for LlamaIndex embedding adapter safeguards."""

import importlib

import pytest


pytest.importorskip("llama_index.core")
llamaindex_module = importlib.import_module("deeptutor.services.rag.pipelines.llamaindex")
CustomEmbedding = llamaindex_module.CustomEmbedding


def test_replace_missing_vectors_uses_valid_batch_dimension() -> None:
    vectors = [[1.0, 2.0], [], None, [3.0, 4.0]]

    assert CustomEmbedding._replace_missing_vectors(vectors) == [
        [1.0, 2.0],
        [0.0, 0.0],
        [0.0, 0.0],
        [3.0, 4.0],
    ]


def test_replace_missing_vectors_rejects_all_missing_batch() -> None:
    with pytest.raises(ValueError, match="no valid vectors"):
        CustomEmbedding._replace_missing_vectors([None, []])
