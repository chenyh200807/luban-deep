from __future__ import annotations

from pathlib import Path

from scripts import check_git_worktree


def test_validate_git_worktree_accepts_aligned_git_view(monkeypatch) -> None:
    project_root = Path("/tmp/repo")

    def _fake_git_output(_project_root: Path, *args: str) -> str | None:
        if args == ("rev-parse", "--show-toplevel"):
            return str(project_root)
        if args == ("config", "--get", "core.worktree"):
            return str(project_root)
        raise AssertionError(args)

    monkeypatch.setattr(check_git_worktree, "_git_output", _fake_git_output)

    assert check_git_worktree.validate_git_worktree(project_root) == []


def test_validate_git_worktree_rejects_misaligned_git_view(monkeypatch) -> None:
    project_root = Path("/tmp/repo")
    other_root = Path("/tmp/other")

    def _fake_git_output(_project_root: Path, *args: str) -> str | None:
        if args == ("rev-parse", "--show-toplevel"):
            return str(other_root)
        if args == ("config", "--get", "core.worktree"):
            return str(other_root)
        raise AssertionError(args)

    monkeypatch.setattr(check_git_worktree, "_git_output", _fake_git_output)

    issues = check_git_worktree.validate_git_worktree(project_root)

    assert len(issues) == 2
    assert "git top-level mismatch" in issues[0]
    assert "git core.worktree mismatch" in issues[1]
