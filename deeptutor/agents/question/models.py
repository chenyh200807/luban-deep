#!/usr/bin/env python
"""
Data models for the refactored question pipeline.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuestionTemplate:
    """
    Standardized intermediate template shared by all input paths.
    """

    question_id: str
    concentration: str
    question_type: str
    difficulty: str
    source: str = "custom"
    reference_question: str | None = None
    reference_answer: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QAPair:
    """
    Final generated Q-A payload.

    plan §Phase 3 (Batch C / A5): `grading_key` 是服务端 hidden authority，
    包含 correct_answer / scoring_points / common_traps / minimal_rationale。
    public serializer 必须 drop 它；只有 active_object.state_snapshot 与
    question_followup_context.items[i] 才能保存。
    """

    question_id: str
    question: str
    correct_answer: str
    explanation: str
    question_type: str
    options: dict[str, str] | None = None
    concentration: str = ""
    difficulty: str = ""
    validation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    # hidden grading authority — never serialized to public payload.
    grading_key: dict[str, Any] = field(default_factory=dict)
