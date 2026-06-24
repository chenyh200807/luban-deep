"""Regression: `always: false` skills must NOT be force-injected every turn.

Root-cause bug: ``SkillsLoader.get_skill_metadata`` used a simple line-based
YAML parser that stored every value as a string, so ``always: false`` became
the string ``"false"``. A non-empty string is truthy in Python, so
``get_always_skills`` treated every ``always: false`` skill as always-on and
injected all of them into the per-turn context (defeating on-demand loading
and crowding the prompt with case-grading + lecture + knowledge-base + ...).
"""
from __future__ import annotations

from pathlib import Path

from deeptutor.tutorbot.agent.skills import SkillsLoader


def _write_skill(skills_root: Path, name: str, always: str) -> None:
    d = skills_root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "test skill {name}"\nalways: {always}\n---\n# {name}\n',
        encoding="utf-8",
    )


def _loader(tmp_path: Path) -> SkillsLoader:
    return SkillsLoader(workspace=tmp_path, builtin_skills_dir=tmp_path / "no-builtin")


def test_always_false_skill_excluded_from_always_list(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, "always-on", "true")
    _write_skill(skills_root, "always-off", "false")

    always = _loader(tmp_path).get_always_skills()

    assert "always-on" in always
    assert "always-off" not in always


def test_get_skill_metadata_coerces_bool_literals(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, "always-off", "false")
    _write_skill(skills_root, "always-on", "true")

    loader = _loader(tmp_path)

    assert loader.get_skill_metadata("always-off")["always"] is False
    assert loader.get_skill_metadata("always-on")["always"] is True


def test_string_values_stay_strings(tmp_path: Path) -> None:
    """Non-boolean frontmatter values must remain untouched strings."""
    skills_root = tmp_path / "skills"
    d = skills_root / "s"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        '---\nname: s\ndescription: "hello"\nstatus: candidate\nalways: false\n---\n# s\n',
        encoding="utf-8",
    )
    meta = _loader(tmp_path).get_skill_metadata("s")
    assert meta["description"] == "hello"
    assert meta["status"] == "candidate"
    assert meta["always"] is False
