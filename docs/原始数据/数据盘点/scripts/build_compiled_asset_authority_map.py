#!/usr/bin/env python3
"""Build an authority map for compiled artifacts and runtime supply."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_COMPILED_LEDGER_ROOT = EXTRACTIONS_ROOT / "compiled_asset_ledger_v1"
DEFAULT_COMPILED_LEDGER_MANIFEST = DEFAULT_COMPILED_LEDGER_ROOT / "manifest.json"
DEFAULT_COMPILED_ASSET_GROUPS = DEFAULT_COMPILED_LEDGER_ROOT / "asset_groups.json"
DEFAULT_COMPILED_FILES = DEFAULT_COMPILED_LEDGER_ROOT / "files.jsonl"
DEFAULT_RUNTIME_SUPPLY_ROOT = REPO_ROOT / "deeptutor" / "services" / "construction_grading" / "runtime_supply"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "compiled_asset_authority_map_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "compiled_asset_authority_map_v1")
SENTINEL_NAME = ".compiled_asset_authority_map_generated.json"

RUNTIME_GUARD = {
    "release_stage": "compiled_asset_authority_map_only",
    "runtime_consumable": False,
    "canonical_write_allowed": False,
    "learner_truth_write_allowed": False,
    "gbrain_write_allowed": False,
    "production_registry_write_allowed": False,
    "official_score_allowed": False,
}


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


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
        EXTRACTIONS_ROOT.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        EXTRACTIONS_ROOT.resolve(),
        DEFAULT_COMPILED_LEDGER_ROOT.resolve(),
        DEFAULT_RUNTIME_SUPPLY_ROOT.resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON input: {display_path(path)}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid JSON object input: {display_path(path)}")
    return data


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL input at {display_path(path)}:{line_no}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"invalid JSONL object at {display_path(path)}:{line_no}")
        records.append(data)
    return records


def load_compiled_ledger_manifest(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema") != "luban_compiled_asset_ledger_manifest.v1":
        raise ValueError(f"invalid compiled asset ledger schema: {display_path(path)}")
    if data.get("authority_status") != "compiled_asset_inventory_only":
        raise ValueError(f"invalid compiled asset ledger authority: {display_path(path)}")
    guard = data.get("runtime_guard") or {}
    if guard.get("runtime_consumable") is not False or guard.get("official_score_allowed") is not False:
        raise ValueError(f"invalid compiled asset ledger runtime guard: {display_path(path)}")
    return data


def load_asset_groups(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if data.get("schema") != "luban_compiled_asset_groups.v1":
        raise ValueError(f"invalid compiled asset groups schema: {display_path(path)}")
    groups = data.get("asset_groups")
    if not isinstance(groups, list):
        raise ValueError(f"invalid compiled asset groups payload: {display_path(path)}")
    return groups


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_compiled_asset_authority_map.py"
        or sentinel.get("kind") != "compiled_asset_authority_map"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed_files = {
        "manifest.json",
        "group_authority.json",
        "runtime_pointers.jsonl",
        "consumer_policy.json",
        "summary.md",
        SENTINEL_NAME,
    }
    for child in path.iterdir():
        if child.name not in allowed_files or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "compiled_asset_authority_map",
        "generated_by": "build_compiled_asset_authority_map.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def source_path_to_path(source_path: str) -> Path:
    path = Path(source_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def group_policy(group: str, group_kind: str) -> dict[str, Any]:
    forbidden = [
        "official_score",
        "learner_truth_writer",
        "gbrain_writer",
        "production_registry_writer",
        "runtime_default_without_pointer_gate",
    ]
    if group == "runtime_supply":
        return {
            "authority_class": "runtime_supply_pointer_gated",
            "owner_authority": "runtime_supply_publisher",
            "llm_role": "summarize published/candidate status; do not promote truth",
            "deterministic_gate": "per canonical pointer: published/status/hash/schema/consumer gate",
            "direct_runtime_read_allowed": False,
            "allowed_consumers": [
                "asset_inventory_agent",
                "runtime_consumer_only_after_runtime_pointers_gate",
            ],
            "forbidden_consumers": forbidden,
            "use_rule": "Do not consume the group as a whole; inspect runtime_pointers.jsonl and the referenced canonical pointer first.",
        }
    if group in {
        "artifacts/luban_consensus_gold",
        "artifacts/luban_human_validation_v1",
        "artifacts/assessment_testset",
        "artifacts/assessment_flywheel",
        "artifacts/qa",
        "artifacts/security",
    }:
        return {
            "authority_class": "review_or_audit_evidence_read_only",
            "owner_authority": "review_or_qa_workbench",
            "llm_role": "critique, compare, summarize review evidence",
            "deterministic_gate": "cannot become runtime supply without source validation and release signing",
            "direct_runtime_read_allowed": False,
            "allowed_consumers": ["asset_inventory_agent", "compiler_reviewer", "qa_reviewer"],
            "forbidden_consumers": forbidden,
            "use_rule": "Use as evidence for review, never as canonical source or runtime packet.",
        }
    if group in {
        "artifacts/luban_case_family_assets",
        "artifacts/luban-posters",
        "artifacts/luban-usage-infographic-v1",
        "artifacts/onboarding_motion_qa_20260612",
    }:
        return {
            "authority_class": "multimedia_or_product_candidate_read_only",
            "owner_authority": "product_asset_workbench",
            "llm_role": "organize candidate visual/product assets and extract metadata",
            "deterministic_gate": "visual QA, source provenance, release packaging",
            "direct_runtime_read_allowed": False,
            "allowed_consumers": ["asset_inventory_agent", "product_reviewer"],
            "forbidden_consumers": forbidden,
            "use_rule": "Use for inspection and product asset planning, not teaching/score truth.",
        }
    if group in {
        "artifacts/knowledge_compiler",
        "artifacts/luban_grading_artifacts",
        "artifacts/luban_agentic_grading_harness",
        "artifacts/luban_case_grading_three_arms",
        "artifacts/luban_no_human_v1_5",
        "artifacts/luban_typed_policy",
        "artifacts/luban_knowql_nexus_three_arm_ab",
    }:
        return {
            "authority_class": "candidate_compiler_workbench_read_only",
            "owner_authority": "compiler_or_skill_kernel_required",
            "llm_role": "extract, align, critique, and propose candidate knowledge/rubric structures",
            "deterministic_gate": "schema validation, source hash, adversarial review, signed release, rollback pointer",
            "direct_runtime_read_allowed": False,
            "allowed_consumers": ["asset_inventory_agent", "compiler_worker", "compiler_reviewer"],
            "forbidden_consumers": forbidden,
            "use_rule": "LLMs may organize candidates here; runtime may only consume a signed packet emitted downstream.",
        }
    return {
        "authority_class": "auxiliary_artifact_or_report_read_only",
        "owner_authority": "local_artifact_owner_unknown",
        "llm_role": "summarize and classify only",
        "deterministic_gate": "manual owner review before any promotion",
        "direct_runtime_read_allowed": False,
        "allowed_consumers": ["asset_inventory_agent"],
        "forbidden_consumers": forbidden,
        "use_rule": "Treat as inventory/audit evidence until a named owner signs a downstream artifact.",
    }


def build_group_authority(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in sorted(groups, key=lambda item: item.get("asset_group", "")):
        group = str(row.get("asset_group", ""))
        kind = str(row.get("group_kind", ""))
        policy = group_policy(group, kind)
        rows.append(
            {
                "schema": "luban_compiled_asset_group_authority.v1",
                "asset_group": group,
                "group_kind": kind,
                "files": row.get("files"),
                "bytes": row.get("bytes"),
                "manifest_like_files": row.get("manifest_like_files"),
                "ledger_authority_status": row.get("authority_status"),
                "authority_class": policy["authority_class"],
                "owner_authority": policy["owner_authority"],
                "llm_role": policy["llm_role"],
                "deterministic_gate": policy["deterministic_gate"],
                "direct_runtime_read_allowed": policy["direct_runtime_read_allowed"],
                "allowed_consumers": policy["allowed_consumers"],
                "forbidden_consumers": policy["forbidden_consumers"],
                "use_rule": policy["use_rule"],
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return rows


def is_runtime_pointer_candidate(record: dict[str, Any], runtime_supply_root: Path) -> bool:
    source_path = str(record.get("source_path", ""))
    path = source_path_to_path(source_path)
    if not is_relative_to(resolve_soft(path), resolve_soft(runtime_supply_root)):
        return False
    name = path.name.lower()
    return name.startswith("canonical_pointer") or "manifest" in name


def runtime_bundle_name(path: Path, runtime_supply_root: Path) -> str:
    try:
        parts = path.relative_to(runtime_supply_root).parts
    except ValueError:
        return "[external_runtime_supply]"
    return parts[0] if parts else "[runtime_supply]"


def extract_hash(data: dict[str, Any]) -> str | None:
    for key in ("expected_content_hash", "content_hash", "source_inventory_hash"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def classify_runtime_pointer(data: dict[str, Any]) -> dict[str, Any]:
    published = data.get("published")
    status = str(data.get("status", "")).lower()
    content_hash = extract_hash(data)
    if published is True and content_hash:
        consumer_status = "published_runtime_supply_hash_gated"
        runtime_read_allowed = True
    elif published is True:
        consumer_status = "published_runtime_supply_missing_hash_blocked"
        runtime_read_allowed = False
    elif published is False and ("candidate" in status or "release" in status):
        consumer_status = "release_candidate_not_runtime_default"
        runtime_read_allowed = False
    elif published is False:
        consumer_status = "unpublished_runtime_supply_blocked"
        runtime_read_allowed = False
    elif "candidate" in status or "release" in status:
        consumer_status = "candidate_manifest_no_publish_flag"
        runtime_read_allowed = False
    else:
        consumer_status = "metadata_requires_manual_review"
        runtime_read_allowed = False
    return {
        "consumer_status": consumer_status,
        "runtime_read_allowed": runtime_read_allowed,
        "requires_hash_gate": bool(content_hash),
        "official_score_allowed": False,
        "learner_truth_write_allowed": False,
        "gbrain_write_allowed": False,
        "production_registry_write_allowed": False,
    }


def build_runtime_pointer_rows(
    records: list[dict[str, Any]],
    runtime_supply_root: Path,
) -> list[dict[str, Any]]:
    rows = []
    for record in sorted(records, key=lambda item: item.get("source_path", "")):
        if not is_runtime_pointer_candidate(record, runtime_supply_root):
            continue
        source_path = str(record["source_path"])
        path = source_path_to_path(source_path)
        parsed: dict[str, Any] = {}
        parse_error = None
        if path.exists():
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                parse_error = str(exc)
        else:
            parse_error = "source file missing"
        if not isinstance(parsed, dict):
            parsed = {}
        pointer_policy = classify_runtime_pointer(parsed)
        rows.append(
            {
                "schema": "luban_runtime_supply_pointer_authority.v1",
                "source_path": source_path,
                "runtime_bundle": runtime_bundle_name(path, runtime_supply_root),
                "pointer_kind": "canonical_pointer" if Path(source_path).name.startswith("canonical_pointer") else "manifest",
                "namespace": parsed.get("namespace"),
                "status": parsed.get("status"),
                "published": parsed.get("published"),
                "schema_version": parsed.get("schema_version") or parsed.get("schema"),
                "bundle_path": parsed.get("bundle_path") or parsed.get("bundle_file"),
                "content_hash": extract_hash(parsed),
                "signature_present": bool(parsed.get("signature")),
                "rollback_pointer": parsed.get("rollback_pointer"),
                "record_count": parsed.get("record_count") or parsed.get("count") or parsed.get("shard_count"),
                "tier": parsed.get("tier"),
                "parse_error": parse_error,
                **pointer_policy,
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return rows


def build_consumer_policy() -> dict[str, Any]:
    return {
        "schema": "luban_compiled_asset_consumer_policy.v1",
        "principle": "LLMs maintain candidate knowledge organization; deterministic gates sign releases and protect authority.",
        "consumers": [
            {
                "consumer": "asset_inventory_agent",
                "can_read": ["group_authority.json", "runtime_pointers.jsonl", "ledger indexes", "manifest snapshots"],
                "cannot_write": ["runtime_supply", "LearnerState", "GBrain", "production_registry", "official_score"],
            },
            {
                "consumer": "llm_compiler_worker",
                "can_read": ["candidate workbench artifacts", "review evidence", "raw source ledgers"],
                "can_write": ["candidate artifacts only"],
                "must_not_write": ["release artifacts", "runtime defaults", "canonical learner truth"],
            },
            {
                "consumer": "runtime_consumer",
                "can_read": ["published runtime pointer rows with runtime_read_allowed=true after hash/schema gate"],
                "must_not_read": ["artifacts/* workbench payloads directly", "unpublished runtime_supply candidates"],
            },
            {
                "consumer": "official_score_or_learner_truth_writer",
                "can_read": [],
                "must_wait_for": ["signed release artifact", "domain-specific gate", "explicit owner authorization"],
            },
        ],
    }


def render_summary(
    manifest: dict[str, Any],
    group_rows: list[dict[str, Any]],
    runtime_rows: list[dict[str, Any]],
) -> str:
    counts = manifest["counts"]
    lines = [
        "# Compiled Asset Authority Map v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Authority: inventory and consumer policy only; not runtime install, not official score authority.",
        f"- Asset groups classified: **{counts['asset_groups']:,}**",
        f"- Runtime pointer / manifest rows: **{counts['runtime_pointer_records']:,}**",
        f"- Published runtime pointers with hash gate: **{counts['published_runtime_pointers']:,}**",
        f"- Candidate / blocked runtime pointers: **{counts['blocked_or_candidate_runtime_pointers']:,}**",
        "",
        "## Group Authority",
        "",
        "| Group | Class | Runtime Direct Read | Required Gate |",
        "|---|---|---:|---|",
    ]
    for row in group_rows:
        lines.append(
            f"| `{row['asset_group']}` | `{row['authority_class']}` | {str(row['direct_runtime_read_allowed']).lower()} | {row['deterministic_gate']} |"
        )
    lines.extend(
        [
            "",
            "## Runtime Pointer Gate",
            "",
            "| Pointer | Published | Status | Runtime Read | Hash Gate |",
            "|---|---:|---|---:|---:|",
        ]
    )
    for row in runtime_rows:
        lines.append(
            f"| `{row['source_path']}` | {row['published']} | `{row['consumer_status']}` | {str(row['runtime_read_allowed']).lower()} | {str(row['requires_hash_gate']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- `artifacts/*` stays candidate/workbench/review evidence unless a downstream signed packet promotes it.",
            "- `runtime_supply` is not consumed as a directory; consumers must read a published pointer with content hash and schema gate.",
            "- Published pointer still does not mean official scoring or learner-truth write authority.",
            "- Candidate artifacts and release artifacts must remain separate namespaces.",
            "",
        ]
    )
    return "\n".join(lines)


def build_compiled_asset_authority_map(
    compiled_ledger_manifest_path: Path = DEFAULT_COMPILED_LEDGER_MANIFEST,
    asset_groups_path: Path = DEFAULT_COMPILED_ASSET_GROUPS,
    files_path: Path = DEFAULT_COMPILED_FILES,
    runtime_supply_root: Path = DEFAULT_RUNTIME_SUPPLY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    ledger_manifest = load_compiled_ledger_manifest(compiled_ledger_manifest_path)
    groups = load_asset_groups(asset_groups_path)
    records = load_jsonl(files_path)
    if not runtime_supply_root.exists() or not runtime_supply_root.is_dir():
        raise ValueError(f"runtime supply root does not exist: {display_path(runtime_supply_root)}")
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    group_rows = build_group_authority(groups)
    runtime_rows = build_runtime_pointer_rows(records, runtime_supply_root)
    status_counts = Counter(row["consumer_status"] for row in runtime_rows)
    authority_counts = Counter(row["authority_class"] for row in group_rows)

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    manifest = {
        "schema": "luban_compiled_asset_authority_map_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "compiled_asset_authority_map_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_paths": {
            "compiled_ledger_manifest": display_path(compiled_ledger_manifest_path),
            "asset_groups": display_path(asset_groups_path),
            "files": display_path(files_path),
            "runtime_supply_root": display_path(runtime_supply_root),
        },
        "compiled_ledger_counts": ledger_manifest.get("counts"),
        "outputs": {
            "group_authority": "group_authority.json",
            "runtime_pointers": "runtime_pointers.jsonl",
            "consumer_policy": "consumer_policy.json",
            "summary": "summary.md",
        },
        "counts": {
            "asset_groups": len(group_rows),
            "runtime_pointer_records": len(runtime_rows),
            "published_runtime_pointers": sum(1 for row in runtime_rows if row["runtime_read_allowed"] is True),
            "blocked_or_candidate_runtime_pointers": sum(1 for row in runtime_rows if row["runtime_read_allowed"] is not True),
            "direct_artifact_runtime_reads_allowed": sum(1 for row in group_rows if row["direct_runtime_read_allowed"] is True),
            "by_authority_class": dict(authority_counts.most_common()),
            "by_runtime_pointer_status": dict(status_counts.most_common()),
        },
        "guardrails": [
            "authority map only; not runtime install",
            "artifacts direct runtime read count must remain zero",
            "runtime supply requires per-pointer published/hash/schema gate",
            "official score remains false",
        ],
    }
    consumer_policy = build_consumer_policy()

    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "group_authority.json").write_text(
        json.dumps({"schema": "luban_compiled_asset_group_authority_map.v1", "groups": group_rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    with (output_root / "runtime_pointers.jsonl").open("w", encoding="utf-8") as f:
        for row in runtime_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output_root / "consumer_policy.json").write_text(
        json.dumps(consumer_policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "summary.md").write_text(render_summary(manifest, group_rows, runtime_rows), encoding="utf-8")
    return {
        "manifest": manifest,
        "group_authority": group_rows,
        "runtime_pointers": runtime_rows,
        "consumer_policy": consumer_policy,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiled-ledger-manifest", type=Path, default=DEFAULT_COMPILED_LEDGER_MANIFEST)
    parser.add_argument("--asset-groups", type=Path, default=DEFAULT_COMPILED_ASSET_GROUPS)
    parser.add_argument("--files", type=Path, default=DEFAULT_COMPILED_FILES)
    parser.add_argument("--runtime-supply-root", type=Path, default=DEFAULT_RUNTIME_SUPPLY_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_compiled_asset_authority_map(
        compiled_ledger_manifest_path=args.compiled_ledger_manifest,
        asset_groups_path=args.asset_groups,
        files_path=args.files,
        runtime_supply_root=args.runtime_supply_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "group_authority": display_path(args.output_root / "group_authority.json"),
                "runtime_pointers": display_path(args.output_root / "runtime_pointers.jsonl"),
                "consumer_policy": display_path(args.output_root / "consumer_policy.json"),
                "summary": display_path(args.output_root / "summary.md"),
                "counts": result["manifest"]["counts"],
                "runtime_consumable": result["manifest"]["runtime_guard"]["runtime_consumable"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
