#!/usr/bin/env python3
"""Build a non-authoritative asset manifest for a diagram microlesson bundle.

The manifest is a preview/production-tooling asset list. It does not claim grading,
runtime, learner-state, or official-score authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


SCHEMA_VERSION = "luban_card_bundle_manifest.v0"


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def asset(role: str, path: Path, *, root: Path, required: bool = True, pending_label: str = "missing") -> dict[str, Any]:
    exists = path.exists()
    status = "ok" if exists else ("missing_required" if required else pending_label)
    return {
        "role": role,
        "path": display_path(path, root),
        "exists": exists,
        "required": required,
        "status": status,
        "bytes": path.stat().st_size if exists and path.is_file() else 0,
        "sha256": sha256(path),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_manifest(master_path: Path, *, rendered_path: Path | None = None, require_practice: bool = False) -> dict[str, Any]:
    master = load_json(master_path)
    root = master_path.parent
    lesson_path = root / master["teaching_lesson_ref"]
    timing_path = lesson_path.with_suffix(".timing.json")
    rendered = rendered_path or master_path.with_name(master_path.name.replace(".master.json", ".journey.html"))
    practice = master_path.with_name(master_path.name.replace(".master.json", ".practice.html"))
    timing = load_json(timing_path) if timing_path.exists() else {}
    audio_ref = str(timing.get("audio") or "").strip()
    assets = [
        asset("master", master_path, root=root),
        asset("lesson", lesson_path, root=root),
        asset("timing", timing_path, root=root),
        asset("rendered_html", rendered, root=root),
        asset("practice_html", practice, root=root, required=require_practice, pending_label="pending_m4"),
    ]
    if audio_ref:
        if is_url(audio_ref):
            assets.append({
                "role": "audio",
                "path": audio_ref,
                "exists": True,
                "required": True,
                "status": "remote",
                "bytes": 0,
                "sha256": None,
            })
        else:
            assets.append(asset("audio", (timing_path.parent / audio_ref).resolve(), root=root))
    blocking_failures = [
        f"{item['role']}:{item['status']}"
        for item in assets
        if item["required"] and item["status"] not in {"ok", "remote"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "pack_id": master.get("master_id") or master_path.stem,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_score_allowed": False,
        "runtime_canonical": False,
        "grading_authority": False,
        "learner_state_write_allowed": False,
        "assets": assets,
        "blocking_failures": blocking_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("master", type=Path)
    parser.add_argument("--rendered", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-practice", action="store_true")
    args = parser.parse_args()

    manifest = build_manifest(
        args.master,
        rendered_path=args.rendered,
        require_practice=args.require_practice,
    )
    out = args.out or args.master.with_name(args.master.name.replace(".master.json", ".bundle_manifest.json"))
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if manifest["blocking_failures"]:
        print(f"{out.name}: FAIL {', '.join(manifest['blocking_failures'])}")
        return 1
    print(f"{out.name}: PASS bundle manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
