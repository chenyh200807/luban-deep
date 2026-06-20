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
DEFAULT_RAW_PROFILE = EXTRACTIONS_ROOT / "2026-06-18-raw-data-current-profile.json"
DEFAULT_JSON_SOURCES = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "sources.jsonl"
DEFAULT_OKF_SCOPE = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "manifest.json"
DEFAULT_OKF_CASES = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "cases.jsonl"
DEFAULT_OKF_RUBRICS = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "rubrics.jsonl"
DEFAULT_OKF_POINTS = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "scoring_points.jsonl"
DEFAULT_OKF_ALIGNMENT = EXTRACTIONS_ROOT / "okf_source_alignment_v0" / "report.json"
DEFAULT_GAP_MANIFEST = EXTRACTIONS_ROOT / "asset_gap_map_v1" / "manifest.json"
DEFAULT_NEXT_ACTIONS = EXTRACTIONS_ROOT / "asset_gap_map_v1" / "next_actions.json"
DEFAULT_KNOWLEDGE_COMPILER_MANIFEST = EXTRACTIONS_ROOT / "knowledge_compiler_okf_v1" / "manifest.json"
DEFAULT_KNOWLEDGE_COMPILER_RUNS = EXTRACTIONS_ROOT / "knowledge_compiler_okf_v1" / "compiler_runs.jsonl"
DEFAULT_GRADING_ARTIFACTS_MANIFEST = EXTRACTIONS_ROOT / "luban_grading_artifacts_okf_v1" / "manifest.json"
DEFAULT_GRADING_ARTIFACTS_RUNS = EXTRACTIONS_ROOT / "luban_grading_artifacts_okf_v1" / "artifact_runs.jsonl"
DEFAULT_GOVERNANCE_MANIFEST = EXTRACTIONS_ROOT / "governance_okf_v1" / "manifest.json"
DEFAULT_GOVERNANCE_FILES = EXTRACTIONS_ROOT / "governance_okf_v1" / "governance_files.jsonl"
DEFAULT_TOPIC_MANIFEST = EXTRACTIONS_ROOT / "topic_okf_v0" / "manifest.json"
DEFAULT_TOPICS = EXTRACTIONS_ROOT / "topic_okf_v0" / "topics.jsonl"
DEFAULT_TOPIC_SOURCE_HITS = EXTRACTIONS_ROOT / "topic_okf_v0" / "source_hits.jsonl"
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError(f"JSONL row is not an object: {display_path(path)}:{line_no}")
            rows.append(data)
    if not rows:
        raise ValueError(f"required JSONL input is empty: {display_path(path)}")
    return rows


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


def short_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def jsonl_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key, "")), []).append(row)
    return grouped


def source_hashes(json_sources: list[dict[str, Any]]) -> dict[str, str]:
    hashes = {}
    for row in json_sources:
        file_info = row.get("file") or {}
        if row.get("source_path") and file_info.get("sha256"):
            hashes[str(row["source_path"])] = str(file_info["sha256"])
    return hashes


def validate_inputs(
    brief_manifest: dict[str, Any],
    okf_scope: dict[str, Any],
    okf_alignment: dict[str, Any],
    gap_manifest: dict[str, Any],
    knowledge_compiler_manifest: dict[str, Any],
    grading_artifacts_manifest: dict[str, Any],
    governance_manifest: dict[str, Any],
    topic_manifest: dict[str, Any],
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
    if knowledge_compiler_manifest.get("authority_status") != "knowledge_compiler_workbench_inventory_only":
        raise ValueError("knowledge compiler OKF must remain workbench-inventory-only")
    if (knowledge_compiler_manifest.get("runtime_guard") or {}).get("runtime_consumable") is not False:
        raise ValueError("knowledge compiler OKF cannot be runtime consumable")
    if grading_artifacts_manifest.get("authority_status") != "ai_project_context_only":
        raise ValueError("grading artifacts OKF must remain AI-context-only")
    if (grading_artifacts_manifest.get("runtime_guard") or {}).get("runtime_consumable") is not False:
        raise ValueError("grading artifacts OKF cannot be runtime consumable")
    if governance_manifest.get("authority_status") != "ai_project_context_only":
        raise ValueError("governance OKF must remain AI-context-only")
    if (governance_manifest.get("runtime_guard") or {}).get("runtime_consumable") is not False:
        raise ValueError("governance OKF cannot be runtime consumable")
    if topic_manifest.get("authority_status") != "ai_topic_navigation_only":
        raise ValueError("Topic OKF must remain AI-topic-navigation-only")
    if (topic_manifest.get("runtime_guard") or {}).get("runtime_consumable") is not False:
        raise ValueError("Topic OKF cannot be runtime consumable")


def build_okf_bundle(
    brief_manifest_path: Path = DEFAULT_BRIEF_MANIFEST,
    asset_buckets_path: Path = DEFAULT_ASSET_BUCKETS,
    raw_profile_path: Path = DEFAULT_RAW_PROFILE,
    json_sources_path: Path = DEFAULT_JSON_SOURCES,
    okf_scope_path: Path = DEFAULT_OKF_SCOPE,
    okf_cases_path: Path = DEFAULT_OKF_CASES,
    okf_rubrics_path: Path = DEFAULT_OKF_RUBRICS,
    okf_points_path: Path = DEFAULT_OKF_POINTS,
    okf_alignment_path: Path = DEFAULT_OKF_ALIGNMENT,
    gap_manifest_path: Path = DEFAULT_GAP_MANIFEST,
    next_actions_path: Path = DEFAULT_NEXT_ACTIONS,
    knowledge_compiler_manifest_path: Path = DEFAULT_KNOWLEDGE_COMPILER_MANIFEST,
    knowledge_compiler_runs_path: Path = DEFAULT_KNOWLEDGE_COMPILER_RUNS,
    grading_artifacts_manifest_path: Path = DEFAULT_GRADING_ARTIFACTS_MANIFEST,
    grading_artifacts_runs_path: Path = DEFAULT_GRADING_ARTIFACTS_RUNS,
    governance_manifest_path: Path = DEFAULT_GOVERNANCE_MANIFEST,
    governance_files_path: Path = DEFAULT_GOVERNANCE_FILES,
    topic_manifest_path: Path = DEFAULT_TOPIC_MANIFEST,
    topics_path: Path = DEFAULT_TOPICS,
    topic_source_hits_path: Path = DEFAULT_TOPIC_SOURCE_HITS,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    validate_output_root(output_root)

    brief_manifest = load_json(brief_manifest_path)
    asset_buckets_doc = load_json(asset_buckets_path)
    raw_profile = load_json(raw_profile_path)
    json_sources = load_jsonl(json_sources_path)
    okf_scope = load_json(okf_scope_path)
    okf_cases = load_jsonl(okf_cases_path)
    okf_rubrics = load_jsonl(okf_rubrics_path)
    okf_points = load_jsonl(okf_points_path)
    okf_alignment = load_json(okf_alignment_path)
    gap_manifest = load_json(gap_manifest_path)
    next_actions = load_json(next_actions_path)
    knowledge_compiler_manifest = load_json(knowledge_compiler_manifest_path)
    knowledge_compiler_runs = load_jsonl(knowledge_compiler_runs_path)
    grading_artifacts_manifest = load_json(grading_artifacts_manifest_path)
    grading_artifacts_runs = load_jsonl(grading_artifacts_runs_path)
    governance_manifest = load_json(governance_manifest_path)
    governance_files = load_jsonl(governance_files_path)
    topic_manifest = load_json(topic_manifest_path)
    topics = load_jsonl(topics_path)
    topic_source_hits = load_jsonl(topic_source_hits_path)
    validate_inputs(
        brief_manifest,
        okf_scope,
        okf_alignment,
        gap_manifest,
        knowledge_compiler_manifest,
        grading_artifacts_manifest,
        governance_manifest,
        topic_manifest,
    )

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
    assets = raw_profile.get("assets") or {}
    source_hash_by_path = source_hashes(json_sources)

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

    compiler_counts = knowledge_compiler_manifest.get("counts") or {}
    compiler_stage_counts = compiler_counts.get("by_stage") or {}
    compiler_kind_counts = compiler_counts.get("by_kind") or {}
    compiler_run_lines = [
        "# Knowledge Compiler Workbench",
        "",
        "## What It Is",
        "",
        "This card routes AI into `artifacts/knowledge_compiler/2026` without copying compiler payloads into OKF.",
        "",
        "## Counts",
        "",
        f"- Runs: {compiler_counts.get('runs')}",
        f"- Files: {compiler_counts.get('files')}",
        f"- Manifest-like files: {compiler_counts.get('manifest_like_files')}",
        f"- Total bytes: {compiler_counts.get('total_bytes')}",
        "",
        "## Stage Split",
        "",
    ]
    for stage, count in compiler_stage_counts.items():
        compiler_run_lines.append(f"- `{stage}`: {count}")
    compiler_run_lines.extend(["", "## Run Kinds", ""])
    for kind, count in compiler_kind_counts.items():
        compiler_run_lines.append(f"- `{kind}`: {count}")
    compiler_run_lines.extend(["", "## Top Runs", ""])
    for run in sorted(knowledge_compiler_runs, key=lambda item: (item.get("compiler_stage", ""), item.get("run_id", "")))[:20]:
        compiler_run_lines.append(
            f"- `{run.get('run_id')}`: stage=`{run.get('compiler_stage')}`, "
            f"kind=`{run.get('run_kind')}`, files={run.get('files')}"
        )
    compiler_run_lines.extend(
        [
            "",
            "## Use",
            "",
            "- Use candidate runs to find compiler-produced teaching cards, rubric candidates, scoring-point assets, and recall calibration material.",
            "- Use fixture runs only for test/workbench reproduction.",
            "- Treat release-named runs as release-shaped until runtime supply has a separate signed pointer.",
            "",
            "## Boundary",
            "",
            "This OKF card is a workbench navigation layer. It does not sign runtime supply, write canonical truth, or authorize official scoring.",
        ]
    )
    write_md(
        output_root / "assets" / "knowledge-compiler-workbench.md",
        {
            "type": "Concept",
            "title": "Knowledge Compiler Workbench",
            "description": "Compiler-run ledger for artifacts/knowledge_compiler with candidate/release/fixture boundaries.",
            "resource": display_path(knowledge_compiler_manifest_path),
            "tags": ["luban", "okf", "knowledge-compiler", "compiled-assets"],
            "timestamp": generated_at,
            "status": knowledge_compiler_manifest.get("authority_status"),
        },
        "\n".join(compiler_run_lines),
    )

    grading_counts = grading_artifacts_manifest.get("counts") or {}
    grading_area_counts = grading_counts.get("by_area") or {}
    grading_risk_counts = grading_counts.get("by_risk_level") or {}
    grading_lines = [
        "# Luban Grading Artifacts Map",
        "",
        "## What It Is",
        "",
        "This card helps AI understand the shape of `artifacts/luban_grading_artifacts` without treating any artifact as production truth.",
        "",
        "## Counts",
        "",
        f"- Runs: {grading_counts.get('runs')}",
        f"- Files: {grading_counts.get('files')}",
        f"- Manifest-like files: {grading_counts.get('manifest_like_files')}",
        f"- Total bytes: {grading_counts.get('total_bytes')}",
        "",
        "## Area Split",
        "",
    ]
    for area, count in grading_area_counts.items():
        grading_lines.append(f"- `{area}`: {count}")
    grading_lines.extend(["", "## Risk Split", ""])
    for risk, count in grading_risk_counts.items():
        grading_lines.append(f"- `{risk}`: {count}")
    grading_lines.extend(["", "## High-Risk Context Sample", ""])
    high_risk_runs = [run for run in grading_artifacts_runs if run.get("risk_level") == "high"]
    for run in sorted(high_risk_runs, key=lambda item: item.get("bytes", 0), reverse=True)[:20]:
        grading_lines.append(
            f"- `{run.get('run_id')}`: area=`{run.get('area')}`, files={run.get('files')}"
        )
    grading_lines.extend(
        [
            "",
            "## Use",
            "",
            "- Use this map to orient AI around grading experiments, gold reviews, source alignment, runtime-shadow evidence, and learning-brain artifacts.",
            "- Treat high-risk entries as context requiring separate verification, not as usable production supply.",
            "- Follow the ledger files when exact artifact paths are needed.",
            "",
            "## Boundary",
            "",
            "This OKF card is only for AI project understanding. It does not participate in production, does not sign runtime supply, and does not authorize official scoring.",
        ]
    )
    write_md(
        output_root / "assets" / "luban-grading-artifacts-map.md",
        {
            "type": "Concept",
            "title": "Luban Grading Artifacts Map",
            "description": "AI-only map of artifacts/luban_grading_artifacts with area and risk boundaries.",
            "resource": display_path(grading_artifacts_manifest_path),
            "tags": ["luban", "okf", "grading-artifacts", "ai-context-only"],
            "timestamp": generated_at,
            "status": grading_artifacts_manifest.get("authority_status"),
        },
        "\n".join(grading_lines),
    )

    governance_counts = governance_manifest.get("counts") or {}
    governance_domain_counts = governance_counts.get("by_domain") or {}
    governance_area_counts = governance_counts.get("by_area") or {}
    governance_risk_counts = governance_counts.get("by_risk_level") or {}
    governance_lines = [
        "# DeepTutor Governance Map",
        "",
        "## What It Is",
        "",
        "This card helps AI find the right project governance source before changing plans, contracts, runbooks, or agent behavior.",
        "",
        "## Counts",
        "",
        f"- Files: {governance_counts.get('files')}",
        f"- Total bytes: {governance_counts.get('total_bytes')}",
        "",
        "## Domain Split",
        "",
    ]
    for domain, count in governance_domain_counts.items():
        governance_lines.append(f"- `{domain}`: {count}")
    governance_lines.extend(["", "## Area Split", ""])
    for area, count in governance_area_counts.items():
        governance_lines.append(f"- `{area}`: {count}")
    governance_lines.extend(["", "## Risk Split", ""])
    for risk, count in governance_risk_counts.items():
        governance_lines.append(f"- `{risk}`: {count}")
    governance_lines.extend(["", "## Mandatory Entry Points", ""])
    entry_points = [
        row for row in governance_files
        if row.get("source_path") in {
            "docs/plan/INDEX.md",
            "contracts/index.yaml",
            "agent-skills/catalog.yaml",
        }
        or row.get("source_path", "").endswith("ci-runtime-smoke-guardrails.md")
    ]
    for row in sorted(entry_points, key=lambda item: item.get("source_path", "")):
        governance_lines.append(
            f"- `{row.get('source_path')}`: role=`{row.get('authority_role')}`, area=`{row.get('area')}`"
        )
    governance_lines.extend(
        [
            "",
            "## Use",
            "",
            "- Use this map before planning, release, CI repair, contract changes, source-grounded changes, or agent-skill work.",
            "- Follow the referenced source document for exact instructions; this card is only a router.",
            "- Treat high-risk governance documents as mandatory read-before-act context.",
            "",
            "## Boundary",
            "",
            "This OKF card is only for AI project understanding. It does not replace contracts, runbooks, plans, or skills and does not participate in production.",
        ]
    )
    write_md(
        output_root / "assets" / "governance-map.md",
        {
            "type": "Concept",
            "title": "DeepTutor Governance Map",
            "description": "AI-only map of plans, runbooks, contracts, docs/contracts, and agent-skills.",
            "resource": display_path(governance_manifest_path),
            "tags": ["deeptutor", "okf", "governance", "ai-context-only"],
            "timestamp": generated_at,
            "status": governance_manifest.get("authority_status"),
        },
        "\n".join(governance_lines),
    )

    exam_year_links = []
    for row in sorted((assets.get("exam") or {}).get("by_year") or [], key=lambda item: item["year"]):
        year = row["year"]
        source_path = f"docs/原始数据/{row['path']}"
        filename = f"year-{year}.md"
        exam_year_links.append((year, f"content_cards/exams/{filename}"))
        exercise_types = row.get("exercise_types") or {}
        stats = row.get("stats") or {}
        body = f"""# {year} 建筑实务真题

## What AI Can Understand Here

This card gives the AI a direct year-level view of the exam source: question volume, case-study coverage, and where to read the cleaned JSON.

## Structure

- Chunks: {row.get('chunks')}
- Exercises: {row.get('exercises')}
- Single choice: {exercise_types.get('single_choice')}
- Multiple choice: {exercise_types.get('multiple_choice')}
- Case study: {exercise_types.get('case_study')}
- Stats keys: {", ".join(sorted(stats.keys())) if stats else "unknown"}

## Source

- Cleaned JSON: `{source_path}`
- Source hash: `{source_hash_by_path.get(source_path, 'unknown')}`

## Use

- Use this as the entry point for year-specific exam analysis.
- Follow the source JSON for full question text, answers, and analysis.
- Use rubric case cards when candidate scoring points are needed.

## Boundary

This content card is source evidence navigation, not official scoring authority.
"""
        write_md(
            output_root / "content_cards" / "exams" / filename,
            {
                "type": "ContentCard",
                "title": f"{year} 建筑实务真题",
                "description": f"{year} cleaned exam source with question and case-study counts.",
                "resource": source_path,
                "tags": ["luban", "exam", str(year), "content-card"],
                "timestamp": generated_at,
                "status": "source_evidence_card",
                "source_hash": source_hash_by_path.get(source_path, ""),
            },
            body,
        )

    rubrics_by_case = jsonl_by_key(okf_rubrics, "case_id")
    points_by_rubric = jsonl_by_key(okf_points, "rubric_id")
    case_links = []
    for case in sorted(okf_cases, key=lambda item: item["case_id"]):
        case_id = case["case_id"]
        filename = f"{slug(case_id)}.md"
        case_links.append((case_id, f"content_cards/rubrics/{filename}"))
        source = case.get("exam_source") or {}
        source_path = source.get("source_path", "")
        question_chunk = case.get("question_chunk") or {}
        lines = [
            f"# {case_id}",
            "",
            "## What AI Can Understand Here",
            "",
            "This card exposes the case-level candidate rubric shape: source chunk, sub-question rubrics, score caps, and representative scoring points.",
            "",
            "## Source Anchor",
            "",
            f"- Exam source: `{source_path}`",
            f"- Source hash: `{source.get('file_sha256', '')}`",
            f"- Chunk: `{question_chunk.get('chunk_id', '')}`",
            f"- Anchor: {question_chunk.get('anchor', '')}",
            f"- Page: {question_chunk.get('page', '')}",
            "",
            "## Rubrics",
            "",
        ]
        for rubric in sorted(rubrics_by_case.get(case_id, []), key=lambda item: item["rubric_id"]):
            lines.append(
                f"### {rubric['rubric_id']} - sub-question {rubric.get('sub_question')} "
                f"({rubric.get('sub_q_total_score')} pts)"
            )
            lines.append("")
            lines.append(f"- Judge rule: {rubric.get('judge_rule')}")
            lines.append(f"- Source path: `{rubric.get('source_json_path')}`")
            lines.append("- Candidate scoring points:")
            for point in points_by_rubric.get(rubric["rubric_id"], [])[:8]:
                lines.append(
                    f"  - `{point.get('point_id')}` [{point.get('point_type')}, "
                    f"{point.get('point_score')} pt]: {short_text(point.get('text'), 180)}"
                )
            lines.append("")
        lines.extend(
            [
                "## Boundary",
                "",
                "This is candidate scoring knowledge from source-layer extraction. It is not a signed grading artifact and not official score authority.",
            ]
        )
        write_md(
            output_root / "content_cards" / "rubrics" / filename,
            {
                "type": "ContentCard",
                "title": case_id,
                "description": f"Candidate rubric content card for {case_id}.",
                "resource": source_path,
                "tags": ["luban", "rubric", "case", case_id, "content-card"],
                "timestamp": generated_at,
                "status": "candidate_source_card",
                "official_score_allowed": False,
            },
            "\n".join(lines),
        )

    textbook = assets.get("textbook") or {}
    textbook_lines = [
        "# 2026 教材结构化内容",
        "",
        "## What AI Can Understand Here",
        "",
        "This card summarizes the structured textbook source and points the AI to the fixed JSON blocks instead of copying the full textbook into OKF.",
        "",
        "## Fixed Source Files",
        "",
        f"- Total fixed content blocks: {textbook.get('v3_fixed_content_blocks')}",
    ]
    for row in textbook.get("v3_fixed") or []:
        source_path = f"docs/原始数据/{row['path']}"
        meta = row.get("meta") or {}
        textbook_lines.append(
            f"- `{source_path}`: {row.get('content_blocks')} blocks, "
            f"subject={meta.get('subject')}, version={meta.get('version')}"
        )
    textbook_lines.extend(
        [
            "",
            "## Use",
            "",
            "- Use this card to locate textbook grounding sources.",
            "- Read the source JSON only when a task needs exact paragraph-level evidence.",
            "",
            "## Boundary",
            "",
            "This card is a curated source map, not a full textbook mirror.",
        ]
    )
    write_md(
        output_root / "content_cards" / "textbooks" / "textbook-2026.md",
        {
            "type": "ContentCard",
            "title": "2026 教材结构化内容",
            "description": "Structured 2026 textbook source files and content-block coverage.",
            "resource": "docs/原始数据/2026_副本/2026教材/第二次加强",
            "tags": ["luban", "textbook", "2026", "content-card"],
            "timestamp": generated_at,
            "status": "source_evidence_card",
        },
        "\n".join(textbook_lines),
    )

    standard_links = []
    for row in sorted((assets.get("standards") or {}).get("rows") or [], key=lambda item: item["title"]):
        filename = f"{slug(row['title'])}.md"
        source_path = f"docs/原始数据/{row['path']}"
        standard_links.append((row["title"], f"content_cards/standards/{filename}"))
        body = f"""# {row['title']}

## What AI Can Understand Here

This card identifies a structured standard/specification source and its node coverage.

## Structure

- Nodes: {row.get('nodes')}
- Content blocks: {row.get('content_blocks')}
- Unmatched nodes: {row.get('unmatched_nodes')}
- Top keys: {", ".join(row.get('keys') or [])}

## Source

- JSON: `{source_path}`
- Source hash: `{source_hash_by_path.get(source_path, 'unknown')}`

## Boundary

Use this as standard evidence navigation. Do not treat it as exam rubric or official scoring authority.
"""
        write_md(
            output_root / "content_cards" / "standards" / filename,
            {
                "type": "ContentCard",
                "title": row["title"],
                "description": f"Structured standard source with {row.get('nodes')} nodes.",
                "resource": source_path,
                "tags": ["luban", "standard", "content-card"],
                "timestamp": generated_at,
                "status": "source_evidence_card",
                "source_hash": source_hash_by_path.get(source_path, ""),
            },
            body,
        )

    lecture_links = []
    for row in sorted((assets.get("lectures") or {}).get("rows") or [], key=lambda item: item["name"]):
        filename = f"{slug(row['name'])}.md"
        source_path = f"docs/原始数据/{row['path']}"
        lecture_links.append((row["name"], f"content_cards/lectures/{filename}"))
        body = f"""# {row['name']}

## What AI Can Understand Here

This card identifies one lecture package and its page-level JSON coverage.

## Structure

- Page JSON files: {row.get('page_json')}
- Aggregate JSON files: {row.get('aggregate_json')}
- Sample pages: {", ".join(row.get('sample_pages') or [])}

## Source

- Package path: `{source_path}`

## Use

Use lecture cards for teacher-expression style, worked examples, and topic explanation material. Prefer textbook/standard cards for source authority.

## Boundary

Lecture material is teaching evidence, not textbook authority and not official scoring authority.
"""
        write_md(
            output_root / "content_cards" / "lectures" / filename,
            {
                "type": "ContentCard",
                "title": row["name"],
                "description": "Lecture package with page-level JSON coverage.",
                "resource": source_path,
                "tags": ["luban", "lecture", "content-card"],
                "timestamp": generated_at,
                "status": "teaching_evidence_card",
            },
            body,
        )

    practice_links = []
    for name, row in sorted((assets.get("practice") or {}).items()):
        filename = f"{slug(name)}.md"
        source_path = f"docs/原始数据/{row['path']}"
        practice_links.append((name, f"content_cards/practice/{filename}"))
        exercise_types = row.get("exercise_types") or {}
        body = f"""# {name} 章节练习库

## What AI Can Understand Here

This card summarizes one objective-practice source for drill generation, answer checking, and weak-point explanation.

## Structure

- Chunks: {row.get('chunks')}
- Exercises: {row.get('exercises')}
- Single choice: {exercise_types.get('single_choice')}
- Multiple choice: {exercise_types.get('multi_choice')}
- Correct answers available: {row.get('correct_answer_nonempty')}
- Analysis available: {row.get('analysis_nonempty')}

## Source

- JSON: `{source_path}`
- Source hash: `{source_hash_by_path.get(source_path, 'unknown')}`

## Boundary

Use this as practice source evidence. It does not replace exam source evidence or official scoring authority.
"""
        write_md(
            output_root / "content_cards" / "practice" / filename,
            {
                "type": "ContentCard",
                "title": f"{name} 章节练习库",
                "description": f"Objective practice source with {row.get('exercises')} exercises.",
                "resource": source_path,
                "tags": ["luban", "practice", name.lower(), "content-card"],
                "timestamp": generated_at,
                "status": "practice_source_card",
                "source_hash": source_hash_by_path.get(source_path, ""),
            },
            body,
        )

    topic_links = []
    hits_by_topic = jsonl_by_key(topic_source_hits, "topic_id")
    for topic in sorted(topics, key=lambda item: item["topic_id"]):
        topic_id = topic["topic_id"]
        filename = f"{slug(topic_id)}.md"
        topic_links.append((topic.get("title", topic_id), f"topics/{filename}"))
        evidence = topic.get("evidence_summary") or {}
        candidate_rubric = evidence.get("candidate_rubric") or {}
        bucket_counts = evidence.get("bucket_hit_counts") or {}
        topic_lines = [
            f"# {topic.get('title', topic_id)}",
            "",
            "## What AI Can Answer Better",
            "",
            str(topic.get("question_intent") or "Topic-level source navigation."),
            "",
            "## Evidence Shape",
            "",
            f"- Raw source hits: {evidence.get('source_hit_count')}",
            f"- Source files: {evidence.get('source_count')}",
            f"- Candidate scoring points: {candidate_rubric.get('candidate_scoring_point_count')}",
            f"- Candidate cases: {candidate_rubric.get('case_count')}",
            f"- Candidate years: {', '.join(candidate_rubric.get('years') or []) or 'none'}",
            "",
            "## Source Buckets",
            "",
        ]
        for bucket, count in sorted(bucket_counts.items()):
            topic_lines.append(f"- `{bucket}`: {count} hits")
        topic_lines.extend(["", "## Aliases", ""])
        for alias in topic.get("aliases") or []:
            topic_lines.append(f"- {alias}")
        topic_lines.extend(["", "## Representative Candidate Scoring Points", ""])
        for point in candidate_rubric.get("representative_points") or []:
            topic_lines.append(
                f"- `{point.get('point_id')}` ({point.get('case_id')}, {point.get('year')}): "
                f"{short_text(point.get('text'), 180)}"
            )
        if not candidate_rubric.get("representative_points"):
            topic_lines.append("- No candidate scoring-point hit in current OKF candidate scope.")
        topic_lines.extend(["", "## Representative Source Hits", ""])
        for hit in hits_by_topic.get(topic_id, [])[:12]:
            topic_lines.append(
                f"- `{hit.get('bucket')}` `{hit.get('source_path')}` at `{hit.get('json_path')}`: "
                f"{short_text(hit.get('snippet'), 180)}"
            )
        topic_lines.extend(
            [
                "",
                "## How To Use",
                "",
                "- Use this card first when the user asks about this topic across exams, textbooks, standards, lectures, or practice sources.",
                "- Follow source paths for exact wording before making high-stakes claims.",
                "- Treat candidate scoring-point counts as candidate evidence, not official exam-frequency truth.",
                "",
                "## Boundary",
                "",
                "This Topic OKF card is AI navigation and synthesis support only. It is not runtime supply, not official scoring authority, and not a full source mirror.",
            ]
        )
        write_md(
            output_root / "topics" / filename,
            {
                "type": "TopicCard",
                "title": topic.get("title", topic_id),
                "description": topic.get("question_intent", ""),
                "resource": display_path(topics_path),
                "tags": ["luban", "okf", "topic", topic_id],
                "timestamp": generated_at,
                "status": topic.get("authority_status"),
                "runtime_consumable": False,
                "official_score_allowed": False,
            },
            "\n".join(topic_lines),
        )

    topic_index_lines = [
        "# Topic OKF v0",
        "",
        "These topic cards move the OKF bundle from asset discovery toward stable AI question-answer context.",
        "",
        "## Topics",
        "",
    ]
    for title, link in topic_links:
        topic_index_lines.append(f"- [{title}]({link.replace('topics/', '')})")
    topic_index_lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Topic OKF is AI-only source navigation. It does not participate in production runtime, official scoring, LearnerState, or GBrain writes.",
        ]
    )
    write_md(
        output_root / "topics" / "index.md",
        {
            "type": "BundleIndex",
            "title": "Topic OKF v0",
            "description": "AI-only topic cards for high-frequency Luban 建筑实务 themes.",
            "resource": display_path(topic_manifest_path),
            "tags": ["luban", "okf", "topic"],
            "timestamp": generated_at,
            "status": topic_manifest.get("status"),
        },
        "\n".join(topic_index_lines),
    )

    content_index_lines = [
        "# OKF Content Cards v0",
        "",
        "These are L1 curated content cards. They make core assets directly scannable without mirroring full JSON/PDF source files into OKF.",
        "",
        "## Exams",
        "",
    ]
    for year, link in exam_year_links:
        content_index_lines.append(f"- [{year} 建筑实务真题]({link.replace('content_cards/', '')})")
    content_index_lines.extend(["", "## Candidate Case Rubrics", ""])
    for case_id, link in case_links:
        content_index_lines.append(f"- [{case_id}]({link.replace('content_cards/', '')})")
    content_index_lines.extend(["", "## Textbooks", "", "- [2026 教材结构化内容](textbooks/textbook-2026.md)", "", "## Standards", ""])
    for title, link in standard_links:
        content_index_lines.append(f"- [{title}]({link.replace('content_cards/', '')})")
    content_index_lines.extend(["", "## Lectures", ""])
    for title, link in lecture_links:
        content_index_lines.append(f"- [{title}]({link.replace('content_cards/', '')})")
    content_index_lines.extend(["", "## Practice", ""])
    for title, link in practice_links:
        content_index_lines.append(f"- [{title} 章节练习库]({link.replace('content_cards/', '')})")
    content_index_lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Content cards summarize and route. They do not copy full source payloads, sign runtime supply, or authorize official scoring.",
        ]
    )
    write_md(
        output_root / "content_cards" / "index.md",
        {
            "type": "BundleIndex",
            "title": "OKF Content Cards v0",
            "description": "L1 curated content cards for core Luban data assets.",
            "resource": display_path(output_root / "content_cards"),
            "tags": ["luban", "okf", "content-card"],
            "timestamp": generated_at,
            "status": "curated_content_cards",
        },
        "\n".join(content_index_lines),
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
- L1 content cards: `{len(exam_year_links) + len(case_links) + len(standard_links) + len(lecture_links) + len(practice_links) + 2}` markdown files.
- Topic cards: `{len(topic_links)}` markdown files.
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
        "- [L1 content cards](content_cards/index.md)",
        "- [Topic OKF cards](topics/index.md)",
        "- [Knowledge compiler workbench](assets/knowledge-compiler-workbench.md)",
        "- [Luban grading artifacts map](assets/luban-grading-artifacts-map.md)",
        "- [DeepTutor governance map](assets/governance-map.md)",
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
            "OKF here means Markdown + YAML frontmatter + links. L1 content cards summarize and route into source evidence; they do not mirror full source payloads. Signing, runtime pointer policy, official scoring, LearnerState, and GBrain writes are DeepTutor governance layers, not OKF format requirements.",
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
    parser.add_argument("--raw-profile", type=Path, default=DEFAULT_RAW_PROFILE)
    parser.add_argument("--json-sources", type=Path, default=DEFAULT_JSON_SOURCES)
    parser.add_argument("--okf-scope", type=Path, default=DEFAULT_OKF_SCOPE)
    parser.add_argument("--okf-cases", type=Path, default=DEFAULT_OKF_CASES)
    parser.add_argument("--okf-rubrics", type=Path, default=DEFAULT_OKF_RUBRICS)
    parser.add_argument("--okf-points", type=Path, default=DEFAULT_OKF_POINTS)
    parser.add_argument("--okf-alignment", type=Path, default=DEFAULT_OKF_ALIGNMENT)
    parser.add_argument("--gap-manifest", type=Path, default=DEFAULT_GAP_MANIFEST)
    parser.add_argument("--next-actions", type=Path, default=DEFAULT_NEXT_ACTIONS)
    parser.add_argument("--knowledge-compiler-manifest", type=Path, default=DEFAULT_KNOWLEDGE_COMPILER_MANIFEST)
    parser.add_argument("--knowledge-compiler-runs", type=Path, default=DEFAULT_KNOWLEDGE_COMPILER_RUNS)
    parser.add_argument("--grading-artifacts-manifest", type=Path, default=DEFAULT_GRADING_ARTIFACTS_MANIFEST)
    parser.add_argument("--grading-artifacts-runs", type=Path, default=DEFAULT_GRADING_ARTIFACTS_RUNS)
    parser.add_argument("--governance-manifest", type=Path, default=DEFAULT_GOVERNANCE_MANIFEST)
    parser.add_argument("--governance-files", type=Path, default=DEFAULT_GOVERNANCE_FILES)
    parser.add_argument("--topic-manifest", type=Path, default=DEFAULT_TOPIC_MANIFEST)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--topic-source-hits", type=Path, default=DEFAULT_TOPIC_SOURCE_HITS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_okf_bundle(
        brief_manifest_path=args.brief_manifest,
        asset_buckets_path=args.asset_buckets,
        raw_profile_path=args.raw_profile,
        json_sources_path=args.json_sources,
        okf_scope_path=args.okf_scope,
        okf_cases_path=args.okf_cases,
        okf_rubrics_path=args.okf_rubrics,
        okf_points_path=args.okf_points,
        okf_alignment_path=args.okf_alignment,
        gap_manifest_path=args.gap_manifest,
        next_actions_path=args.next_actions,
        knowledge_compiler_manifest_path=args.knowledge_compiler_manifest,
        knowledge_compiler_runs_path=args.knowledge_compiler_runs,
        grading_artifacts_manifest_path=args.grading_artifacts_manifest,
        grading_artifacts_runs_path=args.grading_artifacts_runs,
        governance_manifest_path=args.governance_manifest,
        governance_files_path=args.governance_files,
        topic_manifest_path=args.topic_manifest,
        topics_path=args.topics,
        topic_source_hits_path=args.topic_source_hits,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(f"wrote {len(result['files'])} OKF markdown files to {display_path(result['output_root'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
