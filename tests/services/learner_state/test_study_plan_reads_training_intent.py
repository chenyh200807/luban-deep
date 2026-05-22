"""Phase -1.C: study_plan reads from active training_intent.

The plan resolves the long-standing overlap where ``training_intent.py`` and
``study_plan.py`` could each invent a different "today's focus" for the same
learner. After Phase -1.C, ``training_intent`` is the sole prescription
authority; ``study_plan`` becomes a thin presenter that surfaces the same
intent in the home dashboard wording.
"""
from __future__ import annotations

from deeptutor.services.learner_state.study_plan import build_study_plan


def test_study_plan_focus_topic_is_derived_from_active_training_intent() -> None:
    """Plan's literal failing test: when an active intent exists with a
    concept_label, study_plan must adopt that label as focus_topic and
    declare ``source='training_intent'``. Even if weak_points point
    elsewhere, the intent wins."""
    plan = build_study_plan(
        focus_hint="auto",
        active_training_intent={"concept_label": "防火门耐火极限"},
        weak_points=["其它"],
    )

    assert plan["focus_topic"] == "防火门耐火极限"
    assert plan["source"] == "training_intent"


def test_study_plan_intent_concept_label_beats_explicit_focus_topic() -> None:
    """Authority order: explicit focus_topic arg is also a fallback; the
    intent's concept_label is the canonical prescription source."""
    plan = build_study_plan(
        focus_topic="临时章节",
        active_training_intent={"concept_label": "进度索赔"},
        weak_points=["其它"],
    )

    assert plan["focus_topic"] == "进度索赔"
    assert plan["source"] == "training_intent"


def test_study_plan_falls_back_to_weak_points_when_intent_has_no_concept() -> None:
    """An intent without a usable concept_label must not poison the plan;
    fallback proceeds to weak_points as before, and source reports
    ``weak_points`` so consumers can tell."""
    plan = build_study_plan(
        active_training_intent={"concept_label": ""},
        weak_points=["真实薄弱点"],
    )

    assert plan["focus_topic"] == "真实薄弱点"
    assert plan["source"] == "weak_points"


def test_study_plan_falls_back_to_weak_points_when_no_intent_passed() -> None:
    """Backward compat: callers that do not pass active_training_intent see
    the existing behavior; source still reports the truthful origin."""
    plan = build_study_plan(weak_points=["关键线路"])

    assert plan["focus_topic"] == "关键线路"
    assert plan["source"] == "weak_points"


def test_study_plan_source_when_only_hotspots_available() -> None:
    plan = build_study_plan(hotspots=["危大工程"])

    assert plan["focus_topic"] == "危大工程"
    assert plan["source"] == "hotspots"


def test_study_plan_source_when_explicit_focus_topic_only() -> None:
    plan = build_study_plan(focus_topic="进度索赔")

    assert plan["focus_topic"] == "进度索赔"
    assert plan["source"] == "focus_topic_arg"


def test_study_plan_source_default_when_nothing_available() -> None:
    plan = build_study_plan()

    # Existing behavior preserved: empty focus → coach copy.
    assert plan["focus_topic"] == "今天先稳住基础节奏"
    assert plan["source"] == "default"


def test_study_plan_ignores_non_dict_active_training_intent() -> None:
    """Defensive: callers might forward None or a malformed value through
    `home_personalization`; the planner must not crash."""
    plan = build_study_plan(active_training_intent=None, weak_points=["关键线路"])
    assert plan["focus_topic"] == "关键线路"
    assert plan["source"] == "weak_points"

    plan = build_study_plan(active_training_intent="not a dict", weak_points=["关键线路"])  # type: ignore[arg-type]
    assert plan["focus_topic"] == "关键线路"
    assert plan["source"] == "weak_points"
