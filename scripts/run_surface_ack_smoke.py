#!/usr/bin/env python3
"""Run a live surface ACK smoke against the observability ingest path."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability.surface_ack_smoke import run_surface_ack_smoke  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor surface ACK smoke")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--surface", default="web")
    parser.add_argument("--session-id")
    parser.add_argument("--turn-id")
    args = parser.parse_args()

    session_id = args.session_id or f"surface-smoke-session-{int(time.time())}"
    turn_id = args.turn_id or f"surface-smoke-turn-{int(time.time())}"
    payload = run_surface_ack_smoke(
        api_base_url=args.api_base_url,
        surface=args.surface,
        session_id=session_id,
        turn_id=turn_id,
        metadata={"source": "run_surface_ack_smoke.py"},
    )

    print(f"Surface ACK smoke completed: {payload['run_id']}")
    print(f"Surface: {payload['surface']}")
    print(f"Passed: {payload['passed']}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

