from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _git_output(project_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def validate_git_worktree(project_root: Path) -> list[str]:
    issues: list[str] = []
    root = project_root.resolve()

    top_level = _git_output(root, "rev-parse", "--show-toplevel")
    if top_level is None:
        issues.append(f"git top-level unavailable for {root}")
        return issues
    if Path(top_level).resolve() != root:
        issues.append(f"git top-level mismatch: expected {root}, got {Path(top_level).resolve()}")

    configured_worktree = _git_output(root, "config", "--get", "core.worktree")
    if configured_worktree is not None and Path(configured_worktree).expanduser().resolve() != root:
        issues.append(
            "git core.worktree mismatch: "
            f"expected {root}, got {Path(configured_worktree).expanduser().resolve()}"
        )

    return issues


def main() -> int:
    issues = validate_git_worktree(PROJECT_ROOT)
    if issues:
        for issue in issues:
            print(f"git-worktree: FAIL {issue}")
        return 1
    print(f"git-worktree: OK {PROJECT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
