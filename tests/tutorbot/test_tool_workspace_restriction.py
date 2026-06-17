"""TutorBot filesystem/exec tools must be confined to the bot workspace.

The production TutorBot exposes read_file/write_file/exec to the model. Unless
access is confined to the bot's own workspace, a crafted instruction can read
server secrets (.env, keys) or system files. Confinement must therefore be the
*default* (fail-closed), not an opt-in a caller can forget to set.
"""

from __future__ import annotations

import pytest

from deeptutor.tutorbot.agent.tools.registry import build_base_tools
from deeptutor.tutorbot.config.schema import ExecToolConfig, ToolsConfig


def test_tools_config_restricts_to_workspace_by_default() -> None:
    assert ToolsConfig().restrict_to_workspace is True


@pytest.mark.asyncio
async def test_build_base_tools_blocks_filesystem_outside_workspace_by_default(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("API_KEY=topsecret")

    tools = build_base_tools(workspace, ExecToolConfig())
    result = await tools.get("read_file").execute(path=str(secret))

    assert "Error" in result
    assert "topsecret" not in result


@pytest.mark.asyncio
async def test_build_base_tools_blocks_exec_outside_workspace_by_default(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    tools = build_base_tools(workspace, ExecToolConfig())
    result = await tools.get("exec").execute(command="cat /etc/passwd")

    assert "guard" in result.lower() or "outside" in result.lower()


@pytest.mark.asyncio
async def test_build_base_tools_still_allows_in_workspace_access(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    note = workspace / "note.txt"
    note.write_text("lesson notes")

    tools = build_base_tools(workspace, ExecToolConfig())
    result = await tools.get("read_file").execute(path=str(note))

    assert "lesson notes" in result


def test_build_base_tools_omits_exec_when_disabled(tmp_path) -> None:
    """enable_exec=False removes the shell tool entirely (untrusted-student path)."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    tools = build_base_tools(workspace, ExecToolConfig(), enable_exec=False)

    assert "exec" not in tools
    # filesystem/read tools remain available
    assert "read_file" in tools


def test_build_base_tools_includes_exec_by_default(tmp_path) -> None:
    """Default (trusted operator) path keeps the shell tool."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    tools = build_base_tools(workspace, ExecToolConfig())

    assert "exec" in tools
