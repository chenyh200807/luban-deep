"""TDD for scripts/ci/classify_changed_paths.sh.

The script decides whether a changeset contains *code-relevant* paths (so the
heavy CI jobs/steps should run) or is *docs-only* (heavy work skipped, but the
required-check jobs still run and report success). This is the testable kernel
of the fix for docs-only PRs being permanently BLOCKED by required checks that
were path-filtered out of triggering.

Contract: reads a newline-separated file list on stdin, prints exactly
``true`` or ``false`` (code-relevant present?) on stdout.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "classify_changed_paths.sh"


def _classify(file_list: str) -> str:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        input=file_list,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_docs_only_is_not_code() -> None:
    assert _classify("docs/plan/2026-05-30-foo.md\ndocs/plan/INDEX.md\n") == "false"


def test_code_file_is_code() -> None:
    assert _classify("deeptutor/api/main.py\n") == "true"


def test_mixed_docs_and_code_is_code() -> None:
    assert _classify("docs/plan/foo.md\ndeeptutor/x.py\n") == "true"


def test_whitelisted_turn_contract_doc_is_code() -> None:
    # docs/zh/guide/unified-turn-contract.md is an existing code-trigger path:
    # changes to it must still run the heavy contract checks.
    assert _classify("docs/zh/guide/unified-turn-contract.md\n") == "true"


def test_non_docs_root_file_is_code() -> None:
    # Anything outside docs/ (e.g. a root file) must run heavy CI — these were
    # also silently un-triggered before the fix.
    assert _classify("README.md\n") == "true"


def test_contracts_change_is_code() -> None:
    assert _classify("contracts/turn.md\n") == "true"


def test_empty_changeset_is_not_code() -> None:
    # Defensive: no files -> nothing code-relevant. (Heavy work safely skipped;
    # required jobs still report success.)
    assert _classify("") == "false"
