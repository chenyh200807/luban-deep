#!/usr/bin/env python3
"""Create a controlled benchmark registry promotion proposal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.promotion import (  # noqa: E402
    build_case_acceptance_snapshot,
    promote_registry_case_payload,
)
from deeptutor.services.benchmark.runner import DEFAULT_REGISTRY_PATH  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote one benchmark registry case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--target-tier", choices=["regression_tier", "gate_stable"], required=True)
    parser.add_argument("--registry-path", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--output-registry-path", required=True)
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    registry_path = Path(args.registry_path).expanduser().resolve()
    output_path = Path(args.output_registry_path).expanduser().resolve()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    promoted = promote_registry_case_payload(
        registry_payload=payload,
        case_id=args.case_id,
        target_tier=args.target_tier,
        reason=args.reason,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(promoted, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot = build_case_acceptance_snapshot(promoted, args.case_id)

    print("Benchmark promotion proposal written")
    print(f"Case: {args.case_id}")
    print(f"Target tier: {args.target_tier}")
    print(f"Output registry: {output_path}")
    print(f"Incident promoted: {snapshot['is_incident_promoted']}")


if __name__ == "__main__":
    main()
