"""M1 shadow consistency gate (零行为诊断价值核心 gate).

Cross-checks the explicit ``derive_question_lifecycle_state`` against INDEPENDENT
existing signals (NOT its own code — avoids circularity) over a corpus covering
every scenario: 出题 / 单题判 / 套题逐项混合 / open_world 待判 / 挂起 / 切题 / 非题型.

Independent oracles used:
  * ``question_followup._question_has_learner_attempt`` — the existing authority for
    "has the learner attempted this question" (PRESENTED ⟺ not attempted).
  * raw item fields (is_correct / construction_grading_result) for GRADED.
  * ``active_object_builder`` object_type family sets for 题型/非题型.

Asserts the derived FSM state agrees with these implicit signals. Special focus on
the two load-bearing dimensions a flat 4-state cannot hold: 套题 per-item (item2
GRADED while item1 PRESENTED) + open_world graded_pending (is_correct=None).
"""

from __future__ import annotations

from deeptutor.services.active_object_builder import (
    QUESTION_ACTIVE_OBJECT_TYPES,
    build_active_object_from_question_context,
    extract_question_context_from_active_object,
)
from deeptutor.services.semantic_router import (
    GUIDE_ACTIVE_OBJECT_TYPES,
    SESSION_ACTIVE_OBJECT_TYPES,
)
from deeptutor.services.question_followup import _question_has_learner_attempt
from deeptutor.services.question_turn_policy import (
    LIFECYCLE_ATTEMPTED,
    LIFECYCLE_GRADED,
    LIFECYCLE_PRESENTED,
    derive_question_lifecycle_state,
)


def _q(object_type: str, ctx: dict) -> dict:
    ao = build_active_object_from_question_context(ctx)
    assert ao is not None
    ao = dict(ao)
    ao["object_type"] = object_type
    ao["state_snapshot"] = dict(ao.get("state_snapshot") or {})
    return ao


def _item(qid: str, *, answer: str = "", is_correct=None, grading=None) -> dict:
    it = {"question_id": qid, "question": f"题{qid}", "question_type": "choice",
          "options": {"A": "x", "B": "y"}}
    if answer:
        it["user_answer"] = answer
    if is_correct is not None:
        it["is_correct"] = is_correct
    if grading is not None:
        it["construction_grading_result"] = grading
    return it


# 覆盖全场景 corpus: (label, active_object, suspended_stack)
def _corpus() -> list[tuple[str, dict, list]]:
    rows: list[tuple[str, dict, list]] = []
    # 出题未答 (single)
    rows.append(("present_single", _q("single_question", _item("q1")), []))
    # 单题已答待判 (single, answer no verdict)
    rows.append(("attempt_single", _q("single_question", _item("q1", answer="A")), []))
    # 单题已判
    rows.append(("graded_single", _q("single_question", _item("q1", answer="A", is_correct=True)), []))
    # 套题逐项混合: item1 graded, item2 presented (load-bearing)
    rows.append(("set_mixed", _q("question_set", {
        "question_id": "set", "question": "题组",
        "items": [_item("q1", answer="A", is_correct=True), _item("q2")],
    }), []))
    # 套题全判
    rows.append(("set_all_graded", _q("question_set", {
        "question_id": "set", "question": "题组",
        "items": [_item("q1", answer="A", is_correct=True), _item("q2", answer="B", is_correct=False)],
    }), []))
    # 套题全未答
    rows.append(("set_all_present", _q("question_set", {
        "question_id": "set", "question": "题组", "items": [_item("q1"), _item("q2")],
    }), []))
    # open_world 待判 (is_correct=None, attempted) (load-bearing graded_pending)
    rows.append(("open_world_pending", _q("open_world_question",
        {"question_id": "q1", "question": "论述?", "question_type": "essay", "user_answer": "作答"}), []))
    # open_world 已判 (grading_result present)
    rows.append(("open_world_graded", _q("open_world_question",
        {"question_id": "q1", "question": "论述?", "question_type": "essay",
         "user_answer": "作答", "construction_grading_result": {"score_awarded": 6.0}}), []))
    # 挂起: 题型 active + suspended stack
    rows.append(("suspended", _q("single_question", _item("q1")),
        [{"object_type": "question_set", "object_id": "set:Q9"}]))
    # 非题型
    for nt in sorted(GUIDE_ACTIVE_OBJECT_TYPES | SESSION_ACTIVE_OBJECT_TYPES | {"question_lifecycle_clarification"}):
        rows.append((f"non_question_{nt}",
            {"object_type": nt, "object_id": f"{nt}:x", "state_snapshot": {"topic": "x"}}, []))
    return rows


def _independent_item_graded(item: dict) -> bool:
    """Independent GRADED oracle from raw fields (not derive's code)."""
    if isinstance(item.get("is_correct"), bool):
        return True
    g = item.get("construction_grading_result")
    return isinstance(g, dict) and bool(g)


def test_shadow_consistency_over_full_corpus() -> None:
    for label, ao, stack in _corpus():
        state = derive_question_lifecycle_state(active_object=ao, suspended_object_stack=stack)
        object_type = str(ao.get("object_type") or "")

        # 1) 题型/非题型 family ⟺ derive None — cross-check vs active_object_builder sets.
        if object_type not in QUESTION_ACTIVE_OBJECT_TYPES:
            assert state is None, f"{label}: 非题型应返 None"
            continue
        assert state is not None, f"{label}: 题型应有 lifecycle_state"

        ctx = extract_question_context_from_active_object(ao) or {}

        # 2) attempted oracle (既有独立权威): 无 attempt → 全 PRESENTED; 有 → 至少一项非 PRESENTED.
        attempted = _question_has_learner_attempt(ctx)
        item_states = [it["state"] for it in state["items"]]
        if not attempted:
            assert state["state"] == LIFECYCLE_PRESENTED, f"{label}: 无作答应 PRESENTED"
            assert all(s == LIFECYCLE_PRESENTED for s in item_states), f"{label}: 无作答全 PRESENTED"
        else:
            assert any(s in (LIFECYCLE_ATTEMPTED, LIFECYCLE_GRADED) for s in item_states), \
                f"{label}: 有作答至少一项 ATTEMPTED/GRADED"

        # 3) per-item GRADED ⟺ 独立 raw-field oracle.
        raw_items = ctx.get("items") or []
        if raw_items:
            raw_by_id = {str(it.get("question_id") or "").strip(): it for it in raw_items}
            for entry in state["items"]:
                raw = raw_by_id.get(entry["question_id"], {})
                if _independent_item_graded(raw):
                    assert entry["state"] == LIFECYCLE_GRADED, f"{label}/{entry['question_id']}: 应 GRADED"
                else:
                    assert entry["state"] != LIFECYCLE_GRADED, f"{label}/{entry['question_id']}: 不应 GRADED"

        # 4) graded_pending ⟺ open_world + attempted + 无 verdict (load-bearing).
        if object_type == "open_world_question":
            single = (ctx.get("items") or [ctx])[0]
            expect_pending = (
                bool(str(single.get("user_answer") or "").strip())
                and not _independent_item_graded(single)
            )
            assert state["graded_pending"] is expect_pending, f"{label}: graded_pending 不符"
        else:
            assert state["graded_pending"] is False, f"{label}: 非 open_world graded_pending 必 False"

        # 5) suspended ⟺ stack identities.
        assert len(state["suspended"]) == len(stack), f"{label}: suspended 数不符"


def test_shadow_load_bearing_per_item_mixed() -> None:
    """套题: 一个 flat 状态装不下 item1 PRESENTED + item2 GRADED 同时 — 必须 per-item."""
    ao = _q("question_set", {
        "question_id": "set", "question": "题组",
        "items": [_item("q1"), _item("q2", answer="B", is_correct=False)],
    })
    state = derive_question_lifecycle_state(active_object=ao)
    by_id = {it["question_id"]: it["state"] for it in state["items"]}
    assert by_id["q1"] == LIFECYCLE_PRESENTED
    assert by_id["q2"] == LIFECYCLE_GRADED
    # summary 不能丢掉"还有题未答"的信息 — 混合态 summary=ATTEMPTED 非 GRADED.
    assert state["state"] == LIFECYCLE_ATTEMPTED


def test_shadow_load_bearing_open_world_graded_pending() -> None:
    pending = _q("open_world_question",
        {"question_id": "q1", "question": "论述?", "question_type": "essay", "user_answer": "作答"})
    graded = _q("open_world_question",
        {"question_id": "q1", "question": "论述?", "question_type": "essay",
         "user_answer": "作答", "construction_grading_result": {"score_awarded": 6.0}})
    assert derive_question_lifecycle_state(active_object=pending)["graded_pending"] is True
    assert derive_question_lifecycle_state(active_object=graded)["graded_pending"] is False
