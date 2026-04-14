from __future__ import annotations

from scripts.check_contract_guard import evaluate_changed_files


def test_guard_allows_non_protected_changes() -> None:
    ok, message = evaluate_changed_files(["deeptutor/services/member_console/service.py"])
    assert ok is True
    assert "no protected contract domains changed" in message


def test_guard_rejects_turn_change_without_turn_tests() -> None:
    ok, message = evaluate_changed_files(["deeptutor/api/routers/unified_ws.py"])
    assert ok is False
    assert "[turn] protected files changed" in message


def test_guard_rejects_capability_sensitive_change_without_contract_surface() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/runtime/orchestrator.py",
            "tests/runtime/test_orchestrator_autoroute.py",
        ]
    )
    assert ok is False
    assert "[capability] contract-sensitive files changed" in message


def test_guard_accepts_rag_sensitive_change_with_contract_and_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/services/rag/service.py",
            "contracts/rag.md",
            "tests/services/rag/test_rag_pipelines.py",
        ]
    )
    assert ok is True
    assert "[rag] passed" in message


def test_guard_accepts_config_runtime_change_with_contract_and_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/services/config/provider_runtime.py",
            "contracts/config-runtime.md",
            "tests/services/config/test_provider_runtime.py",
        ]
    )
    assert ok is True
    assert "[config_runtime] passed" in message
