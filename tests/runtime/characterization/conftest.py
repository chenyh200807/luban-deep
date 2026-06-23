"""Dual-target LLM mocks for the routing characterization harness.

The decision chain reaches the LLM through TWO different import bindings, so both must be
patched or a row silently makes a live call (and Tier-A determinism claims go unchecked):

  - lifecycle scene proposal: ``deeptutor.services.llm.factory.complete`` (attribute access
    via ``from deeptutor.services.llm import factory``)
  - followup interpreter: ``deeptutor.services.question_followup.complete`` (name bound at
    module import: ``from deeptutor.services.llm.factory import complete``)

The recorder counts calls per target so Tier-A rows can assert NEITHER fired — turning the
harness into a guard on the "deterministic stays deterministic" invariant (turn.md §67/§72).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest


@dataclass
class LLMRecorder:
    lifecycle_calls: int = 0
    followup_calls: int = 0
    scripts: dict = field(default_factory=lambda: {"lifecycle_scene": None, "followup_action": None})


@pytest.fixture
def llm_mocks(monkeypatch) -> LLMRecorder:
    rec = LLMRecorder()

    async def _fake_factory_complete(**_kwargs):
        rec.lifecycle_calls += 1
        script = rec.scripts.get("lifecycle_scene")
        if script is None:
            # mirror an unavailable/declined LLM (deterministic skeleton)
            return ""
        return json.dumps(script, ensure_ascii=False)

    async def _fake_followup_complete(**_kwargs):
        rec.followup_calls += 1
        script = rec.scripts.get("followup_action")
        if script is None:
            return ""
        return json.dumps(script, ensure_ascii=False)

    monkeypatch.setattr("deeptutor.services.llm.factory.complete", _fake_factory_complete)
    monkeypatch.setattr("deeptutor.services.question_followup.complete", _fake_followup_complete)
    return rec
