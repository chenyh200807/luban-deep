from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

try:
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from scripts.wallet_authority_common import discover_repo_root, ensure_output_dir, write_json
except ModuleNotFoundError:
    import sys

    CURRENT_DIR = Path(__file__).resolve().parent
    REPO_ROOT = CURRENT_DIR.parent
    for name in list(sys.modules):
        if name == "deeptutor" or name.startswith("deeptutor."):
            sys.modules.pop(name, None)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from wallet_authority_common import discover_repo_root, ensure_output_dir, write_json


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _is_uuid_like(value: str) -> bool:
    text = _normalize_text(value)
    parts = text.split("-")
    return len(parts) == 5 and all(parts)


def _normalize_fs_key(value: str) -> str:
    text = _normalize_text(value)
    normalized = []
    for char in text:
        normalized.append(char if char.isalnum() or char in {"_", "-", "."} else "_")
    return "".join(normalized).strip("._") or "unknown"


def _read_inventory_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def build_identity_owner_mappings(rows: list[dict[str, Any]]) -> dict[str, str]:
    candidate_map: dict[str, str] = {}
    conflicts: set[str] = set()
    for row in rows or []:
        legacy_user_id = _normalize_text(row.get("member_user_id"))
        canonical_user_id = _normalize_text(row.get("canonical_user_id"))
        if not legacy_user_id or not canonical_user_id or legacy_user_id == canonical_user_id:
            continue
        if not _is_uuid_like(canonical_user_id):
            continue
        existing = candidate_map.get(legacy_user_id)
        if existing and existing != canonical_user_id:
            conflicts.add(legacy_user_id)
            continue
        candidate_map[legacy_user_id] = canonical_user_id
    for legacy_user_id in conflicts:
        candidate_map.pop(legacy_user_id, None)
    return dict(sorted(candidate_map.items()))


def _rewrite_json_user_id(payload: Any, *, old_user_id: str, new_user_id: str) -> Any:
    if isinstance(payload, dict):
        rewritten: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "user_id" and _normalize_text(value) == old_user_id:
                rewritten[key] = new_user_id
            else:
                rewritten[key] = _rewrite_json_user_id(value, old_user_id=old_user_id, new_user_id=new_user_id)
        return rewritten
    if isinstance(payload, list):
        return [_rewrite_json_user_id(item, old_user_id=old_user_id, new_user_id=new_user_id) for item in payload]
    return payload


def _deep_merge_dict(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(dict(merged.get(key) or {}), value)
        else:
            merged[key] = value
    return merged


def _rewrite_json_file(path: Path, *, old_user_id: str, new_user_id: str) -> bool:
    if not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    rewritten = _rewrite_json_user_id(payload, old_user_id=old_user_id, new_user_id=new_user_id)
    if rewritten == payload:
        return False
    path.write_text(json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _merge_json_files(source_path: Path, target_path: Path, *, old_user_id: str, new_user_id: str) -> None:
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    source_payload = _rewrite_json_user_id(source_payload, old_user_id=old_user_id, new_user_id=new_user_id)
    if target_path.exists():
        target_payload = json.loads(target_path.read_text(encoding="utf-8"))
        target_payload = _rewrite_json_user_id(target_payload, old_user_id=old_user_id, new_user_id=new_user_id)
        if isinstance(source_payload, dict) and isinstance(target_payload, dict):
            merged = _deep_merge_dict(source_payload, target_payload)
        else:
            merged = target_payload
    else:
        merged = source_payload
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merge_text_file(source_path: Path, target_path: Path) -> None:
    source_text = source_path.read_text(encoding="utf-8")
    if not target_path.exists() or not target_path.read_text(encoding="utf-8").strip():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(source_text, encoding="utf-8")


def _merge_jsonl_file(source_path: Path, target_path: Path, *, old_user_id: str, new_user_id: str) -> None:
    seen: set[str] = set()
    rendered: list[str] = []
    for candidate_path in (target_path, source_path):
        if not candidate_path.exists():
            continue
        for raw_line in candidate_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                if line not in seen:
                    seen.add(line)
                    rendered.append(line)
                continue
            rewritten = _rewrite_json_user_id(payload, old_user_id=old_user_id, new_user_id=new_user_id)
            normalized_line = json.dumps(rewritten, ensure_ascii=False)
            if normalized_line not in seen:
                seen.add(normalized_line)
                rendered.append(normalized_line)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("".join(f"{line}\n" for line in rendered), encoding="utf-8")


def _migrate_single_learner_directory(
    learner_root: Path,
    *,
    old_user_id: str,
    new_user_id: str,
) -> dict[str, int]:
    summary = {
        "directories_moved": 0,
        "json_files_merged": 0,
        "jsonl_files_merged": 0,
        "text_files_moved": 0,
        "other_files_moved": 0,
    }
    source_dir = learner_root / _normalize_fs_key(old_user_id)
    if not source_dir.exists():
        return summary
    target_dir = learner_root / _normalize_fs_key(new_user_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    for source_path in list(source_dir.iterdir()):
        target_path = target_dir / source_path.name
        if source_path.is_dir():
            if not target_path.exists():
                shutil.move(str(source_path), str(target_path))
                summary["other_files_moved"] += 1
            continue
        if source_path.suffix == ".json":
            _merge_json_files(source_path, target_path, old_user_id=old_user_id, new_user_id=new_user_id)
            summary["json_files_merged"] += 1
        elif source_path.name.endswith(".jsonl"):
            _merge_jsonl_file(source_path, target_path, old_user_id=old_user_id, new_user_id=new_user_id)
            summary["jsonl_files_merged"] += 1
        elif source_path.suffix == ".md":
            _merge_text_file(source_path, target_path)
            summary["text_files_moved"] += 1
        else:
            if not target_path.exists():
                shutil.move(str(source_path), str(target_path))
                summary["other_files_moved"] += 1
                continue
        if source_path.exists():
            source_path.unlink()
    try:
        source_dir.rmdir()
        summary["directories_moved"] += 1
    except OSError:
        pass
    return summary


def _migrate_learner_state_directories(learner_root: Path, owner_mappings: dict[str, str]) -> dict[str, int]:
    summary = {
        "directories_moved": 0,
        "json_files_merged": 0,
        "jsonl_files_merged": 0,
        "text_files_moved": 0,
        "other_files_moved": 0,
    }
    for old_user_id, new_user_id in owner_mappings.items():
        partial = _migrate_single_learner_directory(
            learner_root,
            old_user_id=old_user_id,
            new_user_id=new_user_id,
        )
        for key, value in partial.items():
            summary[key] += value
    return summary


def _migrate_overlay_files(overlay_root: Path, owner_mappings: dict[str, str]) -> dict[str, int]:
    summary = {
        "files_moved": 0,
        "json_files_rewritten": 0,
        "event_files_rewritten": 0,
    }
    if not overlay_root.exists():
        return summary
    for old_user_id, new_user_id in owner_mappings.items():
        old_prefix = f"{_normalize_fs_key(old_user_id)}__"
        new_prefix = f"{_normalize_fs_key(new_user_id)}__"
        for source_path in list(overlay_root.glob(f"{old_prefix}*")):
            target_name = source_path.name.replace(old_prefix, new_prefix, 1)
            target_path = overlay_root / target_name
            if source_path.name.endswith(".events.jsonl"):
                _merge_jsonl_file(source_path, target_path, old_user_id=old_user_id, new_user_id=new_user_id)
                summary["event_files_rewritten"] += 1
            elif source_path.suffix == ".json":
                _merge_json_files(source_path, target_path, old_user_id=old_user_id, new_user_id=new_user_id)
                summary["json_files_rewritten"] += 1
            else:
                if not target_path.exists():
                    shutil.move(str(source_path), str(target_path))
            if source_path.exists():
                source_path.unlink()
            summary["files_moved"] += 1
    return summary


def _merge_heartbeat_jobs(target_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for job in target_jobs:
        key = (
            _normalize_text(job.get("user_id")),
            _normalize_text(job.get("bot_id")),
            _normalize_text(job.get("channel")),
        )
        existing = deduped.get(key)
        current_updated_at = _normalize_text(job.get("updated_at"))
        existing_updated_at = _normalize_text(existing.get("updated_at")) if isinstance(existing, dict) else ""
        if existing is None or current_updated_at >= existing_updated_at:
            deduped[key] = dict(job)
    return list(deduped.values())


def _migrate_heartbeat_jobs(heartbeat_path: Path, owner_mappings: dict[str, str]) -> dict[str, int]:
    summary = {"jobs_rewritten": 0}
    if not heartbeat_path.exists():
        return summary
    payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    jobs = payload.get("jobs") if isinstance(payload, dict) else []
    rewritten_jobs: list[dict[str, Any]] = []
    changed = False
    for item in jobs or []:
        if not isinstance(item, dict):
            continue
        job = dict(item)
        old_user_id = _normalize_text(job.get("user_id"))
        new_user_id = owner_mappings.get(old_user_id, "")
        if new_user_id:
            job["user_id"] = new_user_id
            changed = True
            summary["jobs_rewritten"] += 1
        rewritten_jobs.append(job)
    if changed:
        payload = dict(payload if isinstance(payload, dict) else {})
        payload["jobs"] = _merge_heartbeat_jobs(rewritten_jobs)
        heartbeat_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _migrate_learning_plan_files(guide_root: Path, owner_mappings: dict[str, str]) -> dict[str, int]:
    summary = {"plans_rewritten": 0}
    if not guide_root.exists():
        return summary
    for path in guide_root.rglob("*.json"):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        old_user_id = _normalize_text(payload.get("user_id"))
        new_user_id = owner_mappings.get(old_user_id, "")
        if not new_user_id:
            continue
        payload["user_id"] = new_user_id
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary["plans_rewritten"] += 1
    return summary


def _migrate_outbox_rows(outbox_db_path: Path, owner_mappings: dict[str, str]) -> dict[str, int]:
    summary = {"rows_rewritten": 0}
    if not outbox_db_path.exists():
        return summary
    with sqlite3.connect(outbox_db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'",
            ).fetchall()
        }
        if "learner_state_outbox" not in tables:
            return summary
        rows = conn.execute(
            "select id, user_id, payload_json from learner_state_outbox",
        ).fetchall()
        for row in rows:
            old_user_id = _normalize_text(row["user_id"])
            new_user_id = owner_mappings.get(old_user_id, "")
            if not new_user_id:
                continue
            payload = json.loads(str(row["payload_json"] or "{}"))
            rewritten_payload = _rewrite_json_user_id(payload, old_user_id=old_user_id, new_user_id=new_user_id)
            conn.execute(
                """
                update learner_state_outbox
                set user_id = ?, payload_json = ?
                where id = ?
                """,
                (
                    new_user_id,
                    json.dumps(rewritten_payload, ensure_ascii=False),
                    row["id"],
                ),
            )
            summary["rows_rewritten"] += 1
        conn.commit()
    return summary


def export_identity_ownership_migration(
    *,
    output_dir: Path,
    inventory_path: Path,
    repo_root: Path,
    apply: bool = False,
) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    owner_mappings = build_identity_owner_mappings(_read_inventory_rows(inventory_path))
    summary: dict[str, Any] = {
        "status": "dry_run",
        "repo_root": str(repo_root),
        "owner_mappings": owner_mappings,
        "sqlite": {
            "pairs_applied": 0,
            "sessions_updated": 0,
            "entries_updated": 0,
            "categories_updated": 0,
            "categories_merged": 0,
            "category_links_repointed": 0,
        },
        "learner_state": {
            "directories_moved": 0,
            "json_files_merged": 0,
            "jsonl_files_merged": 0,
            "text_files_moved": 0,
            "other_files_moved": 0,
        },
        "heartbeat": {"jobs_rewritten": 0},
        "overlays": {"files_moved": 0, "json_files_rewritten": 0, "event_files_rewritten": 0},
        "learning_plans": {"plans_rewritten": 0},
        "outbox": {"rows_rewritten": 0},
    }
    if apply and owner_mappings:
        store = SQLiteSessionStore(db_path=repo_root / "data" / "user" / "chat_history.db")
        import asyncio

        summary["sqlite"] = asyncio.run(store.rewrite_owner_keys(owner_mappings))
        summary["learner_state"] = _migrate_learner_state_directories(
            repo_root / "data" / "user" / "learner_state",
            owner_mappings,
        )
        summary["heartbeat"] = _migrate_heartbeat_jobs(
            repo_root / "data" / "runtime" / "learner_state" / "heartbeat_jobs.json",
            owner_mappings,
        )
        summary["overlays"] = _migrate_overlay_files(
            repo_root / "data" / "user" / "learner_state" / "bot_overlays",
            owner_mappings,
        )
        summary["learning_plans"] = _migrate_learning_plan_files(
            repo_root / "data" / "user" / "workspace" / "guide",
            owner_mappings,
        )
        summary["outbox"] = _migrate_outbox_rows(
            repo_root / "data" / "runtime" / "outbox.db",
            owner_mappings,
        )
        summary["status"] = "applied"
    write_json(output_dir / "wallet_identity_ownership_migration_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate local owner_key and learner-state runtime data to canonical UUID users.")
    parser.add_argument("--output-dir", default="", help="Directory for generated summary artifacts.")
    parser.add_argument("--inventory-path", default="", help="Path to identity_inventory.csv")
    parser.add_argument("--repo-root", default="", help="Repository root override.")
    parser.add_argument("--apply", action="store_true", help="Apply the migration instead of dry-run.")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).expanduser() if args.repo_root else discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "ownership"
    inventory_path = (
        Path(args.inventory_path).expanduser()
        if args.inventory_path
        else repo_root / "artifacts" / "wallet_authority" / "identity" / "identity_inventory.csv"
    )
    summary = export_identity_ownership_migration(
        output_dir=output_dir,
        inventory_path=inventory_path,
        repo_root=repo_root,
        apply=bool(args.apply),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
