#!/usr/bin/env python3
"""Build an AI-only governance OKF ledger for plans, runbooks, contracts, and skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "governance_okf_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "governance_okf_v1")
SENTINEL_NAME = ".governance_okf_generated.json"
GENERATOR = "build_governance_okf.py"

DEFAULT_SOURCE_ROOTS = {
    "plan": REPO_ROOT / "docs" / "plan",
    "runbook": REPO_ROOT / "docs" / "runbook",
    "contracts": REPO_ROOT / "contracts",
    "docs_contracts": REPO_ROOT / "docs" / "contracts",
    "agent_skills": REPO_ROOT / "agent-skills",
}

EXCLUDED_PARTS = {".git", "__pycache__", "node_modules", ".pytest_cache"}
EXCLUDED_FILES = {".DS_Store"}
TEXT_EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".txt"}

RUNTIME_GUARD = {
    "release_stage": "ai_project_context_only",
    "runtime_consumable": False,
    "installed_runtime_supply": False,
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


def extension(path: Path) -> str:
    return path.suffix.lower() or "[no_ext]"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        *(root.resolve() for root in DEFAULT_SOURCE_ROOTS.values()),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    if (
        sentinel.get("generated_by") != GENERATOR
        or sentinel.get("kind") != "governance_okf"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {
        SENTINEL_NAME,
        "manifest.json",
        "governance_files.jsonl",
        "domain_summary.json",
        "summary.md",
    }
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "governance_okf",
        "generated_by": GENERATOR,
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_source_files(root: Path) -> list[Path]:
    files = []
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if set(path.relative_to(root).parts) & EXCLUDED_PARTS:
            continue
        if extension(path) not in TEXT_EXTENSIONS:
            continue
        files.append(path)
    return files


def extract_title(path: Path) -> str:
    if extension(path) != ".md":
        return path.stem
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:80]:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip() or path.stem
    except OSError:
        pass
    return path.stem


def governance_area(domain: str, path: Path) -> str:
    text = f"{domain}/{path.as_posix()}".lower()
    rules = [
        ("contract_authority", ("contract", "registry", "schema", "env_", "provider", "turn", "capability")),
        ("release_operations", ("release", "deploy", "aliyun", "go-live", "prelaunch", "hardening")),
        ("ci_quality_gate", ("ci", "test", "smoke", "harness", "benchmark", "quality", "verification")),
        ("learner_state", ("learner", "learning", "memory", "report")),
        ("wechat_frontend", ("wechat", "yousen", "miniprogram", "renderer", "web-bi", "frontend")),
        ("billing_business", ("billing", "wallet", "member", "bi", "cost")),
        ("data_knowledge", ("knowledge", "rubric", "taxonomy", "source", "gbrain", "knowql", "openmaic")),
        ("planning_index", ("index.md", "master-control", "current", "作战", "总控")),
        ("agent_skill", ("skill.md", "agent-skills", "gate")),
    ]
    for area, tokens in rules:
        if any(token in text for token in tokens):
            return area
    return "governance_context"


def authority_role(domain: str, area: str, path: Path) -> str:
    if domain in {"contracts", "docs_contracts"}:
        return "contract_reference"
    if domain == "runbook":
        return "operational_runbook"
    if domain == "agent_skills":
        return "agent_behavior_guidance"
    if path.name == "INDEX.md":
        return "plan_index"
    if area == "release_operations":
        return "release_plan_or_runbook"
    return "planning_context"


def risk_level(domain: str, area: str, path: Path) -> str:
    if domain in {"contracts", "docs_contracts"}:
        return "high"
    if area in {"release_operations", "ci_quality_gate", "contract_authority"}:
        return "high"
    if domain == "agent_skills" or area in {"learner_state", "billing_business", "wechat_frontend"}:
        return "medium"
    return "low"


def build_records(source_roots: dict[str, Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for domain, root in sorted(source_roots.items()):
        for path in iter_source_files(root):
            area = governance_area(domain, path.relative_to(root))
            record = {
                "schema": "deeptutor_governance_file_record.v1",
                "domain": domain,
                "area": area,
                "authority_role": authority_role(domain, area, path),
                "risk_level": risk_level(domain, area, path),
                "title": extract_title(path),
                "source_path": display_path(path),
                "relative_path": path.relative_to(root).as_posix(),
                "extension": extension(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "runtime_guard": RUNTIME_GUARD,
            }
            records.append(record)
    domain_rows = []
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_domain.setdefault(record["domain"], []).append(record)
    for domain, items in sorted(by_domain.items()):
        domain_rows.append(
            {
                "schema": "deeptutor_governance_domain_summary.v1",
                "domain": domain,
                "files": len(items),
                "bytes": sum(item["bytes"] for item in items),
                "by_area": dict(Counter(item["area"] for item in items).most_common()),
                "by_risk_level": dict(Counter(item["risk_level"] for item in items).most_common()),
                "top_files": [
                    {
                        "path": item["source_path"],
                        "title": item["title"],
                        "area": item["area"],
                        "risk_level": item["risk_level"],
                    }
                    for item in sorted(items, key=lambda row: row["bytes"], reverse=True)[:10]
                ],
                "runtime_guard": RUNTIME_GUARD,
            }
        )
    return sorted(records, key=lambda item: item["source_path"]), domain_rows


def render_summary(manifest: dict[str, Any], domains: list[dict[str, Any]]) -> str:
    counts = manifest["counts"]
    lines = [
        "# Governance OKF v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Purpose: AI project understanding only; this is not a production control plane.",
        f"- Files indexed: **{counts['files']}**",
        f"- Total bytes: **{counts['total_bytes']:,}**",
        "",
        "## Domain Counts",
        "",
        "| Domain | Files | Bytes |",
        "|---|---:|---:|",
    ]
    for row in domains:
        lines.append(f"| `{row['domain']}` | {row['files']} | {row['bytes']:,} |")
    lines.extend(["", "## Area Counts", ""])
    for area, count in (counts.get("by_area") or {}).items():
        lines.append(f"- `{area}`: {count}")
    lines.extend(["", "## Risk Counts", ""])
    for risk, count in (counts.get("by_risk_level") or {}).items():
        lines.append(f"- `{risk}`: {count}")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- OKF only helps AI find the right governance source before acting.",
            "- Contracts and runbooks remain the authority; this ledger does not replace them.",
            "- No record here may write runtime supply, learner truth, production registry, or official scores.",
            "- When exact behavior matters, read the referenced source document directly.",
        ]
    )
    return "\n".join(lines)


def build_governance_okf(
    source_roots: dict[str, Path] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    source_roots = source_roots or DEFAULT_SOURCE_ROOTS
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records, domain_rows = build_records(source_roots)
    if not records:
        raise ValueError("no governance files found")
    area_counts = Counter(record["area"] for record in records)
    risk_counts = Counter(record["risk_level"] for record in records)
    domain_counts = Counter(record["domain"] for record in records)
    ext_counts = Counter(record["extension"] for record in records)

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    manifest = {
        "schema": "deeptutor_governance_okf_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "ai_project_context_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_roots": {domain: display_path(path) for domain, path in sorted(source_roots.items())},
        "copy_policy": {
            "payloads_copied": False,
            "reason": "OKF routes AI to governance sources without replacing contracts, plans, runbooks, or skills",
        },
        "artifact_refs": {
            "governance_files": "governance_files.jsonl",
            "domain_summary": "domain_summary.json",
            "summary": "summary.md",
        },
        "counts": {
            "files": len(records),
            "total_bytes": sum(record["bytes"] for record in records),
            "by_domain": dict(domain_counts.most_common()),
            "by_area": dict(area_counts.most_common()),
            "by_risk_level": dict(risk_counts.most_common()),
            "by_extension": dict(ext_counts.most_common()),
        },
        "guardrails": [
            "AI project understanding only",
            "not production",
            "not a replacement for contracts or runbooks",
            "not runtime supply",
            "not official scoring authority",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "governance_files.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output_root / "domain_summary.json").write_text(
        json.dumps({"schema": "deeptutor_governance_domain_summary.v1", "domains": domain_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "summary.md").write_text(render_summary(manifest, domain_rows), encoding="utf-8")
    return {"manifest": manifest, "records": records, "domains": domain_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_governance_okf(output_root=args.output_root, generated_at=args.generated_at)
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "governance_files": display_path(args.output_root / "governance_files.jsonl"),
                "domain_summary": display_path(args.output_root / "domain_summary.json"),
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
