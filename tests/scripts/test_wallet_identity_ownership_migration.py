from __future__ import annotations

import asyncio
import json
import sqlite3

from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key
from scripts.migrate_wallet_identity_ownership import (
    build_identity_owner_mappings,
    export_identity_ownership_migration,
)


def test_build_identity_owner_mappings_prefers_uuid_pairs_and_deduplicates() -> None:
    rows = [
        {
            "alias_type": "legacy_user_id",
            "alias_value": "user_2008",
            "member_user_id": "user_2008",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "source": "member_console",
        },
        {
            "alias_type": "auth_username",
            "alias_value": "chenyh2008",
            "member_user_id": "user_2008",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "source": "member_console",
        },
        {
            "alias_type": "legacy_user_id",
            "alias_value": "user_shadow",
            "member_user_id": "user_shadow",
            "canonical_user_id": "",
            "source": "member_console",
        },
    ]

    mappings = build_identity_owner_mappings(rows)

    assert mappings == {
        "user_2008": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
    }


def test_export_identity_ownership_migration_rewrites_local_runtime_state(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    inventory_path = repo_root / "identity_inventory.csv"
    inventory_path.write_text(
        "\n".join(
            [
                "alias_type,alias_value,member_user_id,canonical_user_id,source",
                "legacy_user_id,user_2008,user_2008,2d9eac15-5d26-4e93-941b-9ec6345ce6d9,member_console",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = repo_root / "data" / "user" / "chat_history.db"
    store = SQLiteSessionStore(db_path=db_path)
    legacy_owner_key = build_user_owner_key("user_2008")
    asyncio.run(store.create_session(title="旧会话", session_id="legacy_session", owner_key=legacy_owner_key))
    asyncio.run(store.update_session_preferences("legacy_session", {"user_id": "user_2008", "owner_key": legacy_owner_key}))

    learner_root = repo_root / "data" / "user" / "learner_state"
    legacy_dir = learner_root / "user_2008"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "PROFILE.json").write_text(
        json.dumps({"user_id": "user_2008", "display_name": "陈同学"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (legacy_dir / "SUMMARY.md").write_text("旧摘要\n", encoding="utf-8")
    (legacy_dir / "MEMORY_EVENTS.jsonl").write_text(
        json.dumps({"event_id": "evt_1", "user_id": "user_2008"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    overlay_root = learner_root / "bot_overlays"
    overlay_root.mkdir(parents=True)
    (overlay_root / "user_2008__bot_alpha.json").write_text(
        json.dumps(
            {
                "bot_id": "bot_alpha",
                "user_id": "user_2008",
                "overlay": {"heartbeat_override": {"enabled": True}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (overlay_root / "user_2008__bot_alpha.events.jsonl").write_text(
        json.dumps({"event_id": "ov_1", "user_id": "user_2008", "bot_id": "bot_alpha"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    heartbeat_path = repo_root / "data" / "runtime" / "learner_state" / "heartbeat_jobs.json"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "job_id": "job_1",
                        "user_id": "user_2008",
                        "bot_id": "bot_alpha",
                        "channel": "heartbeat",
                        "policy_json": {},
                        "next_run_at": "2026-04-19T12:00:00+08:00",
                        "last_run_at": None,
                        "last_result_json": None,
                        "failure_count": 0,
                        "status": "active",
                        "created_at": "2026-04-19T11:00:00+08:00",
                        "updated_at": "2026-04-19T11:00:00+08:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    outbox_db = repo_root / "data" / "runtime" / "outbox.db"
    outbox_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(outbox_db) as conn:
        conn.execute(
            """
            create table learner_state_outbox (
                id text primary key,
                user_id text not null,
                event_type text not null,
                payload_json text not null,
                dedupe_key text not null,
                status text not null,
                retry_count integer not null,
                created_at text not null,
                last_error text
            )
            """
        )
        conn.execute(
            """
            insert into learner_state_outbox (
                id, user_id, event_type, payload_json, dedupe_key, status, retry_count, created_at, last_error
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt_1",
                "user_2008",
                "summary_refresh",
                json.dumps({"user_id": "user_2008", "source_id": "legacy"}),
                "summary_refresh:user_2008",
                "pending",
                0,
                "2026-04-19T11:30:00+08:00",
                None,
            ),
        )
        conn.commit()

    learning_plan_path = repo_root / "data" / "user" / "workspace" / "guide" / "learning_plans" / "plan_1.json"
    learning_plan_path.parent.mkdir(parents=True, exist_ok=True)
    learning_plan_path.write_text(
        json.dumps({"session_id": "plan_1", "user_id": "user_2008", "status": "ready"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = export_identity_ownership_migration(
        output_dir=repo_root / "tmp" / "wallet-ownership-migration",
        inventory_path=inventory_path,
        repo_root=repo_root,
        apply=True,
    )

    assert summary["status"] == "applied"
    assert summary["owner_mappings"]["user_2008"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert summary["sqlite"]["sessions_updated"] == 1
    assert summary["learner_state"]["directories_moved"] == 1
    assert summary["heartbeat"]["jobs_rewritten"] == 1
    assert summary["overlays"]["files_moved"] == 2
    assert summary["learning_plans"]["plans_rewritten"] == 1
    assert summary["outbox"]["rows_rewritten"] == 1

    canonical_dir = learner_root / "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert canonical_dir.exists()
    assert not legacy_dir.exists()
    profile = json.loads((canonical_dir / "PROFILE.json").read_text(encoding="utf-8"))
    assert profile["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    overlay = json.loads(
        (overlay_root / "2d9eac15-5d26-4e93-941b-9ec6345ce6d9__bot_alpha.json").read_text(encoding="utf-8")
    )
    assert overlay["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["jobs"][0]["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    learning_plan = json.loads(learning_plan_path.read_text(encoding="utf-8"))
    assert learning_plan["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    with sqlite3.connect(outbox_db) as conn:
        user_id, payload_json = conn.execute(
            "select user_id, payload_json from learner_state_outbox where id = ?",
            ("evt_1",),
        ).fetchone()
    assert user_id == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert json.loads(payload_json)["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
