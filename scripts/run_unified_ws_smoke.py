#!/usr/bin/env python3
"""Run a real unified /api/v1/ws smoke turn."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability.unified_ws_smoke import run_unified_ws_smoke  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor unified websocket smoke")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--message", default="请只回复“ok”。")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--capability")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()

    payload = asyncio.run(
        run_unified_ws_smoke(
            api_base_url=args.api_base_url,
            message=args.message,
            language=args.language,
            capability=args.capability,
            timeout_seconds=args.timeout_seconds,
        )
    )

    print(f"Unified WS smoke completed: {payload['run_id']}")
    print(f"Passed: {payload['passed']}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

