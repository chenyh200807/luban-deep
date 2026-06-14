from __future__ import annotations

import subprocess

from scripts.check_contract_guard import (
    evaluate_changed_files,
    evaluate_question_lifecycle_authority,
    evaluate_route_model_uniqueness,
    evaluate_upstream_authority_absorption,
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


def test_guard_rejects_luban_grading_engine_change_without_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        ["deeptutor/services/construction_grading/per_question_grading_object.py"]
    )
    assert ok is False
    assert "[luban_grading_engine] protected files changed" in message


def test_guard_accepts_luban_grading_engine_change_with_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/services/construction_grading/per_question_grading_object.py",
            "tests/services/construction_grading/test_per_question_grading_object.py",
        ]
    )
    assert ok is True
    assert "[luban_grading_engine] passed" in message


def test_guard_rejects_luban_judge_change_without_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        ["deeptutor/services/construction_grading/per_question_grading_judge.py"]
    )
    assert ok is False
    assert "[luban_grading_engine] protected files changed" in message


def test_guard_accepts_luban_judge_change_with_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/services/construction_grading/per_question_grading_judge.py",
            "tests/services/construction_grading/test_per_question_grading_judge.py",
        ]
    )
    assert ok is True
    assert "[luban_grading_engine] passed" in message


def test_guard_rejects_luban_pgo_supply_change_without_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        ["deeptutor/services/construction_grading/case_rubric_pgo_supply.py"]
    )
    assert ok is False
    assert "[luban_grading_engine] protected files changed" in message


def test_guard_accepts_luban_pgo_supply_change_with_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/services/construction_grading/case_rubric_pgo_supply.py",
            "tests/services/construction_grading/test_case_rubric_pgo_supply.py",
        ]
    )
    assert ok is True
    assert "[luban_grading_engine] passed" in message


def test_guard_rejects_luban_pgo_supply_script_change_without_domain_tests() -> None:
    ok, message = evaluate_changed_files(["scripts/build_luban_pgo_runtime_supply.py"])
    assert ok is False
    assert "[luban_grading_engine] protected files changed" in message


def test_guard_accepts_luban_pgo_supply_script_change_with_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "scripts/build_luban_pgo_runtime_supply.py",
            "tests/scripts/test_build_luban_pgo_runtime_supply.py",
        ]
    )
    assert ok is True
    assert "[luban_grading_engine] passed" in message


def test_guard_rejects_luban_stage0_runtime_change_without_domain_tests() -> None:
    ok, message = evaluate_changed_files(["deeptutor/tutorbot/agent/loop.py"])
    assert ok is False
    assert "[luban_grading_engine] protected files changed" in message


def test_guard_accepts_luban_stage0_runtime_change_with_domain_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/tutorbot/agent/loop.py",
            "tests/tutorbot/test_agent_loop_case_rubric_v1.py",
        ]
    )
    assert ok is True
    assert "[luban_grading_engine] passed" in message


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


def test_guard_accepts_rag_personalization_tests() -> None:
    ok, message = evaluate_changed_files(
        [
            "deeptutor/services/rag/retrieval_plan.py",
            "contracts/rag.md",
            "tests/services/rag/test_retrieval_plan.py",
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


def test_route_model_uniqueness_guard_rejects_same_name_in_two_routers(tmp_path) -> None:
    # P3#10: two routers defining a same-named pydantic model (with different shapes) is a
    # silent OpenAPI collision — the guard must fail and name both files.
    routers = tmp_path / "deeptutor" / "api" / "routers"
    routers.mkdir(parents=True)
    (routers / "alpha.py").write_text("class CreateSessionRequest(BaseModel):\n    a: int\n", encoding="utf-8")
    (routers / "beta.py").write_text("class CreateSessionRequest(BaseModel):\n    b: str\n", encoding="utf-8")

    ok, message = evaluate_route_model_uniqueness(tmp_path)

    assert ok is False
    assert "CreateSessionRequest" in message
    assert "alpha.py" in message and "beta.py" in message


def test_route_model_uniqueness_guard_allows_unique_names(tmp_path) -> None:
    # A model defined once (or imported, not re-defined) in each router passes.
    routers = tmp_path / "deeptutor" / "api" / "routers"
    routers.mkdir(parents=True)
    (routers / "alpha.py").write_text("class AlphaRequest(BaseModel):\n    a: int\n", encoding="utf-8")
    (routers / "beta.py").write_text(
        "from deeptutor.api.routers.alpha import AlphaRequest\nclass BetaRequest(BaseModel):\n    b: str\n",
        encoding="utf-8",
    )

    ok, message = evaluate_route_model_uniqueness(tmp_path)

    assert ok is True
    assert "all names unique" in message


def test_route_model_uniqueness_guard_passes_on_live_tree() -> None:
    # The live routers tree must stay clean (after the P3#10 dedup of the 5 colliding models).
    ok, message = evaluate_route_model_uniqueness()
    assert ok is True, message


def test_upstream_authority_guard_rejects_partners_runtime_package(tmp_path) -> None:
    offender = tmp_path / "deeptutor" / "partners" / "__init__.py"
    offender.parent.mkdir(parents=True)
    offender.write_text("", encoding="utf-8")

    ok, message = evaluate_upstream_authority_absorption(tmp_path)

    assert ok is False
    assert "deeptutor/partners" in message
    assert "TutorBot remains the business identity" in message


def test_upstream_authority_guard_rejects_partners_runtime_module(tmp_path) -> None:
    offender = tmp_path / "deeptutor" / "partners.py"
    offender.parent.mkdir(parents=True)
    offender.write_text("", encoding="utf-8")

    ok, message = evaluate_upstream_authority_absorption(tmp_path)

    assert ok is False
    assert "deeptutor/partners.py" in message
    assert "TutorBot remains the business identity" in message


def test_upstream_authority_guard_rejects_partners_api_route(tmp_path) -> None:
    offender = tmp_path / "deeptutor" / "api" / "routers" / "partners.py"
    offender.parent.mkdir(parents=True)
    offender.write_text('router_prefix = "/api/v1/partners"\n', encoding="utf-8")

    ok, message = evaluate_upstream_authority_absorption(tmp_path)

    assert ok is False
    assert "/api/v1/partners" in message
    assert "/api/v1/ws" in message


def test_upstream_authority_guard_rejects_standalone_learning_runtime(tmp_path) -> None:
    offender = tmp_path / "deeptutor" / "learning" / "__init__.py"
    offender.parent.mkdir(parents=True)
    offender.write_text("", encoding="utf-8")

    ok, message = evaluate_upstream_authority_absorption(tmp_path)

    assert ok is False
    assert "deeptutor/learning" in message
    assert "Learning Brain" in message


def test_upstream_authority_guard_allows_existing_authorities(tmp_path) -> None:
    for relative in (
        "deeptutor/capabilities/tutorbot.py",
        "deeptutor/services/learner_state/service.py",
        "deeptutor/api/routers/unified_ws.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# existing authority surface\n", encoding="utf-8")

    ok, message = evaluate_upstream_authority_absorption(tmp_path)

    assert ok is True
    assert "upstream-authority-absorption-guard: passed" in message


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


# ── schema-registry register-before-use, wired into the one runner (P0#1) ─────


def test_schema_registry_guard_importable_and_wired_into_contract_guard() -> None:
    # P0#1: the schema-registry changed-files guard must be reachable from the central
    # runner (proves the import wiring) and pass on a registered grading source file.
    from scripts.check_contract_guard import evaluate_schema_registry

    ok, message = evaluate_schema_registry(
        ["deeptutor/services/construction_grading/per_question_grading_object.py"]
    )
    assert ok is True
    assert "schema-registry-guard" in message


def test_main_return_includes_schema_ok(monkeypatch) -> None:
    # P0#1: a schema-registry failure must FAIL the one runner (schema_ok is in the gate).
    import scripts.check_contract_guard as G

    monkeypatch.setattr(G, "resolve_changed_files", lambda *_a, **_k: ["README.md"])
    monkeypatch.setattr(
        G,
        "evaluate_websocket_route_allowlist",
        lambda: (True, "websocket-allowlist-guard: passed"),
    )
    monkeypatch.setattr(G, "evaluate_schema_registry", lambda _f: (False, "schema-registry-guard: failed (test)"))
    assert G.main(["--base", "x", "--head", "y"]) == 1
    # and when it passes, the runner can still pass (other guards permitting on a doc-only change)
    monkeypatch.setattr(G, "evaluate_schema_registry", lambda _f: (True, "schema-registry-guard: passed"))
    assert G.main(["--base", "x", "--head", "y"]) == 0
