from __future__ import annotations

import subprocess

from scripts.check_contract_guard import (
    evaluate_changed_files,
    evaluate_question_lifecycle_authority,
    resolve_changed_files,
)
from scripts.ci.check_websocket_route_allowlist import (
    evaluate_allowlist,
    load_websocket_allowlist,
)


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


def test_question_lifecycle_guard_rejects_competing_attach_call(tmp_path) -> None:
    offender = tmp_path / "deeptutor" / "capabilities" / "deep_question.py"
    offender.parent.mkdir(parents=True)
    offender.write_text(
        "def run(ctx):\n"
        "    attach_question_lifecycle_scene_to_context(ctx)\n",
        encoding="utf-8",
    )

    ok, message = evaluate_question_lifecycle_authority(tmp_path)

    assert ok is False
    assert "attach_question_lifecycle_scene_to_context" in message
    assert "deep_question.py" in message


def test_question_lifecycle_guard_rejects_loop_scene_writer(tmp_path) -> None:
    offender = tmp_path / "deeptutor" / "tutorbot" / "agent" / "loop.py"
    offender.parent.mkdir(parents=True)
    offender.write_text(
        "def run(metadata):\n"
        "    metadata['question_lifecycle_scene'] = 'question_review'\n",
        encoding="utf-8",
    )

    ok, message = evaluate_question_lifecycle_authority(tmp_path)

    assert ok is False
    assert "question_lifecycle_scene writer" in message
    assert "loop.py" in message


def test_question_lifecycle_guard_allows_approved_projection_points(tmp_path) -> None:
    orchestrator = tmp_path / "deeptutor" / "runtime" / "orchestrator.py"
    service = tmp_path / "deeptutor" / "services" / "question_lifecycle_skills.py"
    observer = tmp_path / "deeptutor" / "services" / "session" / "turn_runtime.py"
    for path in (orchestrator, service, observer):
        path.parent.mkdir(parents=True, exist_ok=True)
    orchestrator.write_text(
        "def record(context):\n"
        "    context.metadata['question_lifecycle_scene'] = 'question_review'\n",
        encoding="utf-8",
    )
    service.write_text(
        "def attach_question_lifecycle_scene_to_context(ctx):\n"
        "    metadata['question_lifecycle_scene'] = scene\n"
        "def derive_question_lifecycle_scene(ctx):\n"
        "    return None\n",
        encoding="utf-8",
    )
    observer.write_text(
        "def summarize(summary):\n"
        "    summary['question_lifecycle_scene'] = 'question_review'\n",
        encoding="utf-8",
    )

    ok, message = evaluate_question_lifecycle_authority(tmp_path)

    assert ok is True
    assert "question-lifecycle-authority-guard: passed" in message


_REPO_ALLOWLIST = {
    "/api/v1/ws": {"path": "/api/v1/ws", "kind": "chat"},
    "/api/v1/knowledge/{kb_name}/progress/ws": {
        "path": "/api/v1/knowledge/{kb_name}/progress/ws",
        "kind": "stream",
    },
}


def test_websocket_allowlist_passes_for_declared_production_routes() -> None:
    ok, message = evaluate_allowlist(
        ["/api/v1/knowledge/{kb_name}/progress/ws", "/api/v1/ws"],
        _REPO_ALLOWLIST,
    )
    assert ok is True
    assert "websocket-allowlist-guard: passed" in message


def test_websocket_allowlist_rejects_unlisted_route() -> None:
    ok, message = evaluate_allowlist(
        ["/api/v1/ws", "/api/v1/rogue/ws"],
        _REPO_ALLOWLIST,
    )
    assert ok is False
    assert "unlisted production WebSocket route: /api/v1/rogue/ws" in message


def test_websocket_allowlist_rejects_second_chat_route() -> None:
    allowlist = {
        **_REPO_ALLOWLIST,
        "/api/v1/mobile/tutorbot/ws": {
            "path": "/api/v1/mobile/tutorbot/ws",
            "kind": "chat",
        },
    }
    ok, message = evaluate_allowlist(
        ["/api/v1/ws", "/api/v1/mobile/tutorbot/ws"],
        allowlist,
    )
    assert ok is False
    assert "is not /api/v1/ws" in message
    assert "more than one chat-kind WebSocket route" in message


def test_websocket_allowlist_loads_repo_index_with_single_chat_route() -> None:
    allowlist = load_websocket_allowlist()
    chat_paths = [p for p, e in allowlist.items() if e.get("kind") == "chat"]
    assert chat_paths == ["/api/v1/ws"]


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
