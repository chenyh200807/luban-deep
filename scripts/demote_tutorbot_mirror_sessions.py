#!/usr/bin/env python3
"""One-time stock migration: demote TutorBot engine mirror session rows.

Root cause (2026-07 duplicate-session BI pollution): the TutorBot engine's
bot-side history rows (``sessions.id LIKE 'tutorbot:%'``) were persisted with
the user's ``owner_key`` and the client ``source`` (e.g. ``wx_miniprogram``),
masquerading as a second user conversation per chat. The write-side fix
(deeptutor/tutorbot/session/sqlite_adapter.py ``_metadata_for_persistence``)
stops new rows from carrying user identity; this script demotes the stock
rows the same way so history metrics stop double counting:

- ``owner_key`` column -> ''
- ``source`` column    -> 'tutorbot'
- preferences JSON     -> drop ``user_id`` / ``owner_key``, set ``source``

The preferences JSON must be rewritten too: ``update_session_preferences``
re-derives the owner_key/source columns from the merged JSON, so a stale
``user_id`` inside JSON would re-stamp the row on the next save.

Read-only by default (``--dry-run`` implied); pass ``--apply`` to write.

Usage:
    python scripts/demote_tutorbot_mirror_sessions.py --db-path data/user/chat_history.db
    python scripts/demote_tutorbot_mirror_sessions.py --db-path data/user/chat_history.db --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

_ENGINE_SESSION_SOURCE = "tutorbot"
_MIRROR_ID_PREFIX = "tutorbot:"


def _demoted_preferences(preferences_json: str | None) -> str:
    try:
        preferences = json.loads(preferences_json or "{}")
    except (TypeError, ValueError):
        preferences = {}
    if not isinstance(preferences, dict):
        preferences = {}
    preferences.pop("user_id", None)
    preferences.pop("owner_key", None)
    preferences["source"] = _ENGINE_SESSION_SOURCE
    return json.dumps(preferences, ensure_ascii=False)


def migrate(db_path: Path, *, apply: bool) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, owner_key, source, preferences_json
            FROM sessions
            WHERE id LIKE ?
              AND (
                  COALESCE(owner_key, '') != ''
                  OR COALESCE(source, '') != ?
                  OR preferences_json LIKE '%"user_id"%'
                  OR preferences_json LIKE '%"owner_key"%'
              )
            """,
            (f"{_MIRROR_ID_PREFIX}%", _ENGINE_SESSION_SOURCE),
        ).fetchall()
        print(f"mirror rows needing demotion: {len(rows)}")
        if not apply:
            for row in rows[:10]:
                print(f"  would demote: {row['id']} owner_key={row['owner_key']!r} source={row['source']!r}")
            if len(rows) > 10:
                print(f"  ... and {len(rows) - 10} more")
            print("dry-run only; re-run with --apply to write")
            return len(rows)
        for row in rows:
            conn.execute(
                "UPDATE sessions SET owner_key = '', source = ?, preferences_json = ? WHERE id = ?",
                (
                    _ENGINE_SESSION_SOURCE,
                    _demoted_preferences(row["preferences_json"]),
                    row["id"],
                ),
            )
        conn.commit()
        remaining = conn.execute(
            """
            SELECT COUNT(*)
            FROM sessions
            WHERE id LIKE ?
              AND (COALESCE(owner_key, '') != '' OR COALESCE(source, '') != ?)
            """,
            (f"{_MIRROR_ID_PREFIX}%", _ENGINE_SESSION_SOURCE),
        ).fetchone()[0]
        print(f"demoted: {len(rows)}; remaining undemoted mirror rows: {remaining}")
        return remaining
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()
    if not args.db_path.exists():
        print(f"db not found: {args.db_path}", file=sys.stderr)
        return 2
    result = migrate(args.db_path, apply=args.apply)
    if args.apply and result != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
