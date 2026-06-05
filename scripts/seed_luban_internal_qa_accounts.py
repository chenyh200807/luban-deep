#!/usr/bin/env python
from __future__ import annotations

import json
import os
from pathlib import Path

from deeptutor.services.member_console.external_auth import (
    ensure_external_auth_user,
    verify_external_auth_user,
)
from deeptutor.services.runtime_env import is_production_environment

DEFAULT_PASSWORD = "QaTutorbot2026"
QA_ACCOUNTS = (
    {"username": "qa_tutorbot_mcq", "phone": "13900001001"},
    {"username": "qa_tutorbot_followup", "phone": "13900001002"},
    {"username": "qa_tutorbot_weird", "phone": "13900001003"},
    {"username": "qa_tutorbot_case", "phone": "13900001004"},
)


def _ensure_local_auth_store_defaults() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    users_file = repo_root / "data" / "user" / "external_auth" / "users.json"
    sessions_file = repo_root / "data" / "user" / "external_auth" / "sessions.json"
    os.environ.setdefault("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    os.environ.setdefault("DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE", str(sessions_file))


def main() -> int:
    if is_production_environment():
        raise SystemExit("refusing to seed internal QA accounts in production")
    _ensure_local_auth_store_defaults()
    password = os.getenv("DEEPTUTOR_INTERNAL_QA_TEST_PASSWORD", DEFAULT_PASSWORD).strip()
    if not password:
        raise SystemExit("DEEPTUTOR_INTERNAL_QA_TEST_PASSWORD cannot be empty")

    seeded: list[dict[str, str]] = []
    for account in QA_ACCOUNTS:
        user = ensure_external_auth_user(
            account["username"],
            password,
            phone=account["phone"],
        )
        if verify_external_auth_user(account["username"], password) is None:
            raise SystemExit(f"seeded account cannot login: {account['username']}")
        seeded.append(
            {
                "username": account["username"],
                "user_id": str(user.get("id") or ""),
                "phone": account["phone"],
            }
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "users_file": os.environ["DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE"],
                "password": password,
                "accounts": seeded,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
