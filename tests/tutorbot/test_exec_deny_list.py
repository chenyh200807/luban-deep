"""ExecTool deny-list must match dangerous commands at command boundaries.

Two concrete problems with the pre-backport list:
  1. `dd of=/dev/sda` (raw-disk *write*) slipped past a pattern that only
     matched `dd if=`.
  2. A command name appearing as a quoted *argument* (echo "... rm -rf ...")
     was falsely blocked, because patterns matched anywhere in the string.

Fix: split the command on shell separators and anchor each dangerous pattern
to the start of a command segment, plus a small set of structural patterns
(fork bomb, raw-device redirect) checked across the whole command.

These tests use ExecTool() with restrict_to_workspace=False so they exercise
the deny-list alone, not the path guard.
"""

from __future__ import annotations

import pytest

from deeptutor.tutorbot.agent.tools.shell import ExecTool


def _guard(command: str) -> str | None:
    return ExecTool()._guard_command(command, "/tmp")


def test_dd_writing_raw_device_is_blocked() -> None:
    # Previously slipped past `\bdd\s+if=` because dd is followed by of=.
    assert _guard("dd of=/dev/sda if=/dev/zero") is not None


def test_command_name_inside_quoted_argument_is_not_blocked() -> None:
    # rm here is data inside echo's argument, not a command to run.
    assert _guard('echo "remember: rm -rf is dangerous"') is None


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -fr /tmp/x",
        "ls; rm -rf /tmp/x",            # second segment after ;
        "ls && shutdown now",           # after &&
        "true || reboot",               # after ||
        "cat x | mkfs.ext4 /dev/sdb",   # after pipe
        "$(rm -rf /)",                  # command substitution
        "format c:",
        "dd if=/dev/zero of=/dev/sda",
        "chmod -R 777 /",
    ],
)
def test_dangerous_commands_are_blocked(command: str) -> None:
    assert _guard(command) is not None


def test_fork_bomb_is_blocked() -> None:
    assert _guard(":(){ :|:& };:") is not None


@pytest.mark.parametrize(
    "command",
    [
        "python script.py",
        "ls -la",
        "pip install numpy",
        "echo hello > output.txt",
        "cat notes.md",
        "manim render scene.py",
    ],
)
def test_benign_commands_are_allowed(command: str) -> None:
    assert _guard(command) is None
