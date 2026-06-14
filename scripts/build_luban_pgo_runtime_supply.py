#!/usr/bin/env python3
"""Build a PGO case-rubric runtime supply candidate from grading contracts.

This script writes only to the explicit ``--out-dir``. It does not flip
``LUBAN_CASE_RUBRIC_BANK_SLOT`` and does not touch production workers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.case_rubric_pgo_supply import (  # noqa: E402
    build_pgo_runtime_supply,
    validate_pgo_runtime_supply,
    write_pgo_runtime_supply,
)


def _load_contracts(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        contracts = payload.get("contracts")
        if isinstance(contracts, list):
            return [item for item in contracts if isinstance(item, dict)]
    raise ValueError("contracts input must be a list or an object with contracts[]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        contracts = _load_contracts(args.contracts)
        bundle = build_pgo_runtime_supply(contracts)
        blockers = validate_pgo_runtime_supply(bundle)
        if blockers:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "blockers": blockers,
                        "rejected_count": len(bundle.get("rejected") or []),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1
        paths = write_pgo_runtime_supply(bundle, args.out_dir)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "bank": str(paths["bank"]),
                "pointer": str(paths["pointer"]),
                "content_hash": bundle["manifest"]["content_hash"],
                "question_count": bundle["manifest"]["question_count"],
                "scoring_point_count": bundle["manifest"]["scoring_point_count"],
                "production_default": bundle["manifest"]["production_default"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
