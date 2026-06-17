from __future__ import annotations

from pathlib import Path

from deeptutor.services.observability.plan_completion import (
    build_plan_completion_audit,
    extract_plan_items,
)


def test_extract_plan_items_keeps_checklists_numbered_steps_and_paths(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "\n".join(
            [
                "# Sample Plan",
                "",
                "- [ ] Create: `scripts/run_ws_capacity_probe.py`",
                "- [x] Test: `tests/services/observability/test_ws_capacity_probe.py`",
                "1. Run: `pytest tests/services/observability/test_ws_capacity_probe.py -q`",
            ]
        ),
        encoding="utf-8",
    )

    items = extract_plan_items(plan, project_root=tmp_path)

    assert [item["kind"] for item in items] == ["checkbox", "checkbox", "numbered"]
    assert items[0]["paths"] == ["scripts/run_ws_capacity_probe.py"]
    assert items[1]["paths"] == ["tests/services/observability/test_ws_capacity_probe.py"]
    assert items[2]["commands"] == ["pytest tests/services/observability/test_ws_capacity_probe.py -q"]


def test_plan_completion_marks_changed_paths_done(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    target = tmp_path / "scripts" / "run_ws_capacity_probe.py"
    plan.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text("# probe\n", encoding="utf-8")
    plan.write_text("- [ ] Create: `scripts/run_ws_capacity_probe.py`\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=["scripts/run_ws_capacity_probe.py"],
        project_root=tmp_path,
    )

    assert audit["status"] == "PASS"
    assert audit["summary"]["done"] == 1
    assert audit["items"][0]["status"] == "DONE"


def test_plan_completion_full_scope_fails_when_explicit_path_is_missing(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    target = tmp_path / "scripts" / "run_ws_capacity_probe.py"
    plan.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    plan.write_text("- [ ] Create: `scripts/run_ws_capacity_probe.py`\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=["scripts/other.py"],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "FAIL"
    assert audit["summary"]["not_done"] == 1
    assert audit["blockers"] == ["plan_item_not_done"]
    assert audit["items"][0]["status"] == "NOT_DONE"


def test_plan_completion_full_scope_accepts_current_state_existing_path(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    target = tmp_path / "scripts" / "run_ws_capacity_probe.py"
    plan.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text("# probe\n", encoding="utf-8")
    plan.write_text("- [ ] Create: `scripts/run_ws_capacity_probe.py`\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=[],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "PASS"
    assert audit["summary"]["done"] == 1
    assert audit["items"][0]["status"] == "DONE"
    assert audit["items"][0]["evidence"] == ["current_state_existing:scripts/run_ws_capacity_probe.py"]


def test_plan_completion_full_scope_accepts_declared_complete_step_without_path(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("- [x] **Step 1: Run focused verification**\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=[],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "PASS"
    assert audit["summary"]["done"] == 1
    assert audit["items"][0]["status"] == "DONE"
    assert audit["items"][0]["evidence"] == ["declared_complete"]


def test_plan_completion_full_scope_accepts_declared_complete_existing_path(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    target = tmp_path / "tests" / "services" / "test_probe.py"
    plan.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text("def test_probe():\n    assert True\n", encoding="utf-8")
    plan.write_text("- [x] Test: `tests/services/test_probe.py`\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=[],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "PASS"
    assert audit["summary"]["done"] == 1
    assert audit["items"][0]["status"] == "DONE"
    assert audit["items"][0]["evidence"] == ["declared_complete_existing:tests/services/test_probe.py"]


def test_plan_completion_normalizes_line_qualified_repo_paths(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    target = tmp_path / "deeptutor" / "services" / "worker.py"
    plan.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text("# worker\n", encoding="utf-8")
    plan.write_text("- Modify: `deeptutor/services/worker.py:331`\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=[],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "PASS"
    assert audit["items"][0]["paths"] == ["deeptutor/services/worker.py"]
    assert audit["items"][0]["evidence"] == ["current_state_existing:deeptutor/services/worker.py"]


def test_plan_completion_default_scope_does_not_block_future_plan_items(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    first = tmp_path / "scripts" / "run_ws_capacity_probe.py"
    plan.parent.mkdir(parents=True)
    first.parent.mkdir(parents=True)
    first.write_text("# probe\n", encoding="utf-8")
    plan.write_text(
        "\n".join(
            [
                "- [ ] Create: `scripts/run_ws_capacity_probe.py`",
                "- [ ] Create: `deeptutor/services/session/worker.py`",
            ]
        ),
        encoding="utf-8",
    )

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=["scripts/run_ws_capacity_probe.py"],
        project_root=tmp_path,
    )

    assert audit["status"] == "PASS"
    assert audit["summary"]["scoped"] == 1
    assert audit["summary"]["out_of_scope"] == 1
    assert audit["summary"]["not_done"] == 0
    assert [item["status"] for item in audit["items"]] == ["DONE", "OUT_OF_SCOPE"]


def test_plan_completion_full_scope_blocks_future_plan_items(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    first = tmp_path / "scripts" / "run_ws_capacity_probe.py"
    plan.parent.mkdir(parents=True)
    first.parent.mkdir(parents=True)
    first.write_text("# probe\n", encoding="utf-8")
    plan.write_text(
        "\n".join(
            [
                "- [ ] Create: `scripts/run_ws_capacity_probe.py`",
                "- [ ] Create: `deeptutor/services/session/worker.py`",
            ]
        ),
        encoding="utf-8",
    )

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=["scripts/run_ws_capacity_probe.py"],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "FAIL"
    assert audit["summary"]["scoped"] == 2
    assert audit["summary"]["not_done"] == 1
    assert audit["blockers"] == ["plan_item_not_done"]


def test_plan_completion_warns_when_changed_scope_finds_no_matching_items(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("- [ ] Create: `scripts/run_ws_capacity_probe.py`\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=["docs/plan/sample.md"],
        project_root=tmp_path,
    )

    assert audit["status"] == "WARN"
    assert audit["summary"]["scoped"] == 0
    assert audit["summary"]["out_of_scope"] == 1
    assert audit["blockers"] == []
    assert audit["warnings"] == ["no_scoped_plan_items"]


def test_plan_completion_warns_when_item_has_no_local_evidence(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("- [ ] Confirm Aliyun capacity metrics are stable\n", encoding="utf-8")

    audit = build_plan_completion_audit(
        plan_paths=[plan],
        changed_files=[],
        scope_mode="full",
        project_root=tmp_path,
    )

    assert audit["status"] == "WARN"
    assert audit["summary"]["unverifiable"] == 1
    assert audit["blockers"] == []
    assert audit["items"][0]["status"] == "UNVERIFIABLE"


def test_extract_plan_items_ignores_inline_concepts_that_are_not_commands_or_paths(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plan" / "sample.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "\n".join(
            [
                "- DeepTutor 仍是 `deeptutor` all-in-one 单容器。",
                "1. 再做 Task 4：外置 event stream，为 gateway/worker 分离铺路。",
            ]
        ),
        encoding="utf-8",
    )

    items = extract_plan_items(plan, project_root=tmp_path)

    assert items == [
        {
            "id": "docs/plan/sample.md:2",
            "plan_path": "docs/plan/sample.md",
            "line": 2,
            "kind": "numbered",
            "declared_complete": False,
            "text": "再做 Task 4：外置 event stream，为 gateway/worker 分离铺路。",
            "paths": [],
            "commands": [],
            "command_paths": [],
            "category": "EXTERNAL",
        }
    ]
