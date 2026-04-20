#!/usr/bin/env python3
"""Run a sequential pre-release observability pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability.prerelease_runner import run_prerelease_observability  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor pre-release observability pipeline")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--arr-mode", choices=["lite", "full"], default="lite")
    parser.add_argument("--ws-smoke-message", help="可选，直接通过 /api/v1/ws 发起一次真实 turn smoke")
    parser.add_argument("--surface-smoke", help="可选，触发一次 live surface ack smoke，例如 web")
    parser.add_argument("--metrics-json", help="离线 metrics JSON 文件；提供后不走 live /metrics")
    parser.add_argument("--output-dir")
    parser.add_argument("--long-dialog-source-json")
    parser.add_argument("--long-dialog-max-cases", type=int)
    args = parser.parse_args()

    result = run_prerelease_observability(
        api_base_url=args.api_base_url,
        arr_mode=args.arr_mode,
        ws_smoke_message=args.ws_smoke_message,
        surface_smoke=args.surface_smoke,
        metrics_json=args.metrics_json,
        output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
        explicit_long_dialog_source_json=args.long_dialog_source_json,
        long_dialog_max_cases=args.long_dialog_max_cases,
    )
    gate = result["runs"]["release_gate"]

    print(f"Pre-release observability completed: {gate['run_id']}")
    print(f"Final status: {gate['final_status']}")
    print(f"Recommendation: {gate['recommendation']}")
    print(json.dumps(result["artifacts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
