"""Tests for the control-plane single-writer allowlist guard (Task 1, fast-mode
orchestrator simplification plan §14.A).

Strategy mirrors ``tests/scripts/test_check_harness_authority.py``: load the
guard script as a module and feed synthetic source strings to its internal
``_scan_source(rel, src)`` so each negative case is alias-proof and free of
docstring/comment false-positives. The dormant prospective arms
(``StreamEventType.ACK`` / ``stream.ack`` / ``first_useful_content``) are
asserted via synthetic source only — the real tree has zero hits of those, so
the live ``_scan_repo`` baseline must still come back clean (exit 0).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_guard():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_control_plane_writer_allowlist.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_control_plane_writer_allowlist_under_test", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # register so @dataclass module lookup resolves
    spec.loader.exec_module(module)
    return module


CHK = _load_guard()


# A file path that is NOT registered as any canonical writer, so any detected
# write-site there must be unregistered → red.
_UNREGISTERED_DEEP_QUESTION = "deeptutor/capabilities/deep_question.py"
_UNREGISTERED_TUTORBOT = "deeptutor/capabilities/tutorbot.py"
_UNREGISTERED_TURN_RUNTIME = "deeptutor/services/session/turn_runtime.py"
_CANONICAL_SEMANTIC_ROUTER = "deeptutor/services/semantic_router.py"


def _msgs(violations) -> str:
    return "\n".join(violations)


# --- Negative case 1: unregistered turn_semantic_decision metadata writer -----
def test_unregistered_turn_semantic_decision_metadata_writer_is_red() -> None:
    source = (
        "def _brand_new_helper(context):\n"
        '    context.metadata["turn_semantic_decision"] = {"relation": "x"}\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "unregistered turn_semantic_decision writer must be flagged"
    assert "turn_semantic_decision" in _msgs(violations)
    assert "_brand_new_helper" in _msgs(violations)


# --- Negative case 2: unregistered reveal_answers=True kwarg writer ------------
def test_unregistered_reveal_answers_true_kwarg_is_red() -> None:
    source = (
        "def _sneaky_reveal(self, context):\n"
        "    return self._build_visible_response(\n"
        "        context, reveal_answers=True, reveal_explanations=True\n"
        "    )\n"
    )
    violations = CHK._scan_source(_UNREGISTERED_TUTORBOT, source)
    assert violations, "unregistered reveal_answers=True writer must be flagged"
    assert "reveal" in _msgs(violations)


def test_reveal_answers_false_kwarg_is_not_flagged() -> None:
    # reveal_answers=False is a non-reveal (safe default); only True/non-False
    # reveal is a reveal write.
    source = (
        "def _safe(self, context):\n"
        "    return self._emit(context, reveal_answers=False, reveal_explanations=False)\n"
    )
    assert CHK._scan_source(_UNREGISTERED_TUTORBOT, source) == []


# --- Negative case 3: unregistered terminal stream.result(...) / RESULT --------
def test_unregistered_stream_result_terminal_writer_is_red() -> None:
    source = (
        "async def _emit_rogue_result(self, bus, context):\n"
        '    await bus.result({"response": "..."}, source="rogue")\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "unregistered terminal stream.result writer must be flagged"
    assert "result" in _msgs(violations)


def test_unregistered_stream_event_type_result_is_red() -> None:
    source = (
        "async def _emit_rogue(self, bus):\n"
        "    await bus.emit(StreamEvent(type=StreamEventType.RESULT, source='rogue'))\n"
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "unregistered StreamEventType.RESULT writer must be flagged"


# --- Negative case 4a: answer/score smuggled into bus.progress(...) ------------
def test_score_smuggled_into_progress_metadata_is_red() -> None:
    source = (
        "async def _leak_via_progress(self, bus):\n"
        '    await bus.progress("scoring...", metadata={"score": 4})\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "score smuggled through progress frame must be flagged"
    assert "progress" in _msgs(violations)


# --- Negative case 4b: route/current-object via dormant StreamEventType.ACK ----
def test_route_smuggled_into_ack_frame_is_red_dormant_arm() -> None:
    # ACK does not exist in the live enum (dormant prospective arm); the guard
    # logic must still flag it when fed synthetic source.
    source = (
        "async def _leak_via_ack(self, bus):\n"
        "    await bus.emit(StreamEvent(type=StreamEventType.ACK,\n"
        '        metadata={"route_capability": "deep_question"}))\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "ACK contentful frame must be flagged (dormant arm)"
    assert "ack" in _msgs(violations).lower()


def test_stream_ack_method_call_is_red_dormant_arm() -> None:
    source = (
        "async def _leak(self, bus):\n"
        '    await bus.ack({"current_object": "q1"})\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "stream.ack(...) must be flagged (dormant arm)"
    assert "ack" in _msgs(violations).lower()


# --- Negative case 4c: terminal metadata via dormant first_useful_content ------
def test_terminal_metadata_in_first_useful_content_is_red_dormant_arm() -> None:
    source = (
        "def _stamp(metadata):\n"
        '    metadata["first_useful_content"] = {"grading_key": "B"}\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "first_useful_content writer must be flagged (dormant arm)"
    assert "first_useful_content" in _msgs(violations)


# --- Case 5: docstring / comment mention must not be a false positive ----------
def test_docstring_and_comment_mentions_are_not_false_positives() -> None:
    source = (
        '"""This helper does NOT write metadata["turn_semantic_decision"]; it '
        "reads the canonical one. It also never sets reveal_answers=True or "
        'StreamEventType.RESULT or first_useful_content."""\n'
        "# build_turn_semantic_decision is the canonical writer; do not re-call it.\n"
        "# bus.result(...) and bus.ack(...) are mentioned only in this comment.\n"
        "def f(context):\n"
        '    return context.metadata.get("turn_semantic_decision")\n'
    )
    assert CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source) == []


# --- Case 6: registered canonical writer is not flagged ------------------------
def test_registered_canonical_semantic_writer_passes() -> None:
    # build_turn_semantic_decision in semantic_router.py is the canonical writer.
    source = (
        "def build_turn_semantic_decision(relation, next_action):\n"
        '    return {"relation": relation, "next_action": next_action}\n'
    )
    assert CHK._scan_source(_CANONICAL_SEMANTIC_ROUTER, source) == []


# --- Case 7: the real tree baseline is clean (all sites allowlisted) -----------
def test_real_repo_scan_only_has_allowlisted_sites() -> None:
    violations = CHK._scan_repo()
    assert violations == [], (
        "real-tree control-plane write-sites must all be allowlisted "
        "(register-before-use baseline):\n" + _msgs(violations)
    )


# --- Case 8: runtime recomputes active_object from message/content -------------
def test_turn_runtime_active_object_recompute_is_red() -> None:
    # TurnRuntimeManager may only restore/persist active_object; recomputing it
    # from message/content is a runtime business inference.
    source = (
        "class TurnRuntimeManager:\n"
        "    def _recompute(self, context, message):\n"
        '        if "选" in message:\n'
        '            context.metadata["active_object"] = {"id": "guessed"}\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_TURN_RUNTIME, source)
    assert violations, "runtime active_object recompute must be flagged"
    assert "active_object" in _msgs(violations)


# --- Case 9: fat kernel reads scene then overrides route ----------------------
def test_fat_kernel_reads_scene_then_writes_route_is_red() -> None:
    # Enclosing symbol is a NEW method (not the allowlisted `run`), so the
    # route override is an unregistered fat-kernel writer.
    source = (
        "class DeepQuestionCapability:\n"
        "    def _fat_override(self, context):\n"
        '        scene = context.metadata["question_lifecycle_scene"]\n'
        "        if scene == 'mcq_grading':\n"
        '            context.metadata["turn_semantic_decision"] = {"relation": "y"}\n'
    )
    violations = CHK._scan_source(_UNREGISTERED_DEEP_QUESTION, source)
    assert violations, "fat-kernel route override must be flagged"
    assert "turn_semantic_decision" in _msgs(violations)


# --- Allowlist integrity / fail-closed ----------------------------------------
def test_allowlist_loads_and_is_nonempty() -> None:
    entries = CHK._load_allowlist()
    assert entries, "control_plane_writers allowlist must be present and non-empty"


def test_both_contracts_allowlist_blocks_are_byte_equal() -> None:
    ok, message = CHK.evaluate_contracts_allowlist_parity()
    assert ok, message


def test_check_mode_exit_code_is_zero_on_clean_tree() -> None:
    assert CHK.main(["--check"]) == 0
