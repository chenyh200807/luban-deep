from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from deeptutor.services.member_console import external_auth as external_auth_module


def test_seed_luban_internal_qa_accounts_creates_fixed_users(
    tmp_path: Path,
    monkeypatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    monkeypatch.setenv("DEEPTUTOR_INTERNAL_QA_TEST_PASSWORD", "QaSeedPass123")
    env = os.environ.copy()
    env.update(
        {
            "DEEPTUTOR_ENV": "local",
            "DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE": str(users_file),
            "DEEPTUTOR_INTERNAL_QA_TEST_PASSWORD": "QaSeedPass123",
        }
    )

    result = subprocess.run(
        [sys.executable, "scripts/seed_luban_internal_qa_accounts.py"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    users = json.loads(users_file.read_text(encoding="utf-8"))
    assert {
        "qa_tutorbot_mcq",
        "qa_tutorbot_followup",
        "qa_tutorbot_weird",
        "qa_tutorbot_case",
    }.issubset(users)
    assert users["qa_tutorbot_mcq"]["account_kind"] == "eval_runner"
    assert users["qa_tutorbot_mcq"]["actor_type"] == "machine"
    assert users["qa_tutorbot_mcq"]["created_by"] == "eval_runner"
    assert users["qa_tutorbot_mcq"]["is_internal_test"] is True
    assert "qa_tutorbot_mcq" in result.stdout
    assert external_auth_module.verify_external_auth_user(
        "qa_tutorbot_mcq",
        "QaSeedPass123",
    ) is not None
