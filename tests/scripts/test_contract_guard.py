from __future__ import annotations

import subprocess

from scripts.check_contract_guard import evaluate_changed_files, resolve_changed_files


def test_guard_allows_non_protected_changes() -> None:
    ok, message = evaluate_changed_files(["README.md"])
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


def test_resolve_changed_files_defaults_to_current_candidate(monkeypatch) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        commands.append(tuple(command))
        stdout_by_command = {
            ("git", "diff", "--name-only", "--cached"): "staged.py\nshared.py\n",
            ("git", "diff", "--name-only"): "unstaged.py\nshared.py\n",
            ("git", "ls-files", "--others", "--exclude-standard"): "untracked.py\n",
        }
        return subprocess.CompletedProcess(command, 0, stdout=stdout_by_command[tuple(command)], stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert resolve_changed_files([], base=None, head=None) == [
        "shared.py",
        "staged.py",
        "unstaged.py",
        "untracked.py",
    ]
    assert commands == [
        ("git", "diff", "--name-only", "--cached"),
        ("git", "diff", "--name-only"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    ]


def test_resolve_changed_files_keeps_explicit_refs_authoritative(monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        assert command == ["git", "diff", "--name-only", "origin/main...HEAD"]
        return subprocess.CompletedProcess(command, 0, stdout="from-ref.py\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert resolve_changed_files([], base="origin/main", head="HEAD") == ["from-ref.py"]


def test_resolve_changed_files_keeps_explicit_files_authoritative(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("git not expected")))

    assert resolve_changed_files([" explicit.py ", ""], base=None, head=None) == [" explicit.py "]
