"""P-1 whitelist gate: 未原子化 qid 100% 被拒 (§2.5① / §4 code-level red line).

The gate fails CLOSED: an empty / absent whitelist refuses every qid, and only a
qid explicitly marked ``status == "allowed"`` passes. This is the code-level
enforcement that a non-atomized qid can never enter runtime generation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.construction_grading.case_light_practice_contract import (
    WHITELIST_PATH,
    WhitelistError,
    assert_qid_allowed,
    load_whitelist,
)


def test_v0_placeholder_whitelist_is_empty():
    # The shipped P-1 placeholder is empty until双教研验收 passes.
    assert load_whitelist() == frozenset()


def test_non_whitelisted_qid_is_rejected():
    with pytest.raises(WhitelistError):
        assert_qid_allowed("2017::EXAM_UNATOMIZED::E0", whitelist=frozenset())


def test_absent_whitelist_file_fails_closed(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert load_whitelist(missing) == frozenset()
    with pytest.raises(WhitelistError):
        assert_qid_allowed("any::qid", whitelist=load_whitelist(missing))


def test_only_allowed_status_passes(tmp_path):
    wl = tmp_path / "wl.json"
    wl.write_text(
        json.dumps(
            {
                "entries": [
                    {"qid": "q_allowed", "status": "allowed"},
                    {"qid": "q_pending", "status": "pending"},
                    {"qid": "q_rejected", "status": "rejected"},
                ]
            }
        ),
        encoding="utf-8",
    )
    allowed = load_whitelist(wl)
    assert allowed == frozenset({"q_allowed"})

    assert_qid_allowed("q_allowed", whitelist=allowed)  # does not raise
    for blocked in ("q_pending", "q_rejected", "q_absent"):
        with pytest.raises(WhitelistError):
            assert_qid_allowed(blocked, whitelist=allowed)


def test_shipped_whitelist_path_is_the_supply_artifact():
    # Guard against the path drifting away from the register-before-use artifact.
    assert WHITELIST_PATH.name == "case_light_practice_whitelist.v0.json"
    assert WHITELIST_PATH.parent.name == "case_light_practice"
    assert Path(WHITELIST_PATH).exists(), "P-1 whitelist supply artifact must ship"
