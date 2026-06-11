"""User-facing tool access policy."""

from __future__ import annotations

from collections.abc import Iterable


END_USER_TOOL_ALIASES = {
    "code_execute": "code_execution",
    "run_code": "code_execution",
}
END_USER_BLOCKED_TOOLS = frozenset({"code_execution", "exec"})


def canonical_end_user_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    return END_USER_TOOL_ALIASES.get(normalized, normalized)


def is_end_user_tool_allowed(tool_name: str) -> bool:
    """Return whether a tool may be exposed to untrusted end-user chat flows."""
    normalized = canonical_end_user_tool_name(tool_name)
    return bool(normalized) and normalized not in END_USER_BLOCKED_TOOLS


def filter_end_user_tools(tool_names: Iterable[str]) -> list[str]:
    """Filter tool names while preserving order and removing duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for item in tool_names:
        name = str(item or "").strip()
        if not is_end_user_tool_allowed(name) or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result
