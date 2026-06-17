"""Shared engine result shape and errors.

EngineResult is the only contract the pipeline consumes; every client maps
its provider payload into this shape. line_boxes use [x, y, w, h] pixel
boxes — the L0 box list is the coordinate authority for confirm-page spans
(plan §5 reconcile: spans must anchor back to L0 boxes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.photo_answer.models import PhotoAnswerError


class EngineError(PhotoAnswerError):
    """Provider call failed (network, quota, provider-side error)."""


class EngineNotConfigured(EngineError):
    """Required credentials missing — fail closed, never call without keys."""


@dataclass
class EngineResult:
    engine: str
    raw_text: str
    line_boxes: list[dict[str, Any]] = field(default_factory=list)
    char_confidences: list[dict[str, Any]] = field(default_factory=list)
    alteration_marks: list[dict[str, Any]] = field(default_factory=list)
    engine_model_version: str = ""
    provider_usage_id: str = ""
    request_hash: str = ""
    cost_micros: int = 0
