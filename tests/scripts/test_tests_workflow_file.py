from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _tests_workflow_source() -> str:
    return (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")


def test_tests_workflow_runs_required_checks_for_merge_queue() -> None:
    source = _tests_workflow_source()

    assert "  merge_group:\n    types: [checks_requested]" in source
    assert "github.event_name == 'merge_group' && github.event.merge_group.base_sha" in source


def test_merge_queue_secret_scan_uses_changed_files_not_full_repo() -> None:
    source = _tests_workflow_source()

    assert "if: github.event_name == 'pull_request' || github.event_name == 'merge_group'" in source
    assert "if: github.event_name == 'push'" in source
    assert "github.event_name == 'merge_group' && github.event.merge_group.base_sha" in source


def test_smoke_shards_keep_existing_required_check_name() -> None:
    source = _tests_workflow_source()

    assert "smoke-shards:" in source
    assert "name: Smoke Tests Shard (${{ matrix.shard }})" in source
    assert "smoke-tests:" in source
    assert "name: Smoke Tests (Python 3.11)" in source
    assert "needs: [change-scope, smoke-shards]" in source


def test_merge_queue_uses_change_scope_fast_path_for_domain_jobs() -> None:
    source = _tests_workflow_source()

    assert "if: github.event_name == 'push' || needs.change-scope.outputs.governance == 'true'" in source
    assert "if: github.event_name == 'push' || needs.change-scope.outputs.backend == 'true'" in source
    assert "if: github.event_name == 'push' || needs.change-scope.outputs.frontend == 'true'" in source
    assert "if: github.event_name == 'push' || needs.change-scope.outputs.wx == 'true'" in source
    assert "if: github.event_name == 'push' || needs.change-scope.outputs.yousen == 'true'" in source
