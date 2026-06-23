"""End-user tool access policy — orchestration/RCE tools must never reach students."""

from __future__ import annotations

from deeptutor.services.security.tool_access import (
    END_USER_ALLOWED_TOOLS,
    END_USER_BLOCKED_TOOLS,
    filter_end_user_tools,
    is_end_user_tool_allowed,
)


def test_rce_and_orchestration_tools_blocked_for_end_users() -> None:
    for blocked in ("code_execution", "exec", "spawn", "team", "cron"):
        assert blocked in END_USER_BLOCKED_TOOLS
        assert is_end_user_tool_allowed(blocked) is False


def test_filter_strips_blocked_keeps_safe_tools_in_order() -> None:
    given = ["read_file", "spawn", "web_search", "exec", "team", "rag", "cron"]
    assert filter_end_user_tools(given) == ["web_search", "rag"]


def test_end_user_tool_policy_is_explicit_allowlist() -> None:
    assert {"rag", "web_search", "reason", "brainstorm", "paper_search"}.issubset(
        END_USER_ALLOWED_TOOLS
    )
    for trusted_operator_tool in ("read_file", "write_file", "edit_file", "list_dir", "web_fetch"):
        assert is_end_user_tool_allowed(trusted_operator_tool) is False


def test_aliases_resolve_to_blocked_code_execution() -> None:
    assert is_end_user_tool_allowed("run_code") is False
    assert is_end_user_tool_allowed("code_execute") is False
