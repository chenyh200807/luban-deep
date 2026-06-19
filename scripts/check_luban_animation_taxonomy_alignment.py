from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = (
    REPO_ROOT
    / "docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md"
)
DEFAULT_TAXONOMY_PATH = (
    REPO_ROOT / "deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json"
)

VALID_ALIGNMENT_STATUSES = frozenset(
    {
        "direct",
        "composite",
        "coarse_review",
        "merged_child",
        "conditional_split",
    }
)
PRODUCTION_LIKE_STATUSES = frozenset(
    {
        "production",
        "published",
        "signed",
        "signed_candidate",
        "official",
        "release",
        "released",
    }
)
STUDENT_FACING_KEYS = frozenset(
    {
        "student_title",
        "student_goal",
        "learning_goal",
        "title",
        "subtitle",
        "exam_point",
        "display_label",
        "caption",
        "student_boundary",
        "student_comment",
        "student_feedback",
    }
)

TAXONOMY_CODE_RE = re.compile(r"`(1A[0-9A-Z-]+)`")
RAW_CODE_RE = re.compile(r"(?<![A-Za-z0-9])1A[0-9A-Z-]{4,}(?![A-Za-z0-9])")


@dataclass(frozen=True)
class RegistryRow:
    slot: str
    pack_id: str
    student_title: str
    taxonomy_refs: tuple[str, ...]
    alignment_status: str
    note: str


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]
    registry_rows: int
    manifest_count: int

    @property
    def ok(self) -> bool:
        return not self.errors


def _strip_code(value: str) -> str:
    return value.strip().strip("`")


def pack_key(pack_id: str) -> str:
    text = str(pack_id or "").strip()
    return text.split("_", 1)[0] if "_" in text else text


def parse_registry(path: Path) -> list[RegistryRow]:
    text = path.read_text(encoding="utf-8")
    rows: list[RegistryRow] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| Slot | Pack ID | Student title |"):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            break
        cols = [col.strip() for col in line.strip().strip("|").split("|")]
        if len(cols) != 6:
            raise ValueError(f"malformed registry table row: {line}")
        rows.append(
            RegistryRow(
                slot=cols[0],
                pack_id=cols[1],
                student_title=cols[2],
                taxonomy_refs=tuple(_strip_code(code) for code in TAXONOMY_CODE_RE.findall(cols[3])),
                alignment_status=_strip_code(cols[4]),
                note=cols[5],
            )
        )
    return rows


def load_taxonomy_codes(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") or []
    codes: set[str] = set()
    for node in nodes:
        if isinstance(node, dict):
            code = str(node.get("code") or "").strip()
            if code:
                codes.add(code)
    return codes


def validate_registry(
    rows: list[RegistryRow],
    *,
    taxonomy_codes: set[str],
    min_rows: int,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if len(rows) < min_rows:
        errors.append(f"registry has {len(rows)} row(s), expected at least {min_rows}")

    seen_pack_ids: dict[str, str] = {}
    seen_slots: dict[str, str] = {}
    for row in rows:
        row_id = f"slot={row.slot} pack={row.pack_id}"
        if not row.slot:
            errors.append(f"{row_id}: missing slot")
        if not row.pack_id:
            errors.append(f"slot={row.slot}: missing pack_id")
        if not row.student_title:
            errors.append(f"{row_id}: missing student_title")
        if RAW_CODE_RE.search(row.student_title):
            errors.append(f"{row_id}: student_title leaks raw taxonomy code")
        if not row.taxonomy_refs:
            errors.append(f"{row_id}: missing canonical taxonomy refs")
        for code in row.taxonomy_refs:
            if code not in taxonomy_codes:
                errors.append(f"{row_id}: unknown taxonomy ref {code}")
        if row.alignment_status not in VALID_ALIGNMENT_STATUSES:
            errors.append(f"{row_id}: invalid taxonomy_alignment_status {row.alignment_status!r}")
        previous_slot = seen_pack_ids.get(row.pack_id)
        if previous_slot:
            errors.append(f"{row_id}: duplicate pack_id first seen at slot={previous_slot}")
        seen_pack_ids[row.pack_id] = row.slot
        previous_pack = seen_slots.get(row.slot)
        if previous_pack:
            errors.append(f"{row_id}: duplicate slot first used by pack={previous_pack}")
        seen_slots[row.slot] = row.pack_id
        if row.alignment_status == "coarse_review":
            warnings.append(f"{row_id}: coarse_review requires source/leaf review before production")

    return errors, warnings


def _collect_json_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(p for p in path.rglob("*.json") if p.is_file())


def load_manifest_paths(paths: Iterable[Path], dirs: Iterable[Path]) -> list[Path]:
    manifest_paths: list[Path] = []
    for path in paths:
        manifest_paths.append(path)
    for directory in dirs:
        manifest_paths.extend(_collect_json_files(directory))
    return sorted(dict.fromkeys(manifest_paths))


def _authority_status(payload: dict[str, Any]) -> str:
    authority = payload.get("authority")
    if isinstance(authority, dict):
        status = str(authority.get("status") or "").strip()
        if status:
            return status
        if authority.get("official_score_allowed") is True:
            return "official"
    for key in ("status", "lifecycle_status", "release_status"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_production_like(payload: dict[str, Any]) -> bool:
    status = _authority_status(payload).lower()
    if status in PRODUCTION_LIKE_STATUSES:
        return True
    authority = payload.get("authority")
    return isinstance(authority, dict) and authority.get("official_score_allowed") is True


def _manifest_pack_id(payload: dict[str, Any]) -> str:
    for key in ("pack_id", "card_id", "topic_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _string_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _manifest_taxonomy_refs(
    payload: dict[str, Any],
    *,
    allow_legacy_taxonomy_ref: bool,
) -> tuple[str, tuple[str, ...], bool]:
    primary = str(payload.get("primary_taxonomy_ref") or "").strip()
    supporting = _string_list(payload.get("supporting_taxonomy_refs"))
    used_legacy = False
    if not primary and allow_legacy_taxonomy_ref:
        legacy = str(payload.get("taxonomy_ref") or "").strip()
        if legacy:
            primary = legacy
            used_legacy = True
    return primary, supporting, used_legacy


def _iter_student_facing_values(payload: Any, *, parent_key: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            if key_text in STUDENT_FACING_KEYS and isinstance(value, str):
                yield key_text, value
            if isinstance(value, (dict, list)):
                yield from _iter_student_facing_values(value, parent_key=key_text)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_student_facing_values(item, parent_key=parent_key)


def validate_manifest(
    path: Path,
    payload: dict[str, Any],
    *,
    registry_by_pack: dict[str, RegistryRow],
    taxonomy_codes: set[str],
    allow_legacy_taxonomy_ref: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    label = path.as_posix()

    pack_id = _manifest_pack_id(payload)
    if not pack_id:
        errors.append(f"{label}: missing pack_id/card_id/topic_id")
        return errors, warnings

    registry_key = pack_key(pack_id)
    registry_row = registry_by_pack.get(registry_key)
    if not registry_row:
        errors.append(f"{label}: pack {pack_id!r} not registered in taxonomy alignment registry")
        return errors, warnings

    primary, supporting, used_legacy = _manifest_taxonomy_refs(
        payload,
        allow_legacy_taxonomy_ref=allow_legacy_taxonomy_ref,
    )
    if used_legacy:
        warnings.append(f"{label}: legacy taxonomy_ref used; new packs must use primary/supporting refs")
    if not primary:
        errors.append(f"{label}: missing primary_taxonomy_ref")
    all_manifest_refs = tuple(ref for ref in (primary, *supporting) if ref)
    for ref in all_manifest_refs:
        if ref not in taxonomy_codes:
            errors.append(f"{label}: unknown taxonomy ref {ref}")
        if ref not in registry_row.taxonomy_refs:
            errors.append(f"{label}: taxonomy ref {ref} is not registered for pack {registry_key}")

    manifest_status = str(payload.get("taxonomy_alignment_status") or "").strip()
    if not manifest_status:
        errors.append(f"{label}: missing taxonomy_alignment_status")
    elif manifest_status not in VALID_ALIGNMENT_STATUSES:
        errors.append(f"{label}: invalid taxonomy_alignment_status {manifest_status!r}")
    elif manifest_status != registry_row.alignment_status:
        errors.append(
            f"{label}: taxonomy_alignment_status {manifest_status!r} "
            f"does not match registry {registry_row.alignment_status!r}"
        )

    if _is_production_like(payload) and registry_row.alignment_status == "coarse_review":
        errors.append(f"{label}: production-like pack cannot use coarse_review taxonomy alignment")

    for key, value in _iter_student_facing_values(payload):
        if RAW_CODE_RE.search(value):
            errors.append(f"{label}: student-facing field {key!r} leaks raw taxonomy code")

    return errors, warnings


def evaluate_alignment(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    manifest_paths: Iterable[Path] = (),
    manifest_dirs: Iterable[Path] = (),
    min_registry_rows: int = 60,
    allow_legacy_taxonomy_ref: bool = False,
) -> CheckResult:
    rows = parse_registry(registry_path)
    taxonomy_codes = load_taxonomy_codes(taxonomy_path)
    errors, warnings = validate_registry(rows, taxonomy_codes=taxonomy_codes, min_rows=min_registry_rows)
    registry_by_pack = {row.pack_id: row for row in rows}

    manifests = load_manifest_paths(manifest_paths, manifest_dirs)
    for manifest_path in manifests:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{manifest_path.as_posix()}: cannot load JSON manifest: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{manifest_path.as_posix()}: manifest root must be object")
            continue
        manifest_errors, manifest_warnings = validate_manifest(
            manifest_path,
            payload,
            registry_by_pack=registry_by_pack,
            taxonomy_codes=taxonomy_codes,
            allow_legacy_taxonomy_ref=allow_legacy_taxonomy_ref,
        )
        errors.extend(manifest_errors)
        warnings.extend(manifest_warnings)

    return CheckResult(
        errors=errors,
        warnings=warnings,
        registry_rows=len(rows),
        manifest_count=len(manifests),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Luban animation pack canonical taxonomy alignment.",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--manifest", type=Path, action="append", default=[])
    parser.add_argument("--manifest-dir", type=Path, action="append", default=[])
    parser.add_argument("--min-registry-rows", type=int, default=60)
    parser.add_argument(
        "--allow-legacy-taxonomy-ref",
        action="store_true",
        help="Accept legacy manifest taxonomy_ref as primary_taxonomy_ref with a warning.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = evaluate_alignment(
        registry_path=args.registry,
        taxonomy_path=args.taxonomy,
        manifest_paths=args.manifest,
        manifest_dirs=args.manifest_dir,
        min_registry_rows=args.min_registry_rows,
        allow_legacy_taxonomy_ref=args.allow_legacy_taxonomy_ref,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "registry_rows": result.registry_rows,
                    "manifest_count": result.manifest_count,
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        verdict = "passed" if result.ok else "failed"
        print(
            f"luban-animation-taxonomy-alignment: {verdict} "
            f"(registry_rows={result.registry_rows}, manifests={result.manifest_count})"
        )
        for warning in result.warnings:
            print(f"WARNING: {warning}")
        for error in result.errors:
            print(f"ERROR: {error}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
