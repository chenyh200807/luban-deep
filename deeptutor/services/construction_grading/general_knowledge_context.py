"""Compatibility wrapper for the system compiled knowledge service.

The authority now lives under ``deeptutor.services.compiled_knowledge`` so
knowledge dialogue callers do not depend on a grading namespace. The underlying
canonical taxonomy and compiled bundle remain the single source.
"""
from __future__ import annotations

from deeptutor.services.compiled_knowledge.general_knowledge import *  # noqa: F401,F403
from deeptutor.services.compiled_knowledge.general_knowledge import _anchor_candidates
