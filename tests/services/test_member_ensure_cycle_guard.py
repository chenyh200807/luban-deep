from __future__ import annotations

from deeptutor.services.member_console.service import MemberConsoleService


def _member(uid: str, merged_into: str = "") -> dict:
    return {"user_id": uid, "merged_into": merged_into, "external_auth_user_id": ""}


def test_ensure_member_breaks_two_node_merge_cycle() -> None:
    """A->B->A cyclic merge chain must not RecursionError (login 500)."""
    svc = MemberConsoleService()
    data = {"members": [_member("A", "B"), _member("B", "A")]}
    member = svc._ensure_member(data, "A")
    assert member["user_id"] in {"A", "B"}


def test_ensure_member_breaks_longer_merge_cycle() -> None:
    """A->B->C->A (3-cycle) must also terminate."""
    svc = MemberConsoleService()
    data = {"members": [_member("A", "B"), _member("B", "C"), _member("C", "A")]}
    member = svc._ensure_member(data, "A")
    assert member["user_id"] in {"A", "B", "C"}


def test_ensure_member_terminal_chain_resolves_to_canonical() -> None:
    """A->B (B terminal) resolves to the canonical terminal member B."""
    svc = MemberConsoleService()
    data = {"members": [_member("A", "B"), _member("B", "")]}
    member = svc._ensure_member(data, "A")
    assert member["user_id"] == "B"
