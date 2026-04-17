from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.session.sqlite_store import SQLiteSessionStore


async def _run(session_id: str | None) -> None:
    store = SQLiteSessionStore()
    stats = await store.backfill_message_presentations(session_id=session_id)
    scope = session_id or "ALL"
    print(
        f"presentation backfill complete: scope={scope} scanned={stats['scanned']} updated={stats['updated']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill legacy assistant result summaries into presentation metadata.",
    )
    parser.add_argument(
        "--session-id",
        dest="session_id",
        default=None,
        help="Only backfill one session. Omit to scan the whole chat history DB.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.session_id))


if __name__ == "__main__":
    main()
