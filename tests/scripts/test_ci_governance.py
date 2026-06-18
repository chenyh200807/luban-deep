from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_codeowners_protects_ci_and_security_baselines() -> None:
    source = _read(".github/CODEOWNERS")

    for pattern in [
        "/.github/workflows/** @chenyh200807",
        "/scripts/ci/ @chenyh200807",
        "/scripts/ci/baselines/** @chenyh200807",
        "/.secrets.baseline @chenyh200807",
        "/.bandit-baseline.json @chenyh200807",
    ]:
        assert pattern in source


def test_tests_workflow_path_filter_covers_agent_skills_and_security_baselines() -> None:
    source = _read(".github/workflows/tests.yml")

    for pattern in [
        '- "agent-skills/**"',
        '- ".secrets.baseline"',
        '- ".bandit-baseline.json"',
    ]:
        assert source.count(pattern) == 2
