#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.services.rag.maintenance import build_learning_brain_dream_cycle_maintenance_report


def run_dream_cycle(
    *,
    user_id: str,
    dry_run: bool,
    projection_file: Path | None = None,
) -> dict[str, Any]:
    projection = _read_projection(projection_file)
    return build_learning_brain_dream_cycle_maintenance_report(
        user_id=user_id,
        projection=projection,
        dry_run=dry_run,
    )


def _read_projection(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run Learning Brain dream cycle lint.")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--projection-file", type=Path, default=None)
    args = parser.parse_args(argv)

    result = run_dream_cycle(
        user_id=args.user_id,
        dry_run=bool(args.dry_run),
        projection_file=args.projection_file,
    )
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
