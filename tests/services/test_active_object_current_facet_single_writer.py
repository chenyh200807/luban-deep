"""Single-authority invariant for the ``active_object`` *current facet*
(control-plane collapse Task 2, second fact).

``active_object`` has several legitimate, distinct facets, each with its own
authority — this test does NOT collapse them into one another:

* **current facet** (turn-start restore): the ``TurnRuntimeManager`` restore →
  stamp block reads the stored object, applies the task#14 ordinal-safe demote,
  and stamps the resolved object into the dispatch ``UnifiedContext.metadata``
  (``turn_runtime.py`` ``_run_turn``, restore block ~:4953-5108, dispatch stamp
  ``"active_object": active_object or {}`` ~:5668). This is the SOLE current-facet
  authority.
* **dispatch-prep facet** (orchestrator ``_prepare_*`` / ``_record_lifecycle_decision``):
  builds the submission/grading active object for the capability it is about to
  dispatch — a *different* facet, out of scope here.
* **next-object facet** (capability ``run`` result_payload): the object the
  capability *produces* for the next turn — also out of scope.

Every other ``active_object`` write in the current-facet pipeline is a
projection / mirror, NOT a current-facet decider:

* ``orchestrator._resolve_semantic_routing`` / ``_resolve_turn_semantic_decision``
  mirror the semantic-router's decision (``routing.active_object`` / a normalized
  copy) into the metadata the router reads — router is the authority.
* ``turn_runtime._enrich_result_question_authority_from_trace`` reads the
  already-decided object and only backfills ``state_snapshot`` from trace.
* ``turn_runtime._persist_and_publish`` is a persist-executor: it reads the
  capability output, merges it back into the prior active set (E8/E1 SEV-1 safety
  line), and persists — it self-describes as "NOT a second active_object writer".

This test asserts the contract reflects that single-current-facet-decider reality
(byte-equal across both index copies). It is RED while any current-facet
projection still carries a decider role and GREEN once they are demoted.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INDEX_PATHS = (
    _REPO_ROOT / "contracts" / "index.yaml",
    _REPO_ROOT / "deeptutor" / "contracts" / "index.yaml",
)

_FIELD = "active_object"
_DECIDER_ROLES = {"production_decider", "canonical_writer"}
_PROJECTION_ROLES = {"trace_projection", "adapter_projection", "compat_projection"}

# The sole current-facet authority: the turn-start restore → dispatch-stamp block.
_CANONICAL = ("deeptutor/services/session/turn_runtime.py", "_run_turn")

# The current-facet pipeline writers (turn_runtime restore/persist/enrich + the
# two orchestrator router-transition mirrors). Everything here must be either the
# sole canonical writer or a projection; none may be a competing decider.
_CURRENT_FACET_WRITERS = {
    ("deeptutor/services/session/turn_runtime.py", "_run_turn"),
    ("deeptutor/services/session/turn_runtime.py", "_persist_and_publish"),
    (
        "deeptutor/services/session/turn_runtime.py",
        "_enrich_result_question_authority_from_trace",
    ),
    ("deeptutor/runtime/orchestrator.py", "_resolve_semantic_routing"),
    ("deeptutor/runtime/orchestrator.py", "_resolve_turn_semantic_decision"),
}


def _active_object_entries(index_path: Path) -> list[dict]:
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    entries = payload.get("control_plane_writers") or []
    return [e for e in entries if isinstance(e, dict) and e.get("field") == _FIELD]


def _current_facet_entries(index_path: Path) -> list[dict]:
    return [
        e
        for e in _active_object_entries(index_path)
        if (e.get("file"), e.get("symbol")) in _CURRENT_FACET_WRITERS
    ]


def test_current_facet_has_exactly_one_decider_in_both_index_copies() -> None:
    for index_path in _INDEX_PATHS:
        entries = _current_facet_entries(index_path)
        assert entries, f"no current-facet {_FIELD} writers registered in {index_path}"
        deciders = [e for e in entries if e.get("allowed_role") in _DECIDER_ROLES]
        assert len(deciders) == 1, (
            f"current-facet {_FIELD} must have exactly one decider in {index_path}; "
            f"found {[(e['file'], e['symbol'], e['allowed_role']) for e in deciders]}"
        )
        decider = deciders[0]
        assert (decider["file"], decider["symbol"]) == _CANONICAL, (
            f"the sole current-facet {_FIELD} decider must be the turn_runtime "
            f"restore-block canonical writer, got {(decider['file'], decider['symbol'])}"
        )


def test_current_facet_non_canonical_writers_are_projections() -> None:
    for index_path in _INDEX_PATHS:
        for entry in _current_facet_entries(index_path):
            if (entry.get("file"), entry.get("symbol")) == _CANONICAL:
                continue
            assert entry.get("allowed_role") in _PROJECTION_ROLES, (
                f"non-canonical current-facet {_FIELD} writer "
                f"{(entry['file'], entry['symbol'])} must be a projection role "
                f"{sorted(_PROJECTION_ROLES)}, got {entry.get('allowed_role')!r}"
            )


def test_current_facet_canonical_writer_is_registered() -> None:
    # The canonical current-facet writer must actually appear in the allowlist
    # (guards against the restore block silently losing its registration).
    for index_path in _INDEX_PATHS:
        canonical = [
            e
            for e in _active_object_entries(index_path)
            if (e.get("file"), e.get("symbol")) == _CANONICAL
            and e.get("allowed_role") in _DECIDER_ROLES
        ]
        assert len(canonical) == 1, (
            f"the turn_runtime restore-block canonical {_FIELD} writer must be "
            f"registered exactly once as a decider in {index_path}; found {canonical}"
        )
