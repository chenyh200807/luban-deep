#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from deeptutor.services.learner_state import get_learner_state_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Run learner learning-truth synthesis for one user.")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--event-limit", type=int, default=None)
    args = parser.parse_args()

    service = get_learner_state_service()
    events = service.list_memory_events(args.user_id, limit=args.event_limit)
    result = service.synthesize_learning_truth(
        args.user_id,
        dry_run=bool(args.dry_run),
        event_limit=args.event_limit,
    )
    run = dict(result["projection"].get("synthesis_run") or {})
    payload: dict[str, Any] = {
        "status": "ok" if events else "no_events",
        "user_id": args.user_id,
        "dry_run": bool(args.dry_run),
        "event_count": len(events),
        "created_claim_count": run.get("created_claim_count", 0),
        "updated_claim_count": run.get("updated_claim_count", 0),
        "decayed_claim_count": run.get("decayed_claim_count", 0),
        "conflict_count": run.get("conflict_count", 0),
        "manual_override_count": run.get("manual_override_count", 0),
        "output_projection_hash": run.get("output_projection_hash", ""),
        "projection": result["projection"],
        "outbox_item_id": getattr(result.get("outbox_item"), "id", None),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
