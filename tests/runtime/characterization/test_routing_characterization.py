"""Routing characterization test — the behavior-preservation gate for the task #12 真闭包
migration (single canonical turn-relation/submission authority, contracts/turn.md §硬约束 24).

Freezes the observable routing decision (capability + metadata decision keys) for every
matrix row into golden/routing_decisions.json. Each 收口 step that moves WHERE a decision is
computed must keep this byte-identical; an unexplained diff blocks the PR.

Regenerate the golden (only on an intended, reviewed change):
    DEEPTUTOR_CHAR_UPDATE_GOLDEN=1 pytest tests/runtime/characterization/ -q
Never bulk-regenerate to silence a diff — review the per-row/per-key diff first.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from tests.runtime.characterization.routing_matrix import MATRIX
from tests.runtime.characterization.snapshot import capture_routing_decision

_GOLDEN = Path(__file__).parent / "golden" / "routing_decisions.json"


def _load_golden() -> dict:
    if not _GOLDEN.exists():
        return {}
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


def _run_row(row, llm_mocks) -> dict:
    llm_mocks.scripts["lifecycle_scene"] = row.lifecycle_script
    llm_mocks.scripts["followup_action"] = row.followup_script
    return asyncio.run(
        capture_routing_decision(
            message=row.message,
            context_state=row.context,
            config_overrides=row.config_overrides,
        )
    )


@pytest.mark.skipif(
    not os.getenv("DEEPTUTOR_CHAR_UPDATE_GOLDEN"),
    reason="golden regeneration only on explicit DEEPTUTOR_CHAR_UPDATE_GOLDEN=1",
)
def test_regenerate_golden(llm_mocks) -> None:
    golden = {}
    for row in MATRIX:
        golden[row.id] = _run_row(row, llm_mocks)
    _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN.write_text(
        json.dumps(golden, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("row", MATRIX, ids=lambda r: r.id)
def test_routing_decision_matches_golden(row, llm_mocks) -> None:
    if os.getenv("DEEPTUTOR_CHAR_UPDATE_GOLDEN"):
        pytest.skip("regenerating golden")
    golden = _load_golden()
    assert row.id in golden, (
        f"row {row.id!r} missing from golden — regenerate with DEEPTUTOR_CHAR_UPDATE_GOLDEN=1"
    )
    snap = _run_row(row, llm_mocks)
    assert snap == golden[row.id], (
        f"routing decision drifted for row {row.id!r} (gate: {row.gate}).\n"
        f"  expected: {golden[row.id]}\n  actual:   {snap}"
    )


@pytest.mark.parametrize("row", [r for r in MATRIX if r.tier == "A"], ids=lambda r: r.id)
def test_tier_a_rows_make_no_llm_call(row, llm_mocks) -> None:
    """Tier-A rows must be fully deterministic — neither LLM target may fire.

    Enforces turn.md §67/§72: a deterministic submission/relation gate must not be routed
    through the LLM. If a 收口 accidentally does so, this fails loudly.
    """
    _run_row(row, llm_mocks)
    assert llm_mocks.lifecycle_calls == 0 and llm_mocks.followup_calls == 0, (
        f"Tier-A row {row.id!r} reached the LLM "
        f"(lifecycle={llm_mocks.lifecycle_calls}, followup={llm_mocks.followup_calls})"
    )
