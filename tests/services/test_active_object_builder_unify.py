"""Control-plane Task 2: active_object builder/normalizer unification.

Two builder/normalizer pairs historically diverged on identity口径:

* ``deeptutor/services/semantic_router.py``     (SR-path: orchestrator / deep_question /
  tutorbot produce the *next* active_object)
* ``deeptutor/services/session/sqlite_store.py`` (SS-path: turn_runtime restore / persist
  produce the *current* active_object)

The divergence (object_id derivation for multi-item sets, the missing
``open_world_question`` type on the SS-path, and string-vs-float timestamps)
caused follow-up (回指) mis-binding: the same question set restored on the SS
side and re-derived on the SR side produced *different* ``object_id`` values,
so ``_same_active_object`` returned ``False`` and the turn was routed as a
switch (SEV-1).

These tests pin a SINGLE canonical identity口径 across both paths. They fail
RED before the unification (two paths disagree) and pass GREEN after both paths
delegate to the canonical builder.
"""

from __future__ import annotations

from typing import Any

import deeptutor.services.semantic_router as sr
import deeptutor.services.session.sqlite_store as ss


# --- fixtures: question contexts covering single / set / parent_quiz / open_world ----------


def _single_question_ctx() -> dict[str, Any]:
    return {
        "question_id": "Q1",
        "question": "单题：现浇混凝土水平运输设备有哪些？",
        "question_type": "case",
    }


def _question_set_ctx() -> dict[str, Any]:
    return {
        "question": "多题套：本套含两道题",
        "items": [
            {"question_id": "Q1", "question": "第一题"},
            {"question_id": "Q2", "question": "第二题"},
        ],
    }


def _question_set_with_parent_ctx() -> dict[str, Any]:
    return {
        "question": "多题套（带 parent_quiz_session_id）",
        "parent_quiz_session_id": "QUIZ-7",
        "items": [
            {"question_id": "Q1", "question": "第一题"},
            {"question_id": "Q2", "question": "第二题"},
        ],
    }


def _question_set_with_set_level_id_ctx() -> dict[str, Any]:
    return {
        "question_id": "quiz_old",  # set-level id (no parent_quiz_session_id)
        "question": "多题套（带 set-level question_id）",
        "items": [
            {"question_id": "q1", "question": "第一题"},
            {"question_id": "q2", "question": "第二题"},
        ],
    }


def _open_world_ctx() -> dict[str, Any]:
    return {
        "question_id": "OW1",
        "question": "开放世界变式题：source-backed 变式卡",
        "question_type": "case",
    }


# --- helpers ----------------------------------------------------------------------------------


def _sr_build(ctx: dict[str, Any], **kw: Any) -> dict[str, Any] | None:
    return sr.build_active_object_from_question_context(ctx, **kw)


def _ss_build(ctx: dict[str, Any], **kw: Any) -> dict[str, Any] | None:
    return ss.build_active_object_from_question_context(ctx, **kw)


# --- comparison tests: SR-path vs SS-path must produce the SAME identity ----------------------


def test_single_question_identity_matches_across_paths() -> None:
    ctx = _single_question_ctx()
    sr_ao = _sr_build(ctx)
    ss_ao = _ss_build(ctx)
    assert sr_ao is not None and ss_ao is not None
    assert sr_ao["object_id"] == ss_ao["object_id"] == "Q1"
    assert sr_ao["object_type"] == ss_ao["object_type"] == "single_question"


def test_question_set_object_id_matches_across_paths() -> None:
    """The SEV-1: SR derived ``question_set:Q1`` while SS derived ``question_set:Q1|Q2``."""
    ctx = _question_set_ctx()
    sr_ao = _sr_build(ctx)
    ss_ao = _ss_build(ctx)
    assert sr_ao is not None and ss_ao is not None
    assert sr_ao["object_type"] == ss_ao["object_type"] == "question_set"
    assert sr_ao["object_id"] == ss_ao["object_id"], (
        f"object_id diverged: SR={sr_ao['object_id']!r} SS={ss_ao['object_id']!r}"
    )


def test_parent_quiz_session_id_wins_across_paths() -> None:
    """parent_quiz_session_id must drive object_id identically on both paths."""
    ctx = _question_set_with_parent_ctx()
    sr_ao = _sr_build(ctx)
    ss_ao = _ss_build(ctx)
    assert sr_ao is not None and ss_ao is not None
    assert sr_ao["object_id"] == ss_ao["object_id"] == "QUIZ-7"
    assert sr_ao["object_type"] == ss_ao["object_type"] == "question_set"


def test_set_level_question_id_wins_over_joined_items_across_paths() -> None:
    """A multi-item set carrying a set-level top-level question_id keeps that id
    (migration-stable) identically on both paths, instead of synthesizing one."""
    ctx = _question_set_with_set_level_id_ctx()
    sr_ao = _sr_build(ctx)
    ss_ao = _ss_build(ctx)
    assert sr_ao is not None and ss_ao is not None
    assert sr_ao["object_type"] == ss_ao["object_type"] == "question_set"
    assert sr_ao["object_id"] == ss_ao["object_id"] == "quiz_old"


def test_open_world_question_type_survives_on_both_paths() -> None:
    """SS-path historically lacked ``open_world_question`` and silently downgraded it."""
    ctx = _open_world_ctx()
    sr_ao = _sr_build(ctx, object_type_override="open_world_question")
    ss_ao = _ss_build(ctx, object_type="open_world_question")
    assert sr_ao is not None and ss_ao is not None
    assert sr_ao["object_type"] == "open_world_question"
    assert ss_ao["object_type"] == "open_world_question", (
        f"SS downgraded open_world_question -> {ss_ao['object_type']!r}"
    )
    assert sr_ao["object_id"] == ss_ao["object_id"] == "OW1"


def test_timestamp_type_is_float_on_both_paths() -> None:
    """entered_at / last_touched_at must be time-aware floats (no string化 data loss)."""
    for build in (_sr_build, _ss_build):
        ao = build(_single_question_ctx())
        assert ao is not None
        assert isinstance(ao["entered_at"], float), (
            f"{build.__name__} entered_at not float: {ao['entered_at']!r}"
        )
        assert isinstance(ao["last_touched_at"], float), (
            f"{build.__name__} last_touched_at not float: {ao['last_touched_at']!r}"
        )
        assert ao["entered_at"] > 0 and ao["last_touched_at"] > 0


def test_version_bump_semantics_match_across_paths() -> None:
    """Same-identity re-build bumps version; new identity resets to 1 — both paths."""
    ctx = _single_question_ctx()
    sr_first = _sr_build(ctx)
    ss_first = _ss_build(ctx)
    assert sr_first is not None and ss_first is not None
    assert sr_first["version"] == ss_first["version"] == 1

    sr_second = _sr_build(ctx, previous_active_object=sr_first)
    ss_second = _ss_build(ctx, previous_active_object=ss_first)
    assert sr_second is not None and ss_second is not None
    assert sr_second["version"] == ss_second["version"] == 2


# --- round-trip / build==normalize identity ---------------------------------------------------


def test_round_trip_build_then_normalize_is_identity_sr() -> None:
    for ctx in (_single_question_ctx(), _question_set_with_parent_ctx()):
        built = sr.build_active_object_from_question_context(ctx)
        assert built is not None
        renorm = sr.normalize_active_object(built)
        assert renorm is not None
        assert renorm["object_id"] == built["object_id"]
        assert renorm["object_type"] == built["object_type"]


def test_round_trip_build_then_normalize_is_identity_ss() -> None:
    for ctx in (_single_question_ctx(), _question_set_with_parent_ctx()):
        built = ss.build_active_object_from_question_context(ctx)
        assert built is not None
        renorm = ss.normalize_active_object(built)
        assert renorm is not None
        assert renorm["object_id"] == built["object_id"]
        assert renorm["object_type"] == built["object_type"]


# --- the SEV-1 itself: current(restore=SS) vs next(capability=SR) -> _same_active_object -------


def test_current_restore_equals_next_capability_same_active_object() -> None:
    """Simulate: SS restores the current set; SR re-derives the next set for the same input.

    Before unification their object_ids diverge and ``_same_active_object`` returns
    False (turn routed as a switch = 回指错绑). After unification they must match.
    """
    for ctx in (
        _question_set_ctx(),
        _question_set_with_parent_ctx(),
        _question_set_with_set_level_id_ctx(),
        _single_question_ctx(),
    ):
        current_ss = ss.build_active_object_from_question_context(ctx)  # restore side
        next_sr = sr.build_active_object_from_question_context(ctx)  # capability side
        assert current_ss is not None and next_sr is not None
        assert sr._same_active_object(current_ss, next_sr) is True, (
            f"_same_active_object False for ctx items="
            f"{[i.get('question_id') for i in (ctx.get('items') or [])] or ctx.get('question_id')}; "
            f"current(SS)={current_ss['object_id']!r} next(SR)={next_sr['object_id']!r}"
        )


# --- migration safety: preserve-when-passed (existing persisted object_id not re-formatted) ----


def test_preserve_object_id_when_passed_sr() -> None:
    """An existing persisted object_id (legacy format) must NOT be re-derived."""
    ctx = _question_set_ctx()
    legacy = sr.build_active_object_from_question_context(ctx)
    assert legacy is not None
    legacy_with_old_id = dict(legacy, object_id="legacy::question_set::old-format")
    renorm = sr.normalize_active_object(legacy_with_old_id)
    assert renorm is not None
    assert renorm["object_id"] == "legacy::question_set::old-format"


def test_preserve_object_id_when_passed_ss() -> None:
    ctx = _question_set_ctx()
    built = ss.build_active_object_from_question_context(
        ctx, object_id="legacy::question_set::old-format"
    )
    assert built is not None
    assert built["object_id"] == "legacy::question_set::old-format"
    renorm = ss.normalize_active_object(
        dict(built, object_id="legacy::question_set::old-format")
    )
    assert renorm is not None
    assert renorm["object_id"] == "legacy::question_set::old-format"
