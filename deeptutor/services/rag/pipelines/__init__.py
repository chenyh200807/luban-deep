"""Pre-configured RAG pipelines.

DeepTutor currently ships with a single built-in provider (`llamaindex`).
Additional providers can still be registered dynamically via the factory layer.
"""

from typing import Any

__all__ = [
    "LlamaIndexPipeline",
    "SupabasePipeline",
]


def __getattr__(name: str) -> Any:
    if name == "LlamaIndexPipeline":
        from .llamaindex import LlamaIndexPipeline

        return LlamaIndexPipeline
    if name == "SupabasePipeline":
        from .supabase import SupabasePipeline

        return SupabasePipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
