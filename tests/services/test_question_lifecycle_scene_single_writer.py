"""Single-authority invariant for ``question_lifecycle_scene`` (control-plane
collapse Task 2, first fact).

The canonical scene decider is the orchestrator's ``_record_lifecycle_decision``
(it stamps ``context.metadata["question_lifecycle_scene"]`` from
``resolve_question_lifecycle_scene_decision``). Every other registered scene
write-site is a projection / mirror, NOT a decider:

* ``turn_runtime._summarize_assistant_events`` only read-backs the scene from
  already-emitted events into the observation summary.
* ``deep_question.run`` only mirrors the canonical scene into ``trace_metadata``
  for observability (it reads via ``project_question_lifecycle_scene_from_metadata``
  and never derives one).

This test asserts the contract reflects that single-decider reality (byte-equal
across both index copies). It is RED while either projection is still labelled
with a decider role and GREEN once they are demoted to ``trace_projection``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INDEX_PATHS = (
    _REPO_ROOT / "contracts" / "index.yaml",
    _REPO_ROOT / "deeptutor" / "contracts" / "index.yaml",
)

_FIELD = "question_lifecycle_scene"
_DECIDER_ROLES = {"production_decider", "canonical_writer"}
_CANONICAL = ("deeptutor/runtime/orchestrator.py", "_record_lifecycle_decision")


def _scene_entries(index_path: Path) -> list[dict]:
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    entries = payload.get("control_plane_writers") or []
    return [e for e in entries if isinstance(e, dict) and e.get("field") == _FIELD]


def test_scene_has_exactly_one_decider_in_both_index_copies() -> None:
    for index_path in _INDEX_PATHS:
        entries = _scene_entries(index_path)
        assert entries, f"no {_FIELD} writers registered in {index_path}"
        deciders = [e for e in entries if e.get("allowed_role") in _DECIDER_ROLES]
        assert len(deciders) == 1, (
            f"{_FIELD} must have exactly one decider in {index_path}; "
            f"found {[(e['file'], e['symbol'], e['allowed_role']) for e in deciders]}"
        )
        decider = deciders[0]
        assert (decider["file"], decider["symbol"]) == _CANONICAL, (
            f"the sole {_FIELD} decider must be the orchestrator canonical writer, "
            f"got {(decider['file'], decider['symbol'])}"
        )


def test_scene_non_canonical_writers_are_trace_projection() -> None:
    for index_path in _INDEX_PATHS:
        for entry in _scene_entries(index_path):
            if (entry.get("file"), entry.get("symbol")) == _CANONICAL:
                continue
            assert entry.get("allowed_role") == "trace_projection", (
                f"non-canonical {_FIELD} writer {(entry['file'], entry['symbol'])} "
                f"must be trace_projection, got {entry.get('allowed_role')!r}"
            )
