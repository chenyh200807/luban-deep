#!/usr/bin/env python3
"""Validate presentation-only action metadata for luban_teaching_animation.v0.

This is a tiny compile-artifact guard for beat-level ``animation_action`` metadata.
It does not validate knowledge facts, scoring policy, renderer behavior, or official
answer authority.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "luban_teaching_animation.v0"
ALLOWED_ACTION_TYPES = frozenset({"camera", "highlight", "reveal", "keycard"})
TARGET_PREFIX = "data-id:"


def lesson_schema_id(lesson: dict[str, Any]) -> Any:
    """Return the v0 schema id, accepting the historical `schema` alias."""
    return lesson.get("schema_version") or lesson.get("schema")


def validate_lesson_actions(lesson: dict[str, Any], *, require_actions: bool = False) -> list[str]:
    """Return deterministic schema errors for beat-level animation actions."""
    errors: list[str] = []

    schema_id = lesson_schema_id(lesson)
    if schema_id != SCHEMA_VERSION:
        errors.append(
            f"schema_version/schema must be {SCHEMA_VERSION!r}, got {schema_id!r}"
        )

    beats = (lesson.get("teach") or {}).get("beats")
    if not isinstance(beats, list) or not beats:
        return errors + ["teach.beats must be a non-empty list"]

    for beat_index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            errors.append(f"teach.beats[{beat_index}] must be an object")
            continue

        beat_id = str(beat.get("id") or beat_index)
        actions = beat.get("animation_action")
        if not isinstance(actions, list) or not actions:
            if require_actions:
                errors.append(f"teach beat {beat_id!r} must define non-empty animation_action[]")
            continue

        for action_index, action in enumerate(actions):
            path = f"teach beat {beat_id!r} animation_action[{action_index}]"
            if not isinstance(action, dict):
                errors.append(f"{path} must be an object")
                continue

            action_type = action.get("type")
            if action_type not in ALLOWED_ACTION_TYPES:
                errors.append(
                    f"{path} has unknown action type {action_type!r}; "
                    f"allowed={sorted(ALLOWED_ACTION_TYPES)}"
                )

            target = action.get("target")
            if not isinstance(target, str):
                errors.append(f"{path} target must be a string starting with {TARGET_PREFIX!r}")
                continue
            if not target.startswith(TARGET_PREFIX) or not target[len(TARGET_PREFIX) :].strip():
                errors.append(
                    f"{path} target must start with {TARGET_PREFIX!r} and include a non-empty id"
                )

    return errors


def validate_path(path: Path) -> list[str]:
    return validate_lesson_actions(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    require_actions = "--require-actions" in args
    paths = [arg for arg in args if arg != "--require-actions"]
    if len(paths) != 1:
        print("usage: validate_animation_action_schema.py [--require-actions] <lesson.json>", file=sys.stderr)
        return 2

    path = Path(paths[0])
    lesson = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_lesson_actions(lesson, require_actions=require_actions)
    if errors:
        print(f"{path.name}: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"{path.name}: PASS animation_action schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
