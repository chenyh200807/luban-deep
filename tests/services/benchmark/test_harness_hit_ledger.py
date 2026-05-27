from __future__ import annotations

import pytest

from deeptutor.services.benchmark.harness_hit_ledger import (
    HarnessHit,
    append_hit,
    catch_rate_summary,
    load_ledger,
)


def _hit(gate: str, caught: bool, kind: str) -> HarnessHit:
    return HarnessHit(gate=gate, regression="r", caught=caught, kind=kind, date="2026-05-27")


def test_kind_is_validated() -> None:
    with pytest.raises(ValueError):
        HarnessHit(gate="g", regression="r", caught=True, kind="bogus", date="2026-05-27")


def test_catch_rate_separates_real_from_injected() -> None:
    hits = [
        _hit("g1", True, "injected"),
        _hit("g1", True, "real"),
        _hit("g2", False, "real"),
    ]
    s = catch_rate_summary(hits)
    assert s["injected_total"] == 1 and s["injected_caught"] == 1
    assert s["real_total"] == 2 and s["real_caught"] == 1
    assert s["real_catch_rate"] == 0.5
    assert s["by_gate"]["g1"] == {"caught": 2, "total": 2}
    assert s["by_gate"]["g2"] == {"caught": 0, "total": 1}


def test_empty_ledger_has_none_rates() -> None:
    s = catch_rate_summary([])
    assert s["real_catch_rate"] is None and s["injected_catch_rate"] is None


def test_append_and_load_round_trip(tmp_path) -> None:
    path = tmp_path / "ledger.json"
    append_hit(_hit("g", True, "real"), path)
    append_hit(_hit("g", False, "real"), path)
    hits = load_ledger(path)
    assert len(hits) == 2
    assert catch_rate_summary(hits)["real_catch_rate"] == 0.5


def test_committed_seed_ledger_is_loadable_and_teeth_proven() -> None:
    """The tracked seed ledger records this session's capability proofs."""
    hits = load_ledger()  # default path: eval/harness_hit_ledger.json
    summary = catch_rate_summary(hits)
    # Every seeded injected regression was caught (gates have teeth).
    assert summary["injected_total"] >= 5
    assert summary["injected_caught"] == summary["injected_total"]
    # Honest: no real incidents recorded yet.
    assert summary["real_total"] == 0
