#!/usr/bin/env python3
"""Build a minimal OKF bundle as Markdown files with YAML frontmatter."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_BRIEF_MANIFEST = EXTRACTIONS_ROOT / "data_asset_brief_v1" / "manifest.json"
DEFAULT_ASSET_BUCKETS = EXTRACTIONS_ROOT / "data_asset_brief_v1" / "asset_buckets.json"
DEFAULT_OKF_SCOPE = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "manifest.json"
DEFAULT_OKF_ALIGNMENT = EXTRACTIONS_ROOT / "okf_source_alignment_v0" / "report.json"
DEFAULT_GAP_MANIFEST = EXTRACTIONS_ROOT / "asset_gap_map_v1" / "manifest.json"
DEFAULT_NEXT_ACTIONS = EXTRACTIONS_ROOT / "asset_gap_map_v1" / "next_actions.json"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "okf_bundle_v0"
OUTPUT_ROOT_SUFFIX = ("数据盘点", "okf_bundle_v0")
GENERATOR = "build_okf_bundle.py"


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"required input is not a JSON object: {display_path(path)}")
    return data


def resolve_soft(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def validate_output_root(path: Path) -> None:
    resolved = resolve_soft(path)
    controlled_roots = {
        INVENTORY_ROOT.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        EXTRACTIONS_ROOT.resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"missing YAML frontmatter: {display_path(path)}")
    _, body = text.split("---\n", 1)
    frontmatter, _ = body.split("---\n", 1)
    result: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if not line or line.startswith("  - "):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    log = path / "log.md"
    if not log.exists():
        raise ValueError(f"missing generated log: {display_path(log)}")
    frontmatter = parse_frontmatter(log)
    if frontmatter.get("generated_by") != GENERATOR or frontmatter.get("type") != "Log":
        raise ValueError(f"invalid generated log: {display_path(log)}")
    for child in path.rglob("*"):
        if child.is_file() and child.suffix != ".md":
            raise ValueError(f"OKF bundle must be markdown-only: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def write_md(path: Path, fields: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter(fields) + body.rstrip() + "\n", encoding="utf-8")


def slug(value: str) -> str:
    allowed = []
    for char in value.lower().replace("_", "-"):
        if char.isalnum() or char == "-":
            allowed.append(char)
        else:
            allowed.append("-")
    result = "".join(allowed).strip("-")
    while "--" in result:
        result = result.replace("--", "-")
    return result or "item"


def row_count(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def validate_inputs(
    brief_manifest: dict[str, Any],
    okf_scope: dict[str, Any],
    okf_alignment: dict[str, Any],
    gap_manifest: dict[str, Any],
) -> None:
    if brief_manifest.get("authority_status") != "asset_inventory_only":
        raise ValueError("data asset brief must remain asset_inventory_only")
    if (brief_manifest.get("runtime_guard") or {}).get("runtime_consumable") is not False:
        raise ValueError("data asset brief cannot be runtime consumable")
    if okf_scope.get("status") != "source_layer_candidate_complete":
        raise ValueError("OKF candidate scope is not complete")
    if okf_alignment.get("status") != "case_source_alignment_ready":
        raise ValueError("OKF source alignment is not ready")
    if gap_manifest.get("authority_status") != "asset_gap_map_only":
        raise ValueError("asset gap map must remain gap-map-only")


def build_okf_bundle(
    brief_manifest_path: Path = DEFAULT_BRIEF_MANIFEST,
    asset_buckets_path: Path = DEFAULT_ASSET_BUCKETS,
    okf_scope_path: Path = DEFAULT_OKF_SCOPE,
    okf_alignment_path: Path = DEFAULT_OKF_ALIGNMENT,
    gap_manifest_path: Path = DEFAULT_GAP_MANIFEST,
    next_actions_path: Path = DEFAULT_NEXT_ACTIONS,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    validate_output_root(output_root)

    brief_manifest = load_json(brief_manifest_path)
    asset_buckets_doc = load_json(asset_buckets_path)
    okf_scope = load_json(okf_scope_path)
    okf_alignment = load_json(okf_alignment_path)
    gap_manifest = load_json(gap_manifest_path)
    next_actions = load_json(next_actions_path)
    validate_inputs(brief_manifest, okf_scope, okf_alignment, gap_manifest)

    buckets = asset_buckets_doc.get("asset_buckets")
    if not isinstance(buckets, list) or not buckets:
        raise ValueError("asset_buckets.json must contain non-empty asset_buckets")
    actions = next_actions.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("next_actions.json must contain non-empty actions")

    assert_generated_tree(output_root)
    reset_dir(output_root)

    totals = brief_manifest.get("totals") or {}
    okf_counts = okf_scope.get("counts") or {}
    alignment_counts = okf_alignment.get("counts") or {}
    gap_counts = gap_manifest.get("counts") or {}

    bucket_links = []
    for bucket in buckets:
        bucket_id = str(bucket["id"])
        filename = f"{slug(bucket_id)}.md"
        bucket_links.append((bucket, f"assets/{filename}"))
        body = f"""# {bucket.get('label', bucket_id)}

## What It Is

{bucket.get('ai_use', 'AI-readable asset bucket.')}

## Counts

- Count: {row_count(bucket.get('count'))} {bucket.get('unit', '')}
- Readiness: `{bucket.get('readiness', 'unknown')}`
- Authority status: `{bucket.get('authority_status', 'unknown')}`
- Primary entry: `{bucket.get('primary_entry', 'unknown')}`

## Boundary

This OKF concept is a Markdown navigation card. It does not sign runtime supply, write learner truth, or authorize official scoring.
"""
        write_md(
            output_root / "assets" / filename,
            {
                "type": "Concept",
                "title": bucket.get("label", bucket_id),
                "description": bucket.get("ai_use", ""),
                "resource": bucket.get("primary_entry", ""),
                "tags": ["luban", "asset", bucket_id],
                "timestamp": generated_at,
                "status": "source_navigation",
            },
            body,
        )

    write_md(
        output_root / "okf" / "candidate-scope.md",
        {
            "type": "Concept",
            "title": "OKF Candidate Scope v0",
            "description": "Source-layer candidate cases, rubrics, and scoring points.",
            "resource": display_path(okf_scope_path),
            "tags": ["luban", "okf", "rubric", "candidate"],
            "timestamp": generated_at,
            "status": okf_scope.get("status"),
        },
        f"""# OKF Candidate Scope v0

## Counts

- Cases: {okf_counts.get('cases')}
- Rubrics: {okf_counts.get('rubrics')}
- Scoring points: {okf_counts.get('scoring_points')}

## Boundary

This is candidate source-layer knowledge. It is not a signed release and not official scoring authority.

## Related

- [Source alignment](source-alignment.md)
- [Asset gaps](../gaps/asset-gap-map.md)
""",
    )

    write_md(
        output_root / "okf" / "source-alignment.md",
        {
            "type": "Concept",
            "title": "OKF Source Alignment v0",
            "description": "Alignment between candidate OKF cases and cleaned exam source chunks.",
            "resource": display_path(okf_alignment_path),
            "tags": ["luban", "okf", "source-alignment"],
            "timestamp": generated_at,
            "status": okf_alignment.get("status"),
        },
        f"""# OKF Source Alignment v0

## Counts

- Target cases: {alignment_counts.get('target_cases')}
- Aligned cases: {alignment_counts.get('aligned_cases')}
- Ordinal sub-question matches: {alignment_counts.get('ordinal_subquestion_matches')}
- Case-level-only matches: {alignment_counts.get('case_level_only')}

## Boundary

Alignment helps AI follow evidence links. It does not promote candidate knowledge into runtime truth.

## Related

- [Candidate scope](candidate-scope.md)
- [Asset gaps](../gaps/asset-gap-map.md)
""",
    )

    gap_body = [
        "# Asset Gap Map v1",
        "",
        "## Counts",
        "",
        f"- Open gap items: {gap_counts.get('open_gap_items')}",
        f"- P1 gaps: {(gap_counts.get('by_priority') or {}).get('P1')}",
        f"- P2 gaps: {(gap_counts.get('by_priority') or {}).get('P2')}",
        "",
        "## Next Actions",
        "",
    ]
    for action in actions:
        gap_body.append(
            f"- P{action.get('priority', '')}: `{action.get('gap_id')}` "
            f"({action.get('affected_count')} affected) - {action.get('action')}"
        )
    gap_body.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a navigation concept for gaps. The OKF bundle stays Markdown-first; release signing remains outside the OKF format.",
        ]
    )
    write_md(
        output_root / "gaps" / "asset-gap-map.md",
        {
            "type": "Concept",
            "title": "Asset Gap Map v1",
            "description": "Known gaps before candidate knowledge can become signed runtime supply.",
            "resource": display_path(gap_manifest_path),
            "tags": ["luban", "okf", "gap-map"],
            "timestamp": generated_at,
            "status": gap_manifest.get("authority_status"),
        },
        "\n".join(gap_body),
    )

    write_md(
        output_root / "log.md",
        {
            "type": "Log",
            "title": "OKF Bundle Generation Log",
            "description": "Generated markdown-only OKF bundle log.",
            "resource": display_path(output_root),
            "tags": ["luban", "okf", "generated"],
            "timestamp": generated_at,
            "generated_by": GENERATOR,
            "status": "markdown_yaml_only",
        },
        f"""# Generation Log

- Generated at: `{generated_at}`
- Generator: `{GENERATOR}`
- Output root: `{display_path(output_root)}`
- Format boundary: Markdown files with YAML frontmatter only.
- Runtime boundary: no runtime supply, no official score authority, no LearnerState/GBrain writes.
""",
    )

    index_lines = [
        "# Luban OKF Bundle v0",
        "",
        "This is the minimal OKF shape for Luban data assets: Markdown files with YAML frontmatter and links.",
        "",
        "## Core Counts",
        "",
        f"- Raw asset files: {totals.get('raw_asset_files')}",
        f"- Cleaned JSON sources: {totals.get('cleaned_json_sources')}",
        f"- PDF files: {totals.get('pdf_files')}",
        f"- Compiled asset files: {totals.get('compiled_asset_files')}",
        f"- Candidate cases / rubrics / scoring points: {okf_counts.get('cases')} / {okf_counts.get('rubrics')} / {okf_counts.get('scoring_points')}",
        "",
        "## OKF Concepts",
        "",
        "- [OKF candidate scope](okf/candidate-scope.md)",
        "- [OKF source alignment](okf/source-alignment.md)",
        "- [Asset gap map](gaps/asset-gap-map.md)",
        "",
        "## Asset Buckets",
        "",
    ]
    for bucket, link in bucket_links:
        index_lines.append(f"- [{bucket.get('label', bucket.get('id'))}]({link})")
    index_lines.extend(
        [
            "",
            "## Format Boundary",
            "",
            "OKF here means Markdown + YAML frontmatter + links. Signing, runtime pointer policy, official scoring, LearnerState, and GBrain writes are DeepTutor governance layers, not OKF format requirements.",
            "",
            "## Generation",
            "",
            "- [Generation log](log.md)",
        ]
    )
    write_md(
        output_root / "index.md",
        {
            "type": "BundleIndex",
            "title": "Luban OKF Bundle v0",
            "description": "Minimal markdown-and-yaml OKF navigation bundle for Luban data assets.",
            "resource": display_path(output_root),
            "tags": ["luban", "okf", "asset-inventory"],
            "timestamp": generated_at,
            "status": "markdown_yaml_only",
        },
        "\n".join(index_lines),
    )

    files = sorted(path.relative_to(output_root).as_posix() for path in output_root.rglob("*.md"))
    return {"output_root": output_root, "files": files}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief-manifest", type=Path, default=DEFAULT_BRIEF_MANIFEST)
    parser.add_argument("--asset-buckets", type=Path, default=DEFAULT_ASSET_BUCKETS)
    parser.add_argument("--okf-scope", type=Path, default=DEFAULT_OKF_SCOPE)
    parser.add_argument("--okf-alignment", type=Path, default=DEFAULT_OKF_ALIGNMENT)
    parser.add_argument("--gap-manifest", type=Path, default=DEFAULT_GAP_MANIFEST)
    parser.add_argument("--next-actions", type=Path, default=DEFAULT_NEXT_ACTIONS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_okf_bundle(
        brief_manifest_path=args.brief_manifest,
        asset_buckets_path=args.asset_buckets,
        okf_scope_path=args.okf_scope,
        okf_alignment_path=args.okf_alignment,
        gap_manifest_path=args.gap_manifest,
        next_actions_path=args.next_actions,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(f"wrote {len(result['files'])} OKF markdown files to {display_path(result['output_root'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
