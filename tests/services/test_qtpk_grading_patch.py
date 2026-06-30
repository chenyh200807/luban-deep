"""QTPK E8 grading-merge parity net (QTPK physical extraction plan, S2).

§6 SEV-1 套题防塌安全带 — ``_merge_grading_result_into_active_set`` is the
E8/E1 object-continuity safety line: a grading turn judges ONE item of a batch
question_set; the capability emits a single-question active_object. Persisting
that single object UNCONDITIONALLY would collapse the turn-start full set, so a
later "第1题"/"回到最开始" would bind to the lone surviving question (SEV-1
mis-grade / wrong recall). The merge keeps the SET alive by merging the judged
item back in (by question_id), and only a genuine switch replaces identity.

S2 extracts the **decision logic** (pure, no I/O) of that merge into the QTPK
pure function ``apply_grading_result_patch``. The store read of the prior
active_object stays in ``turn_runtime`` (transport/I/O); the prior is passed in.

This is the differential parity net that makes the S2 move *zero-behavior*:
for every E8 scenario the QTPK pure function's output must be byte-identical to
what the pre-move ``turn_runtime._merge_grading_result_into_active_set`` branch
logic produced for the same ``(prior, result, metadata)``.
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.active_object_builder import (
    build_active_object_from_question_context,
    extract_question_context_from_active_object,
    normalize_active_object,
    normalize_question_followup_context,
)
from deeptutor.services.question_turn_policy import (
    apply_grading_result_patch,
    grading_merge_needs_prior,
)


# ---------------------------------------------------------------------------
# Golden capture: the verbatim pre-move merge decision logic, parameterised on
# the prior active_object (which production reads from the store). This is the
# exact branch logic from turn_runtime._merge_grading_result_into_active_set
# (edfa333bd lines 6320-6383) with the store read replaced by the passed-in
# prior. It is the parity oracle: the QTPK pure function must match it.
# ---------------------------------------------------------------------------
def _legacy_merge_decision(
    *,
    prior_active_object: dict[str, Any] | None,
    result_active_object: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    result_ao = normalize_active_object(result_active_object)
    if result_ao is None:
        return result_active_object
    result_ctx = extract_question_context_from_active_object(result_ao)
    if result_ctx is None:
        return result_active_object
    result_items = result_ctx.get("items") or []
    if len(result_items) > 1:
        return result_active_object
    result_single = result_items[0] if result_items else result_ctx
    result_qid = str(result_single.get("question_id") or "").strip()

    prior_ao = prior_active_object
    normalized_prior_ao = normalize_active_object(prior_ao)
    prior_ctx = extract_question_context_from_active_object(prior_ao)
    prior_items = list((prior_ctx or {}).get("items") or [])
    decision = metadata.get("turn_semantic_decision")
    next_action = (
        str((decision or {}).get("next_action") or "").strip()
        if isinstance(decision, dict)
        else ""
    )
    result_mode = str(
        metadata.get("mode") or metadata.get("selected_mode") or ""
    ).strip().lower()
    is_grading_result = next_action == "route_to_grading" or result_mode == "grading"
    if len(prior_items) <= 1:
        if is_grading_result and prior_ctx is not None:
            prior_object_id = str((normalized_prior_ao or {}).get("object_id") or "").strip()
            result_object_id = str(result_ao.get("object_id") or "").strip()
            if prior_object_id and result_object_id and prior_object_id != result_object_id:
                return prior_ao if isinstance(prior_ao, dict) else result_active_object
        return result_active_object

    prior_qids = [str(it.get("question_id") or "").strip() for it in prior_items]

    # NOTE: the first branch is gated on ``is_grading_result`` to reflect the
    # 2026-06-30 bug fix (stale-active-set on a new question). question_id values
    # are NOT stable identities — they reset to q_1, q_2, … on every generation —
    # so a freshly generated single question recycles qid "q_1", which collides
    # with a prior batch's "q_1". WITHOUT this gate the merge mistook that genuine
    # NEW question (a non-grading generation turn) for a re-grade of set-item-1 and
    # retained the stale q_2/q_3 → a 3-item Frankenstein set → "我选B" then false-
    # rejected as ambiguous-multi. The merge only ever applied to single-item
    # GRADING turns (per this function's contract), so a generation turn must fall
    # through to the genuine-switch replace. This oracle is updated in lock-step
    # with ``apply_grading_result_patch`` so the parity net asserts the corrected
    # behavior.
    if is_grading_result and result_qid and result_qid in prior_qids:
        merged_items = [
            dict(result_single) if qid == result_qid else it
            for it, qid in zip(prior_items, prior_qids)
        ]
    elif next_action == "route_to_grading":
        merged_items = prior_items
    else:
        return result_active_object

    merged_ctx = dict(prior_ctx)
    merged_ctx["items"] = merged_items
    merged_ao = build_active_object_from_question_context(
        merged_ctx,
        previous_active_object=prior_ao,
        source_turn_id=str(metadata.get("turn_id") or "").strip() or None,
    )
    return merged_ao or result_active_object


# ---------------------------------------------------------------------------
# E8 differential corpus: each case fed to BOTH the legacy oracle and the QTPK
# pure function; outputs must be identical. Covers all E8 branches:
#   - 套题判一题不塌 (qid in prior set → merge judged item back, set survives)
#   - 单题判分 (prior was not a batch set → pass through unchanged)
#   - route_to_grading 不塌 (grading turn but qid not in set → keep prior set)
#   - 真切换替换 (genuine switch, not grading turn → replace)
# ---------------------------------------------------------------------------
def _set_active_object(qids: list[str]) -> dict[str, Any]:
    ctx = {
        "items": [
            {
                "question_id": qid,
                "question": f"题目 {qid}",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                "correct_answer": "A",
            }
            for qid in qids
        ]
    }
    return build_active_object_from_question_context(ctx)


def _single_active_object(qid: str, *, graded: bool = False) -> dict[str, Any]:
    item = {
        "question_id": qid,
        "question": f"题目 {qid}",
        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        "correct_answer": "A",
    }
    if graded:
        item["user_answer"] = "A"
    ctx = {**item}
    return build_active_object_from_question_context(ctx)


_E8_CORPUS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "set_item_graded_does_not_collapse",
        {
            "prior_active_object": _set_active_object(["q1", "q2", "q3"]),
            "result_active_object": _single_active_object("q2", graded=True),
            "metadata": {"turn_semantic_decision": {"next_action": "route_to_grading"}},
        },
    ),
    (
        "single_question_grading_passes_through",
        {
            "prior_active_object": _single_active_object("q1"),
            "result_active_object": _single_active_object("q1", graded=True),
            "metadata": {"turn_semantic_decision": {"next_action": "route_to_grading"}},
        },
    ),
    (
        "route_to_grading_qid_not_in_set_keeps_prior",
        {
            "prior_active_object": _set_active_object(["q1", "q2", "q3"]),
            "result_active_object": _single_active_object("qX", graded=True),
            "metadata": {"turn_semantic_decision": {"next_action": "route_to_grading"}},
        },
    ),
    (
        "genuine_switch_replaces",
        {
            "prior_active_object": _set_active_object(["q1", "q2", "q3"]),
            "result_active_object": _single_active_object("qNEW"),
            "metadata": {"turn_semantic_decision": {"next_action": "ask_followup"}},
        },
    ),
    (
        "result_is_set_left_unchanged",
        {
            "prior_active_object": _set_active_object(["q1", "q2"]),
            "result_active_object": _set_active_object(["q9", "q10"]),
            "metadata": {"turn_semantic_decision": {"next_action": "route_to_grading"}},
        },
    ),
    (
        "no_prior_set_grading_mode",
        {
            "prior_active_object": None,
            "result_active_object": _single_active_object("q1", graded=True),
            "metadata": {"selected_mode": "grading"},
        },
    ),
    (
        "single_prior_different_object_id_grading_keeps_prior",
        {
            "prior_active_object": _single_active_object("qA"),
            "result_active_object": _single_active_object("qB", graded=True),
            "metadata": {"mode": "grading"},
        },
    ),
    (
        "set_item_graded_mode_grading_no_decision",
        {
            "prior_active_object": _set_active_object(["q1", "q2"]),
            "result_active_object": _single_active_object("q1", graded=True),
            "metadata": {"selected_mode": "grading", "turn_id": "t-123"},
        },
    ),
    (
        # 2026-06-30 stale-active-set bug: a NEW single question generated after a
        # batch recycles qid "q1" (per-generation numbering, NOT a stable id), which
        # collides with the prior batch's "q1". This is a NON-grading generation turn
        # (route_to_generation), so the merge must NOT fire — the new question fully
        # replaces the stale set. Live DB evidence (run1 T3) showed the unfixed code
        # produced a 3-item Frankenstein [new q1, stale q2, stale q3].
        "new_generation_recycled_qid_replaces_stale_set",
        {
            "prior_active_object": _set_active_object(["q1", "q2", "q3"]),
            "result_active_object": _single_active_object("q1"),
            "metadata": {"turn_semantic_decision": {"next_action": "route_to_generation"}},
        },
    ),
)


def _ids(case: tuple[tuple[str, dict[str, Any]], ...]) -> list[str]:
    return [label for label, _ in case]


def _strip_wallclock(obj: Any) -> Any:
    """Drop the single wall-clock field stamped by build_active_object_*.

    ``build_active_object_from_question_context`` stamps ``last_touched_at`` with
    ``time.time()`` at call time (an inherent clock dependency shared by BOTH the
    legacy path and the QTPK path). The two calls happen microseconds apart, so
    that one field differs by sub-millisecond noise. It is NOT a behavior diff;
    normalise it out so the parity assertion compares the actual decision (object
    identity, items merged, version, entered_at, scope, state_snapshot).
    """
    if isinstance(obj, dict):
        return {k: _strip_wallclock(v) for k, v in obj.items() if k != "last_touched_at"}
    if isinstance(obj, list):
        return [_strip_wallclock(v) for v in obj]
    return obj


import pytest  # noqa: E402


@pytest.mark.parametrize("kwargs", [k for _, k in _E8_CORPUS], ids=_ids(_E8_CORPUS))
def test_qtpk_grading_patch_matches_legacy_merge(kwargs: dict[str, Any]) -> None:
    """QTPK apply_grading_result_patch == pre-move turn_runtime merge logic."""
    expected = _legacy_merge_decision(**kwargs)
    actual = apply_grading_result_patch(**kwargs)
    assert _strip_wallclock(actual) == _strip_wallclock(expected)


def test_new_generation_with_recycled_qid_replaces_stale_set() -> None:
    """A new single question generated after a batch must REPLACE the stale set.

    Root cause (2026-06-30): question_id is per-generation positional ("q1", "q2",
    …), NOT a stable identity. A freshly generated single question recycles "q1",
    colliding with the prior batch's "q1". On a NON-grading generation turn the
    merge must not fire — the new question is a genuine switch and replaces the set.
    Reproduces the exact live DB Frankenstein (run1 T3): prior set [q1,q2,q3] +
    new single q1 (网络计划) on route_to_generation → must become a SINGLE-item
    active_object, never [new q1, stale q2, stale q3].
    """
    prior = _set_active_object(["q1", "q2", "q3"])
    new_single = _single_active_object("q1")
    out = apply_grading_result_patch(
        prior_active_object=prior,
        result_active_object=new_single,
        metadata={"turn_semantic_decision": {"next_action": "route_to_generation"}},
    )
    normalized = normalize_active_object(out)
    assert normalized is not None
    # The new question fully replaces the stale batch: a single_question, NOT a
    # question_set still carrying q2/q3.
    assert normalized.get("object_type") == "single_question", normalized.get("object_type")
    assert str(normalized.get("object_id") or "") == "q1"
    # The disambiguation gate reads the question count via the SAME canonical
    # normalizer; it must see <= 1 item so "我选B" grades instead of being
    # false-rejected as ambiguous-multi-question.
    snapshot_ctx = normalize_question_followup_context(normalized.get("state_snapshot"))
    assert len((snapshot_ctx or {}).get("items") or []) <= 1


def test_qtpk_grading_patch_is_pure_no_store_access() -> None:
    """The QTPK pure function must not read any store: prior is passed in.

    Calling it with only plain dicts/None must succeed without any I/O object,
    proving the I/O (store.get_active_object) stayed behind in turn_runtime.
    """
    prior = _set_active_object(["q1", "q2"])
    result = _single_active_object("q1", graded=True)
    out = apply_grading_result_patch(
        prior_active_object=prior,
        result_active_object=result,
        metadata={"turn_semantic_decision": {"next_action": "route_to_grading"}},
    )
    # Set survives (3->2 items preserved): the graded q1 merged back, q2 intact.
    ctx = extract_question_context_from_active_object(out)
    assert ctx is not None
    qids = [str(it.get("question_id") or "") for it in (ctx.get("items") or [])]
    assert qids == ["q1", "q2"]


# ---------------------------------------------------------------------------
# grading_merge_needs_prior pre-check: byte-identical replica of the three
# early-return conditions at the TOP of the pre-move method (which ran BEFORE
# the store read). The pre-check returns True iff the original would have
# fallen through to the store read; False iff the original early-returned
# WITHOUT reading the store. This keeps the store read conditional in transport.
# ---------------------------------------------------------------------------
def test_needs_prior_false_when_result_not_normalizable() -> None:
    """Condition 1: normalize_active_object(result) is None → no store read."""
    # An object the canonical normalizer rejects (no resolvable question identity).
    assert normalize_active_object({}) is None
    assert grading_merge_needs_prior({}) is False


def test_needs_prior_false_when_result_has_no_question_context() -> None:
    """Condition 2: extract_question_context_from_active_object is None → no read."""
    # A normalizable active_object that yields no question context.
    ao = {"object_type": "open_chat", "object_id": "oc-1"}
    if normalize_active_object(ao) is not None:
        assert extract_question_context_from_active_object(ao) is None
    assert grading_merge_needs_prior(ao) is False


def test_needs_prior_false_when_result_is_a_set() -> None:
    """Condition 3: len(result_items) > 1 → result is itself a set → no read."""
    result_set = _set_active_object(["q9", "q10"])
    assert grading_merge_needs_prior(result_set) is False


def test_needs_prior_true_for_single_item_result() -> None:
    """None of the three early-returns fire → fall through to store read."""
    single = _single_active_object("q1", graded=True)
    assert grading_merge_needs_prior(single) is True


def test_needs_prior_matches_early_return_path_for_whole_corpus() -> None:
    """needs_prior is False exactly on the E8 cases whose result early-returns.

    Cross-check against the legacy oracle: when the result triggers one of the
    three top early-returns, the oracle returns ``result_active_object`` unchanged
    *and* never reads the prior — so needs_prior must be False. Otherwise True.
    """
    for label, kwargs in _E8_CORPUS:
        result = kwargs["result_active_object"]
        # Reconstruct the original top early-return predicate from the result alone.
        result_ao = normalize_active_object(result)
        result_ctx = (
            extract_question_context_from_active_object(result_ao)
            if result_ao is not None
            else None
        )
        result_items = (result_ctx or {}).get("items") or [] if result_ctx else []
        early_returns = (
            result_ao is None or result_ctx is None or len(result_items) > 1
        )
        assert grading_merge_needs_prior(result) is (not early_returns), label
