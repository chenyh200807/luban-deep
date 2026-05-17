#!/usr/bin/env python3
"""Audit docs/plan items against diff and evidence files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.plan_completion import (  # noqa: E402
    build_plan_completion_audit,
    render_plan_completion_markdown,
)


def _write_extra_artifacts(payload: dict, *, output_dir: str | None) -> dict[str, str]:
    if not output_dir:
        return {}
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{payload['run_id']}.json"
    md_path = target_dir / f"{payload['run_id']}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_plan_completion_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor plan completion audit")
    parser.add_argument("--plan", action="append", required=True, help="docs/plan markdown file to audit")
    parser.add_argument("--base-ref", default="origin/main", help="git base ref when --changed-file is omitted")
    parser.add_argument(
        "--scope-mode",
        choices=("changed", "full"),
        default="changed",
        help="changed=只审本次 diff/evidence 关联项；full=整篇 plan 全量硬审",
    )
    parser.add_argument("--changed-file", action="append", default=[], help="changed file to use instead of git diff")
    parser.add_argument("--evidence-file", action="append", default=[], help="test/runtime evidence artifact path")
    parser.add_argument("--output-dir", help="optional extra directory for raw JSON/Markdown copies")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="只生成报告，不用退出码作为 plan completion gate；默认 NOT_DONE 时非 0 退出",
    )
    args = parser.parse_args()

    payload = build_plan_completion_audit(
        plan_paths=args.plan,
        changed_files=args.changed_file or None,
        evidence_files=args.evidence_file,
        base_ref=args.base_ref,
        scope_mode=args.scope_mode,
    )
    store_paths = get_control_plane_store().write_run(
        kind="plan_completion_audits",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(render_plan_completion_markdown(payload), encoding="utf-8")
    extra_paths = _write_extra_artifacts(payload, output_dir=args.output_dir)

    summary = payload.get("summary") or {}
    print(f"Plan completion audit completed: {payload['run_id']}")
    print(f"Status: {payload['status']}")
    print(f"Scope mode: {payload['scope_mode']}")
    print(
        "Summary: "
        f"total={summary.get('total')} scoped={summary.get('scoped')} "
        f"done={summary.get('done')} "
        f"partial={summary.get('partial')} not_done={summary.get('not_done')} "
        f"unverifiable={summary.get('unverifiable')} out_of_scope={summary.get('out_of_scope')}"
    )
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")
    if extra_paths:
        print(f"Extra JSON: {extra_paths['json_path']}")
        print(f"Extra MD:   {extra_paths['md_path']}")

    if not args.report_only and payload.get("status") == "FAIL":
        raise SystemExit("plan_completion_audit_failed: not_done_items_present")


if __name__ == "__main__":
    main()
