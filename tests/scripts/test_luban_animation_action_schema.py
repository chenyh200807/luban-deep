from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
LESSON = (
    ROOT
    / "artifacts/luban_case_family_assets/diagram_microlesson/"
    "J01_danger_work_expert_argumentation.lesson.json"
)
A01_LESSON = (
    ROOT
    / "artifacts/luban_case_family_assets/diagram_microlesson/"
    "A01_crane_lifting_safety.lesson.json"
)
VALIDATOR = (
    ROOT
    / "artifacts/luban_case_family_assets/diagram_microlesson/"
    "validate_animation_action_schema.py"
)
REGISTRY = ROOT / "contracts/schema_registry.yaml"

spec = importlib.util.spec_from_file_location("validate_animation_action_schema", VALIDATOR)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def load_j01() -> dict:
    return json.loads(LESSON.read_text(encoding="utf-8"))


def test_valid_j01_animation_actions_pass() -> None:
    errors = validator.validate_lesson_actions(load_j01())

    assert errors == []


def test_j01_m1_requires_actions_for_every_teach_beat() -> None:
    lesson = load_j01()

    errors = validator.validate_lesson_actions(lesson, require_actions=True)

    assert errors == []


def test_legacy_v0_without_actions_still_passes_when_not_required() -> None:
    lesson = load_j01()
    for beat in lesson["teach"]["beats"]:
        beat.pop("animation_action")

    errors = validator.validate_lesson_actions(lesson)

    assert errors == []


def test_historical_schema_alias_lesson_without_actions_passes_by_default() -> None:
    lesson = json.loads(A01_LESSON.read_text(encoding="utf-8"))

    errors = validator.validate_lesson_actions(lesson)

    assert errors == []


def test_teaching_animation_registered_as_content_asset_not_runtime_authority() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    contracts = {
        entry["name"]: entry
        for entry in registry.get("content_asset_contracts", [])
    }

    entry = contracts["luban_teaching_animation.v0"]
    assert entry["official_score_allowed"] is False
    assert entry["runtime_canonical"] is False
    assert entry["grading_authority"] is False
    assert "--require-actions" in entry["validation_scope"]


def test_card_bundle_manifest_registered_as_content_asset_not_runtime_authority() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    contracts = {
        entry["name"]: entry
        for entry in registry.get("content_asset_contracts", [])
    }

    entry = contracts["luban_card_bundle_manifest.v0"]
    assert entry["official_score_allowed"] is False
    assert entry["runtime_canonical"] is False
    assert entry["grading_authority"] is False
    assert "--require-practice" in entry["validation_scope"]


def test_unknown_action_type_fails() -> None:
    lesson = copy.deepcopy(load_j01())
    lesson["teach"]["beats"][0]["animation_action"][0]["type"] = "panorama"

    errors = validator.validate_lesson_actions(lesson)

    assert any("unknown action type" in error for error in errors)


@pytest.mark.parametrize("target", [None, "stage.intro", "data-id:"])
def test_missing_or_non_data_id_target_fails(target: str | None) -> None:
    lesson = copy.deepcopy(load_j01())
    action = lesson["teach"]["beats"][0]["animation_action"][0]
    if target is None:
        action.pop("target")
    else:
        action["target"] = target

    errors = validator.validate_lesson_actions(lesson)

    assert any("target must" in error for error in errors)
