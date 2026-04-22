from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_aliyun_observability.sh"


def test_verify_aliyun_observability_requires_ready_truth_and_exact_metric() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "readiness.get('ready') is not True" in content
    assert "'deeptutor_ready 1'" in content
