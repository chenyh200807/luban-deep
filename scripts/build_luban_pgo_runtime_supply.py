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
    build_grading_contracts_from_factory_candidate,
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


def _load_pgo_objects(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            objects = payload.get("objects")
            if isinstance(objects, list):
                return [item for item in objects if isinstance(item, dict)]
            return [payload]
        raise ValueError("PGO object input must be an object, list, or object with objects[]")
    if path.is_dir():
        objects: list[dict[str, Any]] = []
        for item in sorted(path.glob("*.json")):
            payload = json.loads(item.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                objects.append(payload)
        return objects
    raise ValueError(f"PGO object path not found: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--contracts", type=Path)
    source.add_argument("--factory-candidate", type=Path)
    parser.add_argument("--pgo-objects-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.contracts is not None:
            contracts = _load_contracts(args.contracts)
            source_summary: dict[str, Any] | None = None
        else:
            if args.pgo_objects_dir is None:
                raise ValueError("--pgo-objects-dir is required with --factory-candidate")
            factory = json.loads(args.factory_candidate.read_text(encoding="utf-8"))
            objects = _load_pgo_objects(args.pgo_objects_dir)
            factory_result = build_grading_contracts_from_factory_candidate(factory, objects)
            contracts = factory_result["contracts"]
            source_summary = factory_result["summary"]
            if factory_result["rejected"]:
                print(
                    json.dumps(
                        {
                            "status": "blocked",
                            "blockers": ["factory_candidate_rejected_cases"],
                            "rejected": factory_result["rejected"],
                            "source_summary": source_summary,
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return 1
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
                "source_summary": source_summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
