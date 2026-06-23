"""User-facing tool access policy."""

from __future__ import annotations

from collections.abc import Iterable


END_USER_TOOL_ALIASES = {
    "code_execute": "code_execution",
    "run_code": "code_execution",
}
# Tools allowed in untrusted end-user (student) chat flows.
#
# This is an allowlist, not a denylist: the TutorBot registry contains trusted
# operator tools such as filesystem and web_fetch tools. Those must not become
# student-facing simply because a caller omitted metadata.default_tools.
END_USER_ALLOWED_TOOLS = frozenset(
    {"rag", "web_search", "reason", "brainstorm", "paper_search", "geogebra", "geogebra_analysis"}
)

# Tools never exposed to untrusted end-user (student) chat flows.
# - code_execution / exec: arbitrary code/command execution (RCE surface).
# - spawn / team / cron: agent-orchestration tools. spawn has no per-call cap, so a
#   student prompt can drive many concurrent subagents (LLM-cost / resource DoS
#   amplification). team and cron are operator-facing, not student features.
#   Blocking here removes them from the tool definitions the model is shown.
END_USER_BLOCKED_TOOLS = frozenset(
    {"code_execution", "exec", "spawn", "team", "cron"}
)


def canonical_end_user_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    return END_USER_TOOL_ALIASES.get(normalized, normalized)


def is_end_user_tool_allowed(tool_name: str) -> bool:
    """Return whether a tool may be exposed to untrusted end-user chat flows."""
    normalized = canonical_end_user_tool_name(tool_name)
    return bool(normalized) and normalized in END_USER_ALLOWED_TOOLS


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
