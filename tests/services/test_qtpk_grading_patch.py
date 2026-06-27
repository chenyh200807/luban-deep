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
)
from deeptutor.services.question_turn_policy import apply_grading_result_patch


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

    if result_qid and result_qid in prior_qids:
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
