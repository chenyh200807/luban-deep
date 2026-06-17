#!/usr/bin/env python3
"""Publish the frozen rich-leaf runtime token pack as tracked runtime supply.

Thin CLI wrapper — ALL validation / quarantine filtering / signing lives in
``deeptutor.services.construction_grading.rich_leaf_runtime.build_runtime_supply_bundle``
(fat skill). This script is the EXTERNAL release-pointer act required by the rich-leaf
compiler plan (controlled_default is pointed-to, never artifact self-claimed):

  - input: the quarantine-annotated v3.0.1 token pack artifact
  - every quarantine_candidate unit is EXCLUDED (hard requirement)
  - output: runtime_supply/v_rich_leaf_context/{rich_leaf_context_bundle.json, canonical_pointer.json}
  - lifecycle stays status=release_candidate / published=false

Writing the supply does NOT enable runtime consumption: the loader is additionally gated by
LUBAN_RICH_LEAF_RUNTIME_ENABLED (default off). Enabling in production is an owner action.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_runtime import (  # noqa: E402
    build_runtime_supply_bundle,
)

DEFAULT_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613"
    / "runtime_token_pack_v301_quarantine_annotated.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO / "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK, help="runtime token pack path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    bundle, pointer = build_runtime_supply_bundle(pack)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = args.output_dir / "rich_leaf_context_bundle.json"
    pointer_path = args.output_dir / "canonical_pointer.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = bundle["manifest"]
    print(f"pack: {args.pack}")
    print(f"source units: {manifest['source_pack_unit_count']}")
    print(f"quarantine excluded: {manifest['quarantine_excluded_count']}")
    print(f"records published: {manifest['record_count']}")
    print(f"content_hash: {manifest['content_hash']}")
    print(f"status: {manifest['status']} / published={manifest['published']}")
    print(f"wrote: {bundle_path}")
    print(f"wrote: {pointer_path}")
    print("runtime consumption stays OFF until LUBAN_RICH_LEAF_RUNTIME_ENABLED=true (owner action)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
