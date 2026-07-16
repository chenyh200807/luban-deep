#!/usr/bin/env python3
"""Refresh every generated DeepTutor data-inventory projection in dependency order."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parents[3]
MANIFEST_PATH = SCRIPT_ROOT.parent / "extractions" / "latest_refresh_manifest.json"

# Thin orchestration only. Each listed builder remains the sole authority for
# its own inventory schema, input discovery, output guardrails, and rendering.
STEP_SCRIPTS = (
    "profile_raw_data_assets.py",
    "build_json_source_ledger.py",
    "build_pdf_source_ledger.py",
    "build_okf_source_alignment.py",
    "build_okf_candidate_scope.py",
    "build_okf_rubric_pilot.py",
    "build_okf_dry_consumer.py",
    "build_okf_landing_gap.py",
    "build_compiled_asset_ledger.py",
    "build_compiled_asset_authority_map.py",
    "build_knowledge_compiler_okf.py",
    "build_luban_grading_artifacts_okf.py",
    "build_governance_okf.py",
    "build_data_asset_brief.py",
    "build_asset_gap_map.py",
    "build_topic_okf.py",
    "build_okf_bundle.py",
    "profile_compiled_assets.py",
)


def normalize_generated_at(value: str | None) -> str:
    if value is None:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def command_for(script_name: str, generated_at: str) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT_ROOT / script_name),
        "--generated-at",
        generated_at,
    ]


def write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generated-at",
        help="One ISO timestamp shared by every generated projection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ordered commands without writing inventory outputs.",
    )
    args = parser.parse_args(argv)
    generated_at = normalize_generated_at(args.generated_at)
    commands = [command_for(script_name, generated_at) for script_name in STEP_SCRIPTS]

    if args.dry_run:
        print(json.dumps({"generated_at": generated_at, "commands": commands}, ensure_ascii=False, indent=2))
        return 0

    outside_inventory_dirty = git_output(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ".",
        ":(exclude)docs/原始数据/数据盘点",
    ).splitlines()
    manifest = {
        "schema": "deeptutor_data_inventory_refresh_v1",
        "generated_at": generated_at,
        "status": "running",
        "scope": "AI-only inventory and navigation projections; not runtime or official scoring authority",
        "source_checkout": {
            "git_head": git_output("rev-parse", "HEAD"),
            "branch": git_output("branch", "--show-current"),
            "outside_inventory_dirty": bool(outside_inventory_dirty),
            "outside_inventory_dirty_entries": len(outside_inventory_dirty),
        },
        "steps": [],
    }
    write_manifest(manifest)

    for script_name, command in zip(STEP_SCRIPTS, commands):
        print(f"\n[{len(manifest['steps']) + 1}/{len(commands)}] {script_name}", flush=True)
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        manifest["steps"].append({"script": script_name, "exit_code": result.returncode})
        if result.returncode != 0:
            manifest["status"] = "failed"
            manifest["failed_step"] = script_name
            write_manifest(manifest)
            return result.returncode or 1
        write_manifest(manifest)

    manifest["status"] = "success"
    write_manifest(manifest)
    print(f"\nrefreshed {len(commands)} inventory projections at {generated_at}")
    print(f"manifest: {MANIFEST_PATH.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
