from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _deploy_gate_source() -> str:
    return (ROOT / ".github/workflows/deploy-gate.yml").read_text(encoding="utf-8")


def test_deploy_gate_ignores_stale_tests_workflow_runs() -> None:
    source = _deploy_gate_source()

    assert "CURRENT_MAIN_SHA: ${{ github.sha }}" in source
    assert 'if [ "$TESTS_HEAD_SHA" != "$CURRENT_MAIN_SHA" ]; then' in source
    assert 'echo "status=stale" >> "$GITHUB_OUTPUT"' in source
    assert 'echo "reason=stale_upstream_run" >> "$GITHUB_OUTPUT"' in source


def test_deploy_gate_only_fails_current_main_red_status() -> None:
    source = _deploy_gate_source()

    assert "if: steps.gate.outputs.status == 'red'" in source
    assert "if: steps.gate.outputs.status != 'green'" not in source
    assert 'echo "status=red" >> "$GITHUB_OUTPUT"' in source
    assert 'echo "reason=current_tests_not_green" >> "$GITHUB_OUTPUT"' in source


def test_deploy_gate_artifact_records_current_and_upstream_sha() -> None:
    source = _deploy_gate_source()

    assert "tests_head_sha=${TESTS_HEAD_SHA}" in source
    assert "current_main_sha=${CURRENT_MAIN_SHA}" in source
    assert "reason=${REASON}" in source
