from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.bi_service import BIService


async def _run(days: int, provider_name: str) -> None:
    service = BIService()
    stats = await service.backfill_usage_ledger(days=days, provider_name=provider_name)
    print(
        "usage ledger backfill complete: "
        f"days={stats['window_days']} "
        f"provider_name={stats['filters']['provider_name']} "
        f"scanned={stats['scanned_result_events']} "
        f"inserted={stats['inserted_ledger_events']} "
        f"measured={stats['inserted_measured_events']} "
        f"estimated={stats['inserted_estimated_events']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill historical turn result cost summaries into llm_usage.db.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3650,
        help="How many days of result events to scan. Default: 3650.",
    )
    parser.add_argument(
        "--provider-name",
        dest="provider_name",
        default="dashscope",
        help="Provider name to stamp onto backfilled rows. Default: dashscope.",
    )
    args = parser.parse_args()
    asyncio.run(_run(days=args.days, provider_name=args.provider_name))


if __name__ == "__main__":
    main()
