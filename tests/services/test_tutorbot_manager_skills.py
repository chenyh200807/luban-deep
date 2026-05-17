from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.services.tutorbot import manager as manager_module
from deeptutor.services.tutorbot.manager import TutorBotManager


def test_tutorbot_manager_skips_unreadable_builtin_skill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    builtin_skills = tmp_path / "builtin"
    good_dir = builtin_skills / "weather"
    bad_dir = builtin_skills / "github"
    good_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)
    good_file = good_dir / "SKILL.md"
    bad_file = bad_dir / "SKILL.md"
    good_file.write_text("# Weather\n", encoding="utf-8")
    bad_file.write_text("# GitHub\n", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == bad_file:
            raise PermissionError(f"Permission denied: '{path}'")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(manager_module, "_BUILTIN_SKILLS_DIR", builtin_skills)

    manager = TutorBotManager()
    monkeypatch.setattr(
        manager,
        "_path_service",
        SimpleNamespace(
            project_root=tmp_path,
            get_memory_dir=lambda: tmp_path / "data" / "memory",
        ),
    )

    manager._seed_skills("construction-exam-coach")

    workspace_skills = tmp_path / "data" / "tutorbot" / "construction-exam-coach" / "workspace" / "skills"
    assert (workspace_skills / "weather" / "SKILL.md").exists()
    assert not (workspace_skills / "github").exists()
