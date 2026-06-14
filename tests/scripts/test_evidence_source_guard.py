"""G4 — evidence_source emit-site register-before-use guard.

The guard cross-checks every hard-coded ``"evidence_source": "<literal>"`` against
``contracts/index.yaml:learning_state_inference.allowed_evidence_sources``. An
unregistered source would make ``learning_synthesis`` (which filters by source)
silently drop that learner-memory evidence.
"""

from __future__ import annotations

from pathlib import Path
import textwrap

from scripts.check_contract_guard import (
    collect_emitted_evidence_sources,
    evaluate_emitted_evidence_sources,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def _index(allowed: list[str]) -> str:
    rows = "\n".join(f"    - {value}" for value in allowed)
    return f"learning_state_inference:\n  allowed_evidence_sources:\n{rows}\n"


def test_passes_on_real_tree() -> None:
    ok, message = evaluate_emitted_evidence_sources()
    assert ok, message


def test_collect_finds_real_emit() -> None:
    found = collect_emitted_evidence_sources()
    assert "conversation_synthesis" in found
    assert any(
        "conversation_learning_evidence.py" in loc
        for loc in found["conversation_synthesis"]
    )


def test_registered_literal_passes(tmp_path: Path) -> None:
    _write(tmp_path / "contracts/index.yaml", _index(["construction_grading", "conversation_synthesis"]))
    _write(
        tmp_path / "deeptutor/services/construction_grading/emit.py",
        'EVENT = {"evidence_source": "construction_grading"}\n',
    )
    ok, message = evaluate_emitted_evidence_sources(tmp_path)
    assert ok, message
    assert "construction_grading" in message


def test_unregistered_literal_fails(tmp_path: Path) -> None:
    _write(tmp_path / "contracts/index.yaml", _index(["construction_grading", "conversation_synthesis", "assessment_testset"]))
    _write(
        tmp_path / "deeptutor/services/learner_state/emit.py",
        'EVENT = {"evidence_source": "bogus_source"}\n',
    )
    ok, message = evaluate_emitted_evidence_sources(tmp_path)
    assert not ok
    assert "bogus_source" in message
    assert "emit.py" in message


def test_empty_allowed_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path / "contracts/index.yaml", "learning_state_inference:\n  allowed_evidence_sources: []\n")
    _write(
        tmp_path / "deeptutor/services/learner_state/emit.py",
        'EVENT = {"evidence_source": "construction_grading"}\n',
    )
    ok, message = evaluate_emitted_evidence_sources(tmp_path)
    assert not ok
    assert "empty" in message or "unreadable" in message


def test_no_literal_passes(tmp_path: Path) -> None:
    _write(tmp_path / "contracts/index.yaml", _index(["construction_grading"]))
    _write(tmp_path / "deeptutor/services/learner_state/empty.py", "X = 1\n")
    ok, message = evaluate_emitted_evidence_sources(tmp_path)
    assert ok, message
    assert "no hard-coded" in message


def test_reader_and_passthrough_not_captured(tmp_path: Path) -> None:
    """Reader comparisons and ``str(...)`` pass-throughs must NOT count as emit."""
    _write(tmp_path / "contracts/index.yaml", _index(["construction_grading"]))
    _write(
        tmp_path / "deeptutor/services/learner_state/reader.py",
        '''
        def f(payload):
            if str(payload.get("evidence_source") or "") == "bogus_reader":
                return 1
            return {"evidence_source": str(payload.get("evidence_source") or "")}
        ''',
    )
    found = collect_emitted_evidence_sources(tmp_path)
    assert found == {}
    ok, _ = evaluate_emitted_evidence_sources(tmp_path)
    assert ok
